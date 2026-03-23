"""Graph-based schema query for Text-to-SQL context retrieval.

Given a user question, extracts entities/intent, queries the Kuzu Schema Graph
to find relevant tables (5-10), discovers JOIN paths, and returns a concise
schema context for LLM-based SQL generation.
"""

import re
import sys
from pathlib import Path
from typing import Optional

import kuzu
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from solutions.graph_schema_kuzu.schema_graph_builder import KUZU_DB_DIR

# Business domain keyword -> specific table names (exact or prefix match)
# Using exact table names gives much better precision than substring matching
DOMAIN_KEYWORDS = {
    # Tenants / contracts
    "租客": {
        "exact": ["qft_whole_tenants", "qft_joint_tenants", "qft_focus_tenants"],
        "pattern": ["tenants"],
    },
    "租户": {
        "exact": ["qft_whole_tenants", "qft_joint_tenants", "qft_focus_tenants"],
        "pattern": ["tenants"],
    },
    "合同": {
        "exact": ["qft_contract_treaty_info", "qft_whole_tenants", "qft_joint_tenants", "qft_focus_tenants"],
        "pattern": ["contract", "treaty"],
    },
    "签约": {
        "exact": ["qft_contract_treaty_info"],
        "pattern": ["contract"],
    },
    "到期": {
        "exact": ["qft_whole_tenants", "qft_joint_tenants", "qft_focus_tenants"],
        "pattern": [],
    },
    # Housing
    "房源": {
        "exact": ["qft_whole_housing", "qft_joint_housing", "qft_focus_parent_room"],
        "pattern": [],
    },
    "房间": {
        "exact": ["qft_joint_room", "qft_focus_room", "qft_room_query_summary_table"],
        "pattern": [],
    },
    "房屋": {
        "exact": ["qft_whole_housing", "qft_joint_housing"],
        "pattern": [],
    },
    "出租率": {
        "exact": ["qft_room_query_summary_table"],
        "pattern": [],
    },
    "空置": {
        "exact": ["qft_room_query_summary_table"],
        "pattern": [],
    },
    # Finance
    "租金": {
        "exact": ["qft_joint_tenants_income", "qft_joint_tenants_sub_income",
                  "qft_whole_bill_expend", "qft_focus_tenants_income"],
        "pattern": [],
    },
    "账单": {
        "exact": ["qft_joint_tenants_income", "qft_joint_tenants_sub_income",
                  "qft_whole_bill_expend", "qft_focus_tenants_income"],
        "pattern": ["income", "bill"],
    },
    "收入": {
        "exact": ["qft_joint_tenants_income", "qft_focus_tenants_income"],
        "pattern": ["income"],
    },
    "支出": {
        "exact": ["qft_whole_bill_expend"],
        "pattern": ["expend"],
    },
    "欠费": {
        "exact": ["qft_joint_tenants_sub_income"],
        "pattern": [],
    },
    "逾期": {
        "exact": ["qft_joint_tenants_sub_income", "qft_joint_tenants"],
        "pattern": [],
    },
    "缴费": {
        "exact": ["qft_joint_tenants_sub_income"],
        "pattern": ["income"],
    },
    "财务": {
        "exact": ["qft_finance", "qft_finance_item"],
        "pattern": ["finance"],
    },
    "流水": {
        "exact": ["qft_finance", "qft_finance_item", "qft_finance_item_extend"],
        "pattern": [],
    },
    # Organization
    "公司": {
        "exact": ["qft_company"],
        "pattern": [],
    },
    "门店": {
        "exact": ["qft_store"],
        "pattern": [],
    },
    "员工": {
        "exact": ["qft_employee"],
        "pattern": [],
    },
    "区域": {
        "exact": ["qft_area"],
        "pattern": [],
    },
    "房东": {
        "exact": ["qft_whole_housing", "qft_joint_housing"],
        "pattern": [],
    },
}

# Business mode detection
MODE_KEYWORDS = {
    "整租": "whole",
    "合租": "joint",
    "集中式": "focus",
}


def extract_keywords(question: str) -> list[str]:
    """Extract domain-relevant keywords from user question."""
    keywords = []
    for kw in DOMAIN_KEYWORDS:
        if kw in question:
            keywords.append(kw)
    return keywords


def extract_entity_ids(question: str) -> dict:
    """Extract entity IDs (company_id, store_id, etc.) from question."""
    entities = {}
    m = re.search(r"公司(?:ID|id)?(?:为|是|:|：)?(\d+)", question)
    if m:
        entities["company_id"] = m.group(1)

    m = re.search(r"门店(?:ID|id)?(?:为|是|:|：)?(\d+)", question)
    if m:
        entities["store_id"] = m.group(1)

    return entities


def detect_business_mode(question: str) -> Optional[str]:
    """Detect if question targets a specific business mode."""
    for kw, mode in MODE_KEYWORDS.items():
        if kw in question:
            return mode
    return None


class GraphSchemaQuery:
    """Query the Schema Graph to find relevant tables and JOIN paths."""

    def __init__(self, kuzu_db_dir: str = KUZU_DB_DIR):
        self.kuzu_db_dir = kuzu_db_dir
        self.db: Optional[kuzu.Database] = None
        self.conn: Optional[kuzu.Connection] = None
        self._table_index: dict[str, dict] = {}  # name -> {full_name, db, ...}
        self._open()
        self._build_table_index()

    def _open(self):
        """Open existing Kuzu database."""
        self.db = kuzu.Database(self.kuzu_db_dir)
        self.conn = kuzu.Connection(self.db)
        logger.info("Opened Kuzu Schema Graph for querying")

    def _build_table_index(self):
        """Build an in-memory index of all table names for fast lookup."""
        result = self.conn.execute(
            "MATCH (t:TableNode) RETURN t.full_name, t.name, t.database_name, t.comment, t.row_count, t.column_count"
        )
        while result.has_next():
            row = result.get_next()
            self._table_index[row[1]] = {
                "full_name": row[0],
                "name": row[1],
                "database_name": row[2],
                "comment": row[3] or "",
                "row_count": row[4],
                "column_count": row[5],
            }
        logger.info(f"Built table index with {len(self._table_index)} tables")

    def _find_table_by_name(self, name: str) -> Optional[dict]:
        """Look up a table by exact name."""
        return self._table_index.get(name)

    def _find_tables_by_pattern(self, pattern: str) -> list[dict]:
        """Find tables whose name contains the pattern."""
        results = []
        for tname, info in self._table_index.items():
            if pattern in tname:
                results.append(info)
        return results

    def find_relevant_tables(self, question: str, limit: int = 10) -> list[dict]:
        """Find tables relevant to the user question.

        Uses a scoring approach:
        - Score 10: Exact table name match from domain keywords
        - Score 5: Pattern-based match from domain keywords
        - Score 3: 1-hop graph expansion from high-score tables
        """
        keywords = extract_keywords(question)
        mode = detect_business_mode(question)

        if not keywords:
            logger.warning("No domain keywords found, falling back to broad search")
            keywords = ["租客", "房源", "账单"]

        logger.info(f"Keywords: {keywords}, Mode: {mode}")

        # Score each table
        table_scores: dict[str, float] = {}  # full_name -> score
        table_info: dict[str, dict] = {}  # full_name -> info dict

        for kw in keywords:
            config = DOMAIN_KEYWORDS.get(kw, {"exact": [], "pattern": []})

            # Exact table matches (highest score)
            for table_name in config.get("exact", []):
                info = self._find_table_by_name(table_name)
                if info:
                    fn = info["full_name"]
                    # Filter by business mode if detected
                    if mode and self._is_mode_specific(table_name) and mode not in table_name:
                        continue
                    table_scores[fn] = table_scores.get(fn, 0) + 10
                    table_info[fn] = info

            # Pattern matches (medium score)
            for pattern in config.get("pattern", []):
                for info in self._find_tables_by_pattern(pattern):
                    fn = info["full_name"]
                    if fn in table_scores:
                        continue  # Already matched exactly
                    if mode and self._is_mode_specific(info["name"]) and mode not in info["name"]:
                        continue
                    table_scores[fn] = table_scores.get(fn, 0) + 5
                    table_info[fn] = info

        logger.info(f"Direct matches: {len(table_scores)} tables")

        # Limit pattern matches to avoid noise: keep top 15 before expansion
        if len(table_scores) > 15:
            top = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)[:15]
            table_scores = dict(top)

        # Graph expansion: for top-scoring tables, follow REFERENCES edges (1 hop)
        high_score_tables = [
            fn for fn, score in sorted(table_scores.items(), key=lambda x: x[1], reverse=True)[:8]
        ]

        for fn in high_score_tables:
            # Forward refs: columns of this table -> referenced tables
            result = self.conn.execute(
                """MATCH (t:TableNode {full_name: $fn})-[:HAS_COLUMN]->(c:ColumnNode)-[r:REFERENCES]->(t2:TableNode)
                   WHERE r.confidence = 'high'
                   RETURN DISTINCT t2.full_name, t2.name, t2.database_name, t2.comment, t2.row_count, t2.column_count""",
                parameters={"fn": fn},
            )
            while result.has_next():
                row = result.get_next()
                t2_fn = row[0]
                if t2_fn not in table_scores:
                    table_scores[t2_fn] = 3
                    table_info[t2_fn] = {
                        "full_name": row[0], "name": row[1], "database_name": row[2],
                        "comment": row[3] or "", "row_count": row[4], "column_count": row[5],
                    }

            # Reverse refs: other columns referencing this table
            result = self.conn.execute(
                """MATCH (c:ColumnNode)-[r:REFERENCES]->(t:TableNode {full_name: $fn})
                   WHERE r.confidence = 'high'
                   MATCH (t2:TableNode)-[:HAS_COLUMN]->(c)
                   RETURN DISTINCT t2.full_name, t2.name, t2.database_name, t2.comment, t2.row_count, t2.column_count
                   LIMIT 10""",
                parameters={"fn": fn},
            )
            while result.has_next():
                row = result.get_next()
                t2_fn = row[0]
                if t2_fn not in table_scores:
                    table_scores[t2_fn] = 3
                    table_info[t2_fn] = {
                        "full_name": row[0], "name": row[1], "database_name": row[2],
                        "comment": row[3] or "", "row_count": row[4], "column_count": row[5],
                    }

        logger.info(f"Total tables after expansion: {len(table_scores)}")

        # Rank by score, break ties by preferring smaller tables (more focused)
        ranked = sorted(
            table_scores.items(),
            key=lambda x: (x[1], -(table_info[x[0]].get("row_count") or 0)),
            reverse=True,
        )

        results = []
        for fn, score in ranked[:limit]:
            info = table_info[fn]
            results.append(dict(info))

        return results

    def _is_mode_specific(self, table_name: str) -> bool:
        """Check if a table is specific to a business mode."""
        return any(m in table_name for m in ("whole", "joint", "focus"))

    def get_table_columns(self, table_full_name: str) -> list[dict]:
        """Get all columns for a table."""
        result = self.conn.execute(
            """MATCH (t:TableNode {full_name: $fn})-[:HAS_COLUMN]->(c:ColumnNode)
               RETURN c.name, c.data_type, c.comment, c.is_primary_key
               ORDER BY c.is_primary_key DESC, c.name""",
            parameters={"fn": table_full_name},
        )
        columns = []
        while result.has_next():
            row = result.get_next()
            columns.append({
                "name": row[0],
                "data_type": row[1],
                "comment": row[2] or "",
                "is_primary_key": row[3],
            })
        return columns

    def find_join_paths(self, table_full_names: list[str]) -> list[dict]:
        """Find JOIN paths between a set of tables via REFERENCES edges."""
        joins = []
        table_set = set(table_full_names)

        for fn in table_full_names:
            result = self.conn.execute(
                """MATCH (t:TableNode {full_name: $fn})-[:HAS_COLUMN]->(c:ColumnNode)-[r:REFERENCES]->(t2:TableNode)
                   RETURN t.name, c.name, t2.name, t2.full_name, r.confidence""",
                parameters={"fn": fn},
            )
            while result.has_next():
                row = result.get_next()
                target_full = row[3]
                if target_full in table_set:
                    joins.append({
                        "source_table": row[0],
                        "source_column": row[1],
                        "target_table": row[2],
                        "target_column": "id",
                        "confidence": row[4],
                    })

        # Deduplicate
        seen = set()
        unique_joins = []
        for j in joins:
            key = (j["source_table"], j["source_column"], j["target_table"])
            if key not in seen:
                seen.add(key)
                unique_joins.append(j)

        return unique_joins

    def get_schema_context(self, question: str, max_tables: int = 10) -> dict:
        """Get complete schema context for a question."""
        tables = self.find_relevant_tables(question, limit=max_tables)
        entity_ids = extract_entity_ids(question)

        if not tables:
            logger.warning("No relevant tables found")
            return {
                "question": question,
                "tables": [],
                "join_conditions": [],
                "entity_ids": entity_ids,
            }

        # Enrich with columns
        for t in tables:
            t["columns"] = self.get_table_columns(t["full_name"])

        # Find JOIN paths
        table_full_names = [t["full_name"] for t in tables]
        joins = self.find_join_paths(table_full_names)

        context = {
            "question": question,
            "tables": tables,
            "join_conditions": joins,
            "entity_ids": entity_ids,
        }

        logger.info(
            f"Schema context: {len(tables)} tables, {len(joins)} join paths, "
            f"entities: {entity_ids}"
        )
        return context


def format_schema_context(ctx: dict) -> str:
    """Format schema context as a readable string for LLM prompts."""
    lines = []
    lines.append(f"## 相关数据表 ({len(ctx['tables'])} 张)")
    lines.append("")

    for t in ctx["tables"]:
        db = t["database_name"]
        comment_str = f" -- {t['comment']}" if t.get("comment") else ""
        lines.append(f"### {db}.{t['name']}{comment_str}")
        lines.append(f"行数: ~{t.get('row_count', '?')}")
        lines.append("列:")
        for col in t.get("columns", []):
            pk_marker = " [PK]" if col.get("is_primary_key") else ""
            comment = f" -- {col['comment']}" if col.get("comment") else ""
            lines.append(f"  - {col['name']} ({col['data_type']}){pk_marker}{comment}")
        lines.append("")

    if ctx["join_conditions"]:
        lines.append("## JOIN 条件")
        for j in ctx["join_conditions"]:
            lines.append(
                f"  - {j['source_table']}.{j['source_column']} = "
                f"{j['target_table']}.{j['target_column']} "
                f"(置信度: {j['confidence']})"
            )
        lines.append("")

    if ctx["entity_ids"]:
        lines.append("## 已识别的实体")
        for k, v in ctx["entity_ids"].items():
            lines.append(f"  - {k} = {v}")

    return "\n".join(lines)


if __name__ == "__main__":
    query = GraphSchemaQuery()

    test_questions = [
        "公司ID为859的公司一共有多少套房源？",
        "目前有多少空置的房间？",
        "逾期未缴费的租客有哪些？列出姓名和欠费金额",
        "本月应收租金总额是多少？",
    ]

    for q in test_questions:
        logger.info(f"\n{'='*60}\nQuestion: {q}")
        ctx = query.get_schema_context(q)
        formatted = format_schema_context(ctx)
        logger.info(f"\n{formatted}")
        logger.info(f"Tables: {[t['name'] for t in ctx['tables']]}")

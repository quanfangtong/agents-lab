"""Graph traversal query logic for Neo4j Schema Graph.

Given a natural language question, finds relevant tables and JOIN paths
by traversing the Neo4j schema graph.
"""

import re
import sys
from pathlib import Path

from neo4j import GraphDatabase
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Neo4j connection config
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "chatbi2024"

# Keyword -> business concept mapping for Chinese NL questions
KEYWORD_MAP = {
    # Housing
    "房源": ["housing", "house", "房源"],
    "房屋": ["housing", "house", "房屋"],
    "整租": ["whole", "整租"],
    "合租": ["joint", "合租"],
    "集中式": ["focus", "集中"],
    "房间": ["room", "房间"],
    # Tenant
    "租客": ["tenant", "tenants", "租客"],
    "租户": ["tenant", "tenants", "租户"],
    # Contract
    "合同": ["contract", "treaty", "合同"],
    "到期": ["expire", "end_time", "到期"],
    "新签": ["contract", "create_time", "新签"],
    # Bill / Finance
    "账单": ["bill", "income", "expend", "账单"],
    "租金": ["rent", "金额", "rent_money", "租金"],
    "应收": ["income", "应收", "receivable"],
    "欠费": ["debt", "欠费", "逾期"],
    "逾期": ["debt", "overdue", "逾期"],
    "收入": ["income", "finance", "收入"],
    "支出": ["expend", "finance", "支出"],
    "费用": ["fee", "charge", "费用"],
    "缴费": ["pay", "缴费"],
    "财务": ["finance", "财务"],
    # Company / Store
    "公司": ["company", "公司"],
    "门店": ["store", "门店"],
    # Area
    "区域": ["area", "region", "区域"],
    # Employee
    "员工": ["employee", "staff", "员工"],
    "房东": ["landlord", "房东", "owner"],
    # Status
    "空置": ["vacant", "空置", "status"],
    "出租率": ["rent_rate", "出租", "occupancy"],
    # Misc
    "联系方式": ["phone", "mobile", "联系"],
}


def extract_keywords(question: str) -> list[str]:
    """Extract search keywords from a Chinese natural language question.

    Returns a flat list of search terms (both Chinese and English).
    """
    keywords = []
    for cn_key, terms in KEYWORD_MAP.items():
        if cn_key in question:
            keywords.extend(terms)

    # Extract company_id pattern like "公司ID为859" or "公司859"
    company_match = re.search(r"公司(?:ID[为是]?)?(\d+)", question)
    if company_match:
        keywords.append("company_id")
        keywords.append(company_match.group(1))

    # Extract store reference
    if "门店" in question or "店" in question:
        keywords.append("store")

    # De-duplicate while preserving order
    seen = set()
    result = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            result.append(k)

    return result


def find_relevant_tables(question: str, neo4j_driver) -> dict:
    """Find relevant tables and JOIN paths by traversing Neo4j schema graph.

    Args:
        question: Natural language question in Chinese
        neo4j_driver: Neo4j driver instance

    Returns:
        dict with keys:
        - tables: list of table info dicts (name, database_name, comment, columns, row_count)
        - join_paths: list of JOIN condition strings
        - keywords_matched: list of matched keywords
    """
    keywords = extract_keywords(question)
    if not keywords:
        # Fallback: split question into individual Chinese characters as search terms
        keywords = [ch for ch in question if '\u4e00' <= ch <= '\u9fff']

    logger.info(f"Extracted keywords: {keywords}")

    matched_tables = {}  # full_name -> table info
    join_paths = []

    with neo4j_driver.session() as session:
        # Strategy 1: Match keywords against Table comment (Chinese, high weight)
        # and Table name (English, medium weight)
        for keyword in keywords:
            is_chinese = any('\u4e00' <= ch <= '\u9fff' for ch in keyword)
            result = session.run(
                """
                MATCH (t:Table)
                WHERE t.comment CONTAINS $kw
                   OR t.name CONTAINS $kw
                RETURN t.full_name AS full_name,
                       t.name AS name,
                       t.database_name AS db,
                       t.comment AS comment,
                       t.row_count AS row_count,
                       t.column_count AS col_count,
                       t.business_domain AS domain,
                       t.comment CONTAINS $kw AS comment_match,
                       t.name CONTAINS $kw AS name_match
                """,
                kw=keyword,
            )
            for record in result:
                fn = record["full_name"]
                if fn not in matched_tables:
                    matched_tables[fn] = {
                        "full_name": fn,
                        "name": record["name"],
                        "database_name": record["db"],
                        "comment": record["comment"],
                        "row_count": record["row_count"],
                        "column_count": record["col_count"],
                        "business_domain": record["domain"],
                        "match_score": 0,
                    }
                # Comment match (Chinese) gets higher weight
                if record["comment_match"]:
                    matched_tables[fn]["match_score"] += 2.0 if is_chinese else 0.8
                if record["name_match"]:
                    matched_tables[fn]["match_score"] += 1.5 if is_chinese else 1.0

        # Strategy 2: Match keywords against Column name and comment
        # Only for tables not already matched at table level, and count distinct matching columns
        for keyword in keywords:
            result = session.run(
                """
                MATCH (t:Table)-[:HAS_COLUMN]->(c:Column)
                WHERE c.comment CONTAINS $kw
                   OR c.name CONTAINS $kw
                RETURN t.full_name AS full_name,
                       t.name AS name,
                       t.database_name AS db,
                       t.comment AS comment,
                       t.row_count AS row_count,
                       t.column_count AS col_count,
                       t.business_domain AS domain,
                       count(c) AS match_count
                """,
                kw=keyword,
            )
            for record in result:
                fn = record["full_name"]
                if fn not in matched_tables:
                    matched_tables[fn] = {
                        "full_name": fn,
                        "name": record["name"],
                        "database_name": record["db"],
                        "comment": record["comment"],
                        "row_count": record["row_count"],
                        "column_count": record["col_count"],
                        "business_domain": record["domain"],
                        "match_score": 0,
                    }
                # Small boost per column match, but cap it
                col_boost = min(record["match_count"] * 0.1, 0.5)
                matched_tables[fn]["match_score"] += col_boost

        # Sort by match score and take top 10
        sorted_tables = sorted(
            matched_tables.values(),
            key=lambda x: x["match_score"],
            reverse=True,
        )[:10]

        if not sorted_tables:
            logger.warning("No tables matched any keywords, returning empty result")
            return {"tables": [], "join_paths": [], "keywords_matched": keywords}

        # Strategy 3: Find JOIN paths between already-matched tables only
        # (avoid expanding to hundreds of unrelated tables)
        table_fns = [t["full_name"] for t in sorted_tables]
        result = session.run(
            """
            MATCH (t1:Table)<-[r:REFERENCES]-(c:Column)<-[:HAS_COLUMN]-(t2:Table)
            WHERE t1.full_name IN $fns AND t2.full_name IN $fns
            RETURN r.join_condition AS join_cond,
                   r.confidence AS confidence,
                   t1.name AS t1_name,
                   t2.name AS t2_name,
                   c.name AS col_name
            """,
            fns=table_fns,
        )
        for record in result:
            jc = record["join_cond"]
            if jc and jc not in join_paths:
                join_paths.append(jc)

        # Strategy 4: Targeted expansion - find tables that bridge matched ones
        # Only expand via high-confidence REFERENCES edges, limit to 5 extra tables
        seed_names = [t["full_name"] for t in sorted_tables[:5]]
        expanded = set(t["full_name"] for t in sorted_tables)

        result = session.run(
            """
            MATCH (t:Table)<-[r:REFERENCES {confidence: 'high'}]-(c:Column)<-[:HAS_COLUMN]-(t2:Table)
            WHERE t.full_name IN $seeds AND NOT t2.full_name IN $expanded
            RETURN DISTINCT t2.full_name AS full_name,
                   t2.name AS name,
                   t2.database_name AS db,
                   t2.comment AS comment,
                   t2.row_count AS row_count,
                   t2.column_count AS col_count,
                   t2.business_domain AS domain,
                   r.join_condition AS join_cond
            LIMIT 5
            """,
            seeds=seed_names,
            expanded=list(expanded),
        )
        for record in result:
            fn = record["full_name"]
            if fn not in expanded:
                expanded.add(fn)
                sorted_tables.append({
                    "full_name": fn,
                    "name": record["name"],
                    "database_name": record["db"],
                    "comment": record["comment"],
                    "row_count": record["row_count"],
                    "column_count": record["col_count"],
                    "business_domain": record["domain"],
                    "match_score": 0.2,
                })
            if record["join_cond"]:
                join_paths.append(record["join_cond"])

        # Fetch columns for each matched table (DDL subset)
        for table_info in sorted_tables:
            result = session.run(
                """
                MATCH (t:Table {full_name: $fn})-[:HAS_COLUMN]->(c:Column)
                RETURN c.name AS name,
                       c.data_type AS data_type,
                       c.comment AS comment,
                       c.is_primary_key AS is_pk,
                       c.sample_values AS samples
                ORDER BY c.is_primary_key DESC, c.name
                """,
                fn=table_info["full_name"],
            )
            table_info["columns"] = [
                {
                    "name": r["name"],
                    "data_type": r["data_type"],
                    "comment": r["comment"],
                    "is_primary_key": r["is_pk"],
                    "sample_values": r["samples"],
                }
                for r in result
            ]

    # Re-sort by match_score, limit to 10
    sorted_tables = sorted(
        sorted_tables,
        key=lambda x: x["match_score"],
        reverse=True,
    )[:10]

    logger.info(
        f"Found {len(sorted_tables)} relevant tables, "
        f"{len(join_paths)} JOIN paths"
    )

    return {
        "tables": sorted_tables,
        "join_paths": list(set(join_paths)),
        "keywords_matched": keywords,
    }


def format_schema_context(query_result: dict) -> str:
    """Format query result into a schema context string for LLM prompt.

    Args:
        query_result: Output from find_relevant_tables()

    Returns:
        Formatted string describing the relevant tables and relationships.
    """
    lines = []
    lines.append("## 相关表结构\n")

    for table in query_result["tables"]:
        db = table["database_name"]
        name = table["name"]
        comment = table.get("comment", "")
        row_count = table.get("row_count", 0)
        lines.append(f"### {db}.{name}  -- {comment} ({row_count} rows)")

        columns = table.get("columns", [])
        if columns:
            col_lines = []
            for col in columns:
                pk_mark = " [PK]" if col.get("is_primary_key") else ""
                comment_str = f"  -- {col['comment']}" if col.get("comment") else ""
                sample_str = ""
                if col.get("sample_values"):
                    sample_str = f"  (samples: {col['sample_values']})"
                col_lines.append(
                    f"  {col['name']} {col['data_type']}{pk_mark}{comment_str}{sample_str}"
                )
            lines.append("\n".join(col_lines))
        lines.append("")

    if query_result["join_paths"]:
        lines.append("## JOIN 条件\n")
        for jp in query_result["join_paths"]:
            lines.append(f"- {jp}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    test_questions = [
        "公司ID为859的公司一共有多少套房源？",
        "目前有多少空置的房间？",
        "租客张三的合同什么时候到期？",
        "逾期未缴费的租客有哪些？",
        "公司859上个月的财务收入和支出分别是多少？",
    ]

    try:
        for q in test_questions:
            logger.info(f"\n{'='*60}")
            logger.info(f"Question: {q}")
            result = find_relevant_tables(q, driver)
            schema_ctx = format_schema_context(result)
            logger.info(f"Keywords: {result['keywords_matched']}")
            logger.info(f"Tables found: {[t['name'] for t in result['tables']]}")
            logger.info(f"JOIN paths: {result['join_paths']}")
            logger.info(f"\nSchema context preview (first 500 chars):\n{schema_ctx[:500]}")
    finally:
        driver.close()

"""Build Kuzu Schema Graph from MySQL metadata.

Connects to three MySQL databases (qft_basics, qft_lease, qft_finance),
extracts table/column metadata, and builds a Kuzu property graph with
inferred foreign key relationships.
"""

import os
import re
import sys
import shutil
import time
from pathlib import Path
from typing import Optional

import kuzu
from sqlalchemy import text
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from common.database import get_db_connection

# Tables matching these patterns are pruned
PRUNE_PATTERNS = [
    r"_bak$", r"_bak\d*$", r"_back$", r"_backup$",
    r"_copy$", r"_copy\d*$",
    r"_tmp$", r"_temp$",
    r"_\d{6,}$",  # date suffixes like _20231001
    r"_old$", r"_old\d*$",
    r"_test$",
]

PRUNE_PREFIXES = [
    "act_",  # activiti workflow tables
]

# High-confidence FK inference rules: column_suffix -> target table patterns
FK_RULES = {
    "company_id": ["qft_company"],
    "housing_id": ["qft_whole_housing", "qft_joint_housing", "qft_focus_parent_room"],
    "house_id": ["qft_whole_housing", "qft_joint_housing"],  # alias
    "room_id": ["qft_joint_room", "qft_focus_room", "qft_whole_housing"],
    "tenant_id": ["qft_whole_tenants", "qft_joint_tenants", "qft_focus_tenants"],
    "tenants_id": ["qft_whole_tenants", "qft_joint_tenants", "qft_focus_tenants"],
    "store_id": ["qft_store"],
    "employee_id": ["qft_employee"],
    "area_id": ["qft_area"],
}

KUZU_DB_DIR = str(PROJECT_ROOT / "data" / "kuzu_schema_graph")


def should_prune_table(table_name: str) -> bool:
    """Check if a table should be pruned based on naming patterns."""
    lower = table_name.lower()
    for prefix in PRUNE_PREFIXES:
        if lower.startswith(prefix):
            return True
    for pattern in PRUNE_PATTERNS:
        if re.search(pattern, lower):
            return True
    return False


def get_table_metadata(db_conn, db_name: str) -> list[dict]:
    """Fetch table metadata (name, comment, row_count, column_count) from MySQL."""
    actual_db = db_conn.databases[db_name]
    query = text("""
        SELECT
            t.TABLE_NAME,
            t.TABLE_COMMENT,
            t.TABLE_ROWS,
            t.AUTO_INCREMENT
        FROM information_schema.TABLES t
        WHERE t.TABLE_SCHEMA = :schema
          AND t.TABLE_TYPE = 'BASE TABLE'
        ORDER BY t.TABLE_NAME
    """)
    with db_conn.get_connection(db_name) as conn:
        rows = conn.execute(query, {"schema": actual_db}).fetchall()

    tables = []
    for row in rows:
        name = row[0]
        if should_prune_table(name):
            continue
        row_count = row[2] or 0
        # Skip empty tables (row_count == 0)
        if row_count == 0:
            continue
        tables.append({
            "name": name,
            "comment": row[1] or "",
            "row_count": row_count,
        })

    logger.info(f"[{db_name}] {len(tables)} tables after pruning (from {len(rows)} total)")
    return tables


def get_columns_metadata(db_conn, db_name: str, table_name: str) -> list[dict]:
    """Fetch column metadata for a given table."""
    actual_db = db_conn.databases[db_name]
    query = text("""
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            COLUMN_COMMENT,
            COLUMN_KEY
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = :schema
          AND TABLE_NAME = :table_name
        ORDER BY ORDINAL_POSITION
    """)
    with db_conn.get_connection(db_name) as conn:
        rows = conn.execute(query, {"schema": actual_db, "table_name": table_name}).fetchall()

    columns = []
    for row in rows:
        columns.append({
            "name": row[0],
            "data_type": row[1] or "unknown",
            "comment": row[2] or "",
            "is_primary_key": row[3] == "PRI",
        })
    return columns


def infer_references(column_name: str, all_table_names: set[str]) -> list[str]:
    """Infer which tables a column might reference based on FK rules."""
    lower = column_name.lower()

    # Direct rule match
    if lower in FK_RULES:
        targets = []
        for candidate in FK_RULES[lower]:
            if candidate in all_table_names:
                targets.append(candidate)
        return targets

    # Generic _id suffix inference
    if lower.endswith("_id") and lower != "id":
        stem = lower[:-3]  # e.g. "contract_id" -> "contract"
        targets = []
        for tbl in all_table_names:
            tbl_lower = tbl.lower()
            # Match tables containing the stem (e.g. qft_contract_*)
            if stem in tbl_lower and not should_prune_table(tbl):
                targets.append(tbl)
        # Limit to avoid noise -- only keep if <= 5 matches
        if len(targets) <= 5:
            return targets

    return []


class SchemaGraphBuilder:
    """Builds and manages a Kuzu Schema Graph from MySQL metadata."""

    def __init__(self, kuzu_db_dir: str = KUZU_DB_DIR):
        self.kuzu_db_dir = kuzu_db_dir
        self.db_conn = get_db_connection()
        self.db: Optional[kuzu.Database] = None
        self.conn: Optional[kuzu.Connection] = None
        # Tracks all table names across databases for FK inference
        self._all_table_names: set[str] = set()
        # Maps table_name -> db_name for cross-db reference
        self._table_db_map: dict[str, str] = {}

    def _init_kuzu(self, force_rebuild: bool = False):
        """Initialize Kuzu database, optionally clearing old data."""
        if force_rebuild and os.path.exists(self.kuzu_db_dir):
            if os.path.isdir(self.kuzu_db_dir):
                shutil.rmtree(self.kuzu_db_dir)
            else:
                os.remove(self.kuzu_db_dir)
            logger.info(f"Removed existing Kuzu DB at {self.kuzu_db_dir}")
        elif os.path.isdir(self.kuzu_db_dir) and not os.listdir(self.kuzu_db_dir):
            shutil.rmtree(self.kuzu_db_dir)

        os.makedirs(os.path.dirname(self.kuzu_db_dir), exist_ok=True)
        self.db = kuzu.Database(self.kuzu_db_dir)
        self.conn = kuzu.Connection(self.db)
        logger.info(f"Kuzu DB initialized at {self.kuzu_db_dir}")

    def _create_schema(self):
        """Create Kuzu node and relationship table schemas."""
        # Node tables
        self.conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS Database(
                name STRING,
                description STRING,
                PRIMARY KEY(name)
            )
        """)
        self.conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS TableNode(
                full_name STRING,
                name STRING,
                comment STRING,
                row_count INT64,
                column_count INT64,
                database_name STRING,
                PRIMARY KEY(full_name)
            )
        """)
        self.conn.execute("""
            CREATE NODE TABLE IF NOT EXISTS ColumnNode(
                full_name STRING,
                name STRING,
                data_type STRING,
                comment STRING,
                is_primary_key BOOL,
                table_full_name STRING,
                PRIMARY KEY(full_name)
            )
        """)

        # Relationship tables
        self.conn.execute("""
            CREATE REL TABLE IF NOT EXISTS HAS_TABLE(
                FROM Database TO TableNode
            )
        """)
        self.conn.execute("""
            CREATE REL TABLE IF NOT EXISTS HAS_COLUMN(
                FROM TableNode TO ColumnNode
            )
        """)
        self.conn.execute("""
            CREATE REL TABLE IF NOT EXISTS REFERENCES(
                FROM ColumnNode TO TableNode,
                confidence STRING
            )
        """)
        logger.info("Kuzu schema created")

    def _insert_database_node(self, db_name: str, description: str):
        """Insert a Database node."""
        self.conn.execute(
            "MERGE (d:Database {name: $name}) SET d.description = $descr",
            parameters={"name": db_name, "descr": description},
        )

    def _insert_table_node(self, db_name: str, table: dict, col_count: int):
        """Insert a TableNode."""
        full_name = f"{db_name}.{table['name']}"
        self.conn.execute(
            """MERGE (t:TableNode {full_name: $full_name})
               SET t.name = $name,
                   t.comment = $comment,
                   t.row_count = $row_count,
                   t.column_count = $col_count,
                   t.database_name = $db_name""",
            parameters={
                "full_name": full_name,
                "name": table["name"],
                "comment": table["comment"],
                "row_count": table["row_count"],
                "col_count": col_count,
                "db_name": db_name,
            },
        )
        # HAS_TABLE relationship
        self.conn.execute(
            """MATCH (d:Database {name: $db_name}), (t:TableNode {full_name: $full_name})
               MERGE (d)-[:HAS_TABLE]->(t)""",
            parameters={"db_name": db_name, "full_name": full_name},
        )

    def _insert_column_node(self, db_name: str, table_name: str, col: dict):
        """Insert a ColumnNode and HAS_COLUMN relationship."""
        table_full = f"{db_name}.{table_name}"
        col_full = f"{table_full}.{col['name']}"
        self.conn.execute(
            """MERGE (c:ColumnNode {full_name: $full_name})
               SET c.name = $name,
                   c.data_type = $data_type,
                   c.comment = $comment,
                   c.is_primary_key = $is_pk,
                   c.table_full_name = $table_full""",
            parameters={
                "full_name": col_full,
                "name": col["name"],
                "data_type": col["data_type"],
                "comment": col["comment"],
                "is_pk": col["is_primary_key"],
                "table_full": table_full,
            },
        )
        self.conn.execute(
            """MATCH (t:TableNode {full_name: $table_full}), (c:ColumnNode {full_name: $col_full})
               MERGE (t)-[:HAS_COLUMN]->(c)""",
            parameters={"table_full": table_full, "col_full": col_full},
        )

    def _insert_references(self):
        """Infer and insert REFERENCES edges based on FK rules."""
        logger.info("Inferring foreign key references...")
        ref_count = 0

        for db_name in self.db_conn.databases:
            actual_db = self.db_conn.databases[db_name]
            # Get all columns with _id suffix
            query = text("""
                SELECT TABLE_NAME, COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :schema
                  AND COLUMN_NAME LIKE '%\\_id'
                ORDER BY TABLE_NAME, COLUMN_NAME
            """)
            with self.db_conn.get_connection(db_name) as conn:
                rows = conn.execute(query, {"schema": actual_db}).fetchall()

            for row in rows:
                table_name, col_name = row[0], row[1]
                if should_prune_table(table_name):
                    continue
                if table_name not in self._all_table_names:
                    continue

                targets = infer_references(col_name, self._all_table_names)
                if not targets:
                    continue

                col_full = f"{db_name}.{table_name}.{col_name}"
                col_lower = col_name.lower()
                confidence = "high" if col_lower in FK_RULES else "medium"

                for target in targets:
                    target_db = self._table_db_map.get(target, db_name)
                    target_full = f"{target_db}.{target}"
                    try:
                        self.conn.execute(
                            """MATCH (c:ColumnNode {full_name: $col_full}),
                                     (t:TableNode {full_name: $target_full})
                               MERGE (c)-[:REFERENCES {confidence: $conf}]->(t)""",
                            parameters={
                                "col_full": col_full,
                                "target_full": target_full,
                                "conf": confidence,
                            },
                        )
                        ref_count += 1
                    except Exception as e:
                        # Column/table may not exist in graph (pruned/empty)
                        logger.debug(f"Skipped ref {col_full} -> {target_full}: {e}")

        logger.info(f"Inserted {ref_count} REFERENCES edges")

    def build(self, force_rebuild: bool = True) -> dict:
        """Build the complete Schema Graph.

        Returns:
            Statistics dict with counts of nodes and edges.
        """
        start = time.time()

        self._init_kuzu(force_rebuild=force_rebuild)
        self._create_schema()

        db_descriptions = {
            "basics": "基础数据库：公司、门店、员工、区域等基础配置",
            "lease": "租赁数据库：房源、房间、租客、合同、账单等租赁核心业务",
            "finance": "财务数据库：财务流水、收支明细、对账等财务业务",
        }

        total_tables = 0
        total_columns = 0

        # Phase 1: Collect all table names for FK inference
        for db_name in self.db_conn.databases:
            tables = get_table_metadata(self.db_conn, db_name)
            for t in tables:
                self._all_table_names.add(t["name"])
                self._table_db_map[t["name"]] = db_name

        logger.info(f"Total tables across all databases: {len(self._all_table_names)}")

        # Phase 2: Insert nodes
        for db_name in self.db_conn.databases:
            desc = db_descriptions.get(db_name, "")
            self._insert_database_node(db_name, desc)

            tables = get_table_metadata(self.db_conn, db_name)
            for table in tables:
                columns = get_columns_metadata(self.db_conn, db_name, table["name"])
                self._insert_table_node(db_name, table, len(columns))
                for col in columns:
                    self._insert_column_node(db_name, table["name"], col)
                total_columns += len(columns)
            total_tables += len(tables)
            logger.info(f"[{db_name}] Inserted {len(tables)} tables")

        # Phase 3: Infer references
        self._insert_references()

        elapsed = time.time() - start

        # Collect stats
        stats = self._get_stats()
        stats["build_time_seconds"] = round(elapsed, 2)
        logger.info(f"Schema Graph built in {elapsed:.1f}s: {stats}")
        return stats

    def _get_stats(self) -> dict:
        """Get graph statistics."""
        db_count = self.conn.execute("MATCH (d:Database) RETURN count(d)").get_next()[0]
        table_count = self.conn.execute("MATCH (t:TableNode) RETURN count(t)").get_next()[0]
        col_count = self.conn.execute("MATCH (c:ColumnNode) RETURN count(c)").get_next()[0]
        has_table = self.conn.execute("MATCH ()-[r:HAS_TABLE]->() RETURN count(r)").get_next()[0]
        has_col = self.conn.execute("MATCH ()-[r:HAS_COLUMN]->() RETURN count(r)").get_next()[0]
        refs = self.conn.execute("MATCH ()-[r:REFERENCES]->() RETURN count(r)").get_next()[0]
        return {
            "databases": db_count,
            "tables": table_count,
            "columns": col_count,
            "has_table_edges": has_table,
            "has_column_edges": has_col,
            "references_edges": refs,
        }

    def get_connection(self) -> kuzu.Connection:
        """Get the Kuzu connection (reopen if needed)."""
        if self.conn is None:
            if self.db is None:
                self.db = kuzu.Database(self.kuzu_db_dir)
            self.conn = kuzu.Connection(self.db)
        return self.conn


if __name__ == "__main__":
    logger.info("Building Schema Graph...")
    builder = SchemaGraphBuilder()
    stats = builder.build(force_rebuild=True)
    logger.info(f"Build complete. Stats: {stats}")

    # Quick verification queries
    conn = builder.get_connection()

    # Show databases
    result = conn.execute("MATCH (d:Database) RETURN d.name, d.description")
    logger.info("Databases:")
    while result.has_next():
        row = result.get_next()
        logger.info(f"  {row[0]}: {row[1]}")

    # Show top 10 tables by row count
    result = conn.execute("""
        MATCH (t:TableNode)
        RETURN t.database_name, t.name, t.row_count, t.column_count
        ORDER BY t.row_count DESC LIMIT 10
    """)
    logger.info("Top 10 tables by row count:")
    while result.has_next():
        row = result.get_next()
        logger.info(f"  {row[0]}.{row[1]}: {row[2]} rows, {row[3]} columns")

    # Show reference edges
    result = conn.execute("""
        MATCH (c:ColumnNode)-[r:REFERENCES]->(t:TableNode)
        RETURN c.full_name, t.full_name, r.confidence
        LIMIT 20
    """)
    logger.info("Sample REFERENCES edges:")
    while result.has_next():
        row = result.get_next()
        logger.info(f"  {row[0]} -> {row[1]} ({row[2]})")

"""Build Neo4j Schema Graph from MySQL metadata.

Connects to three MySQL databases (qft_basics, qft_lease, qft_finance),
extracts table/column metadata, and builds a Neo4j property graph with
inferred foreign key relationships.
"""

import re
import sys
import time
from pathlib import Path

from neo4j import GraphDatabase
from sqlalchemy import text
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from common.database import get_db_connection

# Neo4j connection config
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "chatbi2024"

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
    "act_",        # activiti workflow tables
    "qft_smart_",  # smart device tables
    "qft_sms_",    # SMS tables
    "qft_wechat_", # WeChat tables
    "qft_circle_", # circle tables
    "qft_hfq_",    # channel tables
    "qft_huituiguang_",
    "jian_rong_",
    "qft_cdrm_",
]

# High-confidence FK inference rules: column_suffix -> target table patterns
FK_RULES_HIGH = {
    "company_id": ["qft_company"],
    "store_id": ["qft_store", "qft_store_info"],
    "housing_id": ["qft_whole_housing", "qft_joint_housing", "qft_focus_parent_room"],
    "room_id": ["qft_joint_room", "qft_focus_room", "qft_whole_housing"],
    "tenant_id": ["qft_whole_tenants", "qft_joint_tenants", "qft_focus_tenants"],
    "tenants_id": ["qft_whole_tenants", "qft_joint_tenants", "qft_focus_tenants"],
    "employee_id": ["qft_employee"],
    "contract_id": ["qft_contract_treaty_info"],
    "property_id": ["qft_property"],
    "area_id": ["qft_area"],
}

FK_RULES_MEDIUM = {
    "house_id": ["qft_whole_housing", "qft_joint_housing"],
}

# Low confidence - skip these
FK_SKIP = {"parent_id", "source_id", "id"}

# Business domain classification by table name patterns
BUSINESS_DOMAIN_RULES = [
    (r"housing|house", "housing"),
    (r"room", "housing"),
    (r"tenant|tenants", "tenant"),
    (r"contract|treaty", "contract"),
    (r"bill|income|expend|debt|fee|pay|charge", "bill"),
    (r"finance", "finance"),
    (r"company", "company"),
    (r"store", "company"),
    (r"employee|user|staff", "user"),
    (r"area|region|district", "area"),
    (r"property|estate", "housing"),
]


def classify_business_domain(table_name: str) -> str:
    """Classify a table into a business domain based on its name."""
    lower = table_name.lower()
    for pattern, domain in BUSINESS_DOMAIN_RULES:
        if re.search(pattern, lower):
            return domain
    return "other"


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
    """Fetch table metadata from MySQL information_schema."""
    actual_db = db_conn.databases[db_name]
    query = text("""
        SELECT
            t.TABLE_NAME,
            t.TABLE_COMMENT,
            t.TABLE_ROWS
        FROM information_schema.TABLES t
        WHERE t.TABLE_SCHEMA = :schema
          AND t.TABLE_TYPE = 'BASE TABLE'
        ORDER BY t.TABLE_NAME
    """)
    with db_conn.get_connection(db_name) as conn:
        rows = conn.execute(query, {"schema": actual_db}).fetchall()

    tables = []
    pruned = 0
    empty = 0
    for row in rows:
        name = row[0]
        if should_prune_table(name):
            pruned += 1
            continue
        row_count = row[1] or 0
        if row_count == 0:
            empty += 1
            continue
        tables.append({
            "name": name,
            "comment": row[2] or "",
            "row_count": row[1] or 0,
        })

    # Fix: TABLE_ROWS is index 2, TABLE_COMMENT is index 1
    # Re-read the column order: TABLE_NAME(0), TABLE_COMMENT(1), TABLE_ROWS(2)
    tables = []
    pruned = 0
    empty = 0
    for row in rows:
        name = row[0]
        if should_prune_table(name):
            pruned += 1
            continue
        row_count = row[2] or 0
        if row_count == 0:
            empty += 1
            continue
        tables.append({
            "name": name,
            "comment": row[1] or "",
            "row_count": row_count,
        })

    logger.info(
        f"[{db_name}] {len(tables)} tables kept "
        f"(pruned={pruned}, empty={empty}, total={len(rows)})"
    )
    return tables


def get_columns_metadata(db_conn, db_name: str, table_name: str) -> list[dict]:
    """Fetch column metadata for a given table."""
    actual_db = db_conn.databases[db_name]
    query = text("""
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            COLUMN_COMMENT,
            COLUMN_KEY,
            IS_NULLABLE
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
            "is_nullable": row[4] == "YES",
        })
    return columns


def get_sample_values(db_conn, db_name: str, table_name: str, column_name: str, limit: int = 5) -> str:
    """Get sample distinct values for a column."""
    try:
        query = text(
            f"SELECT DISTINCT `{column_name}` FROM `{table_name}` "
            f"WHERE `{column_name}` IS NOT NULL LIMIT :lim"
        )
        with db_conn.get_connection(db_name) as conn:
            rows = conn.execute(query, {"lim": limit}).fetchall()
        values = [str(r[0])[:50] for r in rows]
        return ", ".join(values)
    except Exception:
        return ""


def infer_references(column_name: str, all_table_names: set[str]) -> list[tuple[str, str]]:
    """Infer which tables a column might reference.

    Returns list of (target_table, confidence) tuples.
    """
    lower = column_name.lower()

    if lower in FK_SKIP:
        return []

    # High confidence rules
    if lower in FK_RULES_HIGH:
        results = []
        for candidate in FK_RULES_HIGH[lower]:
            if candidate in all_table_names:
                results.append((candidate, "high"))
        return results

    # Medium confidence rules
    if lower in FK_RULES_MEDIUM:
        results = []
        for candidate in FK_RULES_MEDIUM[lower]:
            if candidate in all_table_names:
                results.append((candidate, "medium"))
        return results

    # Generic _id suffix inference (medium confidence)
    if lower.endswith("_id") and lower != "id":
        stem = lower[:-3]
        targets = []
        for tbl in all_table_names:
            tbl_lower = tbl.lower()
            if stem in tbl_lower and not should_prune_table(tbl):
                targets.append(tbl)
        if 0 < len(targets) <= 5:
            return [(t, "medium") for t in targets]

    return []


class SchemaGraphBuilder:
    """Builds and manages a Neo4j Schema Graph from MySQL metadata."""

    def __init__(
        self,
        neo4j_uri: str = NEO4J_URI,
        neo4j_user: str = NEO4J_USER,
        neo4j_password: str = NEO4J_PASSWORD,
    ):
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self.driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.db_conn = get_db_connection()
        self._all_table_names: set[str] = set()
        self._table_db_map: dict[str, str] = {}

    def close(self):
        """Close Neo4j driver."""
        self.driver.close()

    def _clear_graph(self):
        """Clear all nodes and relationships in Neo4j."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        logger.info("Cleared existing Neo4j graph data")

    def _create_constraints(self):
        """Create uniqueness constraints and indexes."""
        constraints = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Database) REQUIRE d.name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Table) REQUIRE t.full_name IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Column) REQUIRE c.full_name IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (t:Table) ON (t.name)",
            "CREATE INDEX IF NOT EXISTS FOR (t:Table) ON (t.business_domain)",
            "CREATE INDEX IF NOT EXISTS FOR (t:Table) ON (t.comment)",
            "CREATE INDEX IF NOT EXISTS FOR (c:Column) ON (c.name)",
            "CREATE INDEX IF NOT EXISTS FOR (c:Column) ON (c.comment)",
        ]
        with self.driver.session() as session:
            for stmt in constraints + indexes:
                session.run(stmt)
        logger.info("Created Neo4j constraints and indexes")

    def _insert_database_nodes(self):
        """Insert Database nodes."""
        db_descriptions = {
            "basics": "基础数据库：公司、门店、员工、区域等基础配置",
            "lease": "租赁数据库：房源、房间、租客、合同、账单等租赁核心业务",
            "finance": "财务数据库：财务流水、收支明细、对账等财务业务",
        }
        with self.driver.session() as session:
            for db_name, desc in db_descriptions.items():
                session.run(
                    "MERGE (d:Database {name: $name}) SET d.description = $desc",
                    name=db_name, desc=desc,
                )
        logger.info("Inserted 3 Database nodes")

    def _insert_tables_and_columns(self) -> dict:
        """Insert Table and Column nodes with HAS_TABLE and HAS_COLUMN relationships.

        Uses UNWIND for batch inserts to maximize performance.
        Returns stats dict.
        """
        total_tables = 0
        total_columns = 0

        for db_name in self.db_conn.databases:
            tables = get_table_metadata(self.db_conn, db_name)

            # Batch: collect all table + column data, then insert in bulk
            table_batch = []
            column_batch = []

            for table in tables:
                columns = get_columns_metadata(self.db_conn, db_name, table["name"])
                full_name = f"{db_name}.{table['name']}"
                domain = classify_business_domain(table["name"])

                table_batch.append({
                    "full_name": full_name,
                    "name": table["name"],
                    "comment": table["comment"],
                    "row_count": table["row_count"],
                    "col_count": len(columns),
                    "db_name": db_name,
                    "domain": domain,
                })

                for col in columns:
                    col_full = f"{full_name}.{col['name']}"
                    column_batch.append({
                        "col_full": col_full,
                        "name": col["name"],
                        "data_type": col["data_type"],
                        "comment": col["comment"],
                        "is_pk": col["is_primary_key"],
                        "is_nullable": col["is_nullable"],
                        "sample_vals": "",
                        "table_full": full_name,
                    })

                total_columns += len(columns)

            # Batch insert tables
            with self.driver.session() as session:
                session.run(
                    """
                    UNWIND $batch AS row
                    MERGE (t:Table {full_name: row.full_name})
                    SET t.name = row.name,
                        t.comment = row.comment,
                        t.row_count = row.row_count,
                        t.column_count = row.col_count,
                        t.database_name = row.db_name,
                        t.business_domain = row.domain
                    WITH t, row
                    MATCH (d:Database {name: row.db_name})
                    MERGE (d)-[:HAS_TABLE]->(t)
                    """,
                    batch=table_batch,
                )

                # Batch insert columns in chunks (avoid too-large transactions)
                chunk_size = 500
                for i in range(0, len(column_batch), chunk_size):
                    chunk = column_batch[i:i + chunk_size]
                    session.run(
                        """
                        UNWIND $batch AS row
                        MERGE (c:Column {full_name: row.col_full})
                        SET c.name = row.name,
                            c.data_type = row.data_type,
                            c.comment = row.comment,
                            c.is_primary_key = row.is_pk,
                            c.is_nullable = row.is_nullable,
                            c.sample_values = row.sample_vals
                        WITH c, row
                        MATCH (t:Table {full_name: row.table_full})
                        MERGE (t)-[:HAS_COLUMN]->(c)
                        """,
                        batch=chunk,
                    )

            total_tables += len(tables)
            logger.info(f"[{db_name}] Inserted {len(tables)} tables")

        return {"tables": total_tables, "columns": total_columns}

    def _insert_references(self) -> int:
        """Infer and insert REFERENCES edges based on FK rules."""
        logger.info("Inferring foreign key references...")
        ref_count = 0

        for db_name in self.db_conn.databases:
            actual_db = self.db_conn.databases[db_name]
            query = text("""
                SELECT TABLE_NAME, COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = :schema
                  AND COLUMN_NAME LIKE '%\\_id'
                ORDER BY TABLE_NAME, COLUMN_NAME
            """)
            with self.db_conn.get_connection(db_name) as conn:
                rows = conn.execute(query, {"schema": actual_db}).fetchall()

            with self.driver.session() as session:
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
                    for target_table, confidence in targets:
                        target_db = self._table_db_map.get(target_table, db_name)
                        target_full = f"{target_db}.{target_table}"
                        join_cond = f"{table_name}.{col_name} = {target_table}.id"

                        try:
                            session.run(
                                """
                                MATCH (c:Column {full_name: $col_full}),
                                      (t:Table {full_name: $target_full})
                                MERGE (c)-[r:REFERENCES]->(t)
                                SET r.confidence = $conf,
                                    r.join_condition = $join_cond
                                """,
                                col_full=col_full,
                                target_full=target_full,
                                conf=confidence,
                                join_cond=join_cond,
                            )
                            ref_count += 1
                        except Exception as e:
                            logger.debug(f"Skipped ref {col_full} -> {target_full}: {e}")

        logger.info(f"Inserted {ref_count} REFERENCES edges")
        return ref_count

    def build(self, force_rebuild: bool = True) -> dict:
        """Build the complete Schema Graph.

        Returns:
            Statistics dict with counts of nodes and edges.
        """
        start = time.time()

        if force_rebuild:
            self._clear_graph()

        self._create_constraints()
        self._insert_database_nodes()

        # Phase 1: Collect all table names for FK inference
        for db_name in self.db_conn.databases:
            tables = get_table_metadata(self.db_conn, db_name)
            for t in tables:
                self._all_table_names.add(t["name"])
                self._table_db_map[t["name"]] = db_name

        logger.info(f"Total tables across all databases: {len(self._all_table_names)}")

        # Phase 2: Insert nodes
        node_stats = self._insert_tables_and_columns()

        # Phase 3: Infer references
        ref_count = self._insert_references()

        elapsed = time.time() - start
        stats = self._get_stats()
        stats["build_time_seconds"] = round(elapsed, 2)
        logger.info(f"Schema Graph built in {elapsed:.1f}s: {stats}")
        return stats

    def _get_stats(self) -> dict:
        """Get graph statistics."""
        with self.driver.session() as session:
            db_count = session.run("MATCH (d:Database) RETURN count(d) AS c").single()["c"]
            table_count = session.run("MATCH (t:Table) RETURN count(t) AS c").single()["c"]
            col_count = session.run("MATCH (c:Column) RETURN count(c) AS c").single()["c"]
            has_table = session.run("MATCH ()-[r:HAS_TABLE]->() RETURN count(r) AS c").single()["c"]
            has_col = session.run("MATCH ()-[r:HAS_COLUMN]->() RETURN count(r) AS c").single()["c"]
            refs = session.run("MATCH ()-[r:REFERENCES]->() RETURN count(r) AS c").single()["c"]
        return {
            "databases": db_count,
            "tables": table_count,
            "columns": col_count,
            "has_table_edges": has_table,
            "has_column_edges": has_col,
            "references_edges": refs,
        }

    def get_driver(self):
        """Get the Neo4j driver."""
        return self.driver


if __name__ == "__main__":
    logger.info("Building Neo4j Schema Graph...")
    builder = SchemaGraphBuilder()
    try:
        stats = builder.build(force_rebuild=True)
        logger.info(f"Build complete. Stats: {stats}")

        # Verification queries
        with builder.driver.session() as session:
            # Show databases
            result = session.run("MATCH (d:Database) RETURN d.name, d.description")
            logger.info("Databases:")
            for record in result:
                logger.info(f"  {record['d.name']}: {record['d.description']}")

            # Top 10 tables by row count
            result = session.run("""
                MATCH (t:Table)
                RETURN t.database_name, t.name, t.row_count, t.column_count
                ORDER BY t.row_count DESC LIMIT 10
            """)
            logger.info("Top 10 tables by row count:")
            for record in result:
                logger.info(
                    f"  {record['t.database_name']}.{record['t.name']}: "
                    f"{record['t.row_count']} rows, {record['t.column_count']} columns"
                )

            # Sample REFERENCES edges
            result = session.run("""
                MATCH (c:Column)-[r:REFERENCES]->(t:Table)
                RETURN c.full_name, t.full_name, r.confidence
                LIMIT 20
            """)
            logger.info("Sample REFERENCES edges:")
            for record in result:
                logger.info(
                    f"  {record['c.full_name']} -> {record['t.full_name']} "
                    f"({record['r.confidence']})"
                )

            # Business domain distribution
            result = session.run("""
                MATCH (t:Table)
                RETURN t.business_domain AS domain, count(t) AS cnt
                ORDER BY cnt DESC
            """)
            logger.info("Business domain distribution:")
            for record in result:
                logger.info(f"  {record['domain']}: {record['cnt']} tables")

    finally:
        builder.close()

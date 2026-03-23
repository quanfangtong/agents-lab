"""
Schema importer for FalkorDB graph.

Extracts MySQL schema metadata (tables, columns, relationships) and loads
them into a FalkorDB graph for QueryWeaver-style Text2SQL.

Follows QueryWeaver's graph model:
- Database node
- Table nodes with BELONGS_TO Database
- Column nodes with BELONGS_TO Table
- REFERENCES edges between FK columns
"""

import os
import sys
import json
import time
from typing import Dict, Any, List

import pymysql
from pymysql.cursors import DictCursor
from falkordb import FalkorDB
from dotenv import load_dotenv
from loguru import logger

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))


def get_mysql_connection(database: str) -> pymysql.Connection:
    """Create a MySQL connection for the specified database."""
    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
        database=database,
        cursorclass=DictCursor,
        connect_timeout=30,
        read_timeout=60,
    )


def extract_tables(cursor, db_name: str) -> List[Dict[str, Any]]:
    """Extract table metadata from MySQL information_schema."""
    cursor.execute("""
        SELECT table_name, table_comment, table_rows
        FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """, (db_name,))
    return cursor.fetchall()


def extract_columns(cursor, db_name: str, table_name: str) -> List[Dict[str, Any]]:
    """Extract column metadata for a table."""
    cursor.execute("""
        SELECT
            column_name, data_type, column_type, is_nullable,
            column_default, column_key, column_comment, ordinal_position
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """, (db_name, table_name))
    return cursor.fetchall()


def extract_foreign_keys(cursor, db_name: str) -> List[Dict[str, str]]:
    """Extract all foreign key relationships from a database."""
    cursor.execute("""
        SELECT
            table_name, column_name,
            referenced_table_name, referenced_column_name,
            constraint_name
        FROM information_schema.key_column_usage
        WHERE table_schema = %s AND referenced_table_name IS NOT NULL
        ORDER BY table_name, constraint_name
    """, (db_name,))
    return cursor.fetchall()


def extract_indexes(cursor, db_name: str, table_name: str) -> List[Dict[str, Any]]:
    """Extract index info for a table (helps identify implicit relationships)."""
    cursor.execute("""
        SELECT index_name, column_name, non_unique, seq_in_index
        FROM information_schema.statistics
        WHERE table_schema = %s AND table_name = %s
        ORDER BY index_name, seq_in_index
    """, (db_name, table_name))
    return cursor.fetchall()


def build_graph(falkordb_host: str = "localhost", falkordb_port: int = 6379,
                graph_name: str = "qft_schema", databases: List[str] = None):
    """
    Build FalkorDB graph from MySQL schema.

    Graph model:
    (:Database {name, description})
    (:Table {name, db, description, row_count, column_count})
    (:Column {name, type, nullable, key_type, description, ordinal})
    (:Table)-[:IN_DATABASE]->(:Database)
    (:Column)-[:BELONGS_TO]->(:Table)
    (:Column)-[:REFERENCES]->(:Column)  -- FK relationships
    """
    if databases is None:
        databases = [
            os.getenv("DB_BASICS", "qft_basics"),
            os.getenv("DB_LEASE", "qft_lease"),
            os.getenv("DB_FINANCE", "qft_finance"),
        ]

    fdb = FalkorDB(host=falkordb_host, port=falkordb_port)
    graph = fdb.select_graph(graph_name)

    # Clean existing graph
    try:
        graph.query("MATCH (n) DETACH DELETE n")
        logger.info(f"Cleared existing graph '{graph_name}'")
    except Exception:
        pass

    # Create indexes
    try:
        graph.query("CREATE INDEX FOR (t:Table) ON (t.name)")
        graph.query("CREATE INDEX FOR (c:Column) ON (c.name)")
        graph.query("CREATE INDEX FOR (d:Database) ON (d.name)")
    except Exception:
        pass

    total_tables = 0
    total_columns = 0
    total_fks = 0

    for db_name in databases:
        logger.info(f"Processing database: {db_name}")
        start = time.time()

        conn = get_mysql_connection(db_name)
        cursor = conn.cursor()

        # Create Database node
        graph.query(
            "MERGE (d:Database {name: $name}) SET d.description = $desc",
            {"name": db_name, "desc": f"MySQL database: {db_name}"}
        )

        # Extract and create table/column nodes
        tables = extract_tables(cursor, db_name)
        logger.info(f"  Found {len(tables)} tables in {db_name}")

        for tbl in tables:
            t_name = tbl["table_name"]
            t_comment = tbl.get("table_comment", "") or ""
            t_rows = tbl.get("table_rows", 0) or 0

            columns = extract_columns(cursor, db_name, t_name)

            # Create Table node
            graph.query(
                """
                MATCH (d:Database {name: $db_name})
                MERGE (t:Table {name: $name, db: $db_name})
                SET t.description = $desc,
                    t.row_count = $rows,
                    t.column_count = $col_count
                MERGE (t)-[:IN_DATABASE]->(d)
                """,
                {
                    "db_name": db_name,
                    "name": t_name,
                    "desc": t_comment if t_comment else t_name,
                    "rows": int(t_rows),
                    "col_count": len(columns),
                }
            )

            # Create Column nodes
            for col in columns:
                c_name = col["column_name"]
                c_type = col["data_type"]
                c_nullable = col["is_nullable"]
                c_key = col["column_key"] or ""
                c_comment = col.get("column_comment", "") or ""
                c_ordinal = col["ordinal_position"]

                key_type = {
                    "PRI": "PRIMARY KEY",
                    "MUL": "INDEX",
                    "UNI": "UNIQUE",
                }.get(c_key, "NONE")

                desc = c_comment if c_comment else f"{c_name} ({c_type})"

                graph.query(
                    """
                    MATCH (t:Table {name: $table_name, db: $db_name})
                    MERGE (c:Column {name: $col_name, table: $table_name, db: $db_name})
                    SET c.type = $type,
                        c.nullable = $nullable,
                        c.key_type = $key_type,
                        c.description = $desc,
                        c.ordinal = $ordinal
                    MERGE (c)-[:BELONGS_TO]->(t)
                    """,
                    {
                        "table_name": t_name,
                        "db_name": db_name,
                        "col_name": c_name,
                        "type": c_type,
                        "nullable": c_nullable,
                        "key_type": key_type,
                        "desc": desc,
                        "ordinal": c_ordinal,
                    }
                )

            total_columns += len(columns)
            total_tables += 1

        # Create FK relationships
        fks = extract_foreign_keys(cursor, db_name)
        for fk in fks:
            try:
                graph.query(
                    """
                    MATCH (src:Column {name: $src_col, table: $src_table, db: $db_name})
                    MATCH (tgt:Column {name: $tgt_col, table: $tgt_table, db: $db_name})
                    MERGE (src)-[:REFERENCES {constraint: $constraint}]->(tgt)
                    """,
                    {
                        "src_col": fk["column_name"],
                        "src_table": fk["table_name"],
                        "tgt_col": fk["referenced_column_name"],
                        "tgt_table": fk["referenced_table_name"],
                        "db_name": db_name,
                        "constraint": fk["constraint_name"],
                    }
                )
                total_fks += 1
            except Exception as e:
                logger.warning(f"  FK creation failed: {fk} - {e}")

        cursor.close()
        conn.close()

        elapsed = time.time() - start
        logger.info(f"  Completed {db_name} in {elapsed:.1f}s")

    # Print summary
    result = graph.query("MATCH (n) RETURN labels(n)[0] as label, count(n) as cnt")
    logger.info(f"Graph '{graph_name}' summary:")
    for row in result.result_set:
        logger.info(f"  {row[0]}: {row[1]}")
    logger.info(f"  Total FK relationships: {total_fks}")

    return {
        "graph_name": graph_name,
        "databases": databases,
        "total_tables": total_tables,
        "total_columns": total_columns,
        "total_fk_relationships": total_fks,
    }


def query_graph_schema(graph_name: str = "qft_schema",
                       falkordb_host: str = "localhost",
                       falkordb_port: int = 6379) -> Dict[str, Any]:
    """Query the graph to get schema overview."""
    fdb = FalkorDB(host=falkordb_host, port=falkordb_port)
    graph = fdb.select_graph(graph_name)

    # Get database list
    dbs = graph.query("MATCH (d:Database) RETURN d.name")
    db_names = [r[0] for r in dbs.result_set]

    # Get table counts per database
    table_counts = graph.query("""
        MATCH (t:Table)-[:IN_DATABASE]->(d:Database)
        RETURN d.name, count(t) as cnt
        ORDER BY d.name
    """)

    # Get tables with most columns
    wide_tables = graph.query("""
        MATCH (t:Table)
        RETURN t.name, t.db, t.column_count
        ORDER BY t.column_count DESC
        LIMIT 10
    """)

    # Get FK relationship count
    fk_count = graph.query("""
        MATCH ()-[r:REFERENCES]->()
        RETURN count(r)
    """)

    return {
        "databases": db_names,
        "table_counts": {r[0]: r[1] for r in table_counts.result_set},
        "widest_tables": [
            {"name": r[0], "db": r[1], "columns": r[2]}
            for r in wide_tables.result_set
        ],
        "fk_relationships": fk_count.result_set[0][0] if fk_count.result_set else 0,
    }


def find_relevant_tables(graph_name: str, question: str,
                         falkordb_host: str = "localhost",
                         falkordb_port: int = 6379) -> List[Dict[str, Any]]:
    """
    Find tables potentially relevant to a question using graph structure.

    Uses keyword matching on table/column names and descriptions,
    plus graph traversal for related tables.
    """
    fdb = FalkorDB(host=falkordb_host, port=falkordb_port)
    graph = fdb.select_graph(graph_name)

    # Extract keywords from question
    keywords = _extract_keywords(question)

    # Search tables by name/description match
    matched_tables = set()
    for kw in keywords:
        kw_lower = kw.lower()
        result = graph.query(
            """
            MATCH (t:Table)
            WHERE toLower(t.name) CONTAINS $kw OR toLower(t.description) CONTAINS $kw
            RETURN t.name, t.db, t.description, t.column_count
            """,
            {"kw": kw_lower}
        )
        for row in result.result_set:
            matched_tables.add((row[0], row[1], row[2], row[3]))

    # Search columns by name/description match
    for kw in keywords:
        kw_lower = kw.lower()
        result = graph.query(
            """
            MATCH (c:Column)-[:BELONGS_TO]->(t:Table)
            WHERE toLower(c.name) CONTAINS $kw OR toLower(c.description) CONTAINS $kw
            RETURN DISTINCT t.name, t.db, t.description, t.column_count
            """,
            {"kw": kw_lower}
        )
        for row in result.result_set:
            matched_tables.add((row[0], row[1], row[2], row[3]))

    # Find related tables via FK relationships
    table_names = [t[0] for t in matched_tables]
    related = set()
    for tname in table_names[:5]:  # Limit traversal
        result = graph.query(
            """
            MATCH (t:Table {name: $name})
            MATCH (t)<-[:BELONGS_TO]-(c1)-[:REFERENCES]-(c2)-[:BELONGS_TO]->(t2:Table)
            RETURN DISTINCT t2.name, t2.db, t2.description, t2.column_count
            """,
            {"name": tname}
        )
        for row in result.result_set:
            related.add((row[0], row[1], row[2], row[3]))

    all_tables = matched_tables | related
    return [
        {"name": t[0], "db": t[1], "description": t[2], "columns": t[3]}
        for t in all_tables
    ]


def get_table_details(graph_name: str, table_name: str, db_name: str = None,
                      falkordb_host: str = "localhost",
                      falkordb_port: int = 6379) -> Dict[str, Any]:
    """Get detailed schema for a specific table from the graph."""
    fdb = FalkorDB(host=falkordb_host, port=falkordb_port)
    graph = fdb.select_graph(graph_name)

    # Build match clause
    if db_name:
        match_clause = "MATCH (t:Table {name: $name, db: $db})"
        params = {"name": table_name, "db": db_name}
    else:
        match_clause = "MATCH (t:Table {name: $name})"
        params = {"name": table_name}

    # Get columns
    cols = graph.query(
        f"""
        {match_clause}
        MATCH (c:Column)-[:BELONGS_TO]->(t)
        RETURN c.name, c.type, c.nullable, c.key_type, c.description
        ORDER BY c.ordinal
        """,
        params
    )

    # Get FK references (outgoing)
    fk_out = graph.query(
        f"""
        {match_clause}
        MATCH (c:Column)-[:BELONGS_TO]->(t)
        MATCH (c)-[r:REFERENCES]->(ref:Column)-[:BELONGS_TO]->(rt:Table)
        RETURN c.name, rt.name, ref.name, r.constraint
        """,
        params
    )

    # Get FK references (incoming)
    fk_in = graph.query(
        f"""
        {match_clause}
        MATCH (c:Column)-[:BELONGS_TO]->(t)
        MATCH (src:Column)-[r:REFERENCES]->(c)
        MATCH (src)-[:BELONGS_TO]->(st:Table)
        RETURN st.name, src.name, c.name, r.constraint
        """,
        params
    )

    return {
        "table_name": table_name,
        "db": db_name,
        "columns": [
            {
                "name": r[0],
                "type": r[1],
                "nullable": r[2],
                "key_type": r[3],
                "description": r[4],
            }
            for r in cols.result_set
        ],
        "foreign_keys_out": [
            {"column": r[0], "references_table": r[1], "references_column": r[2]}
            for r in fk_out.result_set
        ],
        "foreign_keys_in": [
            {"from_table": r[0], "from_column": r[1], "to_column": r[2]}
            for r in fk_in.result_set
        ],
    }


def _extract_keywords(question: str) -> List[str]:
    """Extract search keywords from a Chinese/English question."""
    # Common business terms mapping to likely table/column name patterns
    keyword_map = {
        "房源": ["housing", "room", "house", "parent_room"],
        "房间": ["room"],
        "租客": ["tenant"],
        "合同": ["contract", "treaty"],
        "账单": ["bill", "income", "expend"],
        "租金": ["rent", "income", "money"],
        "收入": ["income"],
        "支出": ["expend", "expense"],
        "财务": ["finance"],
        "门店": ["store"],
        "区域": ["area"],
        "公司": ["company"],
        "欠费": ["debt"],
        "逾期": ["debt", "overdue"],
        "空置": ["room_query_summary", "status"],
        "出租率": ["room_query_summary"],
        "到期": ["end_time", "expire"],
        "签约": ["contract", "treaty"],
        "房东": ["landlord", "owner"],
        "整租": ["whole"],
        "合租": ["joint"],
        "集中": ["focus"],
    }

    keywords = []
    for term, patterns in keyword_map.items():
        if term in question:
            keywords.extend(patterns)

    # Also extract English words and numbers from the question
    import re
    english_words = re.findall(r'[a-zA-Z_]+', question)
    keywords.extend(english_words)

    numbers = re.findall(r'\d+', question)
    keywords.extend(numbers)

    return list(set(keywords))


if __name__ == "__main__":
    logger.info("Starting schema import to FalkorDB...")
    result = build_graph()
    logger.info(f"Import complete: {json.dumps(result, indent=2)}")

    logger.info("\nQuerying graph schema overview...")
    overview = query_graph_schema()
    logger.info(f"Overview: {json.dumps(overview, indent=2, ensure_ascii=False)}")

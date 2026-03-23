"""
Benchmark script for QueryWeaver + FalkorDB Text2SQL approach.

Tests natural language to SQL translation using:
1. FalkorDB graph for schema understanding (table/column discovery)
2. LLM (via OpenRouter) for SQL generation
3. MySQL execution for validation

Follows QueryWeaver's methodology:
- Use graph to find relevant tables
- Build schema context from graph
- Send to LLM for Text2SQL
"""

import os
import sys
import json
import time
import traceback
from typing import Dict, Any, List, Optional

from falkordb import FalkorDB
from dotenv import load_dotenv
from loguru import logger

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from common.llm.client import LLMClient
from common.llm.models import ModelType
from common.database.connection import DatabaseConnection

GRAPH_NAME = "qft_schema"
FALKORDB_HOST = "localhost"
FALKORDB_PORT = 6379

# QueryWeaver-style system prompt (adapted from QueryWeaver's config.py)
SYSTEM_PROMPT = """You are a Text-to-SQL expert working with a multi-database MySQL system for a property management SaaS (全房通).

IMPORTANT DATABASE CONTEXT:
- Three databases: qft_basics (基础数据), qft_lease (租赁数据), qft_finance (财务数据)
- The system supports three parallel business modes:
  - 整租 (whole): tables prefixed with qft_whole_*
  - 合租 (joint): tables prefixed with qft_joint_*
  - 集中式 (focus): tables prefixed with qft_focus_*
- Finance tables are sharded by company_id: qft_finance_{company_id}
- There are almost NO foreign keys defined. Relationships are implicit via matching column names (e.g., company_id, store_id, room_id).
- Common join patterns:
  - company_id links most tables
  - store_id links stores to rooms/tenants
  - *_id columns typically reference the id column of the corresponding table

INSTRUCTIONS:
1. Analyze the provided schema carefully.
2. Generate a valid MySQL SQL query.
3. If the question spans multiple business modes, UNION the results from each mode's tables.
4. Use backticks for table/column names.
5. When a specific database needs to be queried, prefix the table with the database name (e.g., `qft_lease`.`qft_joint_housing`).
6. Return ONLY the SQL query, no explanations.
7. If you cannot determine the exact query, provide your best attempt with comments.
8. For date-based queries, use NOW() for current time.
"""


def get_falkordb_graph():
    """Get FalkorDB graph connection."""
    fdb = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
    return fdb.select_graph(GRAPH_NAME)


def find_relevant_tables_via_graph(question: str, graph) -> List[Dict[str, Any]]:
    """
    Use FalkorDB graph to find tables relevant to the question.
    Combines keyword search + graph traversal.
    """
    from solutions.graph_queryweaver.schema_importer import _extract_keywords

    keywords = _extract_keywords(question)
    if not keywords:
        return []

    matched_tables = {}

    # Search by table name/description
    for kw in keywords:
        kw_lower = kw.lower()
        try:
            result = graph.query(
                """
                MATCH (t:Table)
                WHERE toLower(t.name) CONTAINS $kw OR toLower(t.description) CONTAINS $kw
                RETURN t.name, t.db, t.description, t.column_count
                """,
                {"kw": kw_lower}
            )
            for row in result.result_set:
                key = f"{row[1]}.{row[0]}"
                if key not in matched_tables:
                    matched_tables[key] = {
                        "name": row[0], "db": row[1],
                        "description": row[2], "columns": row[3],
                        "match_type": "table_name"
                    }
        except Exception:
            pass

    # Search by column name/description
    for kw in keywords:
        kw_lower = kw.lower()
        try:
            result = graph.query(
                """
                MATCH (c:Column)-[:BELONGS_TO]->(t:Table)
                WHERE toLower(c.name) CONTAINS $kw OR toLower(c.description) CONTAINS $kw
                RETURN DISTINCT t.name, t.db, t.description, t.column_count
                """,
                {"kw": kw_lower}
            )
            for row in result.result_set:
                key = f"{row[1]}.{row[0]}"
                if key not in matched_tables:
                    matched_tables[key] = {
                        "name": row[0], "db": row[1],
                        "description": row[2], "columns": row[3],
                        "match_type": "column_name"
                    }
        except Exception:
            pass

    # Graph traversal: find FK-connected tables
    table_names = list(set(t["name"] for t in matched_tables.values()))
    for tname in table_names[:10]:
        try:
            result = graph.query(
                """
                MATCH (t:Table {name: $name})
                MATCH (t)<-[:BELONGS_TO]-(c1)-[:REFERENCES]-(c2)-[:BELONGS_TO]->(t2:Table)
                RETURN DISTINCT t2.name, t2.db, t2.description, t2.column_count
                """,
                {"name": tname}
            )
            for row in result.result_set:
                key = f"{row[1]}.{row[0]}"
                if key not in matched_tables:
                    matched_tables[key] = {
                        "name": row[0], "db": row[1],
                        "description": row[2], "columns": row[3],
                        "match_type": "fk_related"
                    }
        except Exception:
            pass

    return list(matched_tables.values())


def get_table_schema_from_graph(table_name: str, db_name: str, graph) -> str:
    """Get formatted table schema from FalkorDB graph."""
    result = graph.query(
        """
        MATCH (c:Column)-[:BELONGS_TO]->(t:Table {name: $name, db: $db})
        RETURN c.name, c.type, c.key_type, c.nullable, c.description
        ORDER BY c.ordinal
        """,
        {"name": table_name, "db": db_name}
    )

    if not result.result_set:
        return ""

    lines = [f"Table: `{db_name}`.`{table_name}`"]
    lines.append("Columns:")
    for row in result.result_set:
        col_str = f"  - `{row[0]}` {row[1]}"
        if row[2] and row[2] != "NONE":
            col_str += f" ({row[2]})"
        if row[4] and row[4] != f"{row[0]} ({row[1]})":
            col_str += f" -- {row[4]}"
        lines.append(col_str)

    # Get FK info
    fk_result = graph.query(
        """
        MATCH (c:Column)-[:BELONGS_TO]->(t:Table {name: $name, db: $db})
        MATCH (c)-[:REFERENCES]->(ref:Column)-[:BELONGS_TO]->(rt:Table)
        RETURN c.name, rt.name, ref.name
        """,
        {"name": table_name, "db": db_name}
    )
    if fk_result.result_set:
        lines.append("Foreign Keys:")
        for row in fk_result.result_set:
            lines.append(f"  - `{row[0]}` -> `{row[1]}`.`{row[2]}`")

    return "\n".join(lines)


def build_schema_context(tables: List[Dict[str, Any]], graph,
                         max_tables: int = 15) -> str:
    """Build schema context string for the LLM from relevant tables."""
    # Prioritize tables by relevance
    sorted_tables = sorted(tables, key=lambda t: (
        0 if t.get("match_type") == "table_name" else
        1 if t.get("match_type") == "column_name" else 2
    ))[:max_tables]

    schemas = []
    for t in sorted_tables:
        schema = get_table_schema_from_graph(t["name"], t["db"], graph)
        if schema:
            schemas.append(schema)

    return "\n\n".join(schemas)


def generate_sql(question: str, schema_context: str,
                 llm_client: LLMClient, model: ModelType) -> str:
    """Use LLM to generate SQL from natural language question."""
    prompt = f"""Database Schema:
{schema_context}

Question: {question}

Generate a MySQL SQL query to answer this question. Return ONLY the SQL, no explanations."""

    response = llm_client.chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=0,
    )

    # Clean up response - extract SQL
    sql = response.strip()
    if sql.startswith("```sql"):
        sql = sql[6:]
    if sql.startswith("```"):
        sql = sql[3:]
    if sql.endswith("```"):
        sql = sql[:-3]
    return sql.strip()


def execute_sql(sql: str, db_conn: DatabaseConnection) -> Dict[str, Any]:
    """Execute SQL and return results.

    When SQL uses fully-qualified table names (db.table), we can use any
    database connection. We prefer 'lease' as default since most queries
    target it. Cross-database queries with full prefixes work from any
    connection on the same MySQL server.
    """
    # Pick a default connection - cross-db queries work with full table prefixes
    # Priority: if only one db is mentioned, use it; otherwise use lease
    mentioned_dbs = []
    if "qft_basics" in sql:
        mentioned_dbs.append("basics")
    if "qft_lease" in sql:
        mentioned_dbs.append("lease")
    if "qft_finance" in sql:
        mentioned_dbs.append("finance")

    db_name = mentioned_dbs[0] if len(mentioned_dbs) == 1 else "lease"

    try:
        import pymysql
        from pymysql.cursors import DictCursor

        db_map = {
            "basics": os.getenv("DB_BASICS", "qft_basics"),
            "lease": os.getenv("DB_LEASE", "qft_lease"),
            "finance": os.getenv("DB_FINANCE", "qft_finance"),
        }
        conn = pymysql.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USERNAME"),
            password=os.getenv("DB_PASSWORD"),
            database=db_map.get(db_name, db_map["lease"]),
            cursorclass=DictCursor,
            connect_timeout=10,
            read_timeout=30,
        )
        cursor = conn.cursor()
        cursor.execute(sql)
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        rows = list(results[:20])
        return {"success": True, "rows": rows, "row_count": len(results)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_benchmark(model_type: ModelType = ModelType.OPUS) -> Dict[str, Any]:
    """Run the full benchmark test suite."""
    # Load test cases
    test_file = os.path.join(PROJECT_ROOT, "benchmarks/test_cases/chatbi_questions.json")
    with open(test_file) as f:
        test_cases = json.load(f)

    # Initialize connections
    graph = get_falkordb_graph()
    llm_client = LLMClient()
    db_conn = DatabaseConnection()

    results = {
        "solution": "G1: QueryWeaver + FalkorDB",
        "model": model_type.display_name,
        "model_id": model_type.model_name,
        "graph_name": GRAPH_NAME,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "test_results": [],
        "summary": {},
    }

    total = len(test_cases)
    success_count = 0
    sql_generated_count = 0
    total_time = 0

    for tc in test_cases:
        qid = tc["id"]
        question = tc["question"]
        category = tc["category"]
        difficulty = tc["difficulty"]
        expected_tables = tc.get("expected_tables", [])

        logger.info(f"[{qid}] Testing: {question}")
        test_result = {
            "id": qid,
            "question": question,
            "category": category,
            "difficulty": difficulty,
            "expected_tables": expected_tables,
        }

        start_time = time.time()

        try:
            # Step 1: Find relevant tables via graph
            relevant_tables = find_relevant_tables_via_graph(question, graph)
            found_table_names = [t["name"] for t in relevant_tables]
            test_result["found_tables"] = found_table_names
            test_result["found_table_count"] = len(found_table_names)

            # Check if expected tables were found
            expected_found = [t for t in expected_tables if t in found_table_names]
            test_result["expected_tables_found"] = expected_found
            test_result["table_recall"] = (
                len(expected_found) / len(expected_tables) if expected_tables else 1.0
            )

            # Step 2: Build schema context
            schema_context = build_schema_context(relevant_tables, graph)
            test_result["schema_context_length"] = len(schema_context)

            # Step 3: Generate SQL
            sql = generate_sql(question, schema_context, llm_client, model_type)
            test_result["generated_sql"] = sql
            sql_generated_count += 1

            # Step 4: Execute SQL
            exec_result = execute_sql(sql, db_conn)
            test_result["execution"] = {
                "success": exec_result["success"],
                "row_count": exec_result.get("row_count", 0),
                "error": exec_result.get("error"),
            }

            if exec_result["success"]:
                success_count += 1
                test_result["status"] = "success"
                # Include sample results (limit to avoid huge output)
                sample = exec_result.get("rows", [])[:5]
                # Convert non-serializable values
                clean_sample = []
                for row in sample:
                    clean_row = {}
                    for k, v in row.items():
                        if hasattr(v, 'isoformat'):
                            clean_row[k] = v.isoformat()
                        elif isinstance(v, bytes):
                            clean_row[k] = v.decode('utf-8', errors='replace')
                        else:
                            clean_row[k] = v
                    clean_sample.append(clean_row)
                test_result["sample_results"] = clean_sample
            else:
                test_result["status"] = "execution_error"

        except Exception as e:
            test_result["status"] = "error"
            test_result["error"] = str(e)
            test_result["traceback"] = traceback.format_exc()
            logger.error(f"[{qid}] Error: {e}")

        elapsed = time.time() - start_time
        test_result["elapsed_seconds"] = round(elapsed, 2)
        total_time += elapsed

        logger.info(f"[{qid}] Status: {test_result.get('status')} | Time: {elapsed:.1f}s")
        results["test_results"].append(test_result)

    # Summary
    avg_table_recall = sum(
        r.get("table_recall", 0) for r in results["test_results"]
    ) / total if total else 0

    results["summary"] = {
        "total_questions": total,
        "sql_generated": sql_generated_count,
        "execution_success": success_count,
        "execution_success_rate": round(success_count / total * 100, 1) if total else 0,
        "avg_table_recall": round(avg_table_recall * 100, 1),
        "total_time_seconds": round(total_time, 1),
        "avg_time_per_question": round(total_time / total, 1) if total else 0,
    }

    # Save results
    output_dir = os.path.join(PROJECT_ROOT, "benchmarks/results")
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "g1_queryweaver_results.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"\nBenchmark Results Summary:")
    logger.info(f"  Total: {total} questions")
    logger.info(f"  SQL Generated: {sql_generated_count}")
    logger.info(f"  Execution Success: {success_count} ({results['summary']['execution_success_rate']}%)")
    logger.info(f"  Avg Table Recall: {results['summary']['avg_table_recall']}%")
    logger.info(f"  Total Time: {total_time:.1f}s")
    logger.info(f"  Results saved to: {output_file}")

    db_conn.close_all()
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run QueryWeaver + FalkorDB benchmark")
    parser.add_argument("--model", choices=["opus", "gpt5"], default="opus",
                        help="Model to use for SQL generation")
    args = parser.parse_args()

    model = ModelType.OPUS if args.model == "opus" else ModelType.GPT5
    run_benchmark(model_type=model)

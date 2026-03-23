"""Text-to-SQL pipeline using Neo4j Schema Graph.

Complete pipeline:
1. Graph query to find relevant tables + JOIN paths
2. Construct LLM prompt with schema context
3. Generate SQL via LLM
4. Execute SQL on MySQL
"""

import re
import sys
import time
from pathlib import Path

from neo4j import GraphDatabase
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from common.database import get_db_connection
from common.llm import LLMClient, ModelType
from solutions.graph_schema_neo4j.graph_query import (
    find_relevant_tables,
    format_schema_context,
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
)

SYSTEM_PROMPT = """你是全房通租赁管理系统的 SQL 专家。系统有三个 MySQL 数据库：
- qft_basics: 基础数据（公司、门店、员工、区域）
- qft_lease: 租赁数据（房源、房间、租客、合同、账单）
- qft_finance: 财务数据（财务流水、收支明细）

重要业务规则：
1. 三种业务模式：整租(whole)、合租(joint)、集中式(focus)，相关表有对应前缀
2. 财务表按 company_id 分片，如 qft_finance_859 对应公司859的数据
3. 日期筛选用 MySQL 函数如 NOW(), DATE_SUB(), CURDATE()
4. 金额字段通常为 rent_money, debt_money, total_money 等
5. 状态字段：空置一般对应 status 或 room_status 字段特定值

请根据以下表结构和 JOIN 条件，生成准确的 SQL 查询。

规则：
- 只返回一条 SQL 语句
- 不要使用子查询如果 JOIN 可以实现
- 使用 LEFT JOIN 而非 INNER JOIN 除非确定关联一定存在
- 金额汇总用 SUM() 并考虑 NULL 处理
- 用 LIMIT 限制结果（默认100）
- 如果需要跨多张表统计同类数据（如三种模式的房源），使用 UNION ALL
- SQL 语句结尾不要加分号
- 将 SQL 放在 ```sql 代码块中返回

{schema_context}
"""


def extract_sql(llm_response: str) -> str:
    """Extract SQL from LLM response."""
    # Try to extract from code block
    match = re.search(r"```sql\s*(.*?)\s*```", llm_response, re.DOTALL)
    if match:
        sql = match.group(1).strip()
    else:
        # Try plain code block
        match = re.search(r"```\s*(SELECT.*?)\s*```", llm_response, re.DOTALL | re.IGNORECASE)
        if match:
            sql = match.group(1).strip()
        else:
            # Last resort: find SELECT statement
            match = re.search(r"(SELECT\s+.+)", llm_response, re.DOTALL | re.IGNORECASE)
            sql = match.group(1).strip() if match else llm_response.strip()

    # Remove trailing semicolons
    sql = sql.rstrip(";").strip()
    return sql


def determine_database(tables: list[dict]) -> str:
    """Determine which MySQL database to query based on the tables involved."""
    dbs = set()
    for t in tables:
        db = t.get("database_name", "")
        if db:
            dbs.add(db)

    # If finance tables involved, use finance
    # If only basics, use basics
    # Default to lease (most queries are about leasing)
    if "finance" in dbs and len(dbs) == 1:
        return "finance"
    if "basics" in dbs and len(dbs) == 1:
        return "basics"
    # For cross-db queries, default to lease (most tables are there)
    return "lease"


class TextToSQLPipeline:
    """Text-to-SQL pipeline using Neo4j Schema Graph for context."""

    def __init__(self):
        self.neo4j_driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        self.llm_client = LLMClient()
        self.db_conn = get_db_connection()

    def close(self):
        """Close connections."""
        self.neo4j_driver.close()

    def run(
        self,
        question: str,
        model: ModelType = ModelType.GPT5,
        execute: bool = True,
    ) -> dict:
        """Run the full text-to-SQL pipeline.

        Args:
            question: Natural language question in Chinese
            model: LLM model to use
            execute: Whether to execute the generated SQL

        Returns:
            dict with pipeline results
        """
        result = {
            "question": question,
            "model": model.value,
            "relevant_tables_found": [],
            "generated_sql": "",
            "sql_executable": False,
            "execution_result": None,
            "latency_ms": 0,
            "tokens_used": 0,
            "graph_traversal_ms": 0,
            "success": False,
            "error": None,
        }

        total_start = time.time()

        try:
            # Step 1: Graph query
            graph_start = time.time()
            query_result = find_relevant_tables(question, self.neo4j_driver)
            result["graph_traversal_ms"] = round((time.time() - graph_start) * 1000)
            result["relevant_tables_found"] = [t["name"] for t in query_result["tables"]]

            if not query_result["tables"]:
                result["error"] = "No relevant tables found"
                return result

            # Step 2: Format schema context
            schema_context = format_schema_context(query_result)

            # Step 3: Construct prompt and call LLM
            system_prompt = SYSTEM_PROMPT.format(schema_context=schema_context)

            logger.info(f"Calling {model.display_name} for SQL generation...")
            llm_response = self.llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                model=model,
                temperature=0.0,
                max_tokens=2048,
            )

            # Step 4: Extract SQL
            sql = extract_sql(llm_response)
            result["generated_sql"] = sql
            logger.info(f"Generated SQL: {sql[:200]}...")

            # Step 5: Execute SQL
            if execute and sql:
                target_db = determine_database(query_result["tables"])

                # Check if SQL references a finance shard table (e.g., qft_finance_859)
                finance_match = re.search(r"qft_finance_(\d+)", sql)
                if finance_match:
                    target_db = "finance"

                logger.info(f"Executing on database: {target_db}")
                try:
                    # Add SELECT hint for max execution time (120s)
                    exec_sql = sql
                    if exec_sql.strip().upper().startswith("SELECT") and "MAX_EXECUTION_TIME" not in exec_sql.upper():
                        exec_sql = exec_sql.replace("SELECT", "SELECT /*+ MAX_EXECUTION_TIME(120000) */", 1)
                    rows = self.db_conn.execute_query(target_db, exec_sql)
                    result["sql_executable"] = True

                    # Format results
                    if rows:
                        # Limit display
                        display_rows = rows[:20]
                        result["execution_result"] = [
                            [str(cell) for cell in row]
                            for row in display_rows
                        ]
                        if len(rows) > 20:
                            result["execution_result"].append(
                                [f"... ({len(rows)} total rows)"]
                            )
                    else:
                        result["execution_result"] = []

                    result["success"] = True
                    logger.info(f"Query returned {len(rows)} rows")

                except Exception as e:
                    result["sql_executable"] = False
                    result["error"] = f"SQL execution error: {str(e)}"
                    logger.error(f"SQL execution failed: {e}")
            else:
                result["success"] = bool(sql)

        except Exception as e:
            result["error"] = str(e)
            logger.error(f"Pipeline error: {e}")

        result["latency_ms"] = round((time.time() - total_start) * 1000)
        return result


if __name__ == "__main__":
    pipeline = TextToSQLPipeline()

    test_questions = [
        "公司ID为859的公司一共有多少套房源？",
        "目前有多少空置的房间？",
        "本月应收租金总额是多少？",
    ]

    try:
        for q in test_questions:
            logger.info(f"\n{'='*60}")
            logger.info(f"Question: {q}")
            result = pipeline.run(q, model=ModelType.GPT5)
            logger.info(f"Tables: {result['relevant_tables_found']}")
            logger.info(f"SQL: {result['generated_sql']}")
            logger.info(f"Executable: {result['sql_executable']}")
            logger.info(f"Success: {result['success']}")
            if result['error']:
                logger.error(f"Error: {result['error']}")
            if result['execution_result']:
                logger.info(f"Result preview: {result['execution_result'][:3]}")
            logger.info(f"Latency: {result['latency_ms']}ms (graph: {result['graph_traversal_ms']}ms)")
    finally:
        pipeline.close()

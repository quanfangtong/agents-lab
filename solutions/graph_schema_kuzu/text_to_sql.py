"""Text-to-SQL pipeline using Graph-enhanced schema context.

Pipeline:
1. graph_query.py retrieves relevant tables and JOIN paths
2. Constructs a system prompt with concise schema context
3. Calls LLM to generate SQL
4. Executes SQL on MySQL
5. Returns results
"""

import re
import sys
import time
from pathlib import Path
from typing import Optional

from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from common.database import get_db_connection
from common.llm import LLMClient, ModelType
from solutions.graph_schema_kuzu.graph_query import GraphSchemaQuery, format_schema_context

SYSTEM_PROMPT_TEMPLATE = """你是全房通公寓管理系统的 SQL 专家。根据用户问题和提供的数据库 schema 信息生成正确的 MySQL SQL 查询。

## 业务背景
全房通是一个公寓租赁管理系统，有三种业务模式：
- 整租 (whole)：整套房源出租，表名含 whole
- 合租 (joint)：单间出租，表名含 joint
- 集中式 (focus)：集中式公寓，表名含 focus

核心实体：公司(company) > 门店(store) > 房源(housing) > 房间(room) > 租客(tenants)

## 数据库
- qft_basics: 基础数据（公司、门店、员工、区域等）
- qft_lease: 租赁数据（房源、房间、租客、合同、账单等）
- qft_finance: 财务数据（财务流水、收支明细等）

{schema_context}

## 规则
1. 只使用上面列出的表和列，不要猜测不存在的表或列
2. 使用 MySQL 语法
3. 如果问题涉及多种业务模式，需要 UNION 或分别查询
4. 日期比较使用 MySQL 函数如 CURDATE(), DATE_SUB() 等
5. 注意区分不同数据库的表，跨库查询需要加库名前缀
6. 只返回 SQL 语句，不需要解释

请只输出一条 SQL 查询语句，用 ```sql ... ``` 包裹。"""


def extract_sql(response: str) -> str:
    """Extract SQL from LLM response (inside ```sql ... ```)."""
    pattern = r"```sql\s*(.*?)\s*```"
    match = re.search(pattern, response, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: try to find SELECT/WITH statement
    for line in response.split("\n"):
        stripped = line.strip()
        if stripped.upper().startswith(("SELECT", "WITH")):
            # Collect until semicolon or end
            return response[response.index(stripped):].split(";")[0].strip()
    return response.strip()


class TextToSQL:
    """Graph-enhanced Text-to-SQL pipeline."""

    def __init__(self):
        self.graph_query = GraphSchemaQuery()
        self.llm = LLMClient()
        self.db_conn = get_db_connection()

    def generate_sql(
        self,
        question: str,
        model: ModelType = ModelType.GPT5,
        max_tables: int = 10,
    ) -> dict:
        """Generate SQL for a natural language question.

        Returns:
            {
                "question": str,
                "sql": str,
                "schema_context": dict,
                "model": str,
                "tokens_used": int,  # estimated
                "generation_time_ms": int,
            }
        """
        # Step 1: Get schema context from graph
        start = time.time()
        ctx = self.graph_query.get_schema_context(question, max_tables=max_tables)
        schema_text = format_schema_context(ctx)
        graph_time = time.time() - start

        # Step 2: Build prompt
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema_context=schema_text)

        # Step 3: Call LLM (with timeout)
        start = time.time()
        response = self.llm.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            model=model,
            temperature=0.0,
            max_tokens=2048,
            timeout=60,
        )
        llm_time = time.time() - start

        # Step 4: Extract SQL
        sql = extract_sql(response)

        total_time = int((graph_time + llm_time) * 1000)
        logger.info(
            f"Generated SQL in {total_time}ms "
            f"(graph: {int(graph_time*1000)}ms, LLM: {int(llm_time*1000)}ms)"
        )

        return {
            "question": question,
            "sql": sql,
            "raw_response": response,
            "schema_tables": [t["name"] for t in ctx["tables"]],
            "model": model.display_name,
            "graph_time_ms": int(graph_time * 1000),
            "llm_time_ms": int(llm_time * 1000),
            "total_time_ms": total_time,
        }

    def execute_sql(self, sql: str, db_name: str = "lease", timeout: int = 30) -> dict:
        """Execute SQL on MySQL and return results.

        Args:
            sql: SQL query to execute
            db_name: Target database
            timeout: Query timeout in seconds

        Returns:
            {"success": bool, "data": list, "columns": list, "error": str|None, "row_count": int}
        """
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
        from sqlalchemy import text, create_engine

        def _run_query():
            # Create a dedicated engine with read_timeout
            conn_str = (
                f"mysql+pymysql://{self.db_conn.username}:{self.db_conn.password}"
                f"@{self.db_conn.host}:{self.db_conn.port}/{self.db_conn.databases[db_name]}"
                f"?read_timeout={timeout}&write_timeout={timeout}"
            )
            engine = create_engine(conn_str, pool_pre_ping=True)
            try:
                with engine.connect() as conn:
                    conn.execute(text(f"SET SESSION MAX_EXECUTION_TIME = {timeout * 1000}"))
                    result = conn.execute(text(sql))
                    columns = list(result.keys()) if result.returns_rows else []
                    data = [list(row) for row in result.fetchall()] if result.returns_rows else []
                return columns, data
            finally:
                engine.dispose()

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_query)
                columns, data = future.result(timeout=timeout + 5)

            return {
                "success": True,
                "data": data[:100],
                "columns": columns,
                "row_count": len(data),
                "error": None,
            }
        except FuturesTimeout:
            logger.error(f"SQL execution timed out after {timeout}s")
            return {
                "success": False,
                "data": [],
                "columns": [],
                "row_count": 0,
                "error": f"Query timed out after {timeout}s",
            }
        except Exception as e:
            logger.error(f"SQL execution failed: {e}")
            return {
                "success": False,
                "data": [],
                "columns": [],
                "row_count": 0,
                "error": str(e),
            }

    def detect_database(self, sql: str) -> str:
        """Detect which database to use based on table names in SQL."""
        sql_lower = sql.lower()
        if "qft_finance" in sql_lower:
            return "finance"
        if "qft_company" in sql_lower or "qft_store" in sql_lower or "qft_employee" in sql_lower or "qft_area" in sql_lower:
            return "basics"
        return "lease"

    def run(
        self,
        question: str,
        model: ModelType = ModelType.GPT5,
    ) -> dict:
        """Full pipeline: question -> SQL -> execute -> results.

        Returns:
            {
                "question": str,
                "sql": str,
                "model": str,
                "execution_result": dict,
                "total_time_ms": int,
                "success": bool,
            }
        """
        start = time.time()

        # Generate SQL
        gen_result = self.generate_sql(question, model=model)
        sql = gen_result["sql"]

        # Detect target database
        db_name = self.detect_database(sql)
        logger.info(f"Detected database: {db_name}")

        # Execute
        exec_result = self.execute_sql(sql, db_name=db_name)

        total_time = int((time.time() - start) * 1000)

        return {
            "question": question,
            "sql": sql,
            "model": gen_result["model"],
            "schema_tables": gen_result["schema_tables"],
            "execution_result": exec_result,
            "graph_time_ms": gen_result["graph_time_ms"],
            "llm_time_ms": gen_result["llm_time_ms"],
            "total_time_ms": total_time,
            "success": exec_result["success"],
        }


if __name__ == "__main__":
    pipeline = TextToSQL()

    test_questions = [
        "公司ID为859的公司一共有多少套房源？",
        "目前有多少空置的房间？",
    ]

    for q in test_questions:
        logger.info(f"\n{'='*60}")
        logger.info(f"Question: {q}")
        result = pipeline.run(q, model=ModelType.GPT5)
        logger.info(f"SQL: {result['sql']}")
        logger.info(f"Success: {result['success']}")
        logger.info(f"Total time: {result['total_time_ms']}ms")
        if result["success"]:
            logger.info(f"Rows: {result['execution_result']['row_count']}")
            if result["execution_result"]["data"]:
                logger.info(f"Sample: {result['execution_result']['data'][:3]}")
        else:
            logger.error(f"Error: {result['execution_result']['error']}")

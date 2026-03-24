"""方案 A: Baseline Text-to-SQL — 全量 DDL 直接喂 LLM"""

from .common import Solution, get_datamart_connection, get_all_ddl


class BaselineSolution(Solution):
    name = "A_Baseline"

    def __init__(self):
        self._all_ddl: str = ""

    def setup(self):
        conn = get_datamart_connection()
        self._all_ddl = get_all_ddl(conn)
        conn.close()

    def get_schema_context(self, question: str, intent: dict = None) -> tuple[str, list[str]]:
        conn = get_datamart_connection()
        from .common import get_all_tables
        tables = get_all_tables(conn)
        conn.close()
        return self._all_ddl, tables

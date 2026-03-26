"""方案 A: Text2SQL -- 轻量 schema（表名+注释+列名列表）直接喂 LLM"""

import json
from .common import Solution, UNIFIED_SCHEMA_PATH


class Text2SQLSolution(Solution):
    name = "A_Text2SQL"

    def __init__(self):
        self._schema_text: str = ""
        self._table_names: list[str] = []

    def setup(self):
        """加载统一 schema，构造轻量文本（表名+注释+列名，不含完整 DDL）"""
        with open(UNIFIED_SCHEMA_PATH) as f:
            schema = json.load(f)

        parts = []
        for t in schema["tables"]:
            cols_str = ", ".join(
                f"{c['name']}({c['type']}, {c['comment']})" if c["comment"]
                else f"{c['name']}({c['type']})"
                for c in t["columns"]
            )
            parts.append(f"-- {t['name']}: {t['comment']}\n-- 列: {cols_str}")

        self._schema_text = "\n\n".join(parts)
        self._table_names = [t["name"] for t in schema["tables"]]

    def get_schema_context(self, question: str, intent: dict = None) -> tuple[str, list[str]]:
        return self._schema_text, self._table_names

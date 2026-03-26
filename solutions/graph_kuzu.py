"""方案 B: Kuzu 嵌入式 Schema Graph -- LLM 意图分析 + 图遍历"""

import kuzu
from pathlib import Path
from .common import GraphSolution

KUZU_DB_PATH = str(Path(__file__).resolve().parents[1] / "data" / "kuzu_datamart_graph")


class KuzuSolution(GraphSolution):
    name = "B_Kuzu"

    def __init__(self):
        super().__init__()
        self._db: kuzu.Database | None = None
        self._conn: kuzu.Connection | None = None

    def setup(self):
        self._db = kuzu.Database(KUZU_DB_PATH)
        self._conn = kuzu.Connection(self._db)
        result = self._conn.execute("MATCH (t:TableNode) RETURN t.name")
        while result.has_next():
            self._all_tables.add(result.get_next()[0])

    # ---------- 图谱操作（Kuzu 特有）----------

    def _search(self, keywords: list[str]) -> set[str]:
        matched: set[str] = set()
        for kw in keywords:
            result = self._conn.execute(
                "MATCH (t:TableNode) WHERE t.name CONTAINS $s RETURN t.name",
                {"s": kw},
            )
            while result.has_next():
                matched.add(result.get_next()[0])
        return matched

    def _expand(self, tables: set[str]) -> set[str]:
        expanded = set(tables)
        for tbl in tables:
            for query in [
                "MATCH (a:TableNode {name: $n})-[:REFERENCES]->(b:TableNode) RETURN b.name",
                "MATCH (a:TableNode)-[:REFERENCES]->(b:TableNode {name: $n}) RETURN a.name",
            ]:
                result = self._conn.execute(query, {"n": tbl})
                while result.has_next():
                    expanded.add(result.get_next()[0])
        return expanded

    def _get_joins(self, table_list: list[str]) -> list[str]:
        joins: list[str] = []
        seen: set[str] = set()
        for tbl in table_list:
            result = self._conn.execute(
                "MATCH (a:TableNode {name: $n})-[r:REFERENCES]->(b:TableNode) "
                "WHERE b.name IN $targets RETURN a.name, r.column_name, r.comment, b.name",
                {"n": tbl, "targets": table_list},
            )
            while result.has_next():
                row = result.get_next()
                key = f"{row[0]}.{row[1]}->{row[3]}"
                if key not in seen:
                    seen.add(key)
                    comment = f"  -- {row[2]}" if row[2] else ""
                    joins.append(f"{row[0]}.{row[1]} = {row[3]}.id{comment}")
        return joins

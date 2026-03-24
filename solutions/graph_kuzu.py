"""方案 B: Kuzu 嵌入式 Schema Graph — LLM 意图分析 + 图遍历"""

import kuzu
from pathlib import Path
from .common import Solution, get_datamart_connection, get_tables_ddl

KUZU_DB_PATH = str(Path(__file__).resolve().parents[1] / "data" / "kuzu_datamart_graph")


class KuzuSolution(Solution):
    name = "B_Kuzu"
    is_graph_solution = True

    def __init__(self):
        self._db = None
        self._conn = None

    def setup(self):
        self._db = kuzu.Database(KUZU_DB_PATH)
        self._conn = kuzu.Connection(self._db)

    def _search_by_keywords(self, keywords: list[str]) -> set[str]:
        """用 LLM 提取的 search_keywords 在图谱中搜索表"""
        matched = set()
        for kw in keywords:
            result = self._conn.execute(
                "MATCH (t:TableNode) WHERE t.name CONTAINS $s RETURN t.name",
                {"s": kw}
            )
            while result.has_next():
                matched.add(result.get_next()[0])
        return matched

    def _expand(self, tables: set[str], hops: int = 1) -> set[str]:
        """沿 REFERENCES 边扩展"""
        expanded = set(tables)
        current = set(tables)
        for _ in range(hops):
            next_hop = set()
            for tbl in current:
                # 出边 + 入边
                for query in [
                    "MATCH (a:TableNode {name: $n})-[:REFERENCES]->(b:TableNode) RETURN b.name",
                    "MATCH (a:TableNode)-[:REFERENCES]->(b:TableNode {name: $n}) RETURN a.name",
                ]:
                    result = self._conn.execute(query, {"n": tbl})
                    while result.has_next():
                        next_hop.add(result.get_next()[0])
            expanded.update(next_hop)
            current = next_hop - tables
        return expanded

    def _get_joins(self, table_list: list[str]) -> list[str]:
        """获取表间 JOIN 路径"""
        joins = []
        seen = set()
        for tbl in table_list:
            result = self._conn.execute(
                "MATCH (a:TableNode {name: $n})-[r:REFERENCES]->(b:TableNode) "
                "WHERE b.name IN $targets RETURN a.name, r.column_name, r.comment, b.name",
                {"n": tbl, "targets": table_list}
            )
            while result.has_next():
                row = result.get_next()
                key = f"{row[0]}.{row[1]}->{row[3]}"
                if key not in seen:
                    seen.add(key)
                    comment = f"  -- {row[2]}" if row[2] else ""
                    joins.append(f"{row[0]}.{row[1]} = {row[3]}.id{comment}")
        return joins

    def get_schema_context(self, question: str, intent: dict = None) -> tuple[str, list[str]]:
        """用 intent 中的 search_keywords 驱动图谱搜索"""
        keywords = (intent or {}).get("search_keywords", [])
        if not keywords:
            # fallback: 用问题中可能的英文关键词
            keywords = ["housing", "tenants", "room"]

        # 搜索 + 扩展
        direct = self._search_by_keywords(keywords)
        expanded = self._expand(direct, hops=1)

        # 宁多勿少，最多 20 张
        table_list = sorted(expanded)[:20]

        conn = get_datamart_connection()
        ddl = get_tables_ddl(conn, table_list)
        conn.close()
        return ddl, table_list

    def get_graph_context(self, question: str, intent: dict) -> dict:
        """返回图谱的结构化分析"""
        keywords = intent.get("search_keywords", [])
        direct = self._search_by_keywords(keywords)
        expanded = self._expand(direct, hops=1)
        table_list = sorted(expanded)[:20]

        joins = self._get_joins(table_list)

        return {
            "recommended_tables": "\n".join(f"- {t}" for t in table_list),
            "join_paths": "\n".join(f"- {j}" for j in joins) if joins else "未发现直接关系，请根据 _id 字段推断",
        }

"""方案 C: Neo4j Schema Graph -- LLM 意图分析 + Neo4j 图遍历"""

from neo4j import GraphDatabase
from .common import GraphSolution, get_datamart_connection, get_all_tables, infer_targets

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "chatbi2024")


class Neo4jSolution(GraphSolution):
    name = "C_Neo4j"

    def __init__(self):
        super().__init__()
        self._driver = None

    def setup(self):
        self._driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with self._driver.session() as s:
            count = s.run("MATCH (t:TableNode) RETURN count(t) AS c").single()["c"]
            if count == 0:
                self._import_schema()
            for r in s.run("MATCH (t:TableNode) RETURN t.name"):
                self._all_tables.add(r["t.name"])

    def _import_schema(self):
        """从 MySQL 读取元数据并导入 Neo4j（仅在图谱为空时触发）"""
        conn = get_datamart_connection()
        tables = get_all_tables(conn)
        with self._driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
            for tbl in tables:
                s.run("CREATE (t:TableNode {name: $name})", {"name": tbl})
            cur = conn.cursor()
            for tbl in tables:
                cur.execute(f"""
                    SELECT COLUMN_NAME, COLUMN_COMMENT FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA='qft_datamart' AND TABLE_NAME='{tbl}'
                    AND COLUMN_NAME LIKE '%%_id' AND COLUMN_NAME != 'id'
                    AND COLUMN_NAME NOT IN ('company_id','creater_id','updater_id','deleter_id')
                """)
                for col_name, comment in cur.fetchall():
                    for target in infer_targets(tbl, col_name, tables):
                        s.run(
                            "MATCH (a:TableNode {name:$s}),(b:TableNode {name:$t}) "
                            "CREATE (a)-[:REFERENCES {column_name:$c, comment:$cm}]->(b)",
                            {"s": tbl, "t": target, "c": col_name, "cm": comment or ""},
                        )
        conn.close()

    # ---------- 图谱操作（Neo4j 特有）----------

    def _search(self, keywords: list[str]) -> set[str]:
        matched: set[str] = set()
        with self._driver.session() as s:
            for kw in keywords:
                for r in s.run("MATCH (t:TableNode) WHERE t.name CONTAINS $s RETURN t.name", {"s": kw}):
                    matched.add(r["t.name"])
        return matched

    def _expand(self, tables: set[str]) -> set[str]:
        expanded = set(tables)
        with self._driver.session() as s:
            for tbl in tables:
                for r in s.run(
                    "MATCH (a:TableNode {name:$n})-[:REFERENCES]-(b:TableNode) RETURN DISTINCT b.name",
                    {"n": tbl},
                ):
                    expanded.add(r["b.name"])
        return expanded

    def _get_joins(self, table_list: list[str]) -> list[str]:
        joins: list[str] = []
        seen: set[str] = set()
        with self._driver.session() as s:
            for tbl in table_list:
                for r in s.run(
                    "MATCH (a:TableNode {name:$n})-[r:REFERENCES]->(b:TableNode) "
                    "WHERE b.name IN $t RETURN a.name, r.column_name, r.comment, b.name",
                    {"n": tbl, "t": table_list},
                ):
                    key = f"{r['a.name']}.{r['r.column_name']}->{r['b.name']}"
                    if key not in seen:
                        seen.add(key)
                        cm = f"  -- {r['r.comment']}" if r["r.comment"] else ""
                        joins.append(f"{r['a.name']}.{r['r.column_name']} = {r['b.name']}.id{cm}")
        return joins

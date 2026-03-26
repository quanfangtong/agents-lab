"""方案 D: FalkorDB Schema Graph -- LLM 意图分析 + FalkorDB 图遍历"""

from falkordb import FalkorDB
from .common import GraphSolution, get_datamart_connection, get_all_tables, infer_targets

FALKORDB_HOST = "localhost"
FALKORDB_PORT = 6379
GRAPH_NAME = "qft_schema"


class FalkorDBSolution(GraphSolution):
    name = "D_FalkorDB"

    def __init__(self):
        super().__init__()
        self._db = None
        self._graph = None

    def setup(self):
        self._db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
        self._graph = self._db.select_graph(GRAPH_NAME)
        try:
            result = self._graph.query("MATCH (t:TableNode) RETURN count(t) AS c")
            if result.result_set and result.result_set[0][0] == 0:
                self._import_schema()
        except Exception:
            self._import_schema()
        result = self._graph.query("MATCH (t:TableNode) RETURN t.name")
        for row in result.result_set:
            self._all_tables.add(row[0])

    def _import_schema(self):
        """从 MySQL 读取元数据并导入 FalkorDB（仅在图谱为空时触发）"""
        conn = get_datamart_connection()
        tables = get_all_tables(conn)
        for tbl in tables:
            self._graph.query("CREATE (:TableNode {name: $name})", {"name": tbl})
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
                    try:
                        self._graph.query(
                            "MATCH (a:TableNode {name:$s}),(b:TableNode {name:$t}) "
                            "CREATE (a)-[:REFERENCES {column_name:$c, comment:$cm}]->(b)",
                            {"s": tbl, "t": target, "c": col_name, "cm": comment or ""},
                        )
                    except Exception:
                        pass
        conn.close()

    # ---------- 图谱操作（FalkorDB 特有）----------

    def _search(self, keywords: list[str]) -> set[str]:
        matched: set[str] = set()
        for kw in keywords:
            try:
                result = self._graph.query(
                    "MATCH (t:TableNode) WHERE t.name CONTAINS $s RETURN t.name", {"s": kw},
                )
                for row in result.result_set:
                    matched.add(row[0])
            except Exception:
                pass
        return matched

    def _expand(self, tables: set[str]) -> set[str]:
        expanded = set(tables)
        for tbl in tables:
            try:
                result = self._graph.query(
                    "MATCH (a:TableNode {name:$n})-[:REFERENCES]-(b:TableNode) RETURN DISTINCT b.name",
                    {"n": tbl},
                )
                for row in result.result_set:
                    expanded.add(row[0])
            except Exception:
                pass
        return expanded

    def _get_joins(self, table_list: list[str]) -> list[str]:
        joins: list[str] = []
        seen: set[str] = set()
        for tbl in table_list:
            try:
                result = self._graph.query(
                    "MATCH (a:TableNode {name:$n})-[r:REFERENCES]->(b:TableNode) "
                    "WHERE b.name IN $t RETURN a.name, r.column_name, r.comment, b.name",
                    {"n": tbl, "t": table_list},
                )
                for row in result.result_set:
                    key = f"{row[0]}.{row[1]}->{row[3]}"
                    if key not in seen:
                        seen.add(key)
                        cm = f"  -- {row[2]}" if row[2] else ""
                        joins.append(f"{row[0]}.{row[1]} = {row[3]}.id{cm}")
            except Exception:
                pass
        return joins

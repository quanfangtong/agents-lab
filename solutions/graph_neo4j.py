"""方案 C: Neo4j Schema Graph — LLM 意图分析 + Neo4j 图遍历"""

from neo4j import GraphDatabase
from .common import Solution, get_datamart_connection, get_tables_ddl, get_all_tables

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "chatbi2024")


class Neo4jSolution(Solution):
    name = "C_Neo4j"
    is_graph_solution = True

    def __init__(self):
        self._driver = None

    def setup(self):
        self._driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with self._driver.session() as s:
            count = s.run("MATCH (t:TableNode) RETURN count(t) AS c").single()["c"]
            if count > 0:
                return
        self._import_schema()

    def _import_schema(self):
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
                    targets = self._infer_targets(tbl, col_name, tables)
                    for target in targets:
                        s.run(
                            "MATCH (a:TableNode {name:$s}),(b:TableNode {name:$t}) "
                            "CREATE (a)-[:REFERENCES {column_name:$c, comment:$cm}]->(b)",
                            {"s": tbl, "t": target, "c": col_name, "cm": comment or ""})
        conn.close()

    def _infer_targets(self, src, col, tables):
        if col == "store_id": return ["qft_store"] if "qft_store" in tables else []
        if col == "area_id": return ["qft_area"] if "qft_area" in tables else []
        if col == "butler_id": return ["qft_butler"] if "qft_butler" in tables else []
        if col == "device_id": return ["qft_smart_device"] if "qft_smart_device" in tables else []
        if col in ("housing_id","room_id","tenants_id","tenant_id"):
            prefix = next((p for p in ("whole","joint","focus") if p in src), "")
            stem = col.replace("_id","").rstrip("s")
            return [t for t in tables if (prefix and prefix in t and stem in t) or (not prefix and stem in t) if t != src][:3]
        stem = col.replace("_id","")
        return [t for t in tables if stem in t and t != src][:2]

    def _search(self, keywords):
        matched = set()
        with self._driver.session() as s:
            for kw in keywords:
                for r in s.run("MATCH (t:TableNode) WHERE t.name CONTAINS $s RETURN t.name", {"s": kw}):
                    matched.add(r["t.name"])
        return matched

    def _expand(self, tables):
        expanded = set(tables)
        with self._driver.session() as s:
            for tbl in tables:
                for r in s.run("MATCH (a:TableNode {name:$n})-[:REFERENCES]-(b:TableNode) RETURN DISTINCT b.name", {"n": tbl}):
                    expanded.add(r["b.name"])
        return expanded

    def _get_joins(self, table_list):
        joins, seen = [], set()
        with self._driver.session() as s:
            for tbl in table_list:
                for r in s.run(
                    "MATCH (a:TableNode {name:$n})-[r:REFERENCES]->(b:TableNode) WHERE b.name IN $t RETURN a.name, r.column_name, r.comment, b.name",
                    {"n": tbl, "t": table_list}):
                    key = f"{r['a.name']}.{r['r.column_name']}->{r['b.name']}"
                    if key not in seen:
                        seen.add(key)
                        cm = f"  -- {r['r.comment']}" if r["r.comment"] else ""
                        joins.append(f"{r['a.name']}.{r['r.column_name']} = {r['b.name']}.id{cm}")
        return joins

    def get_schema_context(self, question, intent=None):
        keywords = (intent or {}).get("search_keywords", ["housing","tenants","room"])
        table_list = sorted(self._expand(self._search(keywords)))[:20]
        conn = get_datamart_connection()
        ddl = get_tables_ddl(conn, table_list)
        conn.close()
        return ddl, table_list

    def get_graph_context(self, question, intent):
        keywords = intent.get("search_keywords", [])
        table_list = sorted(self._expand(self._search(keywords)))[:20]
        joins = self._get_joins(table_list)
        return {
            "recommended_tables": "\n".join(f"- {t}" for t in table_list),
            "join_paths": "\n".join(f"- {j}" for j in joins) if joins else "请根据 _id 字段推断",
        }

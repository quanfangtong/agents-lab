#!/usr/bin/env python3
"""
统一 Schema 构建器：
1. 从 Docker MySQL 读取 77 张表的元数据
2. 用统一规则推断关系
3. 输出 unified_schema.json
4. 导入到 Kuzu / Neo4j / FalkorDB（确保三者完全一致）
"""

import json
import sys
import shutil
import argparse
from pathlib import Path

import pymysql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DATAMART_CONFIG = {
    "host": "127.0.0.1", "port": 3307, "user": "root",
    "password": "chatbi2024", "database": "qft_datamart",
    "charset": "utf8mb4",
}

UNIFIED_SCHEMA_PATH = PROJECT_ROOT / "data" / "unified_schema.json"

# 跳过的 _id 列（太普遍或非业务关系）
SKIP_COLUMNS = {"company_id", "creater_id", "updater_id", "deleter_id"}


def get_connection():
    return pymysql.connect(**DATAMART_CONFIG)


def extract_schema() -> dict:
    """从 MySQL 提取完整 schema 元数据"""
    conn = get_connection()
    cur = conn.cursor()

    # 获取所有表
    cur.execute("""
        SELECT TABLE_NAME, TABLE_COMMENT
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = 'qft_datamart' AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
    """)
    tables_raw = cur.fetchall()

    tables = []
    for tbl_name, tbl_comment in tables_raw:
        # 获取列
        cur.execute(f"""
            SELECT COLUMN_NAME, DATA_TYPE, COLUMN_KEY, IS_NULLABLE, COLUMN_COMMENT
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = 'qft_datamart' AND TABLE_NAME = '{tbl_name}'
            ORDER BY ORDINAL_POSITION
        """)
        columns = []
        for col_name, dtype, col_key, nullable, comment in cur.fetchall():
            columns.append({
                "name": col_name,
                "type": dtype,
                "is_pk": col_key == "PRI",
                "nullable": nullable == "YES",
                "comment": comment or "",
            })

        tables.append({
            "name": tbl_name,
            "comment": tbl_comment or "",
            "column_count": len(columns),
            "columns": columns,
        })

    conn.close()
    return tables


def infer_targets(src_table: str, col_name: str, all_table_names: set) -> list:
    """统一的关系推断规则（Kuzu/Neo4j/FalkorDB 共用）"""
    if col_name in SKIP_COLUMNS:
        return []

    if not col_name.endswith("_id") or col_name == "id":
        return []

    # 精确映射
    exact_map = {
        "store_id": ["qft_store"],
        "area_id": ["qft_area"],
        "butler_id": ["qft_butler"],
        "device_id": ["qft_smart_device"],
    }
    if col_name in exact_map:
        return [t for t in exact_map[col_name] if t in all_table_names]

    # 按业务模式前缀推断
    if col_name in ("housing_id", "room_id", "tenants_id", "tenant_id"):
        prefix = next((p for p in ("whole", "joint", "focus") if p in src_table), "")
        stem = col_name.replace("_id", "").rstrip("s")  # tenants_id → tenant
        targets = []
        for t in all_table_names:
            if prefix and prefix in t and stem in t:
                targets.append(t)
            elif not prefix and stem in t:
                targets.append(t)
        return [t for t in targets if t != src_table][:3]

    # 通用推断：xxx_id → 包含 xxx 的表
    stem = col_name.replace("_id", "")
    targets = [t for t in all_table_names if stem in t and t != src_table]
    return targets[:2]


def build_relationships(tables: list) -> list:
    """基于统一规则推断所有关系"""
    all_names = {t["name"] for t in tables}
    relationships = []
    seen = set()

    for table in tables:
        for col in table["columns"]:
            targets = infer_targets(table["name"], col["name"], all_names)
            for target in targets:
                key = f"{table['name']}.{col['name']}->{target}"
                if key not in seen:
                    seen.add(key)
                    relationships.append({
                        "from": table["name"],
                        "column": col["name"],
                        "comment": col["comment"],
                        "to": target,
                    })

    return relationships


def build_unified_schema():
    """构建统一 schema 并保存"""
    print("Extracting schema from MySQL...")
    tables = extract_schema()
    print(f"  Tables: {len(tables)}")

    print("Inferring relationships...")
    relationships = build_relationships(tables)
    print(f"  Relationships: {len(relationships)}")

    schema = {
        "tables": tables,
        "relationships": relationships,
        "stats": {
            "table_count": len(tables),
            "total_columns": sum(t["column_count"] for t in tables),
            "relationship_count": len(relationships),
        },
    }

    UNIFIED_SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(UNIFIED_SCHEMA_PATH, "w") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)

    print(f"Saved to {UNIFIED_SCHEMA_PATH}")
    print(f"Stats: {schema['stats']}")
    return schema


def import_kuzu(schema: dict):
    """导入到 Kuzu"""
    import kuzu

    db_path = str(PROJECT_ROOT / "data" / "kuzu_datamart_graph")
    if Path(db_path).exists():
        shutil.rmtree(db_path) if Path(db_path).is_dir() else Path(db_path).unlink()

    db = kuzu.Database(db_path)
    conn = kuzu.Connection(db)

    # 创建 schema
    conn.execute("CREATE NODE TABLE TableNode(name STRING, comment STRING, column_count INT64, PRIMARY KEY(name))")
    conn.execute("CREATE NODE TABLE ColumnNode(full_name STRING, table_name STRING, column_name STRING, column_type STRING, comment STRING, is_primary_key BOOLEAN, is_nullable BOOLEAN, PRIMARY KEY(full_name))")
    conn.execute("CREATE REL TABLE HAS_COLUMN(FROM TableNode TO ColumnNode)")
    conn.execute("CREATE REL TABLE REFERENCES(FROM TableNode TO TableNode, column_name STRING, comment STRING)")

    # 插入节点
    for t in schema["tables"]:
        conn.execute("CREATE (n:TableNode {name: $n, comment: $c, column_count: $cc})",
                     {"n": t["name"], "c": t["comment"], "cc": t["column_count"]})
        for col in t["columns"]:
            fn = f"{t['name']}.{col['name']}"
            conn.execute("CREATE (c:ColumnNode {full_name: $fn, table_name: $tn, column_name: $cn, column_type: $ct, comment: $cm, is_primary_key: $pk, is_nullable: $nl})",
                         {"fn": fn, "tn": t["name"], "cn": col["name"], "ct": col["type"], "cm": col["comment"], "pk": col["is_pk"], "nl": col["nullable"]})
            conn.execute("MATCH (t:TableNode {name: $tn}), (c:ColumnNode {full_name: $fn}) CREATE (t)-[:HAS_COLUMN]->(c)",
                         {"tn": t["name"], "fn": fn})

    # 插入关系
    for r in schema["relationships"]:
        conn.execute("MATCH (a:TableNode {name: $f}), (b:TableNode {name: $t}) CREATE (a)-[:REFERENCES {column_name: $c, comment: $cm}]->(b)",
                     {"f": r["from"], "t": r["to"], "c": r["column"], "cm": r["comment"]})

    # 验证
    result = conn.execute("MATCH (t:TableNode) RETURN count(t)")
    nodes = result.get_next()[0]
    result = conn.execute("MATCH ()-[r:REFERENCES]->() RETURN count(r)")
    edges = result.get_next()[0]
    print(f"Kuzu: {nodes} nodes, {edges} edges")


def import_neo4j(schema: dict):
    """导入到 Neo4j"""
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "chatbi2024"))

    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        for t in schema["tables"]:
            s.run("CREATE (:TableNode {name: $n, comment: $c, column_count: $cc})",
                  {"n": t["name"], "c": t["comment"], "cc": t["column_count"]})
        for r in schema["relationships"]:
            s.run("MATCH (a:TableNode {name: $f}), (b:TableNode {name: $t}) CREATE (a)-[:REFERENCES {column_name: $c, comment: $cm}]->(b)",
                  {"f": r["from"], "t": r["to"], "c": r["column"], "cm": r["comment"]})

        # 验证
        nodes = s.run("MATCH (t:TableNode) RETURN count(t) AS c").single()["c"]
        edges = s.run("MATCH ()-[r:REFERENCES]->() RETURN count(r) AS c").single()["c"]
        print(f"Neo4j: {nodes} nodes, {edges} edges")

    driver.close()


def import_falkordb(schema: dict):
    """导入到 FalkorDB"""
    from falkordb import FalkorDB
    db = FalkorDB(host="localhost", port=6379)
    graph = db.select_graph("qft_schema")

    # 清空
    try:
        graph.query("MATCH (n) DETACH DELETE n")
    except Exception:
        pass

    for t in schema["tables"]:
        graph.query("CREATE (:TableNode {name: $n, comment: $c, column_count: $cc})",
                    {"n": t["name"], "c": t["comment"], "cc": t["column_count"]})
    for r in schema["relationships"]:
        try:
            graph.query("MATCH (a:TableNode {name: $f}), (b:TableNode {name: $t}) CREATE (a)-[:REFERENCES {column_name: $c, comment: $cm}]->(b)",
                        {"f": r["from"], "t": r["to"], "c": r["column"], "cm": r["comment"]})
        except Exception:
            pass

    # 验证
    result = graph.query("MATCH (t:TableNode) RETURN count(t) AS c")
    nodes = result.result_set[0][0]
    result = graph.query("MATCH ()-[r:REFERENCES]->() RETURN count(r) AS c")
    edges = result.result_set[0][0]
    print(f"FalkorDB: {nodes} nodes, {edges} edges")


def verify_consistency():
    """验证三个图数据库的一致性"""
    import kuzu
    from neo4j import GraphDatabase
    from falkordb import FalkorDB

    # Kuzu
    db = kuzu.Database(str(PROJECT_ROOT / "data" / "kuzu_datamart_graph"))
    conn = kuzu.Connection(db)
    k_nodes = conn.execute("MATCH (t:TableNode) RETURN count(t)").get_next()[0]
    k_edges = conn.execute("MATCH ()-[r:REFERENCES]->() RETURN count(r)").get_next()[0]

    # Neo4j
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "chatbi2024"))
    with driver.session() as s:
        n_nodes = s.run("MATCH (t:TableNode) RETURN count(t) AS c").single()["c"]
        n_edges = s.run("MATCH ()-[r:REFERENCES]->() RETURN count(r) AS c").single()["c"]
    driver.close()

    # FalkorDB
    fdb = FalkorDB(host="localhost", port=6379)
    graph = fdb.select_graph("qft_schema")
    f_nodes = graph.query("MATCH (t:TableNode) RETURN count(t) AS c").result_set[0][0]
    f_edges = graph.query("MATCH ()-[r:REFERENCES]->() RETURN count(r) AS c").result_set[0][0]

    print(f"\nConsistency Check:")
    print(f"  Kuzu:     {k_nodes} nodes, {k_edges} edges")
    print(f"  Neo4j:    {n_nodes} nodes, {n_edges} edges")
    print(f"  FalkorDB: {f_nodes} nodes, {f_edges} edges")

    if k_nodes == n_nodes == f_nodes and k_edges == n_edges == f_edges:
        print("  ✓ ALL CONSISTENT")
    else:
        print("  ✗ INCONSISTENT!")
        return False
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true", help="Build unified schema JSON")
    parser.add_argument("--import-all", action="store_true", help="Import to all graph DBs")
    parser.add_argument("--import-db", choices=["kuzu", "neo4j", "falkordb"], help="Import to specific DB")
    parser.add_argument("--verify", action="store_true", help="Verify consistency")
    args = parser.parse_args()

    if not any([args.build, args.import_all, args.import_db, args.verify]):
        args.build = True
        args.import_all = True
        args.verify = True

    schema = None
    if args.build or args.import_all or args.import_db:
        schema = build_unified_schema()

    if args.import_all:
        print("\nImporting to Kuzu...")
        import_kuzu(schema)
        print("Importing to Neo4j...")
        import_neo4j(schema)
        print("Importing to FalkorDB...")
        import_falkordb(schema)
    elif args.import_db:
        if not schema:
            with open(UNIFIED_SCHEMA_PATH) as f:
                schema = json.load(f)
        {"kuzu": import_kuzu, "neo4j": import_neo4j, "falkordb": import_falkordb}[args.import_db](schema)

    if args.verify:
        verify_consistency()

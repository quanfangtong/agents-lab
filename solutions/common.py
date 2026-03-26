"""公共模块：数据集市连接、多步 Pipeline、Prompt 模板、图谱方案基类"""

import time
import json
import threading
import pymysql
from pathlib import Path
from abc import ABC, abstractmethod
from dotenv import load_dotenv

load_dotenv()

UNIFIED_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "data" / "unified_schema.json"

DATAMART_CONFIG = {
    "host": "127.0.0.1",
    "port": 3307,
    "user": "root",
    "password": "chatbi2024",
    "database": "qft_datamart",
    "charset": "utf8mb4",
    "connect_timeout": 10,
    "read_timeout": 30,
}

COMPANY_ID = 1001

BUSINESS_MODES = ["whole", "joint", "focus"]


# ========== Step 1: 意图分析 Prompt ==========
INTENT_PROMPT = """你是全房通房屋租赁管理系统的查询意图分析器。

## 你的任务
分析用户问题，提取结构化查询意图。你不需要生成 SQL，只需要理解用户想查什么。

## 业务背景
全房通管理三种业务模式的房源：
- 整租(whole)：整套出租，表名含 whole
- 合租(joint)：按房间出租，表名含 joint
- 集中式(focus)：集中管理公寓，表名含 focus

核心业务域和对应表名关键词：
- 房源: housing (whole_housing / joint_housing / focus_housing)
- 房间: room (whole_room / joint_room / focus_room)
- 租客: tenants (whole_tenants / joint_tenants / focus_tenants)
- 合同: contract, electronics_contract, paper_contract
- 账单-应收: income (joint_tenants_income / focus_tenants_income)
- 账单-应支: expend, bill_expend (whole_bill_expend / joint_bill_expend / focus_bill_expend)
- 财务流水: finance, finance_item
- 门店: store
- 小区/物业: area_property
- 智能设备: smart_device, house_device, smart_lock, smart_electricity_meter, smart_water_meter
- 装修: renovation, rm_renovation_record
- 退房: tenants_check_out
- 同住人: tenants_cohabit
- 维修: room_repair
- 管家: butler

## 输出格式（严格 JSON，不要加其他文字）
{
  "entities": [
    {"text": "原文片段", "type": "实体类型", "normalized": "标准化标识"}
  ],
  "query_goal": "查询目标: count/list/sum/compare/rank/rate/detail",
  "business_mode": ["涉及的业务模式: whole/joint/focus，空数组表示全部或不区分"],
  "time_range": "时间范围描述或null",
  "search_keywords": ["用于在图数据库中搜索表的关键词，必须是表名中会出现的英文词根"]
}

## search_keywords 提取规则（最重要）
这些关键词将直接用于在图数据库中做 CONTAINS 搜索。
- 用表名中的英文词根：housing, room, tenants, contract, income, expend, finance, store, device, lock, renovation, repair 等
- 如果明确了业务模式，加前缀：whole_housing, joint_room, focus_tenants 等
- 如果涉及关联查询，包含所有相关实体的词根
- 宁多勿少，多给几个不会错，少给会漏表

## 实体类型
store(门店), housing(房源), room(房间), tenants(租客), contract(合同),
bill(账单), finance(财务), device(设备), renovation(装修), location(小区/地址),
condition(查询条件), metric(指标), time(时间), person(人名)"""


# ========== Step 3: SQL 生成 Prompt ==========
BASELINE_SQL_PROMPT = """你是全房通房屋租赁管理系统的 SQL 专家。

当前公司 company_id = {company_id}。所有查询必须加 WHERE company_id = {company_id}。
软删除字段 is_delete (0=正常, 1=已删除)，查询时加 IFNULL(is_delete,0) = 0。
所有表在同一个数据库中，不需要库名前缀。
只返回纯 SQL，不要解释。SQL 以分号结尾。

以下是数据库全部表结构：
{schema_context}"""

GRAPH_SQL_PROMPT = """你是全房通房屋租赁管理系统的 SQL 专家。

## 公司上下文
当前公司 company_id = {company_id}。所有查询必须加 WHERE company_id = {company_id}。
软删除字段 is_delete (0=正常, 1=已删除)，查询时加 IFNULL(is_delete,0) = 0。
所有表在同一个数据库中，不需要库名前缀。

## 查询意图分析（由 AI 预先分析）
{intent_analysis}

## 图谱定位的表和关系（由知识图谱精准定位）

### 推荐表
{recommended_tables}

### 表间 JOIN 路径（由图谱提供，请严格按此关联）
{join_paths}

## 表结构（仅包含图谱推荐的表）
{schema_context}

## 生成要求
- 只使用上面列出的表，不要猜测其他表名
- JOIN 条件严格按照图谱提供的路径
- 必须加 company_id = {company_id} 和 is_delete = 0 条件
- 只返回纯 SQL，不要解释。SQL 以分号结尾。"""

# ========== Step 4: 纠错 Prompt ==========
CORRECTION_PROMPT = """上一次生成的 SQL 执行失败了。请根据错误信息修正。

## 原始问题
{question}

## 上次生成的 SQL
{failed_sql}

## 错误信息
{error}

## 表结构（供参考）
{schema_context}

## 修正要求
- 分析错误原因
- 修正 SQL
- 确保 company_id = {company_id} 和 is_delete = 0
- 只返回修正后的纯 SQL，不要解释。"""


# ========== 工具函数 ==========

def get_datamart_connection() -> pymysql.Connection:
    return pymysql.connect(**DATAMART_CONFIG)

def get_table_ddl(conn: pymysql.Connection, table_name: str) -> str:
    with conn.cursor() as cur:
        cur.execute(f"SHOW CREATE TABLE `{table_name}`")
        row = cur.fetchone()
        return row[1] if row else ""

def get_all_tables(conn: pymysql.Connection) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SHOW TABLES")
        return [row[0] for row in cur.fetchall()]

def get_all_ddl(conn: pymysql.Connection) -> str:
    tables = get_all_tables(conn)
    ddls = []
    for t in tables:
        ddl = get_table_ddl(conn, t)
        ddls.append(f"-- {t}\n{ddl};")
    return "\n\n".join(ddls)

def get_tables_ddl(conn: pymysql.Connection, table_names: list[str]) -> str:
    ddls = []
    for t in table_names:
        try:
            ddl = get_table_ddl(conn, t)
            ddls.append(f"-- {t}\n{ddl};")
        except Exception:
            pass
    return "\n\n".join(ddls)


# 轻量 schema 缓存
_unified_schema_cache = None

def get_lightweight_schema(table_names: list[str]) -> str:
    """构造轻量 schema 文本（与 Text2SQL 格式一致：表名+注释+列名列表）"""
    global _unified_schema_cache
    if _unified_schema_cache is None:
        with open(UNIFIED_SCHEMA_PATH) as f:
            _unified_schema_cache = {t["name"]: t for t in json.load(f)["tables"]}

    parts = []
    for name in table_names:
        t = _unified_schema_cache.get(name)
        if not t:
            continue
        cols_str = ", ".join(
            f"{c['name']}({c['type']}, {c['comment']})" if c['comment']
            else f"{c['name']}({c['type']})"
            for c in t["columns"]
        )
        parts.append(f"-- {t['name']}: {t['comment']}\n-- 列: {cols_str}")
    return "\n\n".join(parts)

def execute_sql(conn: pymysql.Connection, sql: str) -> dict:
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            for row in rows:
                for k, v in row.items():
                    if hasattr(v, 'isoformat'):
                        row[k] = v.isoformat()
                    elif isinstance(v, bytes):
                        row[k] = v.decode('utf-8', errors='replace')
                    elif not isinstance(v, (str, int, float, bool, type(None))):
                        row[k] = str(v)
            return {"success": True, "rows": rows[:20], "row_count": len(rows), "error": None}
    except Exception as e:
        return {"success": False, "rows": [], "row_count": 0, "error": str(e)[:500]}

def clean_sql(raw: str) -> str:
    if not raw:
        return "SELECT 1; -- ERROR: LLM returned empty response"
    sql = raw.strip()
    if sql.startswith("```"):
        lines = sql.split("\n")
        sql = "\n".join(lines[1:])
    if sql.endswith("```"):
        sql = sql.rsplit("```", 1)[0]
    sql = sql.strip()
    if not sql.endswith(";"):
        sql += ";"
    return sql

def parse_intent_json(raw: str) -> dict:
    """从 LLM 输出中提取 JSON"""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
    if raw.endswith("```"):
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 尝试找 JSON 块
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
    return {"entities": [], "query_goal": "unknown", "business_mode": [], "search_keywords": []}


# ========== Solution 基类 ==========

class Solution(ABC):
    name: str = "base"
    is_graph_solution: bool = False

    @abstractmethod
    def setup(self):
        pass

    @abstractmethod
    def get_schema_context(self, question: str, intent: dict = None) -> tuple[str, list[str]]:
        """返回 (schema_text, table_list)"""
        pass

    def get_graph_context(self, question: str, intent: dict) -> dict:
        """图谱方案重写：返回结构化的图谱分析结果"""
        return {}

    def run(self, question: str, llm_client, model) -> dict:
        """完整的多步 Pipeline"""
        result = {
            "solution": self.name,
            "question": question,
            "model": model.display_name,
        }

        t_start = time.time()
        conn = get_datamart_connection()

        try:
            # ===== Step 1: 意图分析（图谱方案才需要）=====
            intent = {}
            if self.is_graph_solution:
                t1 = time.time()
                raw_intent = llm_client.chat_completion(
                    messages=[
                        {"role": "system", "content": INTENT_PROMPT},
                        {"role": "user", "content": question},
                    ],
                    model=model,
                    temperature=0.0,
                    max_tokens=2000,
                    timeout=300,
                )
                intent = parse_intent_json(raw_intent)
                result["step1_intent"] = intent
                result["step1_ms"] = int((time.time() - t1) * 1000)
                result["step1_raw"] = raw_intent[:500]

            # ===== Step 2: Schema 获取（线程安全）=====
            t2 = time.time()
            _lock = getattr(self, '_lock', None)
            if _lock:
                with _lock:
                    schema_ctx, tables = self.get_schema_context(question, intent)
            else:
                schema_ctx, tables = self.get_schema_context(question, intent)
            result["step2_ms"] = int((time.time() - t2) * 1000)
            result["schema_tables"] = tables
            result["schema_token_estimate"] = len(schema_ctx) // 4

            # ===== Step 3: SQL 生成 =====
            t3 = time.time()
            if self.is_graph_solution:
                if _lock:
                    with _lock:
                        graph_ctx = self.get_graph_context(question, intent)
                else:
                    graph_ctx = self.get_graph_context(question, intent)
                prompt = GRAPH_SQL_PROMPT.format(
                    company_id=COMPANY_ID,
                    intent_analysis=json.dumps(intent, ensure_ascii=False, indent=2),
                    recommended_tables=graph_ctx.get("recommended_tables", "\n".join(f"- {t}" for t in tables)),
                    join_paths=graph_ctx.get("join_paths", "请根据字段名推断"),
                    schema_context=schema_ctx,
                )
            else:
                prompt = BASELINE_SQL_PROMPT.format(
                    company_id=COMPANY_ID,
                    schema_context=schema_ctx,
                )

            raw_sql = llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": question},
                ],
                model=model,
                temperature=0.0,
                max_tokens=8000,
                timeout=300,
            )
            sql = clean_sql(raw_sql)
            result["step3_ms"] = int((time.time() - t3) * 1000)
            result["generated_sql"] = sql

            # ===== Step 4: 执行（无自纠错）=====
            t4 = time.time()
            max_retries = 1
            for attempt in range(max_retries):
                exec_result = execute_sql(conn, sql)

                if exec_result["success"]:
                    result["sql_executable"] = True
                    result["execution_result"] = exec_result["rows"]
                    result["row_count"] = exec_result["row_count"]
                    result["error"] = None
                    result["success"] = True
                    result["attempts"] = attempt + 1
                    break
                else:
                    if attempt < max_retries - 1:
                        # 纠错
                        correction = llm_client.chat_completion(
                            messages=[
                                {"role": "system", "content": CORRECTION_PROMPT.format(
                                    question=question,
                                    failed_sql=sql,
                                    error=exec_result["error"],
                                    schema_context=schema_ctx,
                                    company_id=COMPANY_ID,
                                )},
                                {"role": "user", "content": "请修正 SQL。"},
                            ],
                            model=model,
                            temperature=0.0,
                            max_tokens=8000,
                            timeout=300,
                        )
                        sql = clean_sql(correction)
                        result["generated_sql"] = sql  # 更新为最新的
                    else:
                        result["sql_executable"] = False
                        result["execution_result"] = []
                        result["row_count"] = 0
                        result["error"] = exec_result["error"]
                        result["success"] = False
                        result["attempts"] = attempt + 1

            result["step4_ms"] = int((time.time() - t4) * 1000)

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)[:500]

        finally:
            result["total_ms"] = int((time.time() - t_start) * 1000)
            conn.close()

        return result


# ========== 关系推断（Neo4j/FalkorDB _import_schema 共用）==========

def infer_targets(src_table: str, col_name: str, all_tables: list[str]) -> list[str]:
    """根据 _id 列名推断目标表（仅用于运行时 schema 导入）"""
    EXACT_MAP = {
        "store_id": ["qft_store"],
        "area_id": ["qft_area"],
        "butler_id": ["qft_butler"],
        "device_id": ["qft_smart_device"],
    }
    if col_name in EXACT_MAP:
        return [t for t in EXACT_MAP[col_name] if t in all_tables]

    if col_name in ("housing_id", "room_id", "tenants_id", "tenant_id"):
        prefix = next((p for p in BUSINESS_MODES if p in src_table), "")
        stem = col_name.replace("_id", "").rstrip("s")
        return [
            t for t in all_tables
            if ((prefix and prefix in t and stem in t) or (not prefix and stem in t))
            and t != src_table
        ][:3]

    stem = col_name.replace("_id", "")
    return [t for t in all_tables if stem in t and t != src_table][:2]


# ========== 图谱方案基类 ==========

class GraphSolution(Solution):
    """Kuzu / Neo4j / FalkorDB 的公共基类，封装表选择、模式补全、schema/graph 上下文构建。"""

    is_graph_solution = True

    def __init__(self):
        self._lock = threading.Lock()
        self._all_tables: set[str] = set()
        self._cached_tables: list[str] | None = None

    # ---------- 子类必须实现 ----------

    @abstractmethod
    def _search(self, keywords: list[str]) -> set[str]:
        """用关键词在图谱中 CONTAINS 搜索表名"""

    @abstractmethod
    def _expand(self, tables: set[str]) -> set[str]:
        """沿 REFERENCES 边扩展一跳"""

    @abstractmethod
    def _get_joins(self, table_list: list[str]) -> list[str]:
        """获取表间 JOIN 路径文本"""

    # ---------- 公共逻辑 ----------

    def _complete_business_modes(self, tables: set[str]) -> set[str]:
        """业务模式补全：找到 focus_housing 就自动补上 whole_housing、joint_housing"""
        completed: set[str] = set()
        for t in tables:
            for mode in BUSINESS_MODES:
                if f"_{mode}_" in t:
                    for other in BUSINESS_MODES:
                        if other != mode:
                            variant = t.replace(f"_{mode}_", f"_{other}_")
                            if variant in self._all_tables:
                                completed.add(variant)
                    break
        return completed

    def _select_tables(self, keywords: list[str]) -> list[str]:
        """优先级表选择：直接匹配 + 模式补全全保留，扩展按需补充"""
        direct = self._search(keywords)
        mode_tables = self._complete_business_modes(direct)
        core = direct | mode_tables

        if len(core) < 15:
            extra = self._expand(direct) - core
        else:
            extra = set()

        return sorted(core) + sorted(extra)

    def get_schema_context(self, question: str, intent: dict = None) -> tuple[str, list[str]]:
        """用 intent 中的 search_keywords 驱动图谱搜索"""
        keywords = (intent or {}).get("search_keywords", ["housing", "tenants", "room"])
        table_list = self._select_tables(keywords)
        self._cached_tables = table_list
        return get_lightweight_schema(table_list), table_list

    def get_graph_context(self, question: str, intent: dict) -> dict:
        """返回图谱的结构化分析（复用 get_schema_context 的表列表）"""
        table_list = self._cached_tables
        if table_list is None:
            table_list = self._select_tables(intent.get("search_keywords", []))
        joins = self._get_joins(table_list)
        return {
            "recommended_tables": "\n".join(f"- {t}" for t in table_list),
            "join_paths": "\n".join(f"- {j}" for j in joins) if joins else "请根据 _id 字段推断",
        }

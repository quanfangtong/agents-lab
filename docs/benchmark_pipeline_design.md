# ChatBI Benchmark Pipeline 设计：查询链路架构

> 版本：v1.0 | 日期：2026-03-24
> 基于 Phase 1 实验结论（GPT-5.4 成功率 41.7%）和 77 张核心表的数据集市

---

## 一、核心设计原则

**让 AI 做 AI 擅长的事，让图数据库做图数据库擅长的事。**

| 能力 | AI（LLM）擅长 | 图数据库擅长 |
|------|--------------|-------------|
| 语义理解 | 理解"欠费"="debt_money > 0" | -- |
| 实体识别 | "张三"是租客名，"城东门店"是门店 | -- |
| 结构搜索 | -- | 从关键词定位到具体表名 |
| 路径发现 | -- | 找到 A→B→C 的 JOIN 路径 |
| SQL 生成 | 根据 DDL + 约束写 SQL | -- |
| 关系遍历 | -- | 沿 REFERENCES 边扩展关联表 |

Phase 1 失败的核心原因不是 LLM 能力不足，而是：
1. 意图分析用硬编码关键词匹配，无法处理同义词和模糊表述
2. 图谱搜索和 LLM 调用割裂，没有形成有效的信息流
3. 缺少 company_id 等业务约束的强制注入

---

## 二、方案全景对比

```
方案 A: Baseline          用户问题 ──────────────────────────> LLM(全量DDL) ──> SQL
                          1 次 LLM 调用 | ~20K tokens 上下文

方案 B: Kuzu 图谱增强     用户问题 ──> LLM(意图) ──> 图搜索 ──> LLM(精简DDL) ──> SQL
                          2 次 LLM 调用 | ~3K tokens 上下文

方案 C: Neo4j 图谱增强    同方案 B，图引擎换为 Neo4j
                          2 次 LLM 调用 | ~3K tokens 上下文

方案 D: FalkorDB 图谱增强 同方案 B，图引擎换为 FalkorDB
                          2 次 LLM 调用 | ~3K tokens 上下文

方案 E: 静态规则          用户问题 ──> 关键词匹配 ──> LLM(匹配到的DDL) ──> SQL
                          1 次 LLM 调用 | ~3K tokens 上下文
```

### 推荐链路：方案 B/C/D（图谱增强，两阶段 LLM）

这是本文档重点设计的链路。三个图谱方案共享同一套链路设计，仅图引擎实现不同。

---

## 三、图谱增强查询链路：完整流程

```
                           ┌─────────────────────┐
                           │   用户自然语言问题    │
                           └──────────┬──────────┘
                                      │
                              ┌───────▼────────┐
                    Step 0    │   问题预分类     │  ← 规则（非 LLM）
                              │  闲聊 / 数据查询  │
                              └───┬────────┬───┘
                           闲聊  │        │ 数据查询
                        (直接回复) │        │
                                  │  ┌─────▼──────────────┐
                        Step 1    │  │  LLM 意图分析       │  ← 第 1 次 LLM 调用
                                  │  │  提取实体+查询目标   │     轻量模型 / 低 budget
                                  │  └─────┬──────────────┘
                                  │        │ 结构化 JSON
                                  │  ┌─────▼──────────────┐
                        Step 2    │  │  图谱搜索+路径发现   │  ← 图数据库（零 LLM）
                                  │  │  表定位+JOIN路径     │
                                  │  └─────┬──────────────┘
                                  │        │ 推荐表+路径+关键列
                                  │  ┌─────▼──────────────┐
                        Step 3    │  │  LLM SQL 生成       │  ← 第 2 次 LLM 调用
                                  │  │  精简DDL+图谱约束    │     强模型 / 高 budget
                                  │  └─────┬──────────────┘
                                  │        │ SQL
                                  │  ┌─────▼──────────────┐
                        Step 4    │  │  SQL 执行+验证       │  ← MySQL
                                  │  │  失败则 LLM 纠错    │     可选第 3 次调用
                                  │  └─────┬──────────────┘
                                  │        │
                              ┌───▼────────▼───┐
                              │   返回结果       │
                              └────────────────┘
```

---

## 四、每个步骤的详细设计

### Step 0: 问题预分类（规则，非 LLM）

**目的**：过滤闲聊，避免无谓的 LLM + 图谱开销。

**实现**：简单规则匹配，不用 LLM。

```python
# 数据查询信号词（命中任一即进入查询链路）
QUERY_SIGNALS = [
    "多少", "几个", "几套", "几间", "哪些", "哪个", "有没有",
    "统计", "汇总", "合计", "总共", "一共", "分别",
    "排名", "最多", "最少", "最高", "最低", "最贵", "最便宜",
    "欠费", "空置", "出租率", "到期", "逾期",
    "收入", "支出", "利润", "流水", "账单",
    "租客", "房源", "房间", "门店", "合同",
]

def is_data_query(question: str) -> bool:
    return any(signal in question for signal in QUERY_SIGNALS)
```

**设计决策**：
- 这里故意用规则而非 LLM，因为分类本身非常简单（数据查询 vs 闲聊的边界清晰），不值得消耗一次 LLM 调用
- 如果误判（把数据查询当闲聊），用户会重新问；如果误判反向（把闲聊当查询），后续步骤的 LLM 会自然处理
- 后续如果信号词不够用，直接往列表里加就行，不需要训练

### Step 1: LLM 意图分析

**角色**：让 LLM 做它擅长的语义理解——提取实体、理解同义词、推断查询目标。

**输入**：用户的自然语言问题（原文）

**输出**：结构化 JSON

```json
{
  "entities": [
    {"text": "城东门店", "type": "store", "normalized": "城东"},
    {"text": "合租房间", "type": "room", "normalized": "joint_room"},
    {"text": "没租出去", "type": "condition", "normalized": "is_lease=0"}
  ],
  "query_goal": "count_and_list",
  "business_mode": ["joint"],
  "aggregation": null,
  "time_range": null,
  "search_keywords": ["joint", "room", "store"]
}
```

**Prompt 模板**：

```
你是全房通房屋租赁管理系统的查询意图分析器。

## 你的任务
分析用户问题，提取结构化查询意图。你不需要生成 SQL，只需要理解用户想查什么。

## 业务背景
全房通管理三种业务模式的房源：
- 整租(whole)：整套出租，表名含 whole
- 合租(joint)：按房间出租，表名含 joint
- 集中式(focus)：集中管理公寓，表名含 focus

核心业务域：房源(housing)、房间(room)、租客(tenants)、合同(contract)、
账单(income/expend)、财务(finance)、门店(store)、智能硬件(smart/device)

## 输出格式（严格 JSON）
{
  "entities": [
    {"text": "原文片段", "type": "实体类型", "normalized": "标准化标识"}
  ],
  "query_goal": "查询目标: count/list/sum/compare/rank/rate",
  "business_mode": ["涉及的业务模式: whole/joint/focus，空数组表示不区分"],
  "aggregation": "聚合方式: group_by_store/group_by_month/group_by_quarter/null",
  "time_range": "时间范围描述或null",
  "search_keywords": ["用于图谱搜索的英文关键词，从表名/列名中提取"]
}

## 实体类型
- store: 门店名称 → 标准化为门店名
- housing: 房源相关 → 标准化为 whole_housing/joint_housing/focus_housing
- room: 房间相关 → 标准化为 whole_room/joint_room/focus_room
- tenants: 租客 → 标准化为 tenants_name
- condition: 查询条件 → 标准化为字段条件表达式
- metric: 指标 → 标准化为字段名
- location: 地理位置（小区名等）
- time: 时间表达

## search_keywords 提取规则
这些关键词将用于在图数据库中搜索相关表。请从以下维度提取：
- 业务实体对应的表名词干：housing, room, tenants, contract, income, expend, finance, store, device 等
- 如果涉及特定业务模式，加上前缀：whole_housing, joint_room, focus_tenants 等
- 如果涉及关联查询（如"某小区的房源"），包含关联实体：area_property, store 等

只输出 JSON，不要解释。
```

**模型选择**：使用与 Step 3 相同的模型（GPT-5.4 或 Opus 4.6），但降低 reasoning budget。

| 参数 | Step 1 | Step 3 |
|------|--------|--------|
| 模型 | 同一模型 | 同一模型 |
| reasoning | GPT-5.4: effort=low; Opus: budget=2000 | GPT-5.4: effort=high; Opus: budget=10000 |
| max_tokens | 1000 | 4000 |
| temperature | 0.0 | 0.0 |

**为什么不用更轻量的模型？**
- Step 1 需要理解中文语义和业务术语，小模型在中文理解上差距大
- 同一模型避免了维护两套模型配置的复杂度
- 通过降低 reasoning budget 控制成本（Step 1 不需要深度推理）

**为什么不和 Step 3 合并？**
- 合并意味着把全量 DDL（~20K tokens）塞进 prompt，回到 Baseline 的问题
- 分两步的核心价值是：Step 1 输出的 search_keywords 驱动图谱搜索，精准裁剪 DDL
- 如果合并，图谱搜索就没有输入了，整个图谱增强的意义就不存在了

**Token 消耗预估**：
- System prompt: ~800 tokens
- 用户问题: ~50 tokens
- Reasoning: ~500 tokens（低 budget）
- 输出: ~200 tokens
- **总计: ~1,500 tokens**

### Step 2: 图谱搜索 + 路径发现

**角色**：让图数据库做它擅长的结构化搜索——精准定位表、发现 JOIN 路径、提取关键列。

**输入**：Step 1 输出的 `search_keywords` 和 `entities`

**输出**：推荐表列表、JOIN 路径、关键列

**执行流程（三阶段）**：

```
search_keywords ──> [阶段1: 关键词搜索] ──> 直接命中表
                          │
                          ▼
                    [阶段2: 图遍历扩展] ──> 沿 REFERENCES 边扩展 1 跳
                          │
                          ▼
                    [阶段3: 路径发现]   ──> 提取表间 JOIN 路径 + 关键列
```

**阶段 1：关键词搜索（表定位）**

将 `search_keywords` 转化为 Cypher 查询：

```cypher
-- 对每个 keyword 执行
MATCH (t:TableNode)
WHERE t.name CONTAINS $keyword
RETURN t.name
```

例如 `search_keywords = ["joint", "room", "store"]` 会命中：
- `qft_joint_room`, `qft_joint_housing`, `qft_joint_tenants`, ...（含 joint）
- `qft_whole_room`, `qft_joint_room`, `qft_focus_room`, ...（含 room）
- `qft_store`（含 store）

**阶段 2：图遍历扩展（1 跳邻居）**

对阶段 1 命中的表，沿 REFERENCES 边扩展 1 跳：

```cypher
-- 出边（当前表引用的表）
MATCH (a:TableNode {name: $table_name})-[:REFERENCES]->(b:TableNode)
RETURN b.name

-- 入边（引用当前表的表）
MATCH (a:TableNode)-[:REFERENCES]->(b:TableNode {name: $table_name})
RETURN a.name
```

**阶段 3：路径发现（JOIN 路径 + 关键列）**

在推荐表集合内，查找所有 REFERENCES 边：

```cypher
-- JOIN 路径
MATCH (a:TableNode {name: $table})-[r:REFERENCES]->(b:TableNode)
WHERE b.name IN $recommended_tables
RETURN a.name, r.column_name, r.comment, b.name

-- 关键列（与查询相关的列）
MATCH (t:TableNode {name: $table})-[:HAS_COLUMN]->(c:ColumnNode)
RETURN c.column_name, c.column_type, c.comment
```

**结果排序与过滤**：

推荐表数量控制在 **8-15 张**：
- 阶段 1 命中的表优先级最高（直接相关）
- 阶段 2 扩展的表按 REFERENCES 边数排序（关联度高的优先）
- 超过 15 张时，砍掉扩展阶段中关联度最低的表
- 少于 5 张时，补充通用基础表（qft_store, qft_company）

**输出格式**：

```python
{
    "recommended_tables": ["qft_joint_room", "qft_joint_housing", "qft_store", ...],
    "join_paths": [
        {"from": "qft_joint_room", "column": "housing_id", "to": "qft_joint_housing", "comment": "房源ID"},
        {"from": "qft_joint_room", "column": "store_id", "to": "qft_store", "comment": "门店ID"},
    ],
    "key_columns": [
        "qft_joint_room.is_lease (tinyint) -- 是否出租(0-未出租,1-已出租)",
        "qft_joint_room.pricing_money (decimal) -- 定价金额",
        "qft_store.name (varchar) -- 门店名称",
    ],
}
```

**耗时预估**：< 50ms（Kuzu 嵌入式）/ < 100ms（Neo4j/FalkorDB 网络）

### Step 3: LLM SQL 生成

**角色**：在精简的上下文中生成高质量 SQL。

**输入**：
- Step 2 的推荐表 DDL（精简，~3K tokens vs 全量 ~20K tokens）
- Step 2 的 JOIN 路径和关键列
- Step 1 的意图分析结果
- 业务约束（company_id、is_delete）

**Prompt 模板**：

```
你是全房通房屋租赁管理系统的 SQL 专家。

## 公司上下文
当前公司 company_id = {company_id}。所有查询必须加 WHERE company_id = {company_id}。
软删除字段 is_delete (0=正常, 1=已删除)，查询时加 is_delete = 0。
所有表在同一个数据库中，不需要库名前缀。

## 查询意图（由 AI 分析得出）
{query_intent_summary}

## 推荐使用的表（由知识图谱精准定位，请严格使用这些表）
{recommended_tables_list}

## 表间关系（JOIN 路径，由图谱提供，请严格遵循）
{join_paths}

## 关键字段提示
{key_columns}

## 表结构（仅包含推荐表的 DDL）
{schema_ddl}

## 生成要求
1. 只使用上述推荐的表，不要猜测其他表名
2. JOIN 条件严格按照"表间关系"中给出的路径
3. 所有表加 company_id = {company_id} AND is_delete = 0 条件
4. 如果涉及多种业务模式（整租+合租），使用 UNION ALL
5. 结果加 LIMIT 100 防止返回过多数据
6. 只返回纯 SQL，不要解释。SQL 以分号结尾。
```

**与 Step 1 prompt 的关键区别**：

| 维度 | Step 1 Prompt | Step 3 Prompt |
|------|--------------|--------------|
| 目标 | 提取意图 → JSON | 生成 SQL → SQL |
| 上下文 | 无 DDL，只有业务描述 | 有精简 DDL + JOIN 路径 |
| 约束 | 宽松（允许模糊） | 严格（指定表和路径） |
| Reasoning | 低（理解语义即可） | 高（需要推理 SQL 逻辑） |

**如何确保 LLM 遵循图谱给出的 JOIN 路径？**

三重约束：
1. **Prompt 指令**："严格按照表间关系中给出的路径"
2. **DDL 限制**：只给推荐表的 DDL，LLM 无法引用其他表
3. **后验校验**（Step 4）：解析生成的 SQL，检查 JOIN 条件是否与图谱路径一致

**Token 消耗预估**：
- System prompt + DDL: ~3,000 tokens（8-15 张表）
- 用户问题: ~50 tokens
- Reasoning: ~3,000 tokens（高 budget）
- 输出 SQL: ~200 tokens
- **总计: ~6,000 tokens**

### Step 4: SQL 执行 + 验证 + 纠错

**执行**：在 MySQL 数据集市上执行生成的 SQL。

**验证层次**：

```
SQL ──> [语法检查] ──> [执行] ──> [结果验证]
            │              │            │
         解析失败       执行报错     结果异常
            │              │            │
            └──────────────┴────────────┘
                           │
                    [LLM 纠错（可选）]
                           │
                     重试 1 次
```

**纠错策略**：

```python
def execute_with_retry(sql: str, error: str, context: dict) -> dict:
    """执行失败时，给 LLM 错误信息让它修正 SQL"""
    correction_prompt = f"""
之前生成的 SQL 执行失败。

原始 SQL:
{sql}

错误信息:
{error}

请修正 SQL。常见问题：
- 表名或列名拼写错误
- 缺少 company_id 或 is_delete 条件
- JOIN 条件不正确
- 聚合函数与 GROUP BY 不匹配

只返回修正后的纯 SQL。
"""
    # 使用同一模型，低 reasoning budget
    corrected_sql = llm.chat_completion(messages=[...], reasoning_budget="low")
    return execute_sql(corrected_sql)
```

**纠错限制**：
- 最多重试 1 次（避免死循环和成本失控）
- 只在 SQL 语法错误或执行错误时纠错，不在"结果看起来不对"时纠错（benchmark 中无法判断语义正确性）
- 纠错的 token 消耗计入总成本

---

## 五、方案对比汇总

### 单次查询资源消耗预估

| 维度 | A: Baseline | B/C/D: 图谱增强 | E: 静态规则 |
|------|------------|----------------|------------|
| LLM 调用次数 | 1 | 2 (+可选纠错 1) | 1 |
| 图谱查询次数 | 0 | 3-8 次 Cypher | 0 |
| Context tokens | ~20,000 | ~1,500 + ~6,000 = ~7,500 | ~3,000 |
| Reasoning tokens | ~5,000 | ~500 + ~3,000 = ~3,500 | ~5,000 |
| Output tokens | ~200 | ~200 + ~200 = ~400 | ~200 |
| **总 tokens** | **~25,000** | **~11,400** | **~8,200** |
| 图谱延迟 | 0ms | 50-100ms | 0ms |
| LLM 延迟 | 3-8s (1次) | 1-2s + 3-5s = 4-7s (2次) | 2-4s (1次) |
| **总延迟** | **3-8s** | **4-7s** | **2-4s** |
| 表召回能力 | LLM 从全量 DDL 猜 | 图谱精准定位 | 关键词硬匹配 |
| 可维护性 | 无需维护 | 图谱自动导入 | 需手工维护映射表 |

### 预期成功率（基于 Phase 1 分析）

| 题目类型 | A: Baseline | B/C/D: 图谱增强 | E: 静态规则 |
|---------|------------|----------------|------------|
| L1 单表（Q01-Q08） | 高 | 高 | 高 |
| L2 双表 JOIN（Q09-Q16） | 中 | 高（图谱提供路径） | 中 |
| L3 多域（Q17-Q24） | 低（DDL 太多噪声） | 中-高 | 低-中 |
| L4 复杂（Q25-Q30） | 低 | 中 | 低 |

---

## 六、Benchmark 评估维度

### 6.1 核心指标

| 指标 | 定义 | 计算方法 | 对应步骤 |
|------|------|---------|---------|
| **端到端成功率** | SQL 可执行且结果正确 | correct / total | 全链路 |
| **SQL 可执行率** | SQL 语法正确，MySQL 可执行 | executable / total | Step 3-4 |
| **意图分析准确率** | Step 1 提取的实体覆盖正确表 | 命中的 expected_entities / total_expected | Step 1 |
| **表召回率** | 推荐表包含目标表 | \|found ∩ expected\| / \|expected\| | Step 2 |
| **表精确率** | 推荐表中有多少是有用的 | \|found ∩ expected\| / \|found\| | Step 2 |
| **JOIN 路径准确率** | 生成的 JOIN 与预期一致 | correct_joins / total_joins | Step 2-3 |
| **总延迟** | 从问题输入到结果返回 | end_time - start_time | 全链路 |
| **各步骤延迟** | 每步耗时 | step_end - step_start | 各步骤 |
| **总 token 消耗** | 所有 LLM 调用的 token 之和 | sum(prompt + completion) | Step 1+3(+4) |
| **成本（美元）** | 按 OpenRouter 定价计算 | tokens * price_per_token | 全链路 |

### 6.2 指标计算细节

**端到端成功率（最重要的指标）**：

```python
def is_correct(result: dict, expected: dict) -> bool:
    """判断查询是否成功"""
    # 1. SQL 必须可执行
    if not result["sql_executable"]:
        return False
    # 2. 结果非空（除非预期就是空）
    if result["row_count"] == 0 and expected["expected_row_count"] > 0:
        return False
    # 3. 关键字段匹配（宽松匹配）
    # 例如 Q01 预期 store_count=3，检查结果中是否包含 3
    return fuzzy_match(result["rows"], expected["expected_answer"])
```

**表召回率**：

```python
def table_recall(found_tables: list, expected_tables: list) -> float:
    """推荐表是否覆盖了必要表"""
    found = set(found_tables)
    expected = set(expected_tables)
    return len(found & expected) / len(expected) if expected else 1.0
```

**意图分析准确率**（仅图谱方案）：

```python
def intent_accuracy(extracted_keywords: list, expected_tables: list) -> float:
    """提取的关键词是否能命中目标表"""
    # 模拟图谱搜索：关键词能否定位到 expected_tables
    hittable = set()
    for kw in extracted_keywords:
        for tbl in expected_tables:
            if kw in tbl:
                hittable.add(tbl)
    return len(hittable) / len(expected_tables) if expected_tables else 1.0
```

### 6.3 方案间公平对比

**Token 消耗对比**：

Baseline 只有 1 次 LLM 调用但 context 巨大，图谱方案有 2 次调用但 context 精简。公平的对比维度是 **总 token 消耗**（所有调用的 prompt_tokens + completion_tokens + reasoning_tokens 之和），而非调用次数。

```python
# 每个 result 记录
result["token_breakdown"] = {
    "step1_prompt": 850,      # 意图分析 prompt
    "step1_completion": 200,   # 意图分析输出
    "step1_reasoning": 500,    # 意图分析推理
    "step3_prompt": 3200,      # SQL 生成 prompt
    "step3_completion": 200,   # SQL 输出
    "step3_reasoning": 3000,   # SQL 推理
    "step4_prompt": 0,         # 纠错（如果触发）
    "step4_completion": 0,
    "total": 7950,
}
```

**延迟对比**：

图谱方案多了图遍历时间（~50-100ms）但减少了 LLM 处理时间（context 更小）。记录两个维度：
- `total_latency`: 端到端总耗时
- `llm_latency`: 纯 LLM 调用耗时（排除图谱时间）
- `graph_latency`: 纯图谱查询耗时

**性价比评估**：

```python
def cost_effectiveness(results: list) -> dict:
    """每正确回答的成本"""
    total_cost = sum(r["cost_usd"] for r in results)
    correct_count = sum(1 for r in results if r["is_correct"])
    return {
        "total_cost": total_cost,
        "correct_count": correct_count,
        "cost_per_correct": total_cost / correct_count if correct_count else float("inf"),
        "success_rate": correct_count / len(results),
    }
```

---

## 七、实现优先级

### Phase 2 目标（当前）

1. **重构 Step 1**：用 LLM 替换 KEYWORD_MAP 硬编码，实现结构化意图分析
2. **重构 Step 2**：优化图谱搜索，基于 Step 1 的 search_keywords 而非硬编码 stems
3. **重构 Step 3**：使用 `GRAPH_PROMPT_TEMPLATE` 加入图谱分析结果
4. **新增 Step 4**：SQL 执行失败时的 LLM 纠错（1 次重试）
5. **Benchmark 升级**：记录各步骤指标，支持方案间公平对比

### 代码改动范围

```
solutions/
  common.py          ← 新增 Step 0 预分类、Step 4 纠错
  graph_kuzu.py      ← 重构：删除 KEYWORD_MAP，改用 LLM 意图分析
  graph_neo4j.py     ← 同上
  graph_falkordb.py  ← 同上
  baseline_text2sql.py  ← 不变（对照组）
  static_metadata.py    ← 不变（对照组）

benchmarks/
  run_benchmark.py   ← 新增指标收集：intent_accuracy, table_precision, token_breakdown
```

---

## 八、关键设计决策总结

| 决策 | 选择 | 理由 |
|------|------|------|
| Step 0 用规则还是 LLM？ | 规则 | 分类简单，不值得消耗 LLM 调用 |
| Step 1 用什么模型？ | 与 Step 3 同模型，降低 reasoning | 中文语义理解需要强模型，降 budget 控成本 |
| Step 1 需要 reasoning 吗？ | 需要，但低 budget | 实体识别和同义词理解受益于轻度推理 |
| Step 1 和 3 能否合并？ | 不能 | 合并后失去图谱裁剪 DDL 的核心价值 |
| 图谱搜索结果需要过滤吗？ | 需要，限 8-15 张表 | 过多表增加 context 和噪声，过少可能遗漏 |
| SQL 执行失败是否重试？ | 是，最多 1 次 | 语法错误常因列名拼写，纠错成功率高 |
| 纠错用同一模型吗？ | 是，低 reasoning | 纠错只需理解错误信息，不需要重新推理 |

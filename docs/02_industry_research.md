# 业界 AI 友好数据架构方案调研报告

> 调研日期：2026-03-23
> 调研背景：全房通 SaaS 系统（3 库 1660+ 张表，最宽 131 列），纯 Text-to-SQL 和 RAG 方案效果不佳，需从数据架构层面探索解决方案。

---

## 目录

1. [方案一：语义层（Semantic Layer）](#方案一语义层semantic-layer)
2. [方案二：知识图谱 + 图数据库](#方案二知识图谱--图数据库)
3. [方案三：数据分层 + 视图](#方案三数据分层--视图)
4. [方案四：API/Tool 封装](#方案四apitool-封装)
5. [方案五：混合方案（元数据增强 + 动态裁剪 + 查询路由）](#方案五混合方案)
6. [方案六：最新 Text-to-SQL 技术进展](#方案六最新-text-to-sql-技术进展)
7. [方案对比矩阵](#方案对比矩阵)
8. [针对全房通的推荐策略](#针对全房通的推荐策略)

---

## 方案一：语义层（Semantic Layer）

### 核心思路

在原始数据库之上构建一层语义抽象，将物理表/列映射为业务概念（指标、维度、实体），AI 查询时面对的是语义模型而非原始 schema。

### 主要产品/框架

| 产品 | 特点 | AI 集成能力 |
|------|------|------------|
| **Cube (原 Cube.js)** | API-first 语义层，支持 REST/GraphQL/SQL API，内置预聚合和缓存 | 原生支持 Text-to-SQL via RAG，2025 年推出 Agentic Analytics |
| **dbt Semantic Layer** | 基于 MetricFlow，与 dbt 转换框架深度集成 | 支持自然语言查询，嵌入元数据验证 |
| **LookML (Looker)** | Google 生态，最早的语义层先驱（2019年） | 与 Gemini 集成实现自然语言查询 |
| **AtScale** | 企业级虚拟语义层，支持 OLAP 语义建模 | 通过 API 对接 AI 应用 |

### Cube 的多租户支持

Cube 原生支持多租户架构：
- 每个租户可配置独立数据模型
- 支持按租户同步到不同 BI 工具或不同数据库
- 安全上下文（Security Context）实现行级数据隔离
- 适合 SaaS 场景的租户感知查询

### 与 Text-to-SQL 的结合

Cube 将用户的自然语言 prompt 通过 RAG 确定性地编译为 SQL：
1. 用户提问 -> LLM 理解意图
2. 从语义层元数据中检索相关指标/维度
3. 通过 Cube API 编译为 SQL（确定性过程）
4. 执行查询返回结果

这种方式将 LLM 的不确定性限定在「意图理解」阶段，SQL 生成由确定性引擎完成，大幅提升准确率。

### 对全房通的适用性分析

**优势**：
- 将 1660+ 张表抽象为几十个业务指标和维度，大幅降低 AI 理解成本
- 拼音缩写字段可在语义层映射为可读的业务名称
- 三种业务模式（整租/合租/集中式）可统一为语义模型
- 多租户原生支持，适配 SaaS 场景

**挑战**：
- 初始建模工作量大（1660 张表需要大量业务领域知识）
- 需要持续维护语义模型与底层表的同步
- 对于动态查询场景（用户自定义的 ad-hoc 分析），覆盖度有限

**实施复杂度**：高（初始建设），中（持续维护）
**预计准确率提升**：显著（从 ~30% 提升到 70-85%）

---

## 方案二：知识图谱 + 图数据库

### 核心思路

将数据库 schema 建模为 Property Graph（属性图），节点表示表/列/实体，边表示表间关系（外键、业务关联）。AI 查询时通过图遍历发现正确的表连接路径，解决「AI 不知道表间如何 JOIN」的核心问题。

### 主要产品/框架

| 产品 | 特点 | 适用场景 |
|------|------|---------|
| **QueryWeaver (FalkorDB)** | 开源，基于 FalkorDB 图数据库的 Text-to-SQL 引擎 | 支持 MySQL/PostgreSQL，内置 MCP Server |
| **Neo4j** | 成熟的图数据库，丰富的生态 | 企业级知识图谱 |
| **Apache AGE** | PostgreSQL 图查询扩展 | 无需额外图数据库 |

### QueryWeaver 的工作原理

QueryWeaver 是 2025 年 9 月发布的开源 Graph-powered Text-to-SQL 工具：

1. **Schema 建模**：将数据库 schema 映射为知识图谱（表 -> 节点，关系 -> 边）
2. **语义增强**：节点包含业务语义描述（如"客户"是什么、如何连接到"订单"）
3. **图遍历**：对于多表 JOIN 查询，通过图遍历找到中间桥接表
4. **SQL 生成**：基于图路径生成精确的 JOIN 条件

**核心优势 - 解决多跳查询问题**：

向量数据库在 Text-to-SQL 中的致命缺陷是只能检索语义相似的表，但无法发现结构上必要但语义不相关的桥接表。例如查询 "某区域客户购买的产品"，需要经过 customer -> order -> order_item -> product -> region 五张表，向量检索只能找到 customer 和 product，遗漏了中间的连接路径。

图遍历通过沿着结构路径行走来解决这个 5-hop 查询问题。

### 与 AI 的集成

QueryWeaver 内置 MCP Server，可直接集成到 Claude、Cursor 等 LLM 工具中，实现 Agent 工作流中的 Text-to-SQL。

### 对全房通的适用性分析

**优势**：
- 解决全房通「没有外键约束，表间关系隐藏在代码中」的核心痛点
- 可以将隐式的业务关系（如哪些表通过 company_id 关联）显式建模为图
- 图结构天然适合探索复杂的多表关联
- 开源免费，支持 MySQL

**挑战**：
- 1660 张表的关系梳理工作量非常大
- 需要额外维护图数据库的一致性
- 图查询性能对超大规模 schema 的表现待验证
- 对简单查询（单表或少量表）可能过度工程化

**实施复杂度**：高
**预计准确率提升**：对多表 JOIN 查询显著，对单表查询无明显提升

---

## 方案三：数据分层 + 视图

### 核心思路

借鉴数据仓库的分层设计（ODS -> DWD -> DWS -> ADS），在 MySQL 上通过 View 实现轻量级数据抽象层，AI 查询面对的是简化后的视图而非原始宽表。

### 分层设计

```
ODS 层（原始数据）
├── qft_basics.*     484 表
├── qft_lease.*     1076 表
└── qft_finance.*    107 表

DWD 层（明细数据视图）
├── v_房源明细          合并整租/合租/集中式房源表
├── v_租客明细          统一租客信息
├── v_合同明细          统一合同信息
└── v_账单明细          统一账单和财务流水

DWS 层（汇总数据视图）
├── v_房源出租率统计    按项目/楼栋/时间段聚合
├── v_收入统计          按公司/项目/月份聚合
├── v_租客画像          租客维度聚合分析
└── v_逾期统计          逾期账单聚合

ADS 层（应用数据视图）
├── v_经营看板          CEO/管理层看板数据
├── v_项目运营报表      项目经理维度报表
└── v_财务报表          财务维度报表
```

### MySQL View 实现方式

```sql
-- 示例：统一三种业务模式的房源视图
CREATE VIEW v_房源明细 AS
SELECT
    r.id AS room_id,
    r.room_name AS 房间名称,
    p.project_name AS 项目名称,
    b.building_name AS 楼栋名称,
    CASE r.business_type
        WHEN 1 THEN '整租'
        WHEN 2 THEN '合租'
        WHEN 3 THEN '集中式'
    END AS 业务模式,
    r.area AS 面积,
    r.rent_price AS 租金,
    r.status AS 状态
FROM rooms r
JOIN projects p ON r.project_id = p.id
JOIN buildings b ON r.building_id = b.id
WHERE r.is_deleted = 0;
```

### 物化视图的可行性

MySQL 8.0 不原生支持 Materialized View，但可通过以下方式模拟：
- **定时任务 + 汇总表**：通过 Event Scheduler 或外部 cron 定期刷新汇总表
- **触发器驱动**：在写入时同步更新汇总表（对性能有影响）
- **第三方工具**：使用 Flexviews 等开源工具模拟物化视图

### 对全房通的适用性分析

**优势**：
- 实施成本最低，直接在 MySQL 上操作
- 不引入新技术栈，运维成本低
- 将 1660 张表收敛为几十个 AI 友好的视图
- 中文字段名直接提供语义
- 将三种业务模式统一为一套视图

**挑战**：
- MySQL View 的查询性能受限（尤其是多表 JOIN 的视图）
- 视图嵌套过深时性能急剧下降
- 不支持原生物化视图，模拟方案增加复杂度
- 对于复杂的 ad-hoc 查询，视图覆盖度有限
- 数据一致性问题（模拟物化视图的延迟）

**实施复杂度**：低-中
**预计准确率提升**：中等（视图设计质量依赖对业务的深入理解）

---

## 方案四：API/Tool 封装

### 核心思路

将高频业务查询封装为 Agent Tool（Function Calling），AI 不直接写 SQL，而是调用预定义的查询函数。类似 Salesforce Agentforce 和 Microsoft Copilot 的做法。

### 业界实践

#### Salesforce Agentforce（原 Einstein Copilot）

- **Copilot Actions**：预编程的能力库，每个 Action 封装一个业务操作
- **Agent Topics**：将 Actions 按业务主题分组
- **执行治理**：所有操作经过验证、日志记录和权限控制
- **MCP 协议**：通过 Model Context Protocol 实现 Agent 操作的标准化

#### Microsoft Copilot Studio

- **REST API 工具**：通过 OpenAPI 规范连接 Agent 到外部系统
- **MCP Server**：支持连接 Dataverse、GitHub、Salesforce 等服务
- **权限控制**：自定义 Agent 的安全上下文和数据访问范围

### 全房通的 Tool 设计示例

```python
# 将高频查询封装为 Agent Tool
tools = [
    {
        "name": "query_vacancy_rate",
        "description": "查询项目/楼栋的空置率",
        "parameters": {
            "project_name": "项目名称（可选）",
            "building_name": "楼栋名称（可选）",
            "date_range": "时间范围（可选）"
        }
    },
    {
        "name": "query_rent_collection",
        "description": "查询租金收缴情况",
        "parameters": {
            "company_id": "公司ID",
            "month": "月份",
            "include_overdue": "是否包含逾期"
        }
    },
    {
        "name": "query_tenant_info",
        "description": "查询租客信息",
        "parameters": {
            "tenant_name": "租客姓名（可选）",
            "phone": "手机号（可选）",
            "room_number": "房间号（可选）"
        }
    },
    {
        "name": "query_contract_expiring",
        "description": "查询即将到期的合同",
        "parameters": {
            "days": "多少天内到期",
            "project_name": "项目名称（可选）"
        }
    }
]
```

### 对全房通的适用性分析

**优势**：
- 准确率极高（预定义 SQL，100% 正确）
- 安全可控（SQL 经过审计，不存在注入风险）
- 无需 AI 理解复杂的 schema
- 可覆盖 80% 的高频查询场景
- 实施渐进，可以逐步添加 Tool

**挑战**：
- 灵活性差，无法处理 long-tail 的 ad-hoc 查询
- Tool 数量膨胀后，AI 选择正确 Tool 的难度增加
- 需要持续分析用户查询模式并新增 Tool
- 不能替代 Text-to-SQL，只是补充

**实施复杂度**：低（单个 Tool），中（完整体系）
**预计准确率提升**：对已覆盖的查询接近 100%，对未覆盖的无提升

---

## 方案五：混合方案

### 核心思路

组合多种技术手段，根据查询复杂度进行路由分发，同时通过元数据增强和动态 Schema 裁剪提升 Text-to-SQL 的基础准确率。

### 5.1 元数据增强

#### 研究发现

AWS 的研究表明，通过元数据增强可显著提升 Text-to-SQL 准确率：
- 为列添加业务描述（column descriptions）
- 提供列值样例（sample values），帮助模型生成正确的 WHERE 条件
- 使用业务词汇表（business glossary），将技术名称映射为业务术语

#### Spider 2.0 基准测试结果（2025年4月）

在真实企业场景下，Text-to-SQL 的准确率仅 31%。主要瓶颈：
- 数据湖包含数百万张表，部分表超过 100 列
- 表经常被废弃，信息重叠
- 缺乏充分的元数据描述

#### 对全房通的应用

```yaml
# 元数据增强示例
table: ht_lease_room
description: "房源信息表，记录每个可出租房间的基本信息"
columns:
  - name: fang_yuan_id
    description: "房源唯一标识ID"
    business_name: "房源ID"
  - name: xm_mc
    description: "项目名称，即楼盘/小区名称"
    business_name: "项目名称"
    sample_values: ["阳光花园", "翠苑小区", "万科城"]
  - name: yw_ms
    description: "业务模式：1=整租, 2=合租, 3=集中式"
    business_name: "业务模式"
    enum_values: {1: "整租", 2: "合租", 3: "集中式"}
```

### 5.2 动态 Schema 裁剪

#### 最新研究进展

**AutoLink**（2025年11月）：
- 将 Schema Linking 重构为迭代式的 Agent 驱动过程
- LLM 引导下动态探索和扩展 schema 子集
- 在 Bird-Dev 上达到 97.4% 的 schema 召回率
- 在超过 3000 列的大 schema 上仍保持高性能
- 其他方法在大 schema 上严重退化，而 AutoLink 表现稳定

**LinkAlign**：
- 面向真实大规模多数据库的 Schema Linking
- 隔离无关 schema 信息，减少噪声

**CRED-SQL**：
- 基于语义相似度聚类属性
- 降权大簇中的通用/常见字段
- 减少语义干扰，提升表检索准确率

### 5.3 查询路由（Query Routing）

根据查询的复杂度将请求路由到不同的处理管道：

```
用户提问
  │
  ├── 简单查询（关键词匹配/意图分类）
  │     └── Tool/API 调用（预定义查询，准确率 ~100%）
  │
  ├── 中等复杂度查询（1-3表关联）
  │     └── 语义层 + Text-to-SQL（准确率 ~80%）
  │
  └── 复杂查询（多表关联/聚合/子查询）
        └── 多 Agent 协作 + 图增强 + 自纠错（准确率 ~60%）
```

#### 复杂度分类器

**EllieSQL**（2025）引入了复杂度感知路由系统：
- 根据估计的查询难度将请求路由到不同模型管道
- 简单查询用小模型快速响应
- 复杂查询调用大模型 + 多步推理
- 显著降低整体成本同时保持准确率

### 对全房通的适用性分析

**优势**：
- 兼顾准确率和灵活性
- 渐进式实施，每个组件可独立迭代
- 高频场景高准确率（Tool），长尾场景有兜底（Text-to-SQL）
- 元数据增强是低成本高收益的第一步

**挑战**：
- 系统架构复杂度高
- 路由策略需要持续优化
- 多个子系统的维护成本

**实施复杂度**：高（完整体系），但可分阶段
**预计准确率提升**：综合可达 75-90%（取决于 Tool 覆盖率和元数据质量）

---

## 方案六：最新 Text-to-SQL 技术进展

### 6.1 Schema Linking 技术

| 方法 | 年份 | 核心思路 | Bird-Dev EX |
|------|------|---------|-------------|
| **RSL-SQL** | 2024.11 | 双向 Schema Linking + 二元选择策略 + 多轮自纠错 | 67.2% |
| **AutoLink** | 2025.11 | Agent 驱动的迭代式 Schema 探索，适合大规模 schema | 68.7% |
| **CRED-SQL** | 2025.08 | 聚类检索 + 执行描述增强，面向真实大规模数据库 | - |
| **LinkAlign** | 2025 | 面向多数据库的可扩展 Schema Linking | - |

### 6.2 多 Agent 协作框架

**MAC-SQL**（Multi-Agent Collaborative Framework）：
- 将 Text-to-SQL 分解为多个子任务
- 不同 Agent 负责 Schema Linking、SQL 生成、结果验证
- 子任务分解策略与 DIN-SQL 类似，但引入多 Agent 协作

**CHASE-SQL**：
- 多 Agent 范式 + 多样化候选生成
- 不同 Agent 模型产生多个 SQL 候选
- 偏好排序选择最佳输出

**DB-GPT**：
- 开源 AI 原生数据应用开发框架
- 支持自然语言查询自动生成 SQL
- 内置 Agent 工作流、RAG、多模型支持
- 任务规划 + 工具调用 + 端到端分析流程

### 6.3 推理增强

**SQL-o1**：
- 自奖励启发式搜索框架
- 使用蒙特卡洛树搜索（MCTS）进行结构化查询空间探索
- 通过试错引导找到 SQL 解

**HES-SQL**：
- 混合推理 + 结构骨架引导
- 小模型处理 Schema Linking 和骨架生成
- 大模型专注复杂推理

### 6.4 长上下文 vs Schema 裁剪

VLDB 2025 研究表明：
- 长上下文 LLM 可以容纳更多表（高召回率）
- 但超过一定阈值后，增加无关表不再带来收益
- 延迟成本随上下文增大而增加
- 结论：精确的检索和过滤仍然是必要的，长上下文可作为补偿机制

### 对全房通的启示

- **Schema Linking 是关键瓶颈**：1660 张表场景，AutoLink 的迭代探索方式最适合
- **多 Agent 协作可提升复杂查询**：拆解子任务降低单步难度
- **长上下文不是银弹**：即使 100 万 token 窗口，1660 张表的完整 schema 仍然过大
- **自纠错机制至关重要**：SQL 执行反馈驱动的多轮修正

---

## 方案对比矩阵

| 维度 | 语义层 | 知识图谱 | 数据分层/视图 | API/Tool 封装 | 混合方案 |
|------|--------|----------|--------------|--------------|---------|
| **实施复杂度** | 高 | 高 | 低-中 | 低 | 高（可分阶段） |
| **初始投入** | 大（建模） | 大（图构建） | 中（视图设计） | 小（逐步添加） | 中（分阶段） |
| **持续维护成本** | 中 | 中-高 | 低 | 低 | 中 |
| **查询准确率** | 70-85% | 65-80%（多表JOIN显著提升） | 60-75% | ~100%（已覆盖的） | 75-90% |
| **灵活性** | 中 | 高 | 低 | 低 | 高 |
| **宽表适应性** | 强（字段映射） | 中 | 强（视图裁剪） | 强（预定义） | 强 |
| **多租户支持** | 原生支持 | 需额外设计 | 需额外设计 | 简单 | 需整体设计 |
| **新技术栈引入** | 是（Cube等） | 是（图数据库） | 否 | 否 | 部分 |
| **与现有系统兼容性** | 好（不改原表） | 好（不改原表） | 好（MySQL原生） | 好（应用层） | 好 |

---

## 针对全房通的推荐策略

### 推荐：分阶段混合方案

综合考虑全房通的技术现状（MySQL、1660+ 表、无外键、拼音字段、SaaS 多租户）和实施资源约束，建议采用分阶段实施的混合策略：

### Phase 1：元数据增强 + API/Tool 封装（1-2 个月）

**低成本、高收益的快速见效阶段**

1. **元数据增强**
   - 为核心表（~100 张高频使用表）添加中文业务描述
   - 建立字段级别的业务词汇表（拼音缩写 -> 中文含义）
   - 标注枚举值的业务含义
   - 成本低，但对 Text-to-SQL 准确率有直接提升

2. **高频查询 Tool 化**
   - 分析现有报表和常见查询场景
   - 封装 20-30 个高频 Agent Tool（空置率、收缴率、到期合同等）
   - 实现查询路由：Tool 命中 -> 精确响应，未命中 -> 降级到 Text-to-SQL

3. **预期收益**
   - 高频查询准确率从 ~30% 提升到 ~95%
   - 实施简单，不引入新技术栈

### Phase 2：数据视图层 + Schema Linking 优化（2-3 个月）

**构建 AI 友好的查询抽象层**

1. **MySQL View 层建设**
   - 设计 DWD 层视图：统一三种业务模式的房源/合同/账单表
   - 设计 DWS 层视图：常用汇总指标（出租率、收入、逾期等）
   - 视图使用中文别名，直接提供语义
   - 用汇总表模拟热点数据的物化视图

2. **动态 Schema 裁剪**
   - 参考 AutoLink 思路，实现迭代式 Schema 探索
   - 根据用户提问动态选择相关的视图/表（10-20 张）
   - 将 context window 压力从 1660 张表降低到 10-20 张

3. **预期收益**
   - Text-to-SQL 长尾查询准确率提升到 60-70%
   - AI 面对的 schema 从 1660 张表减少到 50-80 个视图

### Phase 3：语义层 / 知识图谱（可选，3-6 个月）

**根据 Phase 1&2 效果决定是否实施**

1. **方案 A：Cube 语义层**（如需更强的指标管理和 BI 能力）
   - 在视图层之上部署 Cube 语义层
   - 利用 Cube 的 API 实现确定性 SQL 编译
   - 支持自助 BI + AI 查询双模式

2. **方案 B：QueryWeaver 知识图谱**（如多表 JOIN 仍是主要痛点）
   - 基于 FalkorDB 构建 schema 知识图谱
   - 显式建模表间隐含关系
   - 利用图遍历解决复杂 JOIN 路径

3. **预期收益**
   - 综合查询准确率提升到 80-90%
   - 复杂多表查询能力显著增强

### 技术选型建议

| 组件 | 推荐方案 | 理由 |
|------|---------|------|
| 元数据管理 | YAML/JSON 元数据文件 + 版本管理 | 简单直接，可与 Git 集成 |
| 高频查询 | Agent Tool (Function Calling) | 准确率高，渐进式添加 |
| 查询路由 | 基于意图分类的路由器 | 区分 Tool 可处理 vs 需要 SQL 的查询 |
| 数据抽象 | MySQL View | 不引入新依赖，直接在现有 MySQL 上实现 |
| Schema 裁剪 | AutoLink 思路的迭代探索 | 对 1660 表规模有验证，召回率高 |
| 语义层（Phase 3） | Cube | 多租户原生支持，AI 集成最成熟 |
| 知识图谱（Phase 3） | QueryWeaver + FalkorDB | 开源，支持 MySQL，内置 MCP |
| Text-to-SQL 框架 | DB-GPT 或自建多 Agent 管道 | 开源，支持多模型，可定制 |

---

## 参考资源

### 语义层
- [Cube - Semantic Layer and AI](https://cube.dev/blog/semantic-layer-and-ai-the-future-of-data-querying-with-natural-language)
- [Cube Multi-tenancy](https://cube.dev/docs/product/configuration/multitenancy)
- [dbt Semantic Layer](https://docs.getdbt.com/docs/use-dbt-semantic-layer/dbt-sl)
- [Semantic Layer Architectures Explained (2025)](https://www.typedef.ai/resources/semantic-layer-architectures-explained-warehouse-native-vs-dbt-vs-cube)

### 知识图谱
- [QueryWeaver - FalkorDB](https://github.com/FalkorDB/QueryWeaver)
- [Text-to-SQL with Knowledge Graphs: Multi-Hop Queries](https://www.falkordb.com/blog/text-to-sql-knowledge-graphs/)
- [Text2SQL Architecture with Knowledge Graphs and Agentic Framework](https://medium.com/@ranapratapdey/text2sql-architecture-empowered-by-knowledge-graphs-agentic-framework-and-semantic-memory-7d77fb7eef31)

### Schema Linking
- [RSL-SQL: Robust Schema Linking](https://arxiv.org/abs/2411.00073)
- [AutoLink: Autonomous Schema Exploration at Scale](https://arxiv.org/abs/2511.17190)
- [LinkAlign: Scalable Schema Linking for Large-Scale Text-to-SQL](https://aclanthology.org/2025.emnlp-main.51.pdf)
- [CRED-SQL: Real-world Large Scale Database Text-to-SQL](https://arxiv.org/html/2508.12769v3)

### 多 Agent 框架
- [MAC-SQL: Multi-Agent Collaborative Framework](https://arxiv.org/abs/2312.11242)
- [DB-GPT: Open Source AI Data Assistant](https://github.com/eosphoros-ai/DB-GPT)
- [Awesome-Text2SQL 资源汇总](https://github.com/eosphoros-ai/Awesome-Text2SQL)
- [LLM-based Text-to-SQL Survey (TKDE 2025)](https://github.com/DEEP-PolyU/Awesome-LLM-based-Text2SQL)

### 数据仓库分层
- [Data Warehouse Layering - Alibaba Cloud](https://www.alibabacloud.com/help/en/dataworks/user-guide/data-warehouse-layering)
- [Data Model Architecture: Four Layers and Seven Stages](https://dev.to/seatunnel/i-principles-of-data-model-architecture-four-layers-and-seven-stages-1deo)

### 企业级 Agent 平台
- [Salesforce Agentforce](https://www.salesforce.com/agentforce/einstein-copilot/)
- [Microsoft Copilot Studio - REST API Tools](https://learn.microsoft.com/en-us/microsoft-copilot-studio/agent-extend-action-rest-api)

### Text-to-SQL 准确率与优化
- [Google Cloud - Techniques for Improving Text-to-SQL](https://cloud.google.com/blog/products/databases/techniques-for-improving-text-to-sql)
- [AWS - Enriching Metadata for Accurate Text-to-SQL](https://aws.amazon.com/blogs/big-data/enriching-metadata-for-accurate-text-to-sql-generation-for-amazon-athena/)
- [Text-to-SQL for Enterprise Data Analytics](https://arxiv.org/html/2507.14372v1)
- [Long Context vs Schema Pruning (VLDB 2025)](https://www.vldb.org/pvldb/vol18/p2735-ozcan.pdf)

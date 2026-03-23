# 全房通 ChatBI 方案全景图

> 记录所有候选方案、选型分支和决策依据。随项目推进持续更新。

---

## 方案总览

```
ChatBI 解决方案
│
├── 1. Graph-Based（图谱方案）  ← 当前重点
│   ├── 1.1 Schema Graph（元数据图谱）
│   │   ├── 1.1.1 QueryWeaver + FalkorDB
│   │   ├── 1.1.2 自建 Schema Graph + Neo4j
│   │   └── 1.1.3 自建 Schema Graph + Kuzu（嵌入式）
│   │
│   ├── 1.2 Data Graph（数据实体图谱）
│   │   ├── 1.2.1 Kuzu 嵌入式 PoC
│   │   ├── 1.2.2 Neo4j 全量导入
│   │   └── 1.2.3 Apache AGE (PG 扩展)
│   │
│   ├── 1.3 GraphRAG（图增强检索生成）
│   │   ├── 1.3.1 Microsoft GraphRAG + LazyGraphRAG
│   │   ├── 1.3.2 Neo4j GraphRAG
│   │   └── 1.3.3 FalkorDB Graphiti Memory
│   │
│   └── 1.4 查询语言选型
│       ├── 1.4.1 Graph-enhanced Text-to-SQL（图辅助生成 SQL → MySQL 执行）
│       ├── 1.4.2 Text-to-Cypher（直接生成 Cypher → 图数据库执行）
│       └── 1.4.3 Hybrid（简单查询走 SQL，关系查询走 Cypher）
│
├── 2. Semantic Layer（语义层方案）
│   ├── 2.1 Wren AI（开源 GenBI，13k stars）
│   ├── 2.2 Cube.js（API-first 语义层，多租户原生）
│   └── 2.3 dbt Semantic Layer + MetricFlow
│
├── 3. Text-to-SQL（直接生成方案）
│   ├── 3.1 Baseline（原始 schema 直投）
│   ├── 3.2 Metadata Enhanced（元数据增强）
│   ├── 3.3 Schema Pruning（AutoLink 式动态裁剪）
│   ├── 3.4 Multi-Agent（MAC-SQL / CHASE-SQL 多 Agent 协作）
│   └── 3.5 专用模型（SQLCoder-70B / XiYan-SQL）
│
├── 4. API/Tool（封装方案）
│   ├── 4.1 Agent Tool 混合路由
│   ├── 4.2 MCP Server 封装
│   └── 4.3 CLI-Anything 自动化
│
└── 5. Hybrid（组合方案）
    ├── 5.1 Schema Graph + Semantic Layer + Tool 路由
    ├── 5.2 QueryWeaver + Wren AI + MCP
    └── 5.3 Data Graph + Text-to-SQL fallback
```

---

## 1. Graph-Based 方案详细分支

### 1.1 Schema Graph（元数据图谱）

**核心思路**：图谱只存表/列/关系的元数据，不存业务数据。AI 通过图遍历理解 schema → 生成 SQL → 在 MySQL 执行。

#### 1.1.1 QueryWeaver + FalkorDB

| 维度 | 说明 |
|------|------|
| 图数据库 | FalkorDB（Redis 协议，轻量） |
| 图谱内容 | 表→节点，列→属性，关系→边 |
| AI 接口 | 内置 MCP Server，Claude 直接调用 |
| 查询语言 | 最终生成 SQL 在 MySQL 执行 |
| 学习能力 | Graphiti memory 记住查询模式 |
| Stars | QueryWeaver ~384, FalkorDB ~3.7k |
| 成熟度 | 2025.09 发布，较新但活跃 |
| 部署 | Docker: FalkorDB + QueryWeaver Server |

**优势**：开箱即用、MySQL 原生支持、MCP 集成、零数据迁移
**劣势**：项目较新（star 少）、社区小、定制化空间有限
**适合**：快速验证图增强 Text-to-SQL 的效果

#### 1.1.2 自建 Schema Graph + Neo4j

| 维度 | 说明 |
|------|------|
| 图数据库 | Neo4j Community Edition |
| 图谱内容 | 自定义 schema 图谱（表/列/关系/业务语义/枚举映射） |
| AI 接口 | Neo4j MCP Server（官方） |
| 查询语言 | 图遍历找 JOIN 路径 → 生成 SQL |
| Stars | Neo4j ~14k |
| 成熟度 | 最成熟的图数据库生态 |

**优势**：生态最强、工具最多、可高度定制
**劣势**：需要自己写图谱导入和查询逻辑
**适合**：需要深度定制 schema 理解能力

#### 1.1.3 自建 Schema Graph + Kuzu（嵌入式）

| 维度 | 说明 |
|------|------|
| 图数据库 | Kuzu（嵌入式，无需独立服务） |
| 部署 | `pip install kuzu`，零运维 |
| 查询 | Cypher 兼容 |
| 性能 | 列存储，分析查询快 |

**优势**：最轻量、Python 原生、零运维、适合 PoC
**劣势**：无分布式、无 MCP Server（需自建）、社区小
**适合**：本地快速验证图模型设计是否合理

---

### 1.2 Data Graph（数据实体图谱）

**核心思路**：将 MySQL 业务数据清洗后导入图数据库，存储为 15 类节点 + 16 类关系。可以直接在图上查询。

#### 1.2.1 Kuzu 嵌入式 PoC

选一个公司的数据子集，全流程验证：MySQL → ETL → Kuzu → 查询。

**验证目标**：图模型设计是否合理、多跳查询效果、性能基线

#### 1.2.2 Neo4j 全量导入

全量数据导入 Neo4j，建立增量同步机制。

**验证目标**：生产级可行性、大数据量性能、与 AI 集成效果

#### 1.2.3 Apache AGE (PostgreSQL)

在 PostgreSQL 上用图扩展，SQL + Cypher 混合查询。

**注意**：全房通用 MySQL，引入 PG 成本较高，优先级低。

---

### 1.3 GraphRAG（图增强检索生成）

**核心思路**：用图谱作为 RAG 的知识库，AI 查询时检索相关的图上下文来增强生成。

#### 1.3.1 Microsoft GraphRAG + LazyGraphRAG

- 28k stars，最热门的 GraphRAG 实现
- LazyGraphRAG 将索引成本降低 99%
- **但**：主要面向非结构化文本，不直接面向数据库查询
- **可借鉴**：社区摘要思想用于 schema 文档自动生成

#### 1.3.2 Neo4j GraphRAG

- Neo4j 原生的 RAG 集成
- 知识图谱 + 向量搜索
- 适合"从图中检索相关 schema 信息"

#### 1.3.3 FalkorDB Graphiti Memory

- QueryWeaver 内置的 agentic memory
- 记住用户查询模式，越用越准
- 适合 SaaS 场景（同一公司重复查询模式相似）

---

### 1.4 查询语言选型

| 方案 | 最终执行 | 准确率参考 | 适合场景 |
|------|---------|-----------|---------|
| **1.4.1 Graph-enhanced Text-to-SQL** | MySQL | Text-to-SQL ~89-93% | 聚合统计、报表类查询 |
| **1.4.2 Text-to-Cypher** | Graph DB | Text-to-Cypher ~60% | 多跳关系查询 |
| **1.4.3 Hybrid** | 按查询类型路由 | 综合 ~80% | 兼顾两种场景 |

**关键数据点**：
- Text-to-SQL 最优可达 93%（SQLCoder-70B）
- Text-to-Cypher 最优仅 60%（gpt-4o on CypherBench）
- **结论**：图应辅助 SQL 生成，而非替代 SQL

---

## 2-5 其他方案（待展开）

> 当前聚焦 Graph-Based 方案。其他方案在后续 Phase 中展开。

### 2. Semantic Layer
- Wren AI / Cube.js / dbt — 语义模型定义业务指标，确定性编译 SQL

### 3. Text-to-SQL
- Baseline / 元数据增强 / Schema 裁剪 / 多 Agent / 专用模型

### 4. API/Tool
- Agent Tool 路由 / MCP Server / CLI-Anything

### 5. Hybrid
- 多方案组合，按查询复杂度路由

---

## 决策日志

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-03-23 | 优先探索 Graph-Based 方案 | 核心痛点是表间关系隐蔽（4848个隐式关联），图谱最直接解决此问题 |
| 2026-03-23 | Text-to-Cypher 准确率偏低，优先 Graph-enhanced Text-to-SQL | CypherBench 最优仅 60%，Text-to-SQL 可达 93% |
| 2026-03-23 | 数据留在 MySQL，图谱存元数据/关系 | 避免大规模数据迁移，降低实施风险 |

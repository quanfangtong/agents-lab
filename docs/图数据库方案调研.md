# 图数据库 + AI 查数最新技术调研报告（2025-2026）

> 调研时间：2026-03-23
> 调研范围：图数据库、AI 查数（Text-to-SQL / Text-to-Cypher）、ChatBI 开源项目、数据治理工具、MCP 集成方案

---

## 一、图数据库 + AI 查数核心方案

### 1.1 FalkorDB + QueryWeaver（重点推荐）

| 项目 | 详情 |
|------|------|
| 发布时间 | 2025 年 9 月（QueryWeaver）；FalkorDB 持续更新 |
| GitHub Stars | FalkorDB: ~3.7k；QueryWeaver: ~384 |
| 开源 | 是（Apache 2.0） |
| 官网 | https://www.queryweaver.ai/ |
| 仓库 | https://github.com/FalkorDB/QueryWeaver |

**核心机制：**
- 用图数据库（FalkorDB）存储 schema 元数据（表、列作为节点，外键/关联作为边）
- 当 LLM 收到复杂查询时，通过图遍历（graph traversal）找到中间表，解决多跳 JOIN 问题
- 用 Graphiti 做聊天历史和 agentic memory，记住用户查询模式，逐步提升准确率

**关键特性：**
- **Graph-powered Schema Understanding**：不是给 LLM 喂表和列的列表，而是喂入一个知识图谱，让 LLM 理解"客户"是什么、如何关联到"订单"、"活跃用户"在业务中的定义
- **支持 MySQL 和 PostgreSQL**
- **内置 MCP Server**：可直接与 Claude 等 AI 客户端集成
- **Python SDK**（2026.02 新增）：支持 Serverless Text-to-SQL
- **Snowflake Loader**（2026.01 新增）

**对全房通的适用性评估：** ★★★★★
- 直接支持 MySQL，无需迁移数据
- 图谱存储 schema 元数据而非数据本身，引入成本低
- 专为"大量表+复杂关联"的企业场景设计
- 内置 MCP Server，可直接接入 Claude
- 学习型 memory 适合 SaaS 场景的重复查询模式

---

### 1.2 Neo4j + GraphRAG + LLM

| 项目 | 详情 |
|------|------|
| 更新时间 | 持续更新（2025-2026） |
| GitHub Stars | neo4j/neo4j: ~14k；llm-graph-builder: ~3k+ |
| 开源 | 社区版开源（GPLv3）；企业版商业 |
| MCP Server | https://github.com/neo4j/mcp（官方） |

**核心能力：**
- **LLM Knowledge Graph Builder**：用 LLM（OpenAI、Gemini、Claude 等）从非结构化文本构建知识图谱
- **GraphRAG**：知识图谱 + RAG，通过图遍历回答多跳问题
- **Text-to-Cypher**：自然语言转 Cypher 查询
- **MCP Server**：官方 MCP 服务器，支持 get-neo4j-schema、read-neo4j-cypher、write-neo4j-cypher

**Text-to-Cypher 准确率基准（2025-2026）：**

| 基准 | 模型 | 准确率 | 来源 |
|------|------|--------|------|
| CypherBench（2025） | gpt-4o | 60.18% | ACL 2025 |
| CypherBench | <10B 参数模型 | <20% | ACL 2025 |
| Mind the Query（EMNLP 2025） | 多模型 | 27,529 NL-Cypher 对 | IBM Research |
| SynthCypher 微调 | CodeLlama-13B | 69.2% | ScienceDirect 2025 |
| Text2GQL-Bench（2026.02） | 多模型 | 最新多域基准 | arXiv |

**对全房通的适用性评估：** ★★★☆☆
- 需要将数据导入 Neo4j 或维护双存储
- Text-to-Cypher 准确率（60%）低于 Text-to-SQL
- 更适合"已有知识图谱"或"需要从文本构建图谱"的场景
- 对于纯关系数据库查数，引入过重

---

### 1.3 Apache AGE（PostgreSQL 图扩展）

| 项目 | 详情 |
|------|------|
| 更新时间 | 持续更新 |
| GitHub Stars | ~2.3k |
| 开源 | 是（Apache 2.0） |

**核心能力：**
- PostgreSQL 扩展，在同一数据库中同时支持关系查询（SQL）和图查询（openCypher）
- LangChain 集成：可实现自然语言→图查询
- MCP Server：`rioriost-age-graph`，LLM 自然语言→Cypher→AGE 执行

**对全房通的适用性评估：** ★★☆☆☆
- 全房通用的是 MySQL 而非 PostgreSQL
- 如果考虑迁移到 PostgreSQL 则可以考虑
- 可作为"混合图+关系查询"的备选方案

---

### 1.4 Microsoft GraphRAG

| 项目 | 详情 |
|------|------|
| 最新版本 | v3.0.6（2026.03.06）；v2.7.0（2026.01.27） |
| GitHub Stars | ~28k |
| 开源 | 是（MIT） |
| 仓库 | https://github.com/microsoft/graphrag |

**核心能力：**
- 从文本中提取实体和关系，构建知识图谱
- Leiden 算法做社区聚类，LLM 生成社区摘要
- **LazyGraphRAG**（2025.06）：将社区摘要推迟到查询时生成，索引成本降低 99%
- 动态社区选择：计算成本降低 77%

**对全房通的适用性评估：** ★★☆☆☆
- 主要面向非结构化文本的知识图谱构建
- 不直接面向"从关系数据库查数"的场景
- 但其社区摘要思想可借鉴用于 schema 文档自动生成

---

## 二、ChatBI 开源项目对比（2025-2026）

### 2.1 对比总览

| 项目 | Stars | 开源 | 核心特点 | MySQL 支持 | 图谱能力 | 最新更新 |
|------|-------|------|----------|------------|----------|----------|
| **QueryWeaver** | ~384 | 是 | 图驱动 Text-to-SQL | 是 | 核心特性 | 2026.02 |
| **Wren AI** | ~13k | 是 | 语义层 GenBI | 是 | 无 | 2026 活跃 |
| **Chat2DB** | ~30k | 是 | AI 数据库客户端 | 是 | 无 | 2026 活跃 |
| **DB-GPT** | ~15k | 是 | AI 数据应用框架 | 是 | 无（RAG） | 2026 活跃 |
| **Vanna 2.0** | ~13k | 是 | Agent 式 Text-to-SQL | 是 | 无（RAG） | 2025 重写 |
| **Defog SQLCoder** | ~3k | 是 | 专用 NL2SQL 模型 | 是 | 无 | 持续更新 |
| **XiYan-SQL** | ~1k | 是 | 多生成器集成框架 | 是 | 无 | 2025 活跃 |
| **OpenChatBI** | 新项目 | 是 | LangGraph+LangChain | 是 | 无 | 新项目 |
| **DataLine** | ~1k | 是 | 隐私优先数据分析 | 是 | 无 | 活跃 |

### 2.2 重点项目详情

#### Wren AI（★★★★☆ 推荐）

- **定位**：开源 GenBI（生成式 BI）解决方案
- **核心机制**：语义层（Semantic Layer）+ LLM，将业务术语映射到数据源，定义关系和预计算指标
- **2025 进展**：集成 Apache DataFusion 到 Wren Engine，解耦语义层与数据仓库
- **2026 方向**：Agentic BI，Human-in-the-Loop 反馈循环
- **特色**：Text-to-SQL + Text-to-Chart + 报表生成
- **官网**：https://www.getwren.ai/

#### Chat2DB（★★★☆☆）

- **定位**：AI 驱动的数据库管理工具 + SQL 客户端
- **Stars**：30k+，GitHub 上最受欢迎的 Text-to-SQL 工具
- **能力**：NL→SQL 转换、SQL 优化建议、跨平台（Win/Mac/Linux）
- **局限**：更像是增强版数据库客户端，不是完整 ChatBI 平台
- **仓库**：https://github.com/CodePhiliaX/Chat2DB

#### DB-GPT（★★★☆☆）

- **定位**：AI 原生数据应用开发框架
- **核心**：AWEL（Agentic Workflow Expression Language）+ 多 Agent 协作 + Text2SQL + RAG
- **能力**：多模型管理（SMMF）、Text2SQL 微调框架、知识库管理、数据分析报告生成
- **局限**：框架较重，学习曲线陡峭
- **仓库**：https://github.com/eosphoros-ai/DB-GPT

#### Vanna 2.0（★★★★☆）

- **定位**：Agent 式 Text-to-SQL 框架（2025 完全重写）
- **新架构**：从简单 SQL 生成库演进为生产就绪的用户感知 Agent 框架
- **特色**：
  - 行级安全（Row-Level Security）
  - 用户上下文自动注入
  - 审计日志
  - Web-first：内置 `<vanna-chat>` 组件
- **仓库**：https://github.com/vanna-ai/vanna

#### Defog SQLCoder（★★★☆☆）

- **定位**：专用 Text-to-SQL 大模型
- **性能**：SQLCoder-70B 达 93%+ 准确率，超过 GPT-4
- **特色**：可本地部署，CC BY-SA 4.0 许可
- **适用**：需要自托管高精度 SQL 生成的场景

#### XiYan-SQL / XiYan GBI（★★★☆☆）

- **来源**：阿里云百炼
- **开源模型**：XiYanSQL-QwenCoder 系列（3B/7B/14B/32B）
- **性能**：Spider 89.65%，Bird 72.23%
- **特色**：多生成器集成，Schema 召回 + SQL 生成 + SQL 执行三段式
- **适用**：中文场景友好

---

## 三、数据治理和自动化元数据工具

### 3.1 Schema 自动发现和关系推断

| 工具/方法 | 类型 | 适用场景 | 时间 |
|-----------|------|----------|------|
| **QueryWeaver Schema Import** | 开源 | MySQL/PG schema 自动导入为图 | 2025.09 |
| **AI-Driven Relationship Generation** (Salesforce) | 商业 | 自动推断表间关系 | 2025 |
| **DB Designer AI** | 商业 | AI 辅助数据库设计 | 2025-2026 |
| **LLM-based Schema Linking** (EDBT 2026) | 学术 | 大规模 schema 的列匹配 | 2026 |

**关键发现：**
- 2025 年 AI 辅助 schema 设计使迭代时间减少 62%
- AI 工具可通过自动分析发现共享键、映射一对一/一对多/多对多关系
- 即使缺少显式外键约束，也能通过列名相似度和数据模式推断关系
- QueryWeaver 的 schema import 功能正是为此设计的

### 3.2 数据血缘分析工具

| 工具 | Stars | 开源 | 核心能力 |
|------|-------|------|----------|
| **OpenLineage + Marquez** | ~2.5k | 是 | 开放标准 + 血缘收集/可视化 |
| **OpenMetadata** | ~6k+ | 是 | 元数据管理 + 表级/列级血缘 + SQL 日志解析 |
| **Apache Atlas** | ~1.8k | 是 | 元数据管理 + 血缘追踪 |
| **LINEAGEX** | 轻量级 | 是 | Python 库，SQL 脚本列级血缘提取 |

**对全房通的适用性评估：**
- **OpenMetadata** 最适合：支持 MySQL、SQL 日志解析构建血缘、列级别血缘，可用于理解 1660+ 张表的数据流向
- **LINEAGEX** 可用于从现有 SQL 脚本中提取列级血缘

### 3.3 宽表分解 → 实体提取

**学术方法论（2025-2026）：**

将宽表分解为知识图谱的流程：
1. **节点提取**：每列分配节点类型（实体、属性等）
2. **属性分类**：识别每列的属性类型（名称、值、标识符等）
3. **节点聚合**：将代表同一实体不同属性的列聚合
4. **关系提取**：分解联合实体-关系提取为头实体识别和尾实体+关系识别

**实用工具：**
- Neo4j LLM Knowledge Graph Builder：可从表格数据构建图谱
- PingCAP 的 LLM 实体提取方案：用 LLM 从表结构中提取实体和关系

---

## 四、Graph + MCP 集成方案

### 4.1 已有 MCP Server

| MCP Server | 数据库 | 特性 | 成熟度 |
|------------|--------|------|--------|
| **neo4j/mcp** | Neo4j | 官方，schema 查询/Cypher 读写 | 生产就绪 |
| **FalkorDB-MCPServer** | FalkorDB | OpenCypher 查询，图管理 | 稳定 |
| **QueryWeaver MCP** | MySQL/PG (via FalkorDB) | NL→SQL，图驱动 | 新但活跃 |
| **AGE Graph MCP** | PostgreSQL+AGE | NL→Cypher→AGE | 社区 |
| **Cognee MCP** | 多种 | Graph-RAG for Agents | 新 |
| **TigerGraph MCP** | TigerGraph | Schema 管理+GSQL+向量搜索 | 新 |
| **Graphiti KG MCP** | FalkorDB | 知识图谱 memory | 稳定 |

### 4.2 MCP 生态现状（2026.03）

- MCP 协议自 2025 年初以来快速增长，MCP Server 目录已超 12,430 个
- Google Cloud 已为 AlloyDB、Spanner、Cloud SQL 推出托管 MCP 支持
- MongoDB 发布 Winter 2026 MCP Server 更新，支持向量搜索索引
- Spanner Graph 支持 SQL + GQL 统一查询

---

## 五、针对全房通场景的技术选型建议

### 场景特点
- 3 个 MySQL 数据库，1660+ 张表（大量宽表）
- SaaS 租赁业务，有复杂的实体关系
- 非技术用户需要自然语言查数
- 需要高准确率（涉及业务数据）

### 推荐技术栈

#### 方案 A：QueryWeaver + Wren AI（首选，最轻量）

```
MySQL (数据源, 不动)
    |
    v
QueryWeaver (schema → FalkorDB 图谱)  ← 理解表间关系
    |
    v
Wren AI 语义层  ← 定义业务术语和计算指标
    |
    v
MCP Server (QueryWeaver 内置)  ← Claude 直接调用
    |
    v
用户自然语言查询 → SQL → MySQL 执行 → 结果返回
```

**优势：**
- MySQL 数据不动，零迁移成本
- FalkorDB 只存 schema 元数据（轻量）
- QueryWeaver 图遍历解决多跳 JOIN
- Wren AI 语义层编码业务规则
- 内置 MCP Server，Claude 原生集成
- Graphiti memory 学习查询模式

#### 方案 B：Vanna 2.0 + 自建 Schema 图谱

```
MySQL (数据源)
    |
    v
自建 Schema 图谱 (FalkorDB/Neo4j)  ← 存储表关系、业务语义
    |
    v
Vanna 2.0 Agent  ← RAG + Schema 图谱上下文
    |
    v
MCP Server (自建)
    |
    v
用户查询 → SQL → MySQL → 结果
```

**优势：**
- Vanna 2.0 的行级安全适合 SaaS 多租户
- 审计日志满足合规需求
- 更灵活的定制空间

#### 方案 C：DB-GPT 全家桶（重量级）

适合需要完整数据应用平台的场景，包含 Text2SQL、RAG、Agent、报表等全套能力，但学习曲线陡峭。

### 关键决策点

| 因素 | 方案 A | 方案 B | 方案 C |
|------|--------|--------|--------|
| 实施复杂度 | 低 | 中 | 高 |
| MySQL 兼容性 | 原生 | 原生 | 原生 |
| 图谱能力 | 内置 | 自建 | 无 |
| MCP 集成 | 内置 | 自建 | 需适配 |
| 多租户安全 | 需补充 | 内置 | 需配置 |
| 社区成熟度 | 新但活跃 | 成熟 | 成熟 |
| 中文支持 | 依赖 LLM | 依赖 LLM | 原生 |

---

## 六、2025-2026 关键趋势总结

1. **Graph + SQL 融合**：不再是"图数据库 vs 关系数据库"的二选一，而是用图来增强 SQL 查询的上下文理解（QueryWeaver 代表）
2. **语义层复兴**：Wren AI 验证了语义层对 Text-to-SQL 准确率的关键作用
3. **MCP 成为标准**：几乎所有数据库和 AI 工具都在接入 MCP，成为 AI 调用数据的标准协议
4. **Agentic BI**：从单次查询进化为多步推理、自我纠错的 Agent 式数据分析
5. **Text-to-Cypher 准确率仍偏低**：gpt-4o 在 CypherBench 上仅 60%，远低于 Text-to-SQL 的 90%+，因此不建议用 Cypher 作为主查询语言
6. **LazyGraphRAG**：索引成本降低 99%，使图谱方案在大规模场景中经济可行
7. **专用模型逼近通用模型**：SQLCoder-70B（93%）和 XiYan-SQL（89%）已接近或超过 GPT-4 的 SQL 生成能力

---

## 参考资料

### 图数据库 + AI
- [FalkorDB QueryWeaver GitHub](https://github.com/FalkorDB/QueryWeaver)
- [QueryWeaver 官网](https://www.queryweaver.ai/)
- [FalkorDB Text-to-SQL with Knowledge Graphs](https://www.falkordb.com/blog/text-to-sql-knowledge-graphs/)
- [Neo4j LLM Knowledge Graph Builder](https://neo4j.com/labs/genai-ecosystem/llm-graph-builder/)
- [Neo4j MCP Server](https://github.com/neo4j/mcp)
- [FalkorDB MCP Server](https://github.com/FalkorDB/FalkorDB-MCPServer)
- [Apache AGE](https://age.apache.org/)
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)

### Text-to-Cypher 基准
- [CypherBench (ACL 2025)](https://github.com/megagonlabs/cypherbench)
- [Mind the Query (EMNLP 2025)](https://research.ibm.com/publications/mind-the-query-a-benchmark-dataset-towards-text2cypher-task)
- [Text2GQL-Bench (2026)](https://arxiv.org/html/2602.11745)
- [SynthCypher](https://arxiv.org/html/2412.12612v1)

### ChatBI 开源项目
- [Wren AI](https://github.com/Canner/WrenAI)
- [Chat2DB](https://github.com/CodePhiliaX/Chat2DB)
- [DB-GPT](https://github.com/eosphoros-ai/DB-GPT)
- [Vanna AI](https://github.com/vanna-ai/vanna)
- [Defog SQLCoder](https://github.com/defog-ai/sqlcoder)
- [XiYan-SQL](https://github.com/XGenerationLab/XiYan-SQL)
- [OpenChatBI](https://github.com/zhongyu09/openchatbi)

### 数据治理
- [OpenLineage](https://openlineage.io/)
- [OpenMetadata](https://open-metadata.org/)
- [Awesome-Text2SQL](https://github.com/eosphoros-ai/Awesome-Text2SQL)

### MCP 生态
- [Neo4j MCP Integration Guide](https://neo4j.com/developer/genai-ecosystem/model-context-protocol-mcp/)
- [PulseMCP Server Directory](https://www.pulsemcp.com/servers)
- [Awesome MCP Servers](https://github.com/punkpeye/awesome-mcp-servers)

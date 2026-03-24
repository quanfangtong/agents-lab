# Text-to-SQL + 图增强 Benchmark 最佳实践调研

> 调研日期：2026-03-24
> 调研目的：为全房通 ChatBI benchmark 链路设计提供业界最佳实践参考

---

## 一、Multi-step Text-to-SQL 架构

### 1.1 业界共识：多步 Pipeline 优于端到端

业界已达成共识——将 Text-to-SQL 分解为多个阶段（3-5 步），每步专注于特定子任务，显著优于端到端单步生成。主流框架的步骤对比：

| 框架 | 步骤数 | 核心流程 | 代表性能 |
|------|--------|----------|----------|
| **CHESS** (Stanford) | 4 步 | 实体检索 → Schema 选择 → SQL 生成 → 单元测试 | BIRD 66.69% EX |
| **SQL-of-Thought** (NeurIPS'25) | 5 步 | Schema Linking → 子问题分解 → 查询计划 → SQL 生成 → 纠错循环 | Spider 91.59% EX |
| **MAC-SQL** (COLING'25) | 3 Agent | Selector → Decomposer → Refiner | Spider 85%+ EX |
| **ReFoRCE** (Snowflake) | 4 步 | Schema 压缩 → SQL 生成 → 共识投票 → 列探索 | Spider 2.0 SOTA |
| **DIN-SQL** | 4 步 | 分类 → Schema Linking → SQL 生成 → 自纠错 | 早期基线 |

### 1.2 标准化的多步流程

综合分析以上框架，业界标准流程可归纳为以下阶段：

```
用户问题
  │
  ▼
[Step 1] 意图分类 & 问题路由
  │  输入：用户自然语言问题
  │  输出：问题类型（查询/比较/排名/聚合等）、是否需要澄清
  │
  ▼
[Step 2] Schema Linking（表/列选择）
  │  输入：用户问题 + 完整 Schema
  │  输出：精简后的相关表和列子集
  │  方法：图遍历 / 双向检索 / LLM 过滤
  │
  ▼
[Step 3] 查询计划生成（可选但推荐）
  │  输入：用户问题 + 精简 Schema + 子问题分解
  │  输出：step-by-step 的查询执行计划（Chain-of-Thought）
  │
  ▼
[Step 4] SQL 生成
  │  输入：用户问题 + 精简 Schema + 查询计划
  │  输出：候选 SQL 语句
  │
  ▼
[Step 5] 验证 & 自纠错
  │  输入：SQL + 执行结果/错误信息
  │  输出：修正后的 SQL 或最终结果
  │  方法：执行反馈循环 / 分类纠错 / 共识投票
  │
  ▼
最终结果
```

### 1.3 Schema Linking 是关键瓶颈

Schema Linking（从大量表/列中选出相关子集）是整个流程中最关键的一步：

- **RSL-SQL**：双向 schema linking，严格召回率 94%
- **LinkAlign**：多轮语义增强检索 + 无关信息隔离 + Schema 提取增强，3 阶段流程
- **CHESS**：三级剪枝——单列过滤 → 表选择 → 最终列选择，使 token 减少 5x，准确率提升 ~2%
- **双向检索**：table-first + column-first 互补策略，比单向效果好

**全房通启示**：1660+ 张表的场景下，Schema Linking 的效果直接决定了整个 pipeline 的天花板。三级剪枝（CHESS 方案）和图遍历（QueryWeaver 方案）最值得借鉴。

### 1.4 模型选择策略

- **Schema Linking**：可用较小/快速模型（成本低、延迟低），因为这一步主要是匹配而非推理
- **SQL 生成**：需要最强推理能力的模型（如 GPT-5.4、Claude Opus 4.6）
- **自纠错**：与 SQL 生成使用同一强模型，或使用专门微调的模型
- **CHESS 方案**：不同 agent 可用不同模型，Schema Selector 用轻量模型，Candidate Generator 用强模型

---

## 二、Graph-enhanced Text-to-SQL

### 2.1 图谱在流程中的插入位置

图谱主要在 **Step 2 Schema Linking** 阶段发挥作用，具体有三种模式：

#### 模式 A：图谱作为 Schema 表示（QueryWeaver 方案）
```
数据库 Schema → 构建图谱（表=节点, FK=边）→ 图遍历找相关表 → 传递给 LLM
```
- 优点：能发现多跳关系（A→B→C），解决向量检索无法处理的结构性关联
- QueryWeaver 的核心创新：用图遍历找到"隐藏桥梁"（语义不相关但结构必需的中间表）

#### 模式 B：图谱作为知识增强（SQL-KG-Verifier）
```
LLM 生成初始 SQL → 知识图谱验证 SQL 的 JOIN 和约束 → 联合修正
```
- 将知识图谱的结构化信息与 LLM 的生成能力协同，提高结构一致性和可解释性

#### 模式 C：图谱 + 向量检索混合（推荐）
```
用户问题 → 向量检索（语义匹配）→ 候选表集
                                      ↓
             图遍历（结构补全）→ 补充必要的中间表/关联表
                                      ↓
                              最终精简 Schema
```

### 2.2 图谱搜索结果如何传递给 LLM

1. **Schema 子图 DDL**：将图遍历的结果（相关表+列+关系）转化为精简的 CREATE TABLE DDL 传入 prompt
2. **关系路径描述**：将表之间的 JOIN 路径以自然语言描述形式提供（如"房源表通过 room_id 关联合同表"）
3. **候选 JOIN 模板**：直接提供推荐的 JOIN 语句片段，降低 LLM 生成 JOIN 的错误率

### 2.3 LLM 驱动图谱搜索

业界已有 LLM 驱动图谱搜索的案例，而非硬编码规则：

- **AutoLink**：自主 Schema 探索和扩展，LLM 判断何时需要更多 schema 信息并触发图谱搜索
- **DCG-SQL**：LLM 构建深度上下文 Schema Link Graph，剪枝无关节点
- **CHESS 的 Schema Selector Agent**：LLM 扮演 agent 角色，逐步决定保留/丢弃哪些表和列

**全房通启示**：Phase 1 中 QueryWeaver 效果差的根因不是图谱方案本身，而是 Schema 图谱查询未有效生效。推荐采用**模式 C（向量+图混合）**，先用语义匹配缩小范围，再用图遍历补全 JOIN 路径。

---

## 三、LLM-as-Agent for SQL

### 3.1 自纠错机制

#### MAGIC（AAAI'25）：自动生成纠错指南
- 三个 Agent 协作：Manager、Correction、Feedback
- 在失败案例上迭代生成和精炼纠错指南
- 指南是 LLM 错误模式的"药方"，针对不同错误类型有不同修复策略

#### SQL-of-Thought：分类驱动纠错
- 定义 SQL 错误分类体系（schema linking 错误、JOIN 错误、嵌套错误、GROUP BY 错误等）
- 纠错时先分类错误类型，再针对性修复
- 避免"盲目重试"，提高纠错效率

#### ReFoRCE：共识 + 列探索
- 多线程并行生成候选 SQL
- 多数投票选择高置信度结果
- 对分歧大的 case 进入列探索环节，通过执行反馈迭代修正

### 3.2 执行反馈循环

业界标准模式——ReAct 风格的 Think-Act-Observe 循环：

```
Think:  分析问题和当前状态
Act:    生成/修改 SQL 并执行
Observe: 检查执行结果（成功/报错/结果异常）
  │
  ├── 成功且结果合理 → 返回
  ├── 语法错误 → 回到 Think，用错误信息修正
  ├── 执行超时 → 分析是否缺少过滤条件（如 company_id）
  └── 结果异常 → 回到 Think，检查逻辑
```

**MARS-SQL**（强化学习版本）将系统状态定义为元组：(对话历史, Schema, 候选 SQL, 记忆, 执行反馈)，Agent 的动作包括 propose / execute / verify / correct。

### 3.3 多轮对话上下文管理

- **Amazon Bedrock 方案**：意图分类器分析当前消息 + 近期对话历史，路由到不同 Agent
- **PRACTIQ**：实用型多轮 Text-to-SQL 数据集，区分上下文依赖和独立问题
- **Question Detector Agent**：在多轮交互中检测模糊/不可回答的问题，主动请求用户澄清

**全房通启示**：Phase 1 中的主要失败原因（全表扫描超时、缺少 company_id 过滤）正是自纠错机制可以解决的。应在 pipeline 中加入执行反馈循环，特别是超时检测和强制过滤条件注入。

---

## 四、Benchmark 评估设计

### 4.1 主流 Benchmark

| Benchmark | 规模 | 特点 | 主要指标 |
|-----------|------|------|----------|
| **Spider** | 10,181 问题, 200 DB | 跨域泛化，学术标准 | Test Suite Accuracy |
| **Spider 2.0** | 企业级 | 复杂 schema, 多 SQL 方言, 多步推理 | EX（仅 ~6%，极具挑战） |
| **BIRD** | 12,751 对, 95 DB, 33.4GB | 真实脏数据, 大规模 | EX + VES（效率分） |
| **Spider-Realistic** | Spider 变体 | 去除列名与问题的直接映射 | EX |

### 4.2 评估指标体系

#### 端到端指标
| 指标 | 说明 | 适用场景 |
|------|------|----------|
| **Execution Accuracy (EX)** | 执行结果是否与标注一致 | 最核心指标 |
| **Exact Set Match (EM)** | SQL 关键字集合是否匹配 | 辅助分析 |
| **Test Suite Accuracy** | 在多组数据库实例上验证 | Spider 官方指标 |
| **Valid Efficiency Score (VES)** | 在正确的基础上评估查询效率 | BIRD 创新指标 |

#### 部分匹配 & 组件级指标（新趋势）
| 指标 | 说明 | 优势 |
|------|------|------|
| **列级 Fractional EX** | 按列计算部分正确率 | 比 0/1 更细粒度 |
| **语义相似度分数** | SQL embedding 相似度 + 输出匹配 | 捕捉"接近正确"的情况 |
| **LLM-based 等价判断** | 用 LLM 判断两个 SQL 是否语义等价 | 处理等价但形式不同的 SQL |

#### 每步单独评估（推荐）
| 步骤 | 评估指标 | 说明 |
|------|----------|------|
| Schema Linking | 召回率 / F1 | 是否选出了所有必要的表和列 |
| 查询计划 | 人工评分 / LLM 评分 | 推理链的正确性和完整性 |
| SQL 生成 | EX / EM | 标准 SQL 正确性 |
| 自纠错 | 修复成功率 / 迭代次数 | 纠错的效率和有效性 |
| 端到端 | EX + VES + 延迟 | 综合表现 |

### 4.3 Benchmark 设计的新趋势

1. **从 Binary 到 Partial Credit**：不再只看"对/错"，引入部分得分机制
2. **效率纳入评估**：BIRD 的 VES 指标，评估查询执行效率
3. **错误类型分析**：不只报告总准确率，要分析失败案例的错误分布
4. **真实数据挑战**：从干净学术数据（Spider）转向脏数据（BIRD）和企业级数据（Spider 2.0）

**全房通启示**：benchmark 应包含 Schema Linking 召回率、SQL EX、VES（效率分，检测全表扫描）、以及错误类型分布分析。

---

## 五、全房通 ChatBI Benchmark 链路设计建议

### 5.1 推荐的 Pipeline 架构

基于调研结果，推荐采用 **5 步 Pipeline + 图增强 Schema Linking**：

```
用户问题: "公司1293上个月的应收账单有多少？"
  │
  ▼
[Step 1] 意图分析 & 路由（轻量模型）
  │  • 问题分类：聚合查询
  │  • 涉及领域：财务（账单）
  │  • 时间范围：上个月
  │  • 强制参数检测：需要 company_id = 1293
  │
  ▼
[Step 2] Schema Linking（图 + 向量混合）
  │  • 向量检索：从精简的 ~30-40 核心表中语义匹配候选表
  │  • 图遍历（Kuzu）：补全 JOIN 路径，发现必要的中间表
  │  • LLM 过滤：最终确认保留哪些表/列
  │  • 输出：精简 Schema DDL（~5-10 表）
  │
  ▼
[Step 3] 查询计划生成（强模型）
  │  • Chain-of-Thought 推理
  │  • 输出 step-by-step 的查询逻辑
  │  • 包含强制过滤条件（company_id = 1293）
  │
  ▼
[Step 4] SQL 生成（强模型）
  │  • 基于精简 Schema + 查询计划生成 SQL
  │  • 可并行生成多个候选，投票选最佳
  │
  ▼
[Step 5] 执行 & 自纠错（最多 3 轮）
  │  • 执行 SQL，检查结果
  │  • 超时 → 检查是否缺少 company_id 过滤
  │  • 语法错误 → 分类错误类型，针对性修复
  │  • 结果异常 → 重新推理
  │
  ▼
返回结果 + 解释
```

### 5.2 推荐的 Benchmark 评估框架

```yaml
benchmark:
  测试集:
    - 12 道基础测试题（复用 Phase 1）
    - 按难度分级：简单(单表) / 中等(2-3表JOIN) / 困难(多表+子查询+聚合)
    - 按领域分类：房源 / 租客 / 合同 / 账单 / 财务 / 基础数据

  评估指标:
    端到端:
      - execution_accuracy: SQL 执行结果是否正确
      - valid_efficiency_score: 查询是否高效（无全表扫描）
      - latency: 端到端响应时间

    组件级:
      - schema_linking_recall: 是否选出了所有必要的表/列
      - schema_linking_precision: 是否混入了无关表/列
      - plan_quality: 查询计划的逻辑正确性（LLM 评分）
      - sql_syntax_valid: SQL 是否语法正确
      - correction_success_rate: 自纠错的修复成功率
      - correction_iterations: 纠错平均迭代次数

    错误分析:
      - error_distribution: 错误类型分布（schema错误/JOIN错误/过滤遗漏/超时等）
      - failure_root_cause: 失败根因分类
```

### 5.3 关键设计原则

1. **Schema Linking 先行**：在 1660+ 表的环境下，Schema Linking 的召回率决定了 pipeline 天花板。建议先单独优化和评估这一步。

2. **强制 company_id 过滤**：Phase 1 的主要失败原因是全表扫描超时。在查询计划阶段强制注入 `WHERE company_id = ?` 是最直接的改进。

3. **图遍历补全 JOIN 路径**：Kuzu Schema Graph 已经验证了可行性。关键是确保图谱查询真正生效（Phase 1 的 QueryWeaver 未做到这一点）。

4. **执行反馈循环**：加入 ReAct 风格的自纠错循环（最多 3 轮），特别是超时检测和强制过滤条件注入。

5. **每步可独立评估**：benchmark 框架应支持单步评估（仅测 Schema Linking、仅测 SQL 生成等），便于定位瓶颈。

---

## 参考资料

### Multi-step Pipeline
- [MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL](https://arxiv.org/abs/2312.11242) - COLING 2025
- [SQL-of-Thought: Multi-agentic Text-to-SQL with Guided Error Correction](https://arxiv.org/abs/2509.00581) - NeurIPS DL4C 2025
- [CHESS: Contextual Harnessing for Efficient SQL Synthesis](https://arxiv.org/html/2405.16755v1) - Stanford, BIRD SOTA
- [ReFoRCE: A Text-to-SQL Agent with Self-Refinement](https://arxiv.org/abs/2502.00675) - Snowflake, Spider 2.0 SOTA

### Schema Linking
- [RSL-SQL: Robust Schema Linking in Text-to-SQL Generation](https://arxiv.org/pdf/2411.00073)
- [LinkAlign: Scalable Schema Linking for Real-World Large-Scale Databases](https://aclanthology.org/2025.emnlp-main.51.pdf) - EMNLP 2025
- [AutoLink: Autonomous Schema Exploration and Expansion](https://arxiv.org/html/2511.17190)
- [In-depth Analysis of LLM-based Schema Linking](https://research.ibm.com/publications/in-depth-analysis-of-llm-based-schema-linking) - IBM Research, EDBT 2026

### Graph-enhanced
- [QueryWeaver - FalkorDB](https://www.falkordb.com/blog/text-to-sql-knowledge-graphs/)
- [SQL Statement Generation Enhanced Through the Fusion of LLMs and Knowledge Graphs](https://www.mdpi.com/2079-9292/15/2/278)

### Self-Correction
- [MAGIC: Generating Self-Correction Guideline for In-Context Text-to-SQL](https://ojs.aaai.org/index.php/AAAI/article/view/34511) - AAAI 2025
- [MARS-SQL: Multi-Agent Reinforcement Learning for Text-to-SQL](https://arxiv.org/html/2511.01008v1)
- [ExeSQL: Self-Taught Text-to-SQL Models with Execution Feedback](https://aclanthology.org/2025.findings-emnlp.1320.pdf) - EMNLP 2025

### Benchmark & Evaluation
- [Text-to-SQL Evaluation Benchmarks & Metrics Guide](https://promethium.ai/guides/text-to-sql-evaluation-benchmarks-metrics/)
- [BIRD Benchmark Analysis](https://medium.com/@adnanmasood/pushing-towards-human-level-text-to-sql-an-analysis-of-top-systems-on-bird-benchmark-666efd211a2d)
- [Redefining Text-to-SQL Metrics by Incorporating Semantic and Structural Similarity](https://www.nature.com/articles/s41598-025-04890-9) - Nature Scientific Reports 2025
- [Analysis of Text-to-SQL Benchmarks: Limitations, Challenges and Opportunities](https://openproceedings.org/2025/conf/edbt/paper-41.pdf) - EDBT 2025
- [Expert-level False-Less Execution Metric](https://aclanthology.org/2025.naacl-long.228.pdf) - NAACL 2025

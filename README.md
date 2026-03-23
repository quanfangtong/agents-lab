# Agents Lab - ChatBI 实验项目

这是一个用于探索和测试智能问数（ChatBI）解决方案的实验仓库。项目包含多种 Text-to-SQL、智能 BI 和 Agent 问答方案的实现和性能对比。

## 项目背景

全房通业务拥有庞大的宽表数据库，包含用户、租户、房源、财务等多个业务领域的数据。本项目旨在探索如何使用大语言模型和 Agent 技术实现智能数据问答系统。

## 数据库架构

项目连接三个核心数据库：

- **qft_basics**: 基础数据（用户、租户、物业地址等）
- **qft_lease**: 租赁业务数据（房源、租客相关）
- **qft_finance**: 财务数据（流水、账单等）

## 项目结构

```
agents-lab/
├── common/                      # 公共模块
│   ├── database/               # 数据库连接和查询工具
│   │   ├── connection.py       # 数据库连接管理
│   │   └── inspector.py        # 数据库schema检查工具
│   ├── llm/                    # LLM客户端
│   │   ├── client.py           # OpenRouter API客户端
│   │   └── models.py           # 模型类型定义
│   └── utils/                  # 工具函数
│       ├── logger.py           # 日志配置
│       └── timer.py            # 性能计时器
│
├── solutions/                   # 各种解决方案实现
│   ├── text2sql/               # 纯Text-to-SQL方案
│   ├── rag_enhanced/           # RAG增强方案
│   ├── semantic_layer/         # 语义层方案
│   ├── agent_framework/        # Agent框架方案
│   └── hybrid/                 # 混合方案
│
├── benchmarks/                  # 性能测试和对比
│   ├── test_cases/             # 测试用例
│   └── results/                # 测试结果
│
├── scripts/                     # 实用脚本
│   └── explore_database.py     # 数据库探索脚本
│
├── data/                        # 数据文件
│   └── schema/                 # 数据库schema信息
│
├── docs/                        # 文档
│
├── .env                        # 环境变量配置（不提交到git）
├── .env.example                # 环境变量模板
├── requirements.txt            # Python依赖
├── pyproject.toml              # 项目配置
└── README.md                   # 项目说明
```

## 技术栈

### 数据库
- MySQL (通过 PyMySQL 和 SQLAlchemy 连接)

### LLM 模型 (通过 OpenRouter)
- GPT-5.4 (OpenAI)
- Claude Opus 4.6 (Anthropic)

### 开发工具
- Python 3.10+
- Pandas (数据处理)
- LangChain (LLM 应用框架)
- Loguru (日志)
- Rich (命令行美化)

## 快速开始

### 1. 环境配置

克隆仓库：
```bash
git clone https://github.com/quanfangtong/agents-lab.git
cd agents-lab
```

复制环境变量模板：
```bash
cp .env.example .env
```

编辑 `.env` 文件，填入实际的配置信息。

### 2. 安装依赖

使用 pip：
```bash
pip install -r requirements.txt
```

或使用 pip (editable 模式):
```bash
pip install -e .
```

### 3. 探索数据库

运行数据库探索脚本：
```bash
python scripts/explore_database.py
```

这将生成数据库的 schema 概览，保存在 `data/schema/` 目录。

## 解决方案概览

### 1. Text-to-SQL
纯粹的自然语言转 SQL 查询方案。

**优势**: 简单直接
**挑战**: 复杂查询、宽表处理

### 2. RAG Enhanced
使用 RAG 增强上下文理解。

**优势**: 更好的 schema 理解
**挑战**: 检索质量、延迟

### 3. Semantic Layer
构建语义层抽象数据模型。

**优势**: 业务友好、可维护
**挑战**: 需要预先建模

### 4. Agent Framework
多 Agent 协作处理复杂查询。

**优势**: 处理复杂场景
**挑战**: 成本、可靠性

### 5. Hybrid
混合多种方案的优势。

## Benchmark 方法

每个方案将使用统一的测试集进行评估：

- **准确性**: SQL 查询正确性、结果准确性
- **性能**: 响应时间、Token 消耗
- **鲁棒性**: 错误处理、边界情况
- **可扩展性**: 支持的查询复杂度

结果将保存在 `benchmarks/results/` 目录。

## 贡献指南

1. 在 `solutions/` 下创建新的解决方案目录
2. 实现统一的接口（待定义）
3. 添加测试用例和文档
4. 运行 benchmark 并提交结果

## 许可证

内部项目，仅供全房通团队使用。

## 联系方式

如有问题，请联系项目负责人。

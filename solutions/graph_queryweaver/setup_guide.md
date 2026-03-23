# G1: QueryWeaver + FalkorDB 方案测试

## 方案概述

使用 [FalkorDB](https://github.com/FalkorDB/FalkorDB) 图数据库存储数据库 schema 元数据，
结合 [QueryWeaver](https://github.com/FalkorDB/QueryWeaver) 的 Text2SQL 方法论，
通过图结构理解表间关系来辅助 LLM 生成 SQL。

### 核心思路

1. **Schema 图谱化**: 将 MySQL 的 table/column/FK 信息导入 FalkorDB 图
2. **图搜索找表**: 根据自然语言问题，在图中搜索相关的表和列
3. **构建上下文**: 从图中提取相关表的详细 schema 作为 LLM 上下文
4. **LLM 生成 SQL**: 将 schema 上下文 + 问题发送给 LLM 生成 SQL

## 环境要求

- Docker (FalkorDB)
- Python 3.12+
- MySQL 可访问（只读）

## 安装步骤

### 1. 启动 FalkorDB

```bash
docker run -d --name falkordb -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest
```

验证:
```bash
python -c "from falkordb import FalkorDB; print(FalkorDB().list_graphs())"
```

FalkorDB 浏览器界面: http://localhost:3000

### 2. 安装 Python 依赖

```bash
pip install falkordb pymysql python-dotenv loguru openai
```

### 3. 配置 .env

确保项目根目录 `.env` 包含:
```
DB_HOST=rm-m5eh84g28g1b1fee7co.mysql.rds.aliyuncs.com
DB_PORT=3306
DB_USERNAME=qft_read
DB_PASSWORD=d12E7Bs4lY
DB_BASICS=qft_basics
DB_LEASE=qft_lease
DB_FINANCE=qft_finance

OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### 4. 导入 Schema 到 FalkorDB

```bash
python solutions/graph_queryweaver/schema_importer.py
```

导入结果（约 2-3 分钟）:
- 3 个数据库: qft_basics (484 表), qft_lease (1060 表), qft_finance (100 表)
- 共 1644 张表, 27778 个列, 23 个 FK 关系
- 图名称: `qft_schema`

### 5. 运行 Benchmark

```bash
python solutions/graph_queryweaver/benchmark.py --model opus
```

结果输出到 `benchmarks/results/g1_queryweaver_results.json`

## QueryWeaver 完整版部署（可选）

QueryWeaver 支持 Docker 一键部署:

```bash
# 创建 .env
cat > /tmp/qw.env << EOF
FASTAPI_SECRET_KEY=my_secret_key
FALKORDB_URL=redis://host.docker.internal:6379/0
OPENAI_API_KEY=<your_key>
COMPLETION_MODEL=openai/gpt-4.1
EMBEDDING_MODEL=openai/text-embedding-ada-002
EOF

docker run -p 5000:5000 --env-file /tmp/qw.env falkordb/queryweaver
```

**注意**: QueryWeaver 完整版需要:
- Embedding API（OpenAI text-embedding-ada-002），OpenRouter 不支持 embedding
- 图向量索引用于语义搜索表
- OAuth 配置（可选）

本测试采用简化版本（不依赖 embedding），直接用关键词 + 图结构搜索。

## 图模型

```
(:Database {name, description})
(:Table {name, db, description, row_count, column_count})
(:Column {name, type, nullable, key_type, description, ordinal})

(:Table)-[:IN_DATABASE]->(:Database)
(:Column)-[:BELONGS_TO]->(:Table)
(:Column)-[:REFERENCES {constraint}]->(:Column)   -- FK 关系
```

## QueryWeaver 方法论分析

### 优势
1. **图结构天然适合 schema 表示**: table-column-FK 就是图
2. **向量索引 + 图遍历** 找相关表比纯文本搜索更精确（完整版）
3. **FK 关系遍历** 可以发现间接相关的表
4. **MCP 集成**: QueryWeaver 内置 MCP server 端点

### 全房通场景的挑战
1. **FK 极少（23/1644 表仅 1.4%）**: 图遍历效果有限，大部分关系是隐式的
2. **表太多（1644 张）**: 关键词搜索噪音大，需要更好的过滤策略
3. **三模式平行表**: whole/joint/focus 三套表需要同时查询
4. **中文业务概念映射**: 需要中文到英文表名/列名的映射
5. **宽表（最宽 131 列）**: schema 上下文会很大，容易超过 token 限制

### 改进方向
1. 为全房通添加 **隐式关系推断**（基于列名匹配，如 company_id -> company.id）
2. 建立 **中文业务术语到表名的映射字典**
3. 使用 **表重要性排序**（按数据量、查询频率等）
4. 限制 schema 上下文中的列数（只传关键列）

## 文件说明

| 文件 | 说明 |
|------|------|
| `schema_importer.py` | MySQL schema 导入 FalkorDB 图 |
| `benchmark.py` | Text2SQL benchmark 测试脚本 |
| `setup_guide.md` | 本文件 |

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

全房通 ChatBI 实验项目 — 探索如何对大规模 SaaS 宽表数据库实现 AI 智能查数。通过不同方案对比 Benchmark，寻找最优的数据架构重构和 AI 查询路径。

## Database

- **只读账号**，不可修改原始表结构
- 三个库通过 `db_name` 参数切换：`"basics"` / `"lease"` / `"finance"`
- SQLAlchemy 2.x 要求原始 SQL 用 `text()` 包裹：`conn.execute(text("SELECT ..."))`
- 核心挑战：1660+ 张宽表（最宽 131 列）、三种业务模式平行表（整租/合租/集中式）、4848 个隐式关联但 0 个外键、财务表按 company_id 分片 14 张同构表

## Commands

```bash
pip install -r requirements.txt
python scripts/test_connection.py
python scripts/explore_database.py
```

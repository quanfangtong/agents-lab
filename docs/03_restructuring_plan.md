# 全房通 ChatBI 数据层拆分与剪枝方案

> 目标：将 1644 张原始表重构为 AI 可理解的分层数据结构，不改变原始数据库，通过元数据 + 视图 + Schema 裁剪实现。

---

## 0. 现状数据

| 维度 | basics | lease | finance | 合计 |
|------|--------|-------|---------|------|
| 原始表数 | 484 | 1060 | 100 | **1644** |
| 核心业务表 | 387 | 734 | 93 | **1214** |
| 次要/渠道表 | 23 | 161 | 0 | **184** |
| 基础设施表 | 24 | 0 | 0 | **24** |
| 可剪枝表 | 50 | 165 | 7 | **222** |

---

## 第一刀：剪枝（1644 → ~800 张）

### 1.1 立即排除（222 张）

不进入 AI 可见的元数据，对 AI 完全不可见。

| 类别 | 数量 | 规则 |
|------|------|------|
| 备份/临时表 | ~70 | `_bak`, `_copy`, `_backup`, `_temp`, `_tmp`, 带日期后缀 |
| 空表（0行且<0.1MB）| ~100 | 未使用的功能预留表 |
| 空的日志/历史表 | ~50 | `_log`, `_history`, `_record` 且行数为 0 |

### 1.2 隔离到独立域（184 张）

这些表功能独立，和核心业务查询场景弱相关，不注入到通用 ChatBI。

| 模块 | 数量 | 说明 |
|------|------|------|
| qft_smart_* | 72 | 智能设备（门锁/电表/水表） |
| qft_sms_* | 8 | 短信服务 |
| qft_wechat_* | 29 | 微信/小程序 |
| qft_circle_* | 9 | 社区圈子 |
| qft_hfq_* | 21 | 好房圈渠道 |
| qft_huituiguang_* | 17 | 惠推广渠道 |
| jian_rong_* | 23 | 建融对接 |
| qft_fgj_* | 5 | 房管局对接 |

### 1.3 隔离基础设施（24 张）

| 模块 | 数量 | 说明 |
|------|------|------|
| act_* | 24 | Activiti 工作流引擎 |

### 1.4 剪枝后

| 维度 | 剪枝前 | 剪枝后 | 缩减比例 |
|------|--------|--------|---------|
| 表数量 | 1644 | ~1214 | -26% |
| AI 可见表 | 1644 | **~800** | **-51%** |

> 注：从 1214 核心表中进一步排除分片表（如 qft_finance_{id} 合并为逻辑上的 1 张）、纯中间表等，实际 AI 需要理解的表约 **800 张**。

---

## 第二刀：三模式统一（800 → ~500 张）

### 2.1 问题

整租(whole)、合租(joint)、集中式(focus) 三种业务模式导致了 **135 张平行同构表**，结构 90%+ 相同。

### 2.2 统一策略

通过 MySQL View 将三套平行表合并为统一视图，用 `business_type` 字段区分模式：

#### 房源统一视图

```
qft_whole_housing (121列) ─┐
qft_joint_housing (122列) ─┼──→ v_housing（统一房源视图，~40 列核心字段）
qft_focus_parent_room (92列)┘
```

核心保留字段（~40列）：
- **标识**：id, company_id, business_type
- **位置**：area_id, city_id, property_id, building, unit_name, door_number
- **基础**：housing_code, housing_name, room_count, total_area
- **业务**：trust_type, rent_price, landlord_name, landlord_phone
- **状态**：status, is_delete, freeze_state
- **时间**：create_time, update_time, entrust_start_time, entrust_end_time

剪掉的字段域：
- 表底数（9列水/电/气/副表）→ 独立视图 `v_housing_meters`
- 累计免租期（7列）→ 独立视图 `v_housing_rent_free`
- 银行账户（4列）→ 独立视图 `v_housing_bank_accounts`
- 排序/搜索辅助（10列）→ 完全剪掉

#### 租客统一视图

```
qft_whole_tenants (81列) ──┐
qft_joint_tenants (79列) ──┼──→ v_tenants（统一租客视图，~30 列核心字段）
qft_focus_tenants (47列) ──┘
```

核心保留字段（~30列）：
- **标识**：id, company_id, business_type, housing_id, room_id
- **租客**：tenant_name, phone, id_card_number
- **租约**：rent_start_time, rent_end_time, pay_type, rent_price
- **状态**：status, audit_state, is_delete
- **时间**：create_time, check_in_time, check_out_time

#### 账单统一视图

```
qft_joint_tenants_income (67列) ────┐
qft_joint_tenants_sub_income (61列) ┼──→ v_bills（统一账单视图，~25 列）
qft_whole_bill_expend (50列) ───────┤
qft_focus_tenants_income (52列) ────┘
```

核心保留字段（~25列）：
- **标识**：id, company_id, business_type, bill_type (收/支)
- **关联**：housing_id, room_id, tenant_id
- **金额**：total_money, paid_money, debt_money, late_fee_money
- **状态**：pay_status, is_delete
- **时间**：bill_start_date, bill_end_date, pay_time, create_time

### 2.3 合同统一视图

```
各类 contract/treaty 表 ──→ v_contracts（统一合同视图，~20 列）
```

### 2.4 财务统一视图

```
qft_finance (70列) ──────────────┐
qft_finance_{company_id} (14张) ─┼──→ v_finance（统一财务视图，~25 列）
```

剥离审批流程 16 列 → 独立视图 `v_finance_approval`

### 2.5 统一后的效果

| 维度 | 统一前 | 统一后 |
|------|--------|--------|
| 三模式平行表 | 135 张 | 合并为 ~15 个统一视图 |
| 财务分片表 | 14 张 | 合并为 1 个统一视图 |
| AI 需理解的表 | ~800 | ~500 |

---

## 第三刀：宽表拆分（按业务域垂直拆分）

### 3.1 qft_room_query_summary_table (131列) 拆分

这张「超级宽表」是为前端房态图设计的，必须拆解：

```
qft_room_query_summary_table (131列)
    │
    ├── v_room_basic（房间基础）  ~15列
    │     id, room_number, room_type, area, orientation, floor, decoration_state
    │
    ├── v_room_pricing（定价信息）~10列
    │     room_id, rent_price, deposit, day_rent, management_fee
    │
    ├── v_room_tenant_snapshot（当前租客快照）~12列
    │     room_id, tenant_name, phone, rent_start, rent_end, pay_type
    │
    ├── v_room_status（房间状态）~8列
    │     room_id, status, is_vacant, freeze_state, renovation_state
    │
    └── [剪掉] 排序/搜索/前端辅助字段 ~20列
          fuzzy_search, sort_*, user_housing_name_phone 等
```

### 3.2 qft_company (115列) 拆分

```
qft_company (115列)
    │
    ├── v_company_info（公司基础信息）~15列
    │     id, name, legal_person, phone, address, industry, create_time
    │
    ├── v_company_config（功能配置开关）~25列
    │     company_id, wechat_enabled, payment_enabled, ...
    │
    ├── v_company_quota（配额管理）~10列
    │     company_id, sms_count, face_recognition_count, ...
    │
    └── [剪掉] 渠道对接/内部配置字段 ~30列
```

### 3.3 qft_finance (70列) 拆分

```
qft_finance (70列)
    │
    ├── v_finance_core（核心流水）~20列
    │     id, company_id, serial_number, nature, type, money, method,
    │     account_date, source_type, source_id, tenant_id, room_id
    │
    ├── v_finance_approval（审批流程）~16列 → 进一步可转为行存储
    │     finance_id, level(审核/复核/出纳/终审), status, operator_id, time, remark
    │
    ├── v_finance_location（位置信息）~8列
    │     finance_id, area_id, city_id, property_id, building, unit, room_number
    │
    └── [剪掉] 基础设施字段 ~6列
          data_version, to_es, is_copy, ...
```

---

## 第四刀：元数据增强层

### 4.1 字段级元数据

为每个保留字段建立业务语义描述：

```yaml
# metadata/lease/v_housing.yaml
table:
  name: v_housing
  description: "统一房源视图，包含整租/合租/集中式三种模式的房源信息"
  primary_key: id
  partition_key: company_id

columns:
  - name: business_type
    description: "业务模式"
    type: tinyint
    enum:
      1: "集中整租"
      2: "整租"
      3: "合租"
    ai_hint: "用户提到'合租'时筛选 business_type=3，提到'整租'时筛选 business_type=2"

  - name: trust_type
    description: "托管类型"
    type: tinyint
    enum:
      1: "委托"
      2: "自有"

  - name: housing_code
    description: "房源编号，全平台唯一标识"
    type: varchar
    sample_values: ["FY202401001", "FY202401002"]

  - name: rent_price
    description: "月租金（元）"
    type: decimal
    unit: "元/月"
```

### 4.2 业务词汇表

```yaml
# metadata/glossary.yaml
glossary:
  - term: "空置率"
    definition: "未出租房间数 / 总房间数 × 100%"
    related_views: ["v_housing", "v_room_status"]
    sql_hint: "COUNT(CASE WHEN status = 空置) / COUNT(*)"

  - term: "收缴率"
    definition: "已收租金 / 应收租金 × 100%"
    related_views: ["v_bills"]
    sql_hint: "SUM(paid_money) / SUM(total_money)"

  - term: "逾期率"
    definition: "逾期未付账单数 / 总应收账单数 × 100%"
    related_views: ["v_bills"]
    sql_hint: "COUNT(CASE WHEN debt_money > 0 AND bill_end_date < NOW()) / COUNT(*)"

  - term: "出租率"
    definition: "已出租房间数 / 总可出租房间数 × 100%"
    related_views: ["v_room_status"]
```

### 4.3 表间关系图谱

```yaml
# metadata/relationships.yaml
relationships:
  - from: v_housing
    to: v_tenants
    type: one_to_many
    join: "v_housing.id = v_tenants.housing_id"
    description: "一个房源可以有多个租客（合租场景）"

  - from: v_tenants
    to: v_bills
    type: one_to_many
    join: "v_tenants.id = v_bills.tenant_id"
    description: "一个租客有多笔账单"

  - from: v_tenants
    to: v_contracts
    type: one_to_one
    join: "v_tenants.id = v_contracts.tenant_id"
    description: "一个租客对应一份合同"

  - from: v_bills
    to: v_finance
    type: one_to_many
    join: "v_bills.id = v_finance.source_id AND v_finance.source_type IN (2,3)"
    condition: "source_type=2 为应收账单来源，source_type=3 为应支账单来源"
    description: "一笔账单可能产生多笔财务流水"

  - from: v_housing
    to: v_room_basic
    type: one_to_many
    join: "v_housing.id = v_room_basic.housing_id"
    description: "一个房源包含多个房间（合租/集中式）"

  - from: v_company_info
    to: "*"
    type: one_to_many
    join: "v_company_info.id = *.company_id"
    description: "多租户隔离，所有数据都属于某个公司"
```

---

## 最终架构：四层数据模型

```
┌─────────────────────────────────────────────────────┐
│  L4: AI 接口层                                       │
│  ┌─────────┐ ┌──────────┐ ┌───────────────────────┐ │
│  │ Agent   │ │ 元数据    │ │ Schema 裁剪器         │ │
│  │ Tools   │ │ + 词汇表  │ │ (按提问动态选视图)    │ │
│  └─────────┘ └──────────┘ └───────────────────────┘ │
├─────────────────────────────────────────────────────┤
│  L3: 语义视图层 (~50 个视图)                         │
│  ┌──────────────────────────────────────────┐        │
│  │ 统一视图: v_housing, v_tenants, v_bills, │        │
│  │ v_contracts, v_finance, v_room_*,        │        │
│  │ v_company_info, ...                      │        │
│  └──────────────────────────────────────────┘        │
├─────────────────────────────────────────────────────┤
│  L2: 清洗/统一层 (~15 个统一视图)                    │
│  ┌──────────────────────────────────────────┐        │
│  │ 三模式合并 + 分片合并 + 字段标准化        │        │
│  │ UNION ALL + CASE WHEN + 字段别名          │        │
│  └──────────────────────────────────────────┘        │
├─────────────────────────────────────────────────────┤
│  L1: 原始数据层 (1644 张原始表，不做任何修改)        │
│  ┌──────────────────────────────────────────┐        │
│  │ qft_basics.* | qft_lease.* | qft_finance.*│       │
│  └──────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────┘
```

---

## 实施路线

### Phase 1：剪枝 + 元数据（1-2 周）

1. 建立表分类清单（core / secondary / prunable），输出 `metadata/table_classification.yaml`
2. 为 ~50 张核心高频表编写字段级元数据（中文描述 + 枚举映射 + 样例值）
3. 建立业务词汇表和表间关系图谱
4. 实现 Schema 裁剪器原型：根据用户提问，从元数据中筛选相关的 5-10 张表

### Phase 2：统一视图层（2-4 周）

1. 设计并创建三模式统一视图（housing / tenants / bills / contracts）
2. 设计并创建财务分片统一视图
3. 设计并创建宽表拆分视图（room_query_summary / company / finance）
4. 验证视图性能，对热点查询创建汇总表

### Phase 3：AI 集成验证（1-2 周）

1. 基于 L3 视图层 + 元数据，测试 GPT-5.4 和 Claude Opus 的 Text-to-SQL 效果
2. 与直接查原始表的效果做 Benchmark 对比
3. 封装 10-20 个高频 Agent Tool 处理剪枝后仍难以 SQL 化的查询
4. 建立标准测试集（50-100 个业务问题）

### 预期效果

| 指标 | 原始表直查 | 重构后 |
|------|-----------|--------|
| AI 可见表数 | 1644 | ~50 视图 |
| 最大表列数 | 131 | ~40 |
| 单次查询 token 消耗 | 40K+ | ~3-5K |
| 单表简查准确率 | 40-60% | 85-95% |
| 跨表查询准确率 | 15-25% | 60-75% |
| 跨模式查询准确率 | 5-10% | 70-85% |

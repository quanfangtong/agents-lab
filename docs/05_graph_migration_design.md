# 全房通 MySQL → Property Graph 迁移设计

> 目标：将 3 库 1644 张 MySQL 宽表转化为 Property Graph 模型，消除隐式关联、统一三模式、降低 AI 查数复杂度。

---

## 0. 迁移前提与约束

| 约束 | 说明 |
|------|------|
| 源库只读 | qft_read 只读账号，不可修改原始表结构 |
| 零外键 | 4848 个 `_id` 关联列，0 个外键约束，关系需推断 |
| 三模式同构 | 整租/合租/集中式导致 135 张平行表 |
| 财务分片 | 按 company_id 分为 14 张同构财务表 |
| 多租户 | company_id 贯穿所有业务表（339 张表含 business_type） |
| 宽表 | 核心表 50-131 列，混合 6+ 业务域 |

---

## 1. 数据清洗流程

### 1.1 三阶段剪枝管线

```
Stage 1: 表级剪枝 (1644 → 1214)
    ├── 排除备份表: _bak, _copy, _backup, _temp, _tmp, 日期后缀 (~70张)
    ├── 排除空表: 0行 且 <0.1MB (~100张)
    └── 排除空日志表: _log/_history/_record 且行数=0 (~50张)

Stage 2: 域级隔离 (1214 → ~800)
    ├── 智能设备: qft_smart_* (72张) → 独立子图（可选）
    ├── 短信/微信/社区: qft_sms_*, qft_wechat_*, qft_circle_* (46张)
    ├── 渠道对接: qft_hfq_*, qft_huituiguang_*, jian_rong_*, qft_fgj_* (66张)
    └── 工作流引擎: act_* (24张) → 不入图

Stage 3: 模式统一 + 分片合并 (800 → ~500 逻辑实体)
    ├── 三模式平行表合并: 135张 → ~15个统一节点类型
    └── 财务分片合并: 14张 → 1个 FinanceRecord 节点类型
```

### 1.2 字段标准化规则

| 规则 | 示例 | 处理方式 |
|------|------|----------|
| ID 别名统一 | `house_id`(154表) vs `housing_id`(201表) | 统一为 `housing_id`，ETL 层做映射 |
| 时间字段标准化 | `create_time`, `createTime`, `created_at` | 统一为 `created_at` (ISO 8601) |
| 金额字段标准化 | `money`, `total_money`, `rent_price` | 保留原名但统一类型为 DECIMAL(12,2)，单位元 |
| 状态枚举统一 | `status` 在不同表含义各异 | 加前缀：`housing_status`, `tenant_status`, `bill_status` |
| business_type 消歧 | 339张表中含义各异 | 仅在需区分模式的节点上保留，值统一：1=集中整租, 2=整租, 3=合租 |
| 删除标记 | `is_delete`, `is_del`, `deleted` | 统一为 `is_deleted`，ETL 阶段默认过滤 `is_deleted=1` |

### 1.3 枚举值标准化

核心枚举映射（写入 ETL 配置）：

```yaml
enums:
  business_type:
    1: "集中整租"
    2: "整租"
    3: "合租"

  trust_type:
    1: "委托"
    2: "自有"

  housing_status:
    0: "待审核"
    1: "正常"
    2: "已退租"
    3: "冻结"

  tenant_status:
    1: "正常在租"
    2: "已退租"
    3: "未入住"

  bill_type:
    income: "收入"
    expend: "支出"

  pay_status:
    0: "未支付"
    1: "已支付"
    2: "部分支付"

  finance_nature:
    1: "收入"
    2: "支出"
```

---

## 2. Property Graph 模型

### 2.1 核心节点类型（Vertex Labels）

基于 `_id` 关联分析和业务域拆分，识别出以下核心实体：

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Property Graph 核心节点                        │
├──────────────────┬──────────────────────────────────────────────────┤
│ 节点类型          │ 来源                                            │
├──────────────────┼──────────────────────────────────────────────────┤
│ Company          │ qft_company (115列 → 拆分后 ~15 属性)            │
│ Store            │ qft_store / qft_store_info                      │
│ Employee         │ qft_employee / qft_employee_info                │
│ Housing          │ whole_housing + joint_housing + focus_parent_room│
│ Room             │ qft_room + room_query_summary_table 拆分         │
│ Tenant           │ whole_tenants + joint_tenants + focus_tenants    │
│ Contract         │ 各类 contract/treaty 表合并                      │
│ Bill             │ tenants_income + tenants_sub_income + bill_expend│
│ FinanceRecord    │ qft_finance + 14张分片表合并                     │
│ Property         │ qft_property (小区/楼盘)                         │
│ Area             │ qft_area / qft_city (地区)                       │
│ Landlord         │ 从 housing 表中抽取的房东实体                     │
│ ApprovalFlow     │ 从 finance 审批 16列抽取                         │
│ RentConfig       │ 从 housing 表中抽取的租金配置                     │
│ MeterReading     │ 从 housing 表底数字段抽取                        │
└──────────────────┴──────────────────────────────────────────────────┘
```

### 2.2 核心关系类型（Edge Labels）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Property Graph 核心关系                          │
├──────────────────────────┬──────────┬───────────────┬──────────────────┤
│ 关系                      │ 方向     │ 基数          │ 推断依据          │
├──────────────────────────┼──────────┼───────────────┼──────────────────┤
│ Company -[OWNS_STORE]->  │ 1:N      │ company → store│ store.company_id │
│         Store            │          │               │                  │
│                          │          │               │                  │
│ Company -[EMPLOYS]->     │ 1:N      │ company →     │ employee.        │
│         Employee         │          │ employee      │ company_id       │
│                          │          │               │                  │
│ Store -[MANAGES]->       │ 1:N      │ store →       │ housing.         │
│       Housing            │          │ housing       │ store_id         │
│                          │          │               │                  │
│ Housing -[CONTAINS]->    │ 1:N      │ housing → room│ room.housing_id  │
│         Room             │          │               │                  │
│                          │          │               │                  │
│ Housing -[LOCATED_IN]->  │ N:1      │ housing →     │ housing.         │
│         Property         │          │ property      │ property_id      │
│                          │          │               │                  │
│ Property -[IN_AREA]->    │ N:1      │ property →    │ property.area_id │
│          Area            │          │ area          │                  │
│                          │          │               │                  │
│ Housing -[OWNED_BY]->    │ N:1      │ housing →     │ housing.         │
│         Landlord         │          │ landlord      │ landlord_* 字段   │
│                          │          │               │                  │
│ Tenant -[RENTS]->        │ N:1      │ tenant → room │ tenant.room_id   │
│        Room              │          │               │                  │
│                          │          │               │                  │
│ Tenant -[LIVES_IN]->     │ N:1      │ tenant →      │ tenant.          │
│        Housing           │          │ housing       │ housing_id       │
│                          │          │               │                  │
│ Tenant -[SIGNS]->        │ 1:1      │ tenant →      │ contract.        │
│        Contract          │          │ contract      │ tenant_id        │
│                          │          │               │                  │
│ Contract -[FOR_HOUSING]->│ N:1      │ contract →    │ contract.        │
│          Housing         │          │ housing       │ housing_id       │
│                          │          │               │                  │
│ Bill -[CHARGED_TO]->     │ N:1      │ bill → tenant │ bill.tenant_id   │
│      Tenant              │          │               │                  │
│                          │          │               │                  │
│ Bill -[FOR_ROOM]->       │ N:1      │ bill → room   │ bill.room_id     │
│      Room                │          │               │                  │
│                          │          │               │                  │
│ FinanceRecord            │ N:1      │ finance → bill│ finance.source_id│
│ -[SETTLES]-> Bill        │          │               │ + source_type    │
│                          │          │               │                  │
│ FinanceRecord            │ N:1      │ finance →     │ finance.         │
│ -[BELONGS_TO]-> Company  │          │ company       │ company_id       │
│                          │          │               │                  │
│ Employee -[ASSIGNED_TO]->│ N:1      │ employee →    │ employee.        │
│          Store           │          │ store         │ store_id         │
│                          │          │               │                  │
│ ApprovalFlow             │ N:1      │ approval →    │ 审批16列抽取      │
│ -[APPROVES]->            │          │ finance       │                  │
│ FinanceRecord            │          │               │                  │
│                          │          │               │                  │
│ Employee                 │ N:1      │ employee →    │ approval.        │
│ -[REVIEWS]->             │          │ approval      │ operator_id      │
│ ApprovalFlow             │          │               │                  │
└──────────────────────────┴──────────┴───────────────┴──────────────────┘
```

### 2.3 Property Graph Schema（Cypher DDL 风格）

```cypher
// ============================================
// 节点定义
// ============================================

// 公司（多租户根节点）
CREATE NODE TABLE Company (
    id             INT64    PRIMARY KEY,
    name           STRING,
    legal_person   STRING,
    phone          STRING,
    address        STRING,
    industry       STRING,
    created_at     TIMESTAMP,
    -- 从 qft_company 115列中保留核心 ~15 属性
    -- 功能开关(29列) → 独立 CompanyConfig 节点或 JSON 属性
)

// 门店
CREATE NODE TABLE Store (
    id             INT64    PRIMARY KEY,
    company_id     INT64,
    store_name     STRING,
    address        STRING,
    manager_id     INT64,
    phone          STRING,
    status         INT16,
    created_at     TIMESTAMP
)

// 员工
CREATE NODE TABLE Employee (
    id             INT64    PRIMARY KEY,
    company_id     INT64,
    store_id       INT64,
    name           STRING,
    phone          STRING,
    role           STRING,
    status         INT16,
    created_at     TIMESTAMP
)

// 统一房源（三模式合并）
CREATE NODE TABLE Housing (
    id             INT64    PRIMARY KEY,
    company_id     INT64,
    business_type  INT16,      -- 1=集中整租 2=整租 3=合租
    housing_code   STRING,
    housing_name   STRING,
    trust_type     INT16,      -- 1=委托 2=自有
    room_count     INT32,
    total_area     DOUBLE,
    rent_price     DOUBLE,
    housing_status INT16,
    created_at     TIMESTAMP,
    entrust_start  TIMESTAMP,
    entrust_end    TIMESTAMP
)

// 房间
CREATE NODE TABLE Room (
    id             INT64    PRIMARY KEY,
    company_id     INT64,
    housing_id     INT64,
    room_number    STRING,
    room_type      STRING,
    area           DOUBLE,
    orientation    STRING,
    floor          INT32,
    rent_price     DOUBLE,
    deposit        DOUBLE,
    room_status    INT16,
    is_vacant      BOOLEAN,
    created_at     TIMESTAMP
)

// 统一租客（三模式合并）
CREATE NODE TABLE Tenant (
    id             INT64    PRIMARY KEY,
    company_id     INT64,
    business_type  INT16,
    housing_id     INT64,
    room_id        INT64,
    tenant_name    STRING,
    phone          STRING,
    id_card_number STRING,
    rent_start     TIMESTAMP,
    rent_end       TIMESTAMP,
    pay_type       INT16,
    rent_price     DOUBLE,
    tenant_status  INT16,
    check_in_time  TIMESTAMP,
    check_out_time TIMESTAMP,
    created_at     TIMESTAMP
)

// 合同
CREATE NODE TABLE Contract (
    id             INT64    PRIMARY KEY,
    company_id     INT64,
    business_type  INT16,
    housing_id     INT64,
    room_id        INT64,
    tenant_id      INT64,
    contract_no    STRING,
    contract_type  INT16,
    start_date     TIMESTAMP,
    end_date       TIMESTAMP,
    rent_price     DOUBLE,
    deposit        DOUBLE,
    pay_type       INT16,
    contract_status INT16,
    created_at     TIMESTAMP
)

// 统一账单（收入+支出合并）
CREATE NODE TABLE Bill (
    id             INT64    PRIMARY KEY,
    company_id     INT64,
    business_type  INT16,
    bill_type      STRING,     -- income / expend
    housing_id     INT64,
    room_id        INT64,
    tenant_id      INT64,
    total_money    DOUBLE,
    paid_money     DOUBLE,
    debt_money     DOUBLE,
    late_fee       DOUBLE,
    pay_status     INT16,
    bill_start     DATE,
    bill_end       DATE,
    pay_time       TIMESTAMP,
    created_at     TIMESTAMP
)

// 统一财务流水（分片合并）
CREATE NODE TABLE FinanceRecord (
    id             INT64    PRIMARY KEY,
    company_id     INT64,
    serial_number  STRING,
    nature         INT16,      -- 1=收入 2=支出
    finance_type   STRING,
    money          DOUBLE,
    method         STRING,
    account_date   DATE,
    source_type    INT16,
    source_id      INT64,
    tenant_id      INT64,
    room_id        INT64,
    created_at     TIMESTAMP
)

// 小区/楼盘
CREATE NODE TABLE Property (
    id             INT64    PRIMARY KEY,
    company_id     INT64,
    area_id        INT64,
    property_name  STRING,
    address        STRING,
    building_count INT32,
    created_at     TIMESTAMP
)

// 地区
CREATE NODE TABLE Area (
    id             INT64    PRIMARY KEY,
    city_id        INT64,
    area_name      STRING,
    city_name      STRING,
    province       STRING
)

// 房东（从 housing 的 landlord_* 字段抽取为独立实体）
CREATE NODE TABLE Landlord (
    id             INT64    PRIMARY KEY,  -- 生成的代理键
    company_id     INT64,
    name           STRING,
    phone          STRING,
    id_card        STRING,
    bank_account   STRING,
    bank_name      STRING
)

// 审批流（从 finance 审批16列抽取，列转行）
CREATE NODE TABLE ApprovalFlow (
    id             INT64    PRIMARY KEY,  -- 生成的代理键
    finance_id     INT64,
    level          INT16,      -- 1=审核 2=复核 3=出纳 4=终审
    operator_id    INT64,
    status         INT16,
    remark         STRING,
    operated_at    TIMESTAMP
)

// ============================================
// 关系定义
// ============================================

CREATE REL TABLE OWNS_STORE     (FROM Company  TO Store,        since TIMESTAMP)
CREATE REL TABLE EMPLOYS        (FROM Company  TO Employee,     since TIMESTAMP)
CREATE REL TABLE ASSIGNED_TO    (FROM Employee TO Store,        role STRING)
CREATE REL TABLE MANAGES        (FROM Store    TO Housing)
CREATE REL TABLE CONTAINS       (FROM Housing  TO Room)
CREATE REL TABLE LOCATED_IN     (FROM Housing  TO Property)
CREATE REL TABLE IN_AREA        (FROM Property TO Area)
CREATE REL TABLE OWNED_BY       (FROM Housing  TO Landlord,     trust_type INT16)
CREATE REL TABLE RENTS          (FROM Tenant   TO Room,         since TIMESTAMP, until TIMESTAMP)
CREATE REL TABLE LIVES_IN       (FROM Tenant   TO Housing,      since TIMESTAMP, until TIMESTAMP)
CREATE REL TABLE SIGNS          (FROM Tenant   TO Contract)
CREATE REL TABLE FOR_HOUSING    (FROM Contract TO Housing)
CREATE REL TABLE CHARGED_TO     (FROM Bill     TO Tenant)
CREATE REL TABLE FOR_ROOM       (FROM Bill     TO Room)
CREATE REL TABLE SETTLES        (FROM FinanceRecord TO Bill,    source_type INT16)
CREATE REL TABLE BELONGS_TO     (FROM FinanceRecord TO Company)
CREATE REL TABLE APPROVES       (FROM ApprovalFlow  TO FinanceRecord)
CREATE REL TABLE REVIEWS        (FROM Employee      TO ApprovalFlow)
```

### 2.4 完整关系拓扑图

```
                          Area
                           ^
                           | IN_AREA
                           |
Company ──OWNS_STORE──> Store ──MANAGES──> Housing ──LOCATED_IN──> Property
   |                      ^                  |   |
   |                      |               CONTAINS  OWNED_BY
   └──EMPLOYS──> Employee─┘ (ASSIGNED_TO)    |       |
                    |                        v       v
                    |                      Room   Landlord
                    |                        ^
                    |                   RENTS |
                    |                        |
                    |    Tenant ─────LIVES_IN──> Housing
                    |      |  |
                    |      |  └──SIGNS──> Contract ──FOR_HOUSING──> Housing
                    |      |
                    |    CHARGED_TO <── Bill ──FOR_ROOM──> Room
                    |                    ^
                    |                    | SETTLES
                    |                    |
                    └──REVIEWS──> ApprovalFlow ──APPROVES──> FinanceRecord
                                                    |
                                             BELONGS_TO ──> Company
```

---

## 3. 颗粒度治理方案

### 3.1 宽表拆分为图属性的原则

| 原则 | 说明 | 示例 |
|------|------|------|
| **实体属性** | 描述节点自身特征的稳定属性 | Housing.total_area, Tenant.name |
| **关系属性** | 描述两个实体之间连接特征的属性 | RENTS.since, RENTS.until, SETTLES.source_type |
| **提升为独立节点** | 当某组字段有独立生命周期或被多个实体引用 | Landlord 从 housing 表抽取、ApprovalFlow 从 finance 列转行 |
| **度量 vs 维度** | 度量(金额/数量)留在实体上，维度(类型/状态)留在实体上但标准化枚举 | Bill.total_money(度量), Bill.pay_status(维度) |
| **丢弃** | 前端辅助、排序搜索、基础设施字段不入图 | fuzzy_search, sort_*, data_version, to_es |

### 3.2 核心宽表拆分明细

#### qft_room_query_summary_table (131列 → 3个节点 + 属性)

```
原始 131 列分布：
├── 房间信息 44列 ──→ Room 节点属性 (~15列核心)
│   保留: room_number, room_type, area, orientation, floor, decoration_state,
│         rent_price, deposit, day_rent, management_fee
│   丢弃: 排序辅助字段 sort_*, user_housing_name_phone 等
│
├── 租客信息 28列 ──→ Tenant 节点属性 + RENTS 关系
│   保留: tenant_name, phone, rent_start, rent_end, pay_type
│   由关系承载: 租客与房间的关联由 RENTS 边表达
│
├── 地址 15列 ──→ 通过 LOCATED_IN → Property → IN_AREA → Area 关系链表达
│   不冗余存储在 Room 上，通过图遍历获取
│
├── 房源 23列 ──→ Housing 节点属性
│   保留: housing_code, housing_name, business_type, trust_type
│   关联: Room -[CONTAINS]- Housing
│
├── 财务 4列 ──→ 通过 Bill/FinanceRecord 节点 + 关系获取
│   不冗余存储，按需遍历
│
├── 状态 4列 ──→ Room 节点属性
│   保留: room_status, is_vacant, freeze_state
│
├── 排序搜索 11列 ──→ 全部丢弃
│   纯前端辅助字段，图模型不需要
│
└── 基础设施 2列 ──→ 丢弃
    data_version, 同步标记等
```

#### qft_whole_housing / qft_joint_housing (122/121列 → Housing 节点 + 关联节点)

```
原始 ~122 列分布：
├── 地址 8列 ──→ 通过关系链：Housing → Property → Area
│   housing 上仅保留 property_id 作为关系锚点
│
├── 房源 14列 ──→ Housing 节点核心属性
│   保留: housing_code, housing_name, room_count, total_area, rent_price
│
├── 合同 9列 ──→ Contract 节点属性 + FOR_HOUSING 关系
│   不冗余在 Housing 上
│
├── 状态 17列 ──→ Housing 节点属性 (精简为 ~5 个状态字段)
│   保留: housing_status, freeze_state, audit_state
│   丢弃: 细粒度子状态（UI 用途）
│
├── 时间 10列 ──→ Housing 节点属性 (精简为 ~4 个)
│   保留: created_at, entrust_start, entrust_end, updated_at
│   丢弃: 冗余时间戳
│
├── 表底数 9列 ──→ MeterReading 节点（可选）
│   水/电/气的初始读数，有独立生命周期
│
├── 免租期 7列 ──→ RentConfig 节点或 Housing 的 JSON 属性
│
├── 银行账户 4列 ──→ Landlord 节点属性
│   与房东绑定更合理
│
└── 排序/搜索辅助 ~10列 ──→ 全部丢弃
```

#### qft_finance (70列 → FinanceRecord + ApprovalFlow 节点)

```
原始 70 列分布：
├── 审批流程 16列 (4级×4列) ──→ ApprovalFlow 节点（列转行）
│   每级审批变为一个 ApprovalFlow 节点：
│   {level, operator_id, status, remark, operated_at}
│   通过 APPROVES 关系连接 FinanceRecord
│   通过 REVIEWS 关系连接 Employee
│
├── 财务核心 ~20列 ──→ FinanceRecord 节点属性
│   保留: serial_number, nature, type, money, method,
│         account_date, source_type, source_id
│
├── 位置 8列 ──→ 通过关系链获取
│   FinanceRecord → Bill → Room → Housing → Property → Area
│   不冗余存储位置信息
│
├── 状态 10列 ──→ FinanceRecord 节点属性 (精简为 ~3 个)
│   保留: finance_status, audit_state, is_deleted
│
├── 操作记录 7列 ──→ FinanceRecord 节点属性
│   保留: operator_id, created_at, updated_at
│
└── 基础设施 6列 ──→ 全部丢弃
    data_version, to_es, is_copy 等
```

#### qft_company (115列 → Company + CompanyConfig)

```
原始 115 列分布：
├── 公司信息 ~20列 ──→ Company 节点核心属性
│   保留: name, legal_person, phone, address, industry, created_at
│
├── 功能开关 29列 ──→ CompanyConfig 节点 或 Company.config (JSON属性)
│   如 wechat_enabled, payment_enabled, ...
│   这些开关与 ChatBI 查数场景无关，可延迟处理
│
├── 配额管理 ~10列 ──→ Company 节点属性或独立节点
│   sms_count, face_recognition_count 等
│
├── 渠道配置 ~25列 ──→ 丢弃（与查数无关）
│
└── 合伙模式 ~30列 ──→ 按需保留
```

### 3.3 时间序列数据处理

| 时间维度 | 图模型处理 | 说明 |
|----------|-----------|------|
| 合同周期 | Contract 节点 `start_date`, `end_date` | 历史合同保留为节点，通过 status 区分有效/过期 |
| 租期 | RENTS 关系属性 `since`, `until` | 退租后关系保留但 until 有值 |
| 账单周期 | Bill 节点 `bill_start`, `bill_end` | 支持按时间范围查询 |
| 财务流水 | FinanceRecord 节点 `account_date` | 按日期分区索引 |
| 状态变更 | 不建模变更历史 | 图中保留最新状态，历史变更留在 MySQL |

### 3.4 多租户处理

```
策略：company_id 作为图的一级分区维度

方案 A（推荐）：全局图 + 属性过滤
  - 所有公司数据在同一个图中
  - 每个节点携带 company_id 属性
  - 查询时始终带 WHERE company_id = ? 过滤
  - 优点：支持跨公司分析、部署简单
  - 缺点：需确保查询隔离

方案 B：每公司一个子图/命名空间
  - 每个 company_id 独立的图空间
  - 优点：天然隔离
  - 缺点：不支持跨公司查询、管理复杂

选择方案 A，原因：
1. ChatBI 场景下查询始终绑定 company_id（用户登录态）
2. 未来可能需要平台级分析（跨公司聚合）
3. 图数据库通常支持高效属性索引
```

---

## 4. ETL 管道设计

### 4.1 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                          ETL Pipeline                            │
│                                                                  │
│  ┌──────────┐    ┌───────────┐    ┌──────────┐    ┌──────────┐  │
│  │  Extract  │───>│ Transform │───>│  Validate │───>│   Load   │  │
│  │ (MySQL)   │    │ (Python)  │    │ (Python)  │    │ (Graph)  │  │
│  └──────────┘    └───────────┘    └──────────┘    └──────────┘  │
│       │                │                │               │        │
│       v                v                v               v        │
│  binlog/query     清洗+合并+        完整性校验       批量写入     │
│  只读连接         字段标准化        关系有效性       事务保证     │
│                   枚举映射          去重检查                      │
│                   实体抽取                                       │
│                   关系推断                                       │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 Extract 阶段

```python
# 伪代码：全量抽取逻辑
extract_config = {
    "qft_basics": {
        "tables": ["qft_company", "qft_store", "qft_employee", "qft_property", "qft_area"],
        "filter": "is_delete = 0 OR is_delete IS NULL",
        "batch_size": 10000,
    },
    "qft_lease": {
        "tables": [
            # 三模式房源 → 统一抽取
            "qft_whole_housing", "qft_joint_housing", "qft_focus_parent_room",
            # 三模式租客 → 统一抽取
            "qft_whole_tenants", "qft_joint_tenants", "qft_focus_tenants",
            # 三模式账单 → 统一抽取
            "qft_joint_tenants_income", "qft_joint_tenants_sub_income",
            "qft_whole_bill_expend", "qft_focus_tenants_income",
            # 房间
            "qft_room", "qft_room_query_summary_table",
        ],
        "filter": "is_delete = 0 OR is_delete IS NULL",
        "batch_size": 5000,
    },
    "qft_finance": {
        "tables": ["qft_finance"],
        # 加上 14 张分片表，动态发现
        "shard_pattern": "qft_finance_{company_id}",
        "filter": "is_delete = 0 OR is_delete IS NULL",
        "batch_size": 5000,
    },
}
```

### 4.3 Transform 阶段

```python
# 伪代码：核心转换流程

def transform_housing(rows_whole, rows_joint, rows_focus):
    """三模式房源合并为 Housing 节点"""
    nodes = []
    for row in rows_whole:
        nodes.append(Housing(
            id=row["id"],
            company_id=row["company_id"],
            business_type=2,  # 整租
            housing_code=row["housing_code"],
            housing_name=row.get("housing_name") or row.get("house_name"),
            trust_type=row["trust_type"],
            room_count=row["room_count"],
            total_area=row["total_area"],
            rent_price=row["rent_price"],
            housing_status=row["status"],
            created_at=normalize_timestamp(row["create_time"]),
            entrust_start=normalize_timestamp(row.get("entrust_start_time")),
            entrust_end=normalize_timestamp(row.get("entrust_end_time")),
        ))
    # joint → business_type=3, focus → business_type=1 同理
    return nodes

def extract_landlord(housing_rows):
    """从 housing 宽表中抽取 Landlord 实体"""
    landlords = {}
    for row in housing_rows:
        phone = row.get("landlord_phone")
        if phone and phone not in landlords:
            landlords[phone] = Landlord(
                id=generate_surrogate_key(),
                company_id=row["company_id"],
                name=row.get("landlord_name"),
                phone=phone,
                id_card=row.get("landlord_id_card"),
                bank_account=row.get("bank_account"),
                bank_name=row.get("bank_name"),
            )
    return landlords

def transform_approval_flow(finance_rows):
    """将 finance 审批 16 列 列转行 为 ApprovalFlow 节点"""
    flows = []
    levels = [
        (1, "audit"),    # 审核
        (2, "review"),   # 复核
        (3, "cashier"),  # 出纳
        (4, "final"),    # 终审
    ]
    for row in finance_rows:
        for level_num, prefix in levels:
            operator = row.get(f"{prefix}_id") or row.get(f"{prefix}_operator_id")
            status = row.get(f"{prefix}_status")
            if operator:
                flows.append(ApprovalFlow(
                    id=generate_surrogate_key(),
                    finance_id=row["id"],
                    level=level_num,
                    operator_id=operator,
                    status=status,
                    remark=row.get(f"{prefix}_remark"),
                    operated_at=normalize_timestamp(row.get(f"{prefix}_time")),
                ))
    return flows

def infer_relationships(nodes_by_type):
    """基于 _id 字段推断关系"""
    edges = []

    # Housing → Property (housing.property_id)
    for h in nodes_by_type["Housing"]:
        if h.property_id:
            edges.append(("LOCATED_IN", h.id, h.property_id))

    # Tenant → Room (tenant.room_id)
    for t in nodes_by_type["Tenant"]:
        if t.room_id:
            edges.append(("RENTS", t.id, t.room_id, {
                "since": t.rent_start, "until": t.rent_end
            }))

    # Bill → Tenant (bill.tenant_id)
    for b in nodes_by_type["Bill"]:
        if b.tenant_id:
            edges.append(("CHARGED_TO", b.id, b.tenant_id))

    # ... 其他关系同理
    return edges
```

### 4.4 Validate 阶段

```python
def validate_graph(nodes, edges):
    """入库前校验"""
    errors = []

    # 1. 引用完整性：边的端点必须存在
    node_ids = {(type, n.id) for type, n in nodes}
    for edge_type, src, dst, *props in edges:
        if src not in node_ids:
            errors.append(f"Dangling source: {edge_type} src={src}")
        if dst not in node_ids:
            errors.append(f"Dangling target: {edge_type} dst={dst}")

    # 2. 关键属性非空检查
    for type, node in nodes:
        if type == "Housing" and not node.company_id:
            errors.append(f"Housing {node.id} missing company_id")

    # 3. 去重检查（同一 phone 的 Landlord 应合并）
    # ...

    return errors
```

### 4.5 Load 阶段

```python
def load_to_graph(graph_db, nodes, edges, batch_size=1000):
    """批量写入图数据库"""
    # 按依赖顺序写入节点（先写被引用的，后写引用者）
    load_order = [
        "Area", "Property", "Company", "Store", "Landlord",
        "Employee", "Housing", "Room", "Tenant", "Contract",
        "Bill", "FinanceRecord", "ApprovalFlow",
    ]

    for node_type in load_order:
        type_nodes = [n for t, n in nodes if t == node_type]
        for batch in chunked(type_nodes, batch_size):
            graph_db.batch_create_nodes(node_type, batch)

    # 写入关系
    for batch in chunked(edges, batch_size):
        graph_db.batch_create_edges(batch)
```

### 4.6 增量同步策略

```
┌──────────────────────────────────────────────────────────┐
│                    增量同步方案                            │
├────────────┬─────────────────────────────────────────────┤
│ 方案        │ 基于 update_time 轮询（推荐初期方案）        │
├────────────┼─────────────────────────────────────────────┤
│ 频率        │ 每 15 分钟                                  │
│ 原理        │ SELECT * WHERE update_time > last_sync_time │
│ 覆盖范围    │ 每轮扫描所有核心表                           │
│ 幂等性      │ UPSERT（按主键 id 合并）                    │
│ 删除同步    │ is_delete=1 → 图中标记 soft_deleted=true    │
├────────────┼─────────────────────────────────────────────┤
│ 进阶方案    │ MySQL binlog CDC（未来）                     │
├────────────┼─────────────────────────────────────────────┤
│ 工具        │ Debezium / Maxwell → Kafka → 图写入器       │
│ 优点        │ 近实时、不遗漏、减少源库压力                  │
│ 前提        │ 需要 binlog 访问权限（当前只有只读账号）      │
└────────────┴─────────────────────────────────────────────┘
```

### 4.7 数据一致性保证

| 机制 | 说明 |
|------|------|
| 全量校验 | 每日凌晨对比 MySQL COUNT(*) 与图节点数 |
| 增量水印 | 记录每轮同步的 max(update_time)，下轮从此处开始 |
| 事务写入 | 同一批次的节点+关系在同一事务中写入 |
| 回滚能力 | 每次全量同步前做图快照（或记录同步批次 ID） |
| 监控告警 | 源库与图库节点数偏差 > 1% 时告警 |

---

## 5. 图数据库选型建议

| 数据库 | 优势 | 劣势 | 适合场景 |
|--------|------|------|----------|
| **Kuzu** (嵌入式) | 零运维、列存高性能、Cypher 兼容、Python 原生 | 无分布式、社区较小 | 单机分析、PoC 验证 |
| **Neo4j** | 生态最成熟、GDS 算法库、LLM 集成 (GraphRAG) | 社区版单机、企业版昂贵 | 生产级部署、GraphRAG |
| **Apache AGE** | PostgreSQL 扩展、SQL+Cypher 混合 | 性能中等、社区活跃度一般 | 已有 PG 基础设施 |
| **NebulaGraph** | 国产、分布式、性能好 | nGQL 语法、生态偏弱 | 大规模图、国产化要求 |

**推荐路径**：Kuzu (本地 PoC) → Neo4j (生产验证) → 按需切换

---

## 6. 迁移里程碑

```
Phase 0: PoC 验证（1-2 周）
├── 选 1 个公司的数据做端到端验证
├── 覆盖 Housing + Room + Tenant + Bill 4 个核心节点
├── 用 Kuzu 嵌入式，Python 脚本驱动
├── 验证 ChatBI 查询是否因图结构而显著简化
└── 输出：PoC 报告 + 性能基线

Phase 1: 核心图构建（2-4 周）
├── 实现完整 ETL 管道
├── 覆盖全部 15 个节点类型 + 16 个关系类型
├── 全量导入所有公司数据
├── 建立增量同步机制
└── 输出：可查询的完整图

Phase 2: AI 集成（2-3 周）
├── 图 Schema + 自然语言 → Cypher 查询（Text-to-Cypher）
├── 与现有 Text-to-SQL 做 Benchmark 对比
├── 多跳查询（如：某门店下所有逾期租客的房东联系方式）
└── 输出：ChatBI 图查询原型

Phase 3: 生产化（3-4 周）
├── 切换到 Neo4j 或适合的图数据库
├── 监控、告警、一致性校验
├── 混合查询：简单聚合走 SQL，关系型查询走图
└── 输出：生产级服务
```

---

## 7. 核心收益预估

| 指标 | SQL 宽表查询 | 图模型查询 | 提升 |
|------|-------------|-----------|------|
| AI 需理解的 Schema 量 | ~50 视图 ×40列 = 2000 字段 | 15 节点 ×10属性 + 16 关系 = ~170 元素 | **12x 精简** |
| 3 跳关系查询（如：公司→门店→房源→租客） | 4 表 JOIN | 3 跳遍历 | 语义更直觉 |
| "某门店逾期租客的房东电话" | 5 表 JOIN + 子查询 | `MATCH (s:Store)-[:MANAGES]->(h:Housing)<-[:LIVES_IN]-(t:Tenant)<-[:CHARGED_TO]-(b:Bill), (h)-[:OWNED_BY]->(l:Landlord) WHERE b.debt_money > 0` | **声明式 vs 过程式** |
| 三模式查询 | UNION ALL 3 张表 | 统一 Housing 节点 + business_type 过滤 | 消除模式差异 |
| 新增关系发现 | 需人工写 JOIN | 图遍历自动发现 | 可扩展性 |

---

## 附录 A: _id 字段推断的完整关系清单

基于已知数据分析（4848 个 _id 关联列），以下是高频被引用的 ID 字段及其推断关系：

| ID 字段 | 推断引用表数 | 对应图节点 | 推断关系 |
|---------|-------------|-----------|---------|
| company_id | 339+ | Company | 多租户根节点，贯穿所有实体 |
| housing_id | 201 | Housing | 房源是核心枢纽实体 |
| house_id | 154 | Housing (别名) | 同 housing_id，ETL 层统一 |
| room_id | ~100 | Room | 房间级关联 |
| tenant_id / tenants_id | ~80 | Tenant | 租客关联 |
| store_id | ~60 | Store | 门店关联 |
| employee_id | ~50 | Employee | 员工/操作人关联 |
| contract_id | ~30 | Contract | 合同关联 |
| property_id | ~20 | Property | 小区/楼盘关联 |
| area_id | ~15 | Area | 地区关联 |
| landlord_id | ~10 | Landlord | 房东关联 |

> 注：上述引用表数为基于已知分析的估算值。建立数据库连接模块后，应运行 `_id` 字段聚合查询获取精确数字。

## 附录 B: 关系推断的置信度分级

| 置信度 | 标准 | 处理方式 |
|--------|------|----------|
| **高** (85%+) | 命名规范（`housing_id` → Housing.id）且数据类型一致 | 直接建关系 |
| **中** (50-85%) | 命名有歧义（`house_id` 可能指 Housing 或 House 表）但值域匹配 | 采样验证后建关系 |
| **低** (<50%) | 命名模糊（`parent_id`, `source_id`）且可能指向多种实体 | 暂不建关系，标记为待确认 |

高置信度关系（直接建模）：company_id, housing_id, room_id, tenant_id, store_id, employee_id, contract_id, property_id, area_id

中置信度关系（需验证）：house_id → housing_id 映射, tenants_id → tenant_id 映射, source_id (finance 表中按 source_type 多态)

低置信度关系（暂缓）：parent_id (多张表含义不同), business_type (非 ID 但跨 339 张表)

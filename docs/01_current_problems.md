# 全房通现有数据结构问题分析报告

> 分析目标：从 AI 驱动的 ChatBI 视角，评估全房通现有数据库结构对大模型查询的适配性问题。

## 0. 数据库全景

| 维度 | qft_basics | qft_lease | qft_finance | 合计 |
|------|-----------|-----------|-------------|------|
| 表数量 | 484 | 1,076 | 100 | **1,660** |
| 列数量 | 5,921 | 19,503 | 2,615 | **28,039** |
| 估计行数 | ~3.1 亿 | ~12.3 亿 | ~3.5 亿 | **~18.9 亿** |
| 存储大小 | 99.94 GB | 500.24 GB | 149.18 GB | **749.36 GB** |

---

## 1. 宽表问题分析：131 列的灾难

### 1.1 核心问题表

| 表名 | 列数 | 行数 | 说明 |
|------|------|------|------|
| qft_room_query_summary_table | 131 | - | 房间汇总查询宽表 |
| qft_joint_housing | 122 | ~47万 | 合租房源 |
| qft_huituiguang_house | 122 | - | 会推广房源 |
| qft_whole_housing | 121 | ~72万 | 整租房源 |
| qft_company | 115 | - | 公司主表 |
| qft_focus_parent_room | 92 | ~3.9万 | 集中式房源 |

### 1.2 对 AI 查询的具体影响

**Token 消耗爆炸**

- `qft_room_query_summary_table` 的 `CREATE TABLE` DDL 长度为 **10,047 字符**，约消耗 **3,349 tokens**
- 仅 lease 库 Top 20 宽表的 DDL 合计 **127,317 字符**，约 **42,439 tokens**
- 若将全部 1,660 张表的 schema 传递给 LLM，token 消耗将远超任何模型的上下文窗口
- 即便只传递表名和列名（不含注释），1,660 张表 × 平均 17 列 ≈ 28,039 个列名，也将消耗数万 tokens

**上下文污染**

`qft_room_query_summary_table`（131 列）是一个典型的"什么都有"的查询宽表，将房源、房间、租客、定金、维修、保洁、装修、排序等完全不同的业务域压缩到一张表中：

- 房源域（housing_*）：25+ 列，含地址、托管类型、业务员、冻结状态等
- 房间域（room_*）：35+ 列，含面积、朝向、窗户、阳台、定价、装修等
- 租客域（tenants_*）：25+ 列，含姓名、电话、租期、缴费、审核等
- 定金域（earnest_*）：6 列
- 运维域（repair_count, cleanup_count, patrol_house_count 等）
- 排序辅助域（sort_*）：10 列，纯技术字段

当用户问"某房间的月租金是多少"时，LLM 需要从 131 列中筛选相关字段。大量无关列（如 `sort_building_unit`、`room_day_rent_time`、`fuzzy_search`）会严重干扰模型的注意力分配。

**字段歧义**

`business_type` 出现在 **339 张表**中，但含义各不相同：
- 在房源表中：`1集中整租 2整租 3合租`
- 在某些表中：`1求租 2求购`
- 在其他表中：`1=focus 2=whole 3=joint`

`type` 出现在 **97 张表**，含义从"财务类型"到"门锁/电表/水表"再到"企微客户类型"完全不同。AI 极易混淆。

---

## 2. 命名与语义问题

### 2.1 统一前缀 qft_ 无区分度

所有 1,660 张表均以 `qft_` 开头，这个前缀对 AI 来说是纯噪音——它既不能帮助推断业务含义，也不能区分不同的业务域。

### 2.2 拼音缩写泛滥

| 缩写 | 实际含义 | 出现位置 |
|------|---------|---------|
| hzf | 合租房 | `qft_hzf_model_send_result` |
| fgj | 房管局 | `qft_fgj_*` 系列 (88 列引用) |
| weg | 水电(water/electricity/gas) | `room_field_weg_*` |
| hpop | 会推广 | `hpop_account_id`, `hpop_housing_sync_state` |
| wty | 梧桐寓 | `wty_mark` |
| bj | 业绩(business performance) | `qft_bj_merits_*` |
| cdrm | 成都房门(?) | `qft_cdrm_kingdee_push_finance_log` |

这些拼音缩写对 LLM 来说是完全不可理解的。当用户用中文自然语言提问时，AI 无法将"房管局备案"映射到 `fgj`，也无法将"水电费余额"映射到 `weg_balance_money`。

### 2.3 命名风格不一致

同一业务概念存在多种命名：
- 租客ID：`tenant_id` vs `tenants_id` (单复数不一致)
- 房源ID：`housing_id` vs `house_id` (154 张表用 `house_id`，201 张表用 `housing_id`)
- 删除标记：`is_delete` vs `is_deleted` 不一致
- 时间字段：`create_time` vs `registration_time` vs `register_time`

---

## 3. 结构碎片化：三种业务模式的表爆炸

### 3.1 平行表体系

全房通支持整租(whole)、合租(joint)、集中式(focus)三种业务模式，导致大量同构但分散的表：

| 业务域 | 整租(whole) | 合租(joint) | 集中式(focus) |
|--------|-------------|-------------|---------------|
| 表数量 | 19 张 | 39 张 | 77 张 |
| 房源主表 | qft_whole_housing (121列) | qft_joint_housing (122列) | qft_focus_parent_room (92列) |
| 租客主表 | qft_whole_tenants (81列) | qft_joint_tenants (79列) | qft_focus_tenants (47列) |
| 账单支出 | qft_whole_bill_expend | qft_joint_bill_expend | qft_focus_bill_expend |

### 3.2 同构但有微妙差异

以租客表为例，三种模式的列对比：
- 共有列：**37** 列（核心业务字段）
- 整租独有：`square_price`（平米单价）、`use_type`（用途）
- 集中式独有：`age`、`sex`、`occupation`、`qq_wechat` 等 **10 列**（更完整的客户画像）
- 合租独有：无

**对 AI 的影响**：当用户问"查一下租客张三的合同到期时间"时，AI 必须：
1. 先判断该租客属于哪种业务模式
2. 选择对应的租客表（三选一）
3. 使用正确的列名查询

这个三步推理过程极易出错。AI 无法仅从自然语言中判断业务模式，需要先查询确认。

### 3.3 汇总表试图掩盖碎片化

`qft_room_query_summary_table`（131 列）的存在本身就说明了问题——开发团队不得不创建一张"超级宽表"来跨模式查询，用 `business_type` 字段区分三种模式。这种做法在应用层有效，但对 AI 来说制造了更大的噪音。

---

## 4. 财务表分片策略问题

### 4.1 按 company_id 手工分片

`qft_finance` 库中存在 13 张结构完全一致的分片表：

```
qft_finance       (主表)
qft_finance_1     (~47,023 rows)
qft_finance_332   (~322,591 rows)
qft_finance_859   (~1,040,223 rows)
qft_finance_994   (~812,124 rows)
qft_finance_1017  (~871,770 rows)
... 共 13 张
```

每张分片表的 70 列结构完全一致，按 `company_id` 分配到不同表中。

### 4.2 对 AI 的致命影响

- **表选择困难**：AI 必须知道某个 `company_id` 对应哪张分片表，而这个映射关系在代码逻辑中，不在数据库元数据中
- **跨公司查询不可能**：若用户问"所有公司本月收入总额"，AI 需要对 14 张表 UNION ALL，这对 LLM 生成 SQL 来说极不可靠
- **分片规则不透明**：表名后缀的数字就是 company_id，但 AI 无法推断这个规则

### 4.3 四级审批流程的列膨胀

`qft_finance` 的 70 列中，审批流程贡献了 16 列（4 级 × 4 列/级）：

```
audit / auditor_id / audit_time / audit_introduction          (审核)
review / reviewer_id / review_time / reviewer_introduction    (复核)
cashier / cashier_id / cashier_time / cashier_introduction    (出纳)
final_audit / final_auditor_id / final_audit_time / final_audit_introduction  (终审)
```

这是典型的扁平化设计，应拆为独立的审批流水表。

---

## 5. 冗余数据干扰

### 5.1 备份/临时表

| 数据库 | 备份/冗余表数量 | 典型示例 |
|--------|-----------------|---------|
| basics | 25 张 | `qft_company_copy`, `qft_my_agent_bak`, `qft_my_agent_copy1_bak` |
| lease | 40 张 | `qft_focus_room_config_copy`, `qft_joint_tenants_renewal_copy`, `jian_rong_house_backup` |
| finance | 3 张 | `qft_finance_1_copy1`, `qft_bill_finance_incr_temp` |

共 **68 张**垃圾表混在正式表中。AI 无法区分 `qft_joint_tenants_renewal` 和 `qft_joint_tenants_renewal_copy` 哪个是正式表。

### 5.2 ES 同步标记字段

| 字段 | 分布 |
|------|------|
| `data_version` | basics 8 表, lease 67 表, finance 29 表 = **104 张表** |
| `to_es` | finance 14 张表 |

这些字段纯粹是基础设施层面的同步标记，对业务查询毫无意义，但会出现在 schema 中干扰 AI。

### 5.3 Activiti 工作流引擎表

basics 库中混入了 **24 张** Activiti 流程引擎表（`act_ge_*`、`act_hi_*`、`act_ru_*`、`act_re_*`、`act_id_*`），这些是框架自动生成的表，与业务数据无关。

### 5.4 冗余的前台辅助字段

`qft_room_query_summary_table` 中的以下字段完全是前端展示辅助，不应存在于分析层：
- `fuzzy_search` - 模糊搜索拼接字段
- `sort_*` 系列 - 10 个排序辅助字段
- `user_housing_name_phone` - 冗余的"姓名+手机号"拼接字段（还有 4 个类似字段）

---

## 6. 关系隐蔽性：无外键的 4,848 个关联

### 6.1 外键约束统计

| 数据库 | _id 关联列 | 外键约束数 |
|--------|-----------|-----------|
| basics | - | 23（仅 Activiti 引擎表有） |
| lease | **4,848** | **0** |
| finance | - | **0** |

lease 库有 4,848 个以 `_id` 结尾的关联列，**但没有一个外键约束**。所有表间关系完全依赖代码逻辑，AI 无法从 schema 中推断。

### 6.2 典型的隐蔽关系链

要回答"某个租客的全部账单明细"，需要理解以下隐式关系链：

```
qft_joint_tenants.id ← (无外键) → qft_joint_tenants_sub_income.tenants_id
    └→ 需要先通过 business_type 判断是合租
qft_joint_tenants.housing_id ← (无外键) → qft_joint_housing.id
qft_joint_tenants.room_id ← (无外键) → qft_joint_room.id
qft_finance.source_id ← (无外键) → qft_joint_tenants_sub_income.id
    └→ 且需要 source_type = 2 (应收账单)
```

AI 必须同时知道：
1. 哪些表存在关联
2. 通过哪个字段关联
3. 关联时的过滤条件（如 `source_type = 2`）
4. 跨库关联的存在（lease → finance）

### 6.3 同名但含义不同的 ID 字段

`house_id` 出现在 154 张表中，但含义包括：
- 全房通房源ID
- 58同城房源ID
- 建融家园房源ID
- 房东ID
- 房间ID（在某些表中被错误命名）

AI 看到两张表都有 `house_id`，可能错误地 JOIN 它们，产生笛卡尔积灾难。

---

## 7. 综合影响评估

### 7.1 AI 查询成功率预估

| 查询复杂度 | 示例 | 预估成功率 |
|-----------|------|-----------|
| 单表简单查询 | "XX公司有多少房源" | 40-60% (需选对表) |
| 单模式跨表 | "合租租客的欠费列表" | 15-25% |
| 跨模式查询 | "所有空置房间列表" | 5-10% |
| 跨库查询 | "某租客的财务收支明细" | < 5% |
| 涉及分片表 | "全平台本月收入" | < 3% |

### 7.2 根因总结

| 问题 | 严重程度 | 原因 |
|------|---------|------|
| 宽表 token 爆炸 | **致命** | 物化查询视图直接暴露给 AI |
| 三模式表碎片化 | **致命** | 业务模式导致的平行表体系 |
| 财务分片不透明 | **严重** | 手工分片逻辑在代码中 |
| 无外键约束 | **严重** | 4,848 个隐式关系 |
| 拼音/缩写命名 | **高** | LLM 无法理解中文拼音缩写 |
| 冗余表/字段噪音 | **中** | 68 张垃圾表 + 同步标记字段 |
| 同名字段歧义 | **高** | business_type 出现 339 次 |

### 7.3 结论

全房通现有数据库是典型的 **OLTP 业务库直接暴露给分析场景** 的反模式。这套结构为业务应用服务多年，在应用代码中运行良好，但对 AI 驱动的自然语言查询来说几乎是不可用的。

要实现可靠的 ChatBI，不能简单地"把 schema 扔给 LLM"，必须构建一个 **AI 友好的语义层**，将业务模型从物理存储中解耦出来。

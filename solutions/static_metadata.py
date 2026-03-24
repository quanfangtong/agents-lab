"""方案 E: 静态元数据 — 手工关键词→表映射，无图数据库"""

from .common import Solution, get_datamart_connection, get_tables_ddl

# 手工编写的关键词→表映射
KEYWORD_TABLE_MAP = {
    # 房源
    "房源": ["qft_whole_housing", "qft_joint_housing", "qft_focus_housing"],
    "整租房源": ["qft_whole_housing"],
    "合租房源": ["qft_joint_housing"],
    "集中式房源": ["qft_focus_housing"],
    "储备房源": ["qft_reserve_housing"],
    # 房间
    "房间": ["qft_whole_room", "qft_joint_room", "qft_focus_room"],
    "空置": ["qft_whole_room", "qft_joint_room", "qft_focus_room"],
    "床位": ["qft_room_bed"],
    "维修": ["qft_room_repair"],
    # 租客
    "租客": ["qft_whole_tenants", "qft_joint_tenants", "qft_focus_tenants"],
    "退房": ["qft_tenants_check_out"],
    "换房": ["qft_tenants_change_houses"],
    "转租": ["qft_tenants_relet"],
    "同住人": ["qft_tenants_cohabit"],
    # 合同
    "合同": ["qft_electronics_contract", "qft_paper_contract"],
    "签约": ["qft_electronics_contract", "qft_paper_contract"],
    "交割单": ["qft_focus_delivery_order"],
    # 账单
    "账单": ["qft_bill", "qft_bill_item"],
    "应收": ["qft_joint_tenants_income", "qft_focus_tenants_income"],
    "应支": ["qft_whole_bill_expend", "qft_joint_bill_expend", "qft_focus_bill_expend"],
    "租金": ["qft_joint_tenants_income", "qft_whole_bill_expend", "qft_focus_tenants_income"],
    "欠费": ["qft_joint_tenants_income", "qft_whole_bill_expend", "qft_focus_tenants_income",
              "qft_joint_tenants", "qft_whole_tenants", "qft_focus_tenants"],
    "逾期": ["qft_joint_tenants_income", "qft_whole_bill_expend", "qft_focus_tenants_income"],
    "支付": ["qft_pay_order", "qft_pay_log"],
    # 财务
    "财务": ["qft_finance", "qft_finance_item"],
    "收入": ["qft_finance"],
    "支出": ["qft_finance"],
    "流水": ["qft_finance", "qft_finance_item"],
    # 门店
    "门店": ["qft_store"],
    "公司": ["qft_company"],
    "员工": ["qft_user"],
    "管家": ["qft_butler"],
    # 智能硬件
    "门锁": ["qft_smart_device", "qft_smart_lock_open_record", "qft_smart_lock_statistics"],
    "电表": ["qft_smart_device", "qft_smart_electricity_meter_recharge_record"],
    "水表": ["qft_smart_device", "qft_smart_water_meter_usage_record"],
    "智能设备": ["qft_smart_device", "qft_house_device"],
    "充值": ["qft_smart_electricity_meter_recharge_record"],
    # 装修
    "装修": ["qft_renovation", "qft_rm_renovation_record"],
    "摊销": ["qft_rm_renovation_amortization"],
    # 出租率
    "出租率": ["qft_whole_room", "qft_joint_room", "qft_focus_room"],
    # 续约
    "续约": ["qft_common_tenant_renewal", "qft_common_housing_renewal"],
}


class StaticMetadataSolution(Solution):
    name = "E_StaticMetadata"

    def setup(self):
        pass  # 无需初始化

    def get_schema_context(self, question: str, intent: dict = None) -> tuple[str, list[str]]:
        # 关键词匹配
        matched_tables = set()
        for keyword, tables in KEYWORD_TABLE_MAP.items():
            if keyword in question:
                matched_tables.update(tables)

        # 兜底：没匹配到就给通用表
        if not matched_tables:
            matched_tables = {
                "qft_whole_housing", "qft_joint_housing",
                "qft_whole_tenants", "qft_joint_tenants",
                "qft_store",
            }

        table_list = sorted(matched_tables)
        conn = get_datamart_connection()
        ddl = get_tables_ddl(conn, table_list)
        conn.close()
        return ddl, table_list

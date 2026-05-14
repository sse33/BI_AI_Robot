# 硬编码仪表板配置 — 第一迭代
# 仪表板：1.2 单品图册(SKC版)
# page_id: c38a7adbd12bc40eeaa00526

DASHBOARD = {
    "page_id": "c38a7adbd12bc40eeaa00526",
    "name": "1.2 单品图册(SKC版)",
    "description": "SKC 单品图册，展示各 SKC 的销售、库存、消化率等核心指标",
    # 仅保留数据卡片（排除 SELECTOR / TEXT 类型）
    "cards": [
        {
            "card_id": "o6722f8db3ad0414f8a53c6a",
            "card_name": "上周销额",
            "card_type": "KPI_CARD",
            "business_description": (
                "上周及累计销售额汇总，含线下/线上拆分及与上上周的环比变化（▲销额%）"
            ),
            "filter_listeners": [
                "实际上市日期", "实际波段", "运营中类", "商品年", "运营大类",
                "产品线(新)", "是否上市", "运营系列(新)", "denim fit-name",
                "spu", "商品标签", "商品期", "skc编码", "denim fit-family",
            ],
        },
        {
            "card_id": "e219996b5356947cd83cd2b3",
            "card_name": "上周销量",
            "card_type": "KPI_CARD",
            "business_description": (
                "上周及累计销售量汇总，含线下/线上拆分及与上上周的环比变化（▲销量%）"
            ),
            "filter_listeners": [
                "实际上市日期", "实际波段", "运营中类", "商品年", "运营大类",
                "产品线(新)", "是否上市", "运营系列(新)", "denim fit-name",
                "spu", "商品标签", "商品期", "skc编码", "denim fit-family",
            ],
        },
        {
            "card_id": "h421da6b674dd4c9bb56c5f6",
            "card_name": "上周折扣",
            "card_type": "KPI_CARD",
            "business_description": "上周及累计销售折扣率（销售额/销售吊牌额）",
            "filter_listeners": [
                "实际上市日期", "实际波段", "运营中类", "商品年", "运营大类",
                "产品线(新)", "是否上市", "运营系列(新)", "denim fit-name",
                "spu", "商品标签", "商品期", "skc编码", "denim fit-family",
            ],
        },
        {
            "card_id": "sa40a6b95cc3640b4808df14",
            "card_name": "周转W",
            "card_type": "KPI_CARD",
            "business_description": "当前库存周转周数（库存金额 / 上周销售吊牌额）",
            "filter_listeners": [
                "实际上市日期", "实际波段", "运营中类", "商品年", "运营大类",
                "产品线(新)", "是否上市", "运营系列(新)", "denim fit-name",
                "spu", "商品标签", "商品期", "skc编码", "denim fit-family",
            ],
        },
        {
            "card_id": "qa1b78eea3ded465bb8594ec",
            "card_name": "上周消化率",
            "card_type": "KPI_CARD",
            "business_description": "上周及累计消化率（销售吊牌额 / 订单金额）",
            "filter_listeners": [
                "实际上市日期", "实际波段", "运营中类", "商品年", "运营大类",
                "产品线(新)", "是否上市", "运营系列(新)", "denim fit-name",
                "spu", "商品标签", "商品期", "skc编码", "denim fit-family",
            ],
        },
        {
            "card_id": "fa6f8e8c5f5b2443cbe36a40",
            "card_name": "2/4/8/16/20周消化率",
            "card_type": "KPI_CARD",
            "business_description": "上市后各关键节点（2/4/8/16周及季末）的累计消化率",
            "filter_listeners": [
                "实际上市日期", "实际波段", "运营中类", "商品年", "运营大类",
                "产品线(新)", "是否上市", "运营系列(新)", "denim fit-name",
                "spu", "商品标签", "商品期", "skc编码", "denim fit-family",
            ],
        },
        {
            "card_id": "beba57f768e164e699daec5d",
            "card_name": "单品图册(SKC版_竖排)",
            "card_type": "PIVOT_TABLE",
            "business_description": (
                "SKC 粒度的单品图册竖排版，包含销售排名、累计销量/消化率、"
                "库存、订单量、各渠道（自营/托管/电商/港澳）明细，以及电商平台拆分"
            ),
            "filter_listeners": ["运营中类", "商品期"],
        },
        {
            "card_id": "x01a786e3b192412e81dda72",
            "card_name": "单品图册(SKC版_横排)",
            "card_type": "PIVOT_TABLE",
            "business_description": (
                "SKC 粒度的单品图册横排版，展示上周销额/销量、环比、累计消化率、"
                "库存、订单、各渠道明细及电商平台数据"
            ),
            "filter_listeners": [
                "实际上市日期", "实际波段", "运营中类", "商品年", "运营大类",
                "产品线(新)", "是否上市", "运营系列(新)", "denim fit-name",
                "spu", "商品标签", "商品期", "skc编码", "denim fit-family",
            ],
        },
        {
            "card_id": "id230bb4bf4274286ba13931",
            "card_name": "单品图册(SKC版_横排)_副本",
            "card_type": "PIVOT_TABLE",
            "business_description": (
                "单品图册横排副本，在横排基础上额外展示总订量(PO)和尺码销售%"
            ),
            "filter_listeners": [],  # 无筛选器联动
        },
        {
            "card_id": "nc56bbc94f6284d76bc9226c",
            "card_name": "单品图册(SKC版_横排)-简易采买版",
            "card_type": "PIVOT_TABLE",
            "business_description": (
                "采买视角的单品图册，重点展示上市2/4/8周销量、线下/线上库存与订量、"
                "累计折扣和全渠道消化率"
            ),
            "filter_listeners": [],  # 无筛选器联动
        },
        {
            "card_id": "i69e432d0789c47f6a3ac47d",
            "card_name": "简易版-营运",
            "card_type": "PIVOT_TABLE",
            "business_description": (
                "SPU 粒度的营运视角简易图册，展示周销排名、销额/销量及环比、"
                "累计消化率、周转、库存和订量"
            ),
            "filter_listeners": [],  # 无筛选器联动，且为 SPU 粒度
        },
    ],
    # 页面可用筛选维度（SELECTOR 卡片对应字段）
    "available_filters": [
        "实际上市日期", "实际波段", "运营中类", "商品年", "运营大类",
        "产品线(新)", "是否上市", "运营系列(新)", "denim fit-name",
        "spu", "商品标签", "商品期", "skc编码", "denim fit-family",
    ],
}

"""项目说明页：产品价值、技术架构与数据限制。"""

from __future__ import annotations

import streamlit as st

from src import config
from src.data_loader import Catalog
from src.ui import components, state
from src.ui.theme import bullet_list, facts


def render(catalog: Catalog) -> None:
    components.page_header(
        "关于智购参谋",
        "我们如何帮你做一次有依据的购买决策，以及这份数据能信到什么程度。",
    )

    # --- 产品价值 ---------------------------------------------------------
    components.section_title("产品价值")
    components.caption(
        "电商平台的推荐排序服务于广告曝光和转化率，通用聊天机器人又容易编造"
        "参数和评价。智购参谋要做的是第三件事：把你的预算和真实用途放在第一位，"
        "给出一个能追溯到具体数据的结论。"
    )
    st.write("")
    st.markdown(
        bullet_list(
            [
                "需求先于商品：先弄清预算、用途、核心需求与可妥协项，再谈选哪件",
                "排序看匹配度，不看价格高低，也不看曝光量",
                "结论可解释：每个分数都由明确的维度加权得出，加分扣分项一一列出",
                "超预算就说超预算，缺数据就说缺数据，不做没有依据的判断",
            ]
        ),
        unsafe_allow_html=True,
    )

    # --- 评分口径 ---------------------------------------------------------
    components.section_title("关于「系统匹配评分」")
    components.show_notice(
        f"界面上看到的分数叫「{config.SCORE_DISPLAY_NAME}」，"
        "它衡量的是某件商品与你在本次分析中提出的需求的匹配程度。"
        "它不是用户评分、不是销量排名、也不是市场口碑。",
        "info",
    )
    st.markdown(
        bullet_list(
            [
                "评分由预算匹配、核心需求匹配、性能功能适配、性价比、便携性等维度加权得出",
                f"「{config.SCORE_DISPLAY_NAME}」的权重按商品类别分别配置，"
                "笔记本与手机各自一套（例如手机更看重核心需求匹配）",
                "数据缺失的维度会被排除计算并在页面上注明，不会补一个默认分充数",
            ]
        ),
        unsafe_allow_html=True,
    )

    # --- 数据限制 ---------------------------------------------------------
    components.section_title("数据来源与限制")
    components.show_notice(catalog.disclaimer or "当前数据集未附带说明。", "warn")
    st.write("")
    st.markdown(
        bullet_list(
            [
                f"数据集共 {len(catalog)} 件商品，"
                f"覆盖 {'、'.join(config.category_label(c) for c in catalog.present_categories())}",
                "商品、参数、适用场景与优缺点均依据公开资料整理，"
                "不是厂商宣传、也不是真实用户评价；"
                "全部记录未逐条核验，不代表任何真实在售商品的实时状态",
                "参数中的档位值（如处理器档位、屏幕档位）是本项目为规则评分设定的分级，"
                "不是厂商跑分或专业评测结果",
                "本项目不接入任何电商平台，不提供实时价格、库存、销量或真实评价",
                "因此本工具的输出只能用于了解「如何用数据支撑一次消费决策」，"
                "不能作为真实购买的依据",
            ]
        ),
        unsafe_allow_html=True,
    )

"""项目说明页：产品价值、技术架构与数据限制。"""

from __future__ import annotations

import streamlit as st

from src import config
from src.data_loader import Catalog
from src.ui import components, state
from src.ui.theme import bullet_list, facts


def render(catalog: Catalog) -> None:
    components.page_header(
        "项目说明",
        "这个工具是怎么想的、怎么搭的，以及它现在的能力边界在哪里。",
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

    # --- 技术架构 ---------------------------------------------------------
    components.section_title("技术架构")
    st.markdown(
        facts(
            [
                ("界面", "Streamlit 单页应用，五个页面"),
                ("业务层", "Python，按职责分为配置、数据、解析、评分、推荐、比较等模块"),
                ("数据存储", "本地 JSON（商品）+ SQLite（历史与收藏，阶段四接入）"),
                ("模型能力", "可选。未配置密钥时完全由本地规则驱动，不联网"),
                ("测试", "pytest，覆盖各能力规格中定义的场景"),
            ]
        ),
        unsafe_allow_html=True,
    )
    st.write("")
    components.caption(
        "业务逻辑全部放在 src/ 下的模块里，界面只做编排。"
        "因此评分、筛选、比较这些核心逻辑可以脱离界面单独做单元测试，"
        "未来若要换成 FastAPI + 独立前端，业务模块可以原样搬走。"
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
                "笔记本和手机计入便携性，耳机和键盘不计入",
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
                "所有商品、价格、参数、优缺点均为演示用途而构造，不代表任何真实在售商品",
                "参数中的档位值（如处理器档位、音质档位）是本项目为规则评分设定的分级，"
                "不是厂商跑分或专业评测结果",
                "本项目不接入任何电商平台，不提供实时价格、库存、销量或真实评价",
                "因此本工具的输出只能用于了解「如何用数据支撑一次消费决策」，"
                "不能作为真实购买的依据",
            ]
        ),
        unsafe_allow_html=True,
    )

    # --- 已知限制 ---------------------------------------------------------
    components.section_title("已知限制")
    st.markdown(
        bullet_list(
            [
                "自然语言解析只覆盖预算、类别、用途、核心需求这类高置信字段；"
                "拿不准的一律留空并追问，不做猜测",
                "中文数字只识别按位书写（「三千」「两千五百」），"
                "口语省略式（「两千五」表示 2500）识别不了，会退回「未识别到预算」",
                "结构化预算输入框只接受阿拉伯数字，填「三千块」会提示格式错误",
                "第一版不做账号体系与多用户隔离，数据保存在本机",
            ]
        ),
        unsafe_allow_html=True,
    )

    # --- 运行环境 ---------------------------------------------------------
    components.section_title("当前运行环境")
    mode, detail = state.current_mode()
    st.markdown(
        facts(
            [
                ("运行模式", mode),
                ("说明", detail),
                ("分值名称", config.SCORE_DISPLAY_NAME),
                ("商品数据库", config.display_path(config.products_db_path())),
            ]
        ),
        unsafe_allow_html=True,
    )

"""可复用的界面片段。

全部是**展示逻辑**：把业务层算好的结果拼成 HTML 或调用 Streamlit 组件。
这里不做任何筛选、评分或排序。

图标分工见 theme 模块 docstring：内容区一律用 `src/ui/icons.py` 的内联 SVG，
因为 `unsafe_allow_html` 的 HTML 里不解析 `:material/x:` 语法。
"""

from __future__ import annotations

import math
from collections.abc import Callable

import streamlit as st

from src import config
from src.comparison import format_param
from src.data_loader import Product
from src.scoring import DimensionScore, ScoreResult
from src.ui import icons, theme
from src.ui.theme import bullet_list, chip, esc, facts, notice, section

#: 卡片与商品行上优先展示的核心参数。
_HEADLINE_SPECS: dict[str, list[str]] = {
    "laptop": ["cpu", "ram_gb", "storage_gb", "weight_kg"],
    "phone": ["chip", "ram_gb", "storage_gb", "weight_g"],
    "headphone": ["driver_mm", "connection", "battery_h", "noise_cancelling"],
    "keyboard": ["layout", "switch_type", "connection"],
}

_SPEC_LABELS = {
    "cpu": "处理器",
    "chip": "芯片",
    "ram_gb": "内存",
    "storage_gb": "存储",
    "weight_kg": "重量",
    "weight_g": "重量",
    "battery_h": "续航",
    "battery_mah": "电池",
    "driver_mm": "单元",
    "connection": "连接",
    "noise_cancelling": "降噪",
    "layout": "布局",
    "switch_type": "轴体",
    "has_dedicated_gpu": "独显",
}

#: 匹配档位 → 标签色调
_MATCH_TONE = {
    "高度匹配": "ok",
    "较为匹配": "brand",
    "基本可用": "neutral",
    "匹配度较低": "warn",
}


def _budget_tone(label: str) -> str:
    if label == "预算内":
        return "ok"
    if label.startswith("超出预算"):
        return "warn"
    return "neutral"


# --------------------------------------------------------------------------
# 页面骨架
# --------------------------------------------------------------------------


def page_header(title: str, subtitle: str = "", *, right: str = "") -> None:
    """页面顶部标题区。`right` 可放一段右对齐的 HTML（按钮等）。"""
    sub = f"<p>{esc(subtitle)}</p>" if subtitle else ""
    left = f'<div style="min-width:0"><h1>{esc(title)}</h1>{sub}</div>'
    row = f'<div class="zg-hero-row">{left}{right}</div>' if right else left
    st.markdown(f'<div class="zg-hero">{row}</div>', unsafe_allow_html=True)


def section_title(text: str, count: int | None = None) -> None:
    st.markdown(section(text, count), unsafe_allow_html=True)


def caption(text: str) -> None:
    st.markdown(f'<div class="zg-caption">{esc(text)}</div>', unsafe_allow_html=True)


def empty_state(text: str, icon_name: str = "search") -> None:
    st.markdown(
        f'<div class="zg-empty"><div class="zg-empty-icon">'
        f'{icons.icon(icon_name, size=30)}</div>{esc(text)}</div>',
        unsafe_allow_html=True,
    )


def show_notice(text: str, tone: str = "info") -> None:
    st.markdown(notice(text, tone), unsafe_allow_html=True)


def render_notes(notes: list[str]) -> None:
    """把分析过程中的说明按重要程度分色展示。

    含「低于」「超出」「不完整」等字样的当成需要留意的，其余当普通说明——
    只做关键词分类，不额外增加业务判断。
    """
    for text in notes:
        tone = (
            "warn"
            if any(k in text for k in ("低于", "超出", "不完整", "缺少", "无法确认"))
            else "info"
        )
        st.markdown(notice(text, tone), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 统计卡与功能卡
# --------------------------------------------------------------------------


def stat_tile(icon_name: str, value: str, label: str) -> str:
    """一个统计格：图标 + 数值 + 说明。"""
    return (
        f'<div class="zg-stat">'
        f'  <div class="zg-stat-icon">{icons.icon(icon_name, size=19)}</div>'
        f'  <div class="zg-stat-value">{esc(value)}</div>'
        f'  <div class="zg-stat-label">{esc(label)}</div>'
        f"</div>"
    )


def stat_row(tiles: list[tuple[str, str, str]]) -> None:
    """一行统计卡。tiles 为 (图标名, 数值, 说明) 列表。"""
    columns = st.columns(len(tiles), gap="small")
    for column, (icon_name, value, label) in zip(columns, tiles, strict=True):
        with column:
            st.markdown(stat_tile(icon_name, value, label), unsafe_allow_html=True)


def feature_card(icon_name: str, title: str, description: str) -> str:
    return (
        f'<div class="zg-feature">'
        f'  <div class="zg-feature-icon">{icons.icon(icon_name, size=21)}</div>'
        f'  <div class="zg-feature-title">{esc(title)}</div>'
        f'  <div class="zg-feature-desc">{esc(description)}</div>'
        f"</div>"
    )


def feature_row(cards: list[tuple[str, str, str]]) -> None:
    """一行功能卡。cards 为 (图标名, 标题, 描述) 列表。"""
    columns = st.columns(len(cards), gap="small")
    for column, (icon_name, title, desc) in zip(columns, cards, strict=True):
        with column:
            st.markdown(feature_card(icon_name, title, desc), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 圆环与星级
# --------------------------------------------------------------------------


def score_ring(percent: float, title: str, description: str, *, size: int = 100) -> str:
    """圆环进度 + 右侧说明。percent 取 0–100。"""
    value = max(0.0, min(100.0, percent))
    radius = (size - 12) / 2
    circumference = 2 * math.pi * radius
    filled = circumference * value / 100.0
    center = size / 2
    stroke = 9

    return (
        f'<div class="zg-ring-wrap">'
        f'  <div class="zg-ring" style="width:{size}px;height:{size}px">'
        f'    <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'      <circle cx="{center}" cy="{center}" r="{radius}" fill="none" '
        f'stroke="{theme.LINE_SOFT}" stroke-width="{stroke}"/>'
        f'      <circle cx="{center}" cy="{center}" r="{radius}" fill="none" '
        f'stroke="{theme.BRAND}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-dasharray="{filled:.2f} {circumference - filled:.2f}" '
        f'transform="rotate(-90 {center} {center})"/>'
        f"    </svg>"
        f'    <div class="zg-ring-value">'
        f'      <div class="zg-ring-num">{value:.0f}%</div>'
        f"    </div>"
        f"  </div>"
        f'  <div class="zg-ring-text">'
        f'    <div class="zg-ring-title">{esc(title)}</div>'
        f'    <div class="zg-ring-desc">{esc(description)}</div>'
        f"  </div>"
        f"</div>"
    )


def stars(score: float, *, count: int = 5, size: int = 13) -> str:
    """把 0–100 分映射成星级显示。

    这只是**系统匹配评分的可视化**，不是用户评分——调用处必须在旁边
    写明「系统匹配评分」，否则星星会被读成真实口碑。
    """
    filled = int(round(max(0.0, min(100.0, score)) / 100 * count))
    glyphs = "".join(
        f'<span class="{"zg-star-on" if i < filled else "zg-star-off"}">'
        f'{icons.icon("star", size=size)}</span>'
        for i in range(count)
    )
    return f'<span class="zg-stars">{glyphs}</span>'


# --------------------------------------------------------------------------
# 评分构成
# --------------------------------------------------------------------------


def _dimension_bar(dimension: DimensionScore) -> str:
    width = max(0.0, min(100.0, dimension.score))
    return (
        f'<div class="zg-dim">'
        f'  <div class="zg-dim-head">'
        f'    <span class="zg-dim-name">{esc(dimension.label)}'
        f'      <span class="zg-dim-weight">权重 {dimension.weight:.0%}</span></span>'
        f'    <span class="zg-dim-score">{dimension.score:.0f}</span>'
        f"  </div>"
        f'  <div class="zg-bar"><div class="zg-bar-fill" style="width:{width:.1f}%"></div></div>'
        f'  <div class="zg-dim-reason">{esc(dimension.reason)}</div>'
        f"</div>"
    )


def score_breakdown_html(score: ScoreResult) -> str:
    """评分构成：各维度得分条 + 加分项 + 扣分项 + 未参与计算的维度。"""
    ordered = sorted(score.dimensions, key=lambda d: (-d.score, d.key))
    parts = ["".join(_dimension_bar(d) for d in ordered)]

    if score.bonus:
        parts.append(f'<div class="zg-caption" style="margin-top:14px">主要加分项</div>')
        parts.append(bullet_list(score.bonus))
    if score.penalty:
        parts.append('<div class="zg-caption" style="margin-top:12px">主要扣分项</div>')
        parts.append(bullet_list(score.penalty, tone="con"))
    if score.excluded:
        parts.append(
            '<div class="zg-caption" style="margin-top:12px">'
            "以下维度因数据缺失或类别不适用，未参与本次计算</div>"
        )
        parts.append(
            bullet_list([f"{label}：{reason}" for label, reason in score.excluded])
        )
    return "".join(parts)


def render_score_breakdown(score: ScoreResult, *, expanded: bool = False) -> None:
    with st.expander(
        f"评分构成与依据 · {config.SCORE_DISPLAY_NAME} {score.total:.0f} 分"
        f"（{score.match_level}）",
        expanded=expanded,
    ):
        st.markdown(
            f'<div class="zg-caption" style="margin-bottom:10px">'
            f"「{config.SCORE_DISPLAY_NAME}」是本系统按你的需求与商品数据算出的匹配程度，"
            f"<strong>不是用户评价、销量或市场口碑</strong>。</div>",
            unsafe_allow_html=True,
        )
        st.markdown(score_breakdown_html(score), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 商品展示
# --------------------------------------------------------------------------


def _spec_line(product: Product) -> str:
    """一行式规格摘要，例如「R7-7530U · 16GB · 512GB · 1.28kg」。"""
    keys = _HEADLINE_SPECS.get(product.category, sorted(product.specs)[:3])
    parts: list[str] = []
    for key in keys:
        if product.has_spec(key):
            parts.append(format_param(key, product.spec(key)))
        else:
            parts.append("信息缺失")
    return " · ".join(parts)


def _highlight_chips(score: ScoreResult) -> str:
    """把得分最高的两个维度做成标签。

    标签来自各维度实际得分，不是另写的固定文案。
    """
    ranked = sorted(score.dimensions, key=lambda d: (-d.score, d.key))
    chunks: list[str] = []
    for dimension in ranked[:2]:
        tone = "ok" if dimension.score >= 80 else ("brand" if dimension.score >= 60 else "neutral")
        chunks.append(chip(f"{dimension.label} {dimension.score:.0f}", tone))
    return "".join(chunks)


def product_row(
    product: Product,
    score: ScoreResult,
    budget_label: str,
    *,
    rank: int | None = None,
    highlight: bool = False,
) -> str:
    """推荐列表里的一行商品。

    必须能看到：排名、类别图标（图片占位）、名称、规格、预算匹配状态、
    参考价格、系统匹配评分、以及数据来源标注——最后一项是需求硬性要求的。
    """
    rank_html = ""
    if rank is not None:
        muted = " is-muted" if rank > 3 else ""
        rank_html = f'<div class="zg-rank{muted}">{rank}</div>'

    return (
        f'<div class="zg-card{" is-accent" if highlight else ""}">'
        f'  <div class="zg-row">'
        f"    {rank_html}"
        f'    <div class="zg-thumb">{icons.category_icon(product.category, size=27)}</div>'
        f'    <div class="zg-row-main">'
        f'      <div class="zg-row-name">{esc(product.name or product.id)}</div>'
        f'      <div class="zg-row-spec">{esc(product.brand or "品牌未知")}'
        f"        · {esc(product.category_label)} · {esc(_spec_line(product))}</div>"
        f'      <div style="display:flex;flex-wrap:wrap;gap:6px">'
        f'        {chip(budget_label, _budget_tone(budget_label))}'
        f'        {chip(score.match_level, _MATCH_TONE.get(score.match_level, "neutral"))}'
        f"        {_highlight_chips(score)}"
        f"      </div>"
        f"    </div>"
        f'    <div style="text-align:right;flex-shrink:0">'
        f'      <div class="zg-price">{esc(product.price_label)}</div>'
        f"    </div>"
        f'    <div class="zg-row-score">'
        f'      <div class="zg-score-num">{score.total:.0f}<small>/100</small></div>'
        f'      <div style="margin:3px 0">{stars(score.total)}</div>'
        f'      <div class="zg-score-name">{esc(config.SCORE_DISPLAY_NAME)}</div>'
        f"    </div>"
        f"  </div>"
        f'  <div class="zg-source">数据来源：{esc(product.data_source or "信息缺失")}'
        f"　·　更新时间：{esc(product.updated_at or '信息缺失')}</div>"
        f"</div>"
    )


def render_product_row(
    product: Product,
    score: ScoreResult,
    budget_label: str,
    *,
    rank: int | None = None,
    highlight: bool = False,
    expanded: bool = False,
    extra_actions: Callable[[], None] | None = None,
) -> None:
    """商品行 + 可展开的评分构成与优缺点。

    `extra_actions` 会在「优点与不足」展开区末尾调用一次，用于挂收藏之类的
    操作按钮。做成回调而不是直接在这里写按钮，是为了让组件层不依赖数据库——
    它只管画，不该知道数据存在哪。
    """
    st.markdown(
        product_row(product, score, budget_label, rank=rank, highlight=highlight),
        unsafe_allow_html=True,
    )
    render_score_breakdown(score, expanded=expanded)

    with st.expander("优点与不足"):
        left, right = st.columns(2)
        with left:
            st.markdown('<div class="zg-caption">优点</div>', unsafe_allow_html=True)
            st.markdown(bullet_list(product.pros), unsafe_allow_html=True)
        with right:
            st.markdown('<div class="zg-caption">缺点</div>', unsafe_allow_html=True)
            st.markdown(bullet_list(product.cons, tone="con"), unsafe_allow_html=True)
        if extra_actions is not None:
            st.write("")
            extra_actions()


def product_mini(product: Product, *, budget_label: str = "") -> str:
    """紧凑商品条，用于比较页顶部与历史记录。"""
    chip_html = (
        chip(budget_label, _budget_tone(budget_label)) if budget_label else ""
    )
    return (
        f'<div class="zg-card is-flat">'
        f'  <div class="zg-row">'
        f'    <div class="zg-thumb is-lg">{icons.category_icon(product.category, size=30)}</div>'
        f'    <div class="zg-row-main">'
        f'      <div class="zg-row-name">{esc(product.name or product.id)}</div>'
        f'      <div class="zg-row-spec">{esc(product.brand or "品牌未知")}'
        f"        · {esc(product.category_label)}</div>"
        f'      <div class="zg-price">{esc(product.price_label)}</div>'
        f'      <div style="margin-top:8px">{chip_html}</div>'
        f"    </div>"
        f"  </div>"
        f"</div>"
    )


def runtime_chip() -> str:
    """当前运行模式的标签。"""
    from src.ui.state import current_mode

    mode, detail = current_mode()
    tone = "info" if mode == "AI 增强模式" else "neutral"
    return chip(f"{mode} · {detail}", tone)


def facts_block(pairs: list[tuple[str, str]]) -> None:
    st.markdown(facts(pairs), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 历史报告（快照）的渲染
# --------------------------------------------------------------------------
#
# 历史报告里存的是 ReportItem 快照，不是当前的 Product + ScoreResult，
# 所以不能复用上面的商品行渲染——那会诱使我们去当前数据里查商品，
# 从而把「还原历史结论」变成「按当前数据重算」。这两件事必须分开。


def report_item_card(item, *, show_rank: bool = True) -> str:
    """渲染一条历史推荐快照。"""
    rank_html = ""
    if show_rank:
        muted = " is-muted" if item.rank > 3 else ""
        rank_html = f'<div class="zg-rank{muted}">{item.rank}</div>'

    budget_tone = _budget_tone(item.budget_label)
    chips = chip(item.budget_label, budget_tone) + chip(
        item.match_level, _MATCH_TONE.get(item.match_level, "neutral")
    )

    return (
        f'<div class="zg-card{" is-accent" if show_rank and item.rank == 1 else ""}">'
        f'  <div class="zg-row">'
        f"    {rank_html}"
        f'    <div class="zg-row-main">'
        f'      <div class="zg-row-name">{esc(item.name)}</div>'
        f'      <div class="zg-row-spec">{esc(item.brand or "品牌未知")}'
        f"        · {esc(item.category_label)}</div>"
        f'      <div style="display:flex;flex-wrap:wrap;gap:6px">{chips}</div>'
        f"    </div>"
        f'    <div style="text-align:right;flex-shrink:0">'
        f'      <div class="zg-price">{esc(item.price_label)}</div>'
        f"    </div>"
        f'    <div class="zg-row-score">'
        f'      <div class="zg-score-num">{item.score_total:.0f}<small>/100</small></div>'
        f'      <div style="margin:3px 0">{stars(item.score_total)}</div>'
        f'      <div class="zg-score-name">{esc(config.SCORE_DISPLAY_NAME)}</div>'
        f"    </div>"
        f"  </div>"
        f'  <div class="zg-source">数据来源：{esc(item.data_source or "信息缺失")}'
        f"　·　更新时间：{esc(item.updated_at or '信息缺失')}</div>"
        f"</div>"
    )


def render_stored_report(report) -> None:
    """把一份**固化的**历史报告渲染出来。

    所有数据都来自报告快照本身，不访问当前商品库——
    这样商品数据更新后，历史报告的结论依然与当时一致。
    """
    from src.ui.theme import notice as notice_html

    st.markdown(
        f'<div class="zg-caption">生成时间：{esc(report.created_at.replace("T", " ")[:19])}</div>',
        unsafe_allow_html=True,
    )

    section_title("需求摘要")
    st.markdown(f'<div class="zg-card is-flat">{facts(report.demand_facts)}</div>', unsafe_allow_html=True)
    if report.demand_text:
        with st.expander("原始输入"):
            st.write(report.demand_text)

    section_title("预算与筛选条件")
    st.markdown(f'<div class="zg-card is-flat">{facts(report.filter_facts)}</div>', unsafe_allow_html=True)

    section_title("推荐商品及排序", len(report.recommendations) or None)
    if report.recommendations:
        for item in report.recommendations:
            st.markdown(report_item_card(item), unsafe_allow_html=True)
            with st.expander(f"{item.name} 的推荐理由与优缺点"):
                st.markdown('<div class="zg-caption">推荐理由</div>', unsafe_allow_html=True)
                st.markdown(bullet_list(item.reasons), unsafe_allow_html=True)
                left, right = st.columns(2)
                with left:
                    st.markdown('<div class="zg-caption">优点</div>', unsafe_allow_html=True)
                    st.markdown(bullet_list(item.pros), unsafe_allow_html=True)
                with right:
                    st.markdown('<div class="zg-caption">缺点</div>', unsafe_allow_html=True)
                    st.markdown(bullet_list(item.cons, tone="con"), unsafe_allow_html=True)
    else:
        empty_state("这次分析没有预算内的匹配商品。", icon_name="alert")

    if report.over_budget:
        section_title("超出预算的候选", len(report.over_budget))
        for item in report.over_budget:
            st.markdown(report_item_card(item, show_rank=False), unsafe_allow_html=True)

    if report.relaxations:
        section_title("放宽条件的建议")
        st.markdown(
            f'<div class="zg-card is-flat">{bullet_list(report.relaxations)}</div>',
            unsafe_allow_html=True,
        )

    section_title("需要进一步核实的信息")
    st.markdown(
        f'<div class="zg-card is-flat">{bullet_list(report.to_verify or ["无"])}</div>',
        unsafe_allow_html=True,
    )

    section_title("最终决策建议")
    st.markdown(
        f'<div class="zg-card is-accent">{esc(report.conclusion)}</div>',
        unsafe_allow_html=True,
    )

    if report.dataset_disclaimer:
        st.markdown(notice_html(report.dataset_disclaimer, "warn"), unsafe_allow_html=True)

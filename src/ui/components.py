"""可复用的界面片段。

全部是**展示逻辑**：把业务层算好的结果拼成 HTML 或调用 Streamlit 组件。
这里不做任何筛选、评分或排序。
"""

from __future__ import annotations

import streamlit as st

from src import config
from src.comparison import format_param
from src.data_loader import Product
from src.scoring import DimensionScore, ScoreResult
from src.ui import theme
from src.ui.theme import badge, bullet_list, esc, facts, notice

#: 卡片上优先展示的核心参数（按重要性排序）。
_HEADLINE_SPECS: dict[str, list[str]] = {
    "laptop": ["cpu", "ram_gb", "storage_gb", "weight_kg"],
    "phone": ["chip", "ram_gb", "battery_mah", "weight_g"],
    "headphone": ["connection", "battery_h", "noise_cancelling"],
    "keyboard": ["layout", "switch_type", "connection"],
}

#: 匹配档位 → 徽章样式。
_MATCH_TONE = {
    "高度匹配": "ok",
    "较为匹配": "info",
    "基本可用": "neutral",
    "匹配度较低": "warn",
}


# --------------------------------------------------------------------------
# 页面骨架
# --------------------------------------------------------------------------


def page_header(title: str, subtitle: str = "") -> None:
    """页面顶部的标题区。"""
    sub = f"<p>{esc(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="zg-hero"><h1>{esc(title)}</h1>{sub}</div>',
        unsafe_allow_html=True,
    )


def section_title(text: str) -> None:
    """区块标题。"""
    st.markdown(f'<div class="zg-section">{esc(text)}</div>', unsafe_allow_html=True)


def caption(text: str) -> None:
    st.markdown(f'<div class="zg-caption">{esc(text)}</div>', unsafe_allow_html=True)


def empty_state(text: str) -> None:
    """空状态占位块。"""
    st.markdown(f'<div class="zg-empty">{esc(text)}</div>', unsafe_allow_html=True)


def show_notice(text: str, tone: str = "info") -> None:
    st.markdown(notice(text, tone), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 评分
# --------------------------------------------------------------------------


def _dimension_bar(dimension: DimensionScore) -> str:
    width = max(0.0, min(100.0, dimension.score))
    return (
        f'<div class="zg-dim">'
        f'  <div class="zg-dim-head">'
        f'    <span class="zg-dim-name">{esc(dimension.label)}'
        f'      <span style="opacity:.65">· 权重 {dimension.weight:.0%}</span></span>'
        f'    <span class="zg-dim-score">{dimension.score:.0f}</span>'
        f"  </div>"
        f'  <div class="zg-bar"><div class="zg-bar-fill" style="width:{width:.1f}%"></div></div>'
        f'  <div class="zg-dim-reason">{esc(dimension.reason)}</div>'
        f"</div>"
    )


def score_breakdown_html(score: ScoreResult) -> str:
    """评分构成：各维度得分条 + 加分项 + 扣分项 + 未参与计算的维度。"""
    ordered = sorted(score.dimensions, key=lambda d: (-d.score, d.key))
    bars = "".join(_dimension_bar(d) for d in ordered)

    parts = [bars]

    if score.bonus:
        parts.append('<div class="zg-caption" style="margin-top:12px">主要加分项</div>')
        parts.append(bullet_list(score.bonus))
    if score.penalty:
        parts.append('<div class="zg-caption" style="margin-top:10px">主要扣分项</div>')
        parts.append(bullet_list(score.penalty, tone="con"))
    if score.excluded:
        parts.append(
            '<div class="zg-caption" style="margin-top:10px">'
            "以下维度因数据缺失或类别不适用，未参与本次计算</div>"
        )
        parts.append(
            bullet_list([f"{label}：{reason}" for label, reason in score.excluded])
        )

    return "".join(parts)


def render_score_breakdown(score: ScoreResult, *, expanded: bool = False) -> None:
    """把评分构成放进一个可展开区域。

    展开区标题里带上总分，收起时也能看到结论。
    """
    with st.expander(
        f"评分构成与依据 · {config.SCORE_DISPLAY_NAME} {score.total:.0f} 分（{score.match_level}）",
        expanded=expanded,
    ):
        st.markdown(
            f'<div class="zg-caption" style="margin-bottom:8px">'
            f"「{config.SCORE_DISPLAY_NAME}」是本系统按你的需求与商品数据算出的匹配程度，"
            f"<strong>不是用户评价、销量或市场口碑</strong>。</div>",
            unsafe_allow_html=True,
        )
        st.markdown(score_breakdown_html(score), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 商品卡片
# --------------------------------------------------------------------------


def _headline_specs(product: Product) -> list[tuple[str, str]]:
    keys = _HEADLINE_SPECS.get(
        product.category,
        sorted(product.specs)[:3],
    )
    pairs: list[tuple[str, str]] = []
    for key in keys:
        label = _SPEC_LABELS.get(key, key)
        if product.has_spec(key):
            pairs.append((label, format_param(key, product.spec(key))))
        else:
            pairs.append((label, "信息缺失"))
    return pairs


_SPEC_LABELS = {
    "cpu": "处理器",
    "chip": "芯片",
    "ram_gb": "内存",
    "storage_gb": "存储",
    "weight_kg": "重量",
    "weight_g": "重量",
    "battery_h": "续航",
    "battery_mah": "电池",
    "connection": "连接",
    "noise_cancelling": "降噪",
    "layout": "布局",
    "switch_type": "轴体",
}


def _budget_tone(label: str) -> str:
    if label == "预算内":
        return "ok"
    if label.startswith("超出预算"):
        return "warn"
    return "neutral"


def product_card_html(
    product: Product,
    score: ScoreResult,
    budget_label: str,
    *,
    rank: int | None = None,
    highlight: bool = False,
) -> str:
    """一张商品卡片的 HTML。

    卡片上必须能看到：名称、品牌、参考价格、关键参数、系统匹配评分、
    预算匹配状态、以及数据来源标注——最后一项是需求硬性要求的。
    """
    prefix = f"{rank}. " if rank is not None else ""
    title = f"{prefix}{product.name or product.id}"

    badges = [
        badge(budget_label, _budget_tone(budget_label)),
        badge(score.match_level, _MATCH_TONE.get(score.match_level, "neutral")),
    ]
    if not product.is_complete:
        badges.append(badge(f"信息不完整（缺 {len(product.missing_fields)} 项）", "warn"))

    spec_rows = "".join(
        f'<div class="zg-fact"><span class="zg-fact-key">{esc(k)}</span>'
        f'<span class="zg-fact-val">{esc(v)}</span></div>'
        for k, v in _headline_specs(product)
    )

    return (
        f'<div class="zg-card{" is-top" if highlight else ""}">'
        f'  <div class="zg-card-head">'
        f"    <div>"
        f'      <div class="zg-card-title">{esc(title)}</div>'
        f'      <div class="zg-card-sub">{esc(product.brand or "品牌未知")}'
        f"        · {esc(product.category_label)}</div>"
        f'      <div style="margin-top:8px">{"".join(badges)}</div>'
        f"    </div>"
        f'    <div class="zg-score-top">'
        f'      <div class="zg-score-num">{score.total:.0f}<small> / 100</small></div>'
        f'      <div class="zg-score-level">{esc(config.SCORE_DISPLAY_NAME)}</div>'
        f"    </div>"
        f"  </div>"
        f'  <div class="zg-price">{esc(product.price_label)}<small> 参考价格</small></div>'
        f'  <div class="zg-facts" style="margin-top:10px">{spec_rows}</div>'
        f'  <div class="zg-source">数据来源：{esc(product.data_source or "信息缺失")}'
        f"　·　更新时间：{esc(product.updated_at or '信息缺失')}</div>"
        f"</div>"
    )


def render_product_card(
    product: Product,
    score: ScoreResult,
    budget_label: str,
    *,
    rank: int | None = None,
    highlight: bool = False,
    expanded: bool = False,
) -> None:
    """渲染一张完整卡片：主体 + 可展开的评分构成与优缺点。"""
    st.markdown(
        product_card_html(product, score, budget_label, rank=rank, highlight=highlight),
        unsafe_allow_html=True,
    )
    render_score_breakdown(score, expanded=expanded)

    pros_cons = st.expander("优点与不足")
    with pros_cons:
        left, right = st.columns(2)
        with left:
            st.markdown('<div class="zg-caption">优点</div>', unsafe_allow_html=True)
            st.markdown(bullet_list(product.pros), unsafe_allow_html=True)
        with right:
            st.markdown('<div class="zg-caption">缺点</div>', unsafe_allow_html=True)
            st.markdown(bullet_list(product.cons, tone="con"), unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 提示汇总
# --------------------------------------------------------------------------


def render_notes(notes: list[str]) -> None:
    """把分析过程中的说明按重要程度分色展示。

    含「低于」「超出」「不完整」等字样的当成需要留意的，
    其余当普通说明——不额外增加业务判断，只按关键词分类。
    """
    if not notes:
        return
    for text in notes:
        tone = "warn" if any(k in text for k in ("低于", "超出", "不完整", "缺少", "无法确认")) else "info"
        st.markdown(notice(text, tone), unsafe_allow_html=True)


def runtime_badge() -> str:
    """当前运行模式的徽章 HTML。"""
    from src.ui.state import current_mode

    mode, detail = current_mode()
    tone = "info" if mode == "AI 增强模式" else "neutral"
    return badge(f"{mode} · {detail}", tone)

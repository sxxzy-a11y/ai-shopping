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

#: 卡片与商品行上优先展示的核心参数。**只覆盖商品库实际的两个类别**——
#: 表外的类别会落到下面那句 `sorted(product.specs)[:3]` 兜底，不会不显示。
_HEADLINE_SPECS: dict[str, list[str]] = {
    "laptop": ["cpu", "ram_gb", "storage_gb", "weight_kg"],
    "phone": ["chip", "ram_gb", "storage_gb", "weight_g"],
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


def enter_once(key: str) -> str:
    """本次会话第一次进入某页时返回入场类名，之后返回空串。

    每页一个标记：侧栏切换、展开评分、提交表单都会重跑脚本，
    没有这个标记的话入场动画会在每次交互时重播。
    """
    flag = f"zg_enter_{key}"
    if st.session_state.get(flag):
        return ""
    st.session_state[flag] = True
    return " zg-enter"


def page_header(
    title: str,
    subtitle: str = "",
    *,
    right: str = "",
    kicker: str = "采购工作台",
    enter_key: str = "",
) -> None:
    """页面顶部标题区。`right` 可放一段右对齐的 HTML（状态、按钮等）。"""
    sub = f"<p>{esc(subtitle)}</p>" if subtitle else ""
    kicker_html = (
        f'<div class="zg-hero-kicker"><span>{esc(kicker)}</span></div>'
        if kicker
        else ""
    )
    left = f'<div style="min-width:0"><h1>{esc(title)}</h1>{sub}</div>'
    row = f'<div class="zg-hero-row">{left}{right}</div>' if right else left
    enter = enter_once(enter_key) if enter_key else ""
    st.markdown(
        f'<div class="zg-hero{enter}">{kicker_html}{row}</div>',
        unsafe_allow_html=True,
    )


def home_masthead(
    title: str,
    subtitle: str,
    *,
    right: str = "",
    enter_class: str = "",
) -> str:
    """首页深色刊头：把「决策台」的流程直接写在页面上。"""
    return (
        f'<section class="zg-home-masthead{enter_class}">'
        f'  <div class="zg-masthead-top">'
        f'    <span><b>智购参谋</b> · 采购决策工作台</span>'
        f"    <span>{right}</span>"
        f"  </div>"
        f'  <h1 class="zg-masthead-title">{esc(title)}</h1>'
        f'  <p class="zg-masthead-sub">{esc(subtitle)}</p>'
        f'  <div class="zg-masthead-steps">'
        f"    <span>描述需求</span>"
        f"    <span>核对证据</span>"
        f"    <span>做出决定</span>"
        f"  </div>"
        f"</section>"
    )


def rail_notes(
    items: list[tuple[str, str, str]], *, enter_class: str = ""
) -> str:
    """编号脚注列表：把能力说明从「四张卡」改成一条可读的边栏。"""
    notes = "".join(
        f'<div class="zg-rail-note">'
        f'  <span class="zg-rail-index"></span>'
        f"  <div><b>{esc(title)}</b><p>{esc(desc)}</p></div>"
        f"</div>"
        for _icon, title, desc in items
    )
    cls = f"zg-rail{enter_class}"
    return f'<div class="{cls}">{notes}</div>'


def brief_label(text: str) -> None:
    """表单/区块前的等宽小标，像研究简报的栏目标签。"""
    st.markdown(
        f'<div class="zg-brief-label">{esc(text)}</div>', unsafe_allow_html=True
    )


def section_title(text: str, count: int | None = None) -> None:
    st.markdown(section(text, count), unsafe_allow_html=True)


def verdict_strip(item) -> str:
    """分析结果的第一屏结论：首选、分数、预算状态与最强项。

    只使用本次已经算出的真实字段，不另写推荐语。
    """
    product = item.product
    score = item.score
    dims = sorted(score.dimensions, key=lambda d: (-d.score, d.key))[:2]
    dim_html = "".join(
        f"<span>{esc(d.label)} <b>{d.score:.0f}</b></span>" for d in dims
    )
    return (
        '<div class="zg-verdict">'
        '  <div class="zg-verdict-kicker">首选方案</div>'
        '  <div class="zg-verdict-main">'
        f'    <div class="zg-verdict-name">{esc(product.name or product.id)}</div>'
        f'    <div class="zg-verdict-score">{score.total:.0f}<small>/100</small></div>'
        f"  </div>"
        f'  <div class="zg-verdict-meta">{esc(product.price_label)}'
        f"　·　{esc(item.budget_label)}　·　{esc(score.match_level)}</div>"
        f'  <div class="zg-verdict-dims">{dim_html}</div>'
        f"</div>"
    )


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
        f'  <div class="zg-stat-icon">{icons.icon(icon_name, size=20)}</div>'
        f'  <div>'
        f'    <div class="zg-stat-value">{esc(value)}</div>'
        f'    <div class="zg-stat-label">{esc(label)}</div>'
        f"  </div>"
        f"</div>"
    )


def stat_row(tiles: list[tuple[str, str, str]]) -> None:
    """一条统计带。tiles 为 (图标名, 数值, 说明) 列表。

    整条渲染成**一个** HTML 块而不是 N 个 Streamlit 列——用 grid 才能保证
    格子之间有分隔线、整条共享一层白底；拆成列的话每格各自为政，
    又会变回「四张卡」的样子。
    """
    cells = "".join(stat_tile(*tile) for tile in tiles)
    st.markdown(f'<div class="zg-statstrip">{cells}</div>', unsafe_allow_html=True)


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
        f"查看详情 · 评分构成与依据 · {config.SCORE_DISPLAY_NAME} {score.total:.0f} 分"
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


#: 执行轨迹里状态的展示文案与色调。
_TRACE_TONES: dict[str, tuple[str, str]] = {
    "ok": ("ok", "成功"),
    "rejected": ("stop", "参数被拒"),
    "error": ("warn", "执行出错"),
}


def render_agent_trace(run) -> None:
    """渲染一次 Agent 编排的执行轨迹。

    展示的是**真实发生过的工具调用**——工具名、模型给的参数、结果摘要。
    刻意不展示模型的思考文字：那才是「看起来像 Agent、实际只是聊天」的形态。

    被参数校验拒绝的调用同样展示，并且用醒目的色调标出来。那不是失败展示，
    而是**校验在起作用的证据**：模型给错了参数、系统拦住了、模型换了说法。
    """
    if run is None:
        return

    if run.answer:
        with st.container(border=True):
            st.markdown(
                '<div class="zg-card-title">AI 的分析结论</div>',
                unsafe_allow_html=True,
            )
            st.markdown(run.answer)
            caption(
                "这段结论由 AI 调用下列工具后得出，请以工具返回的数据为准。"
            )

    section_title("AI 执行过程", len(run.trace))

    if not run.trace:
        show_notice("本次未使用工具，AI 直接依据已有数据作答。", "info")
        return

    caption(
        f"共 {run.rounds} 轮、{len(run.trace)} 次工具调用。"
        "下面是实际发生过的调用记录，不是模型的思考过程。"
    )

    for index, step in enumerate(run.trace, start=1):
        tone, status_text = _TRACE_TONES.get(step.status, ("neutral", step.status))
        st.markdown(
            f'<div class="zg-card is-flat" style="margin-bottom:8px">'
            f'  <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">'
            f"    <strong>{index}. {esc(step.tool)}</strong>"
            f"    {chip(f'第 {step.round} 轮', 'neutral')}"
            f"    {chip(status_text, tone)}"
            f"  </div>"
            f'  <div class="zg-caption" style="margin-top:6px">'
            f"    参数：{esc(step.arguments_label)}</div>"
            f'  <div class="zg-caption">结果：{esc(step.summary)}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )


#: 「资料存疑」标记的文案。
#: 刻意不用「数据错误」——规则是保守的，标记的用途是**提示核实**，不是判决。
DATA_ISSUE_LABEL = "资料存疑"


def data_issue_chip(product: Product) -> str:
    """商品记录内部有矛盾时的标记；没有矛盾时返回空串。

    悬停可看到具体是哪一项、为什么判为矛盾。标记**不影响**该商品参与
    筛选、评分与比较——只是提醒这些属性不要直接采信。
    """
    issues = getattr(product, "data_issues", None)
    if not issues:
        return ""
    detail = "；".join(f"{issue.reason}" for issue in issues)
    return chip(DATA_ISSUE_LABEL, "warn", title=detail)


def product_row(
    product: Product,
    score: ScoreResult,
    budget_label: str,
    *,
    rank: int | None = None,
    highlight: bool = False,
    ai_note: str = "",
) -> str:
    """推荐列表里的一行商品。

    必须能看到：排名、类别图标（图片占位）、名称、规格、预算匹配状态、
    参考价格、系统匹配评分、以及数据来源标注——最后一项是需求硬性要求的。
    """
    rank_html = ""
    if rank is not None:
        muted = " is-muted" if rank > 3 else ""
        rank_html = f'<div class="zg-rank{muted}">{rank}</div>'

    top_dim = (
        max(score.dimensions, key=lambda dimension: dimension.score)
        if score.dimensions
        else None
    )
    reason_html = (
        f'<div class="zg-row-reason">{esc(top_dim.reason)}</div>'
        if top_dim is not None and top_dim.reason
        else ""
    )

    return (
        f'<div class="zg-card{" is-accent" if highlight else ""}">'
        f'  <div class="zg-row">'
        f"    {rank_html}"
        f'    {_thumb(product, size=27)}'
        f'    <div class="zg-row-main">'
        f'      <div class="zg-row-name">{esc(product.name or product.id)}</div>'
        f'      <div class="zg-row-spec">{esc(product.brand or "品牌未知")}'
        f"        · {esc(product.category_label)} · {esc(_spec_line(product))}</div>"
        f'      <div style="display:flex;flex-wrap:wrap;gap:6px">'
        f'        {chip(budget_label, _budget_tone(budget_label))}'
        f'        {chip(score.match_level, _MATCH_TONE.get(score.match_level, "neutral"))}'
        f"        {data_issue_chip(product)}"
        f"      </div>"
        f"      {reason_html}"
        f"    </div>"
        f'    <div style="text-align:right;flex-shrink:0">'
        f'      <div class="zg-price">{esc(product.price_label)}</div>'
        f"    </div>"
        f'    <div class="zg-row-score">'
        f'      <div class="zg-score-num">{score.total:.0f}<small>/100</small></div>'
        f'      <div class="zg-score-name">{esc(config.SCORE_DISPLAY_NAME)}</div>'
        f"    </div>"
        f"  </div>"
        + (
            f'  <div class="zg-notice zg-notice-info" style="margin:12px 0 0 0">'
            f'<span class="zg-notice-icon">{icons.icon("sparkles", size=16)}</span>'
            f'<span><strong>AI 解读</strong>：{esc(ai_note)}</span></div>'
            if ai_note
            else ""
        )
        + "  " + _source_line(product)
        + f"</div>"
    )


def _source_line(product) -> str:
    """商品卡片底部的来源信息行。

    需求硬性要求「看到资料来源与更新时间」，这个变更又加了核验状态与
    逐条来源链接。**未核验要显眼**——不标注的话，用户会把整理来的数据
    当成核实过的信息。

    价格来自价格记录，所以它有自己的来源与采集时间；与整条记录的来源
    不同时才单独列出，避免同一句话重复两遍。
    """
    parts = [f"数据来源：{esc(product.data_source or '信息缺失')}"]
    parts.append(f"更新时间：{esc(product.updated_at or '信息缺失')}")

    status = "已核验" if getattr(product, "is_verified", False) else "未核验"
    tone = "ok" if status == "已核验" else "warn"
    parts.append(chip(status, tone))

    if getattr(product, "has_source_url", False):
        url = esc(product.source_url)
        parts.append(f'<a href="{url}" target="_blank" rel="noopener">来源链接</a>')

    price_source = getattr(product, "price_source", "")
    if price_source and price_source != product.data_source:
        collected = getattr(product, "price_collected_at", "")
        suffix = f"（{esc(collected)}）" if collected else ""
        parts.append(f"价格来自：{esc(price_source)}{suffix}")

    return '<div class="zg-source">' + "　·　".join(parts) + "</div>"


def _thumb(product, *, size: int = 27, large: bool = False, style: str = "") -> str:
    """商品缩略图：有图片显示图片，没有或加载失败回落类别图标。

    **外链图片随时会挂，而演示现场最不能接受的就是破图。** 做法是把类别图标
    垫在底下、图片绝对定位盖在上面，图片 `onerror` 时把自己隐藏——
    「图挂了」于是退化成「看到图标」，而不是「看到一张破图」。
    """
    klass = "zg-thumb is-lg" if large else "zg-thumb"
    attrs = f' style="{style}"' if style else ""
    icon = icons.category_icon(product.category, size=size)
    # 要 strip：只有空白的地址不是地址，拼进 `src` 之后浏览器会把它当成
    # 当前页面地址再请求一次——多一个无意义的请求，还得靠 onerror 兜回来。
    url = str(getattr(product, "image_url", "") or "").strip()
    if not url:
        return f'<div class="{klass}"{attrs}>{icon}</div>'
    return (
        f'<div class="{klass}"{attrs}>{icon}'
        f'<img src="{esc(url)}" alt="" loading="lazy" '
        f"onerror=\"this.style.display='none'\"></div>"
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
    ai_note: str = "",
) -> None:
    """商品行 + 可展开的评分构成与优缺点。

    `extra_actions` 会在「优点与不足」展开区末尾调用一次，用于挂收藏之类的
    操作按钮。做成回调而不是直接在这里写按钮，是为了让组件层不依赖数据库——
    它只管画，不该知道数据存在哪。
    """
    st.markdown(
        product_row(
            product, score, budget_label, rank=rank, highlight=highlight, ai_note=ai_note
        ),
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
        f'    {_thumb(product, size=30, large=True)}'
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


def compare_overview(products, *, budgets: dict[str, str], scores: dict) -> str:
    """比较页顶部的商品概览网格。

    竖向排布（图标在上、文字在下）而不是横向的行式卡片：
    比较 5 件时每格只有 150–200px，横向排布会把中文名挤成一个字一行。
    用 grid 让列数随宽度自适应，窄屏自动减少列数。
    """
    cells = []
    for product in products:
        score = scores.get(product.id)
        score_html = ""
        if score is not None:
            score_html = (
                f'<div class="zg-compare-score">{score.total:.0f}<small>/100</small></div>'
                f'<div style="margin-top:4px">{stars(score.total, size=12)}</div>'
                f'<div style="font-size:11px;color:{theme.INK_SOFT};margin-top:3px">'
                f"{esc(config.SCORE_DISPLAY_NAME)}</div>"
            )
        budget = budgets.get(product.id, "")
        cells.append(
            f'<div class="zg-compare-cell">'
            f'  {_thumb(product, size=26)}'
            f'  <div class="zg-compare-name">{esc(product.name or product.id)}</div>'
            f'  <div class="zg-compare-brand">{esc(product.brand or "品牌未知")}'
            f"    · {esc(product.category_label)}</div>"
            f'  <div class="zg-compare-price">{esc(product.price_label)}</div>'
            f'  <div>{chip(budget, _budget_tone(budget))}</div>'
            f'  <div style="margin-top:11px">{score_html}</div>'
            f"</div>"
        )
    return f'<div class="zg-compare-grid">{"".join(cells)}</div>'


def pros_cons_grid(products) -> str:
    """所有参评商品的优缺点，平铺展示、不用逐个点开。

    原先用的是折叠面板，比较 5 件时要点 5 次才看得到内容——
    而「优缺点」恰恰是决策时最需要横向看的东西。
    """
    cards = []
    for product in products:
        pros = "".join(f"<li>{esc(item)}</li>" for item in product.pros) or "<li>无</li>"
        cons = "".join(f"<li>{esc(item)}</li>" for item in product.cons) or "<li>无</li>"
        cards.append(
            f'<div class="zg-proscons-card">'
            f'  <div class="zg-proscons-title">'
            f'    {_thumb(product, size=17, style="width:30px;height:30px;border-radius:8px")}'
            f"    {esc(product.name or product.id)}</div>"
            f'  <div class="zg-proscons-sub">优点</div>'
            f'  <ul class="zg-list">{pros}</ul>'
            f'  <div class="zg-proscons-sub">缺点</div>'
            f'  <ul class="zg-list zg-list-con">{cons}</ul>'
            f"</div>"
        )
    return f'<div class="zg-proscons">{"".join(cards)}</div>'


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
        f"  {_source_line(item)}"
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

"""配色令牌与全局样式。

样式策略
--------
分三层，按「稳定性」排序使用：

1. `.streamlit/config.toml` 的官方 `[theme]` —— 最稳，跨版本可用。
2. 标准 HTML 标签与稳定类名（`label`、`button[kind]`、`.stButton`）上的自定义
   样式 —— 这些不是 Streamlit 生成的哈希类名，改版不会失效。
3. 少量 `[data-testid="..."]` 选择器 —— **只有深色侧栏这一处**。

关于第 3 层的说明
-----------------
Streamlit 没有官方 API 能改侧栏底色，只能用 `[data-testid="stSidebar"]`。
这确实是在依赖非公开结构。缓解措施有三条：

- 需求里已经把这个风险写明了，这里不装作没有
- `requirements.txt` 锁定 Streamlit 版本到实测通过的那一版
- `tests/test_app.py` 里有一条断言检查侧栏确实是深色 —— 将来升级把它改坏了，
  测试会失败，而不是悄悄退化成浅色

绝不使用 `st-emotion-cache-*` 这类哈希类名：那是每次发版都会变的东西。

图标分工
--------
- 侧栏导航：官方 Material Symbols（通过 `st.button(icon=...)`）
- 卡片与内容区：本项目的内联 SVG（`src/ui/icons.py`），因为
  `unsafe_allow_html` 的 HTML 里不解析 `:material/x:` 语法
"""

from __future__ import annotations

import html

# --------------------------------------------------------------------------
# 色彩令牌
# --------------------------------------------------------------------------

# 品牌深蓝：侧栏底色
NAVY_900 = "#0F2942"
NAVY_800 = "#16324F"

# 主操作色
BRAND = "#2563EB"
BRAND_DARK = "#1D4ED8"
BRAND_50 = "#EFF4FF"
BRAND_100 = "#DCE7FF"

# 页面与卡片
BG = "#F7F9FC"
SURFACE = "#FFFFFF"
LINE = "#E4E7EC"
LINE_SOFT = "#F0F2F5"

# 文字
INK = "#101828"
INK_SOFT = "#667085"
INK_FAINT = "#98A2B3"
ON_NAVY = "#C3D0E0"       # 深色侧栏上的次级文字
SIDEBAR_MUTED = "#8296AD"  # 深色侧栏上的弱化文字

# 语义色（前缀 _BG 为浅底，无后缀为前景）
OK = "#12B76A"
OK_BG = "#ECFDF3"
WARN = "#F79009"
WARN_BG = "#FFFAEB"
DANGER = "#F04438"
DANGER_BG = "#FEF3F2"
INFO = "#175CD3"
INFO_BG = "#EFF8FF"
STAR = "#F59E0B"

#: 卡片阴影。克制的一层，不用大扩散。
SHADOW = "0 1px 2px rgba(16,24,40,.05), 0 1px 3px rgba(16,24,40,.06)"

_STYLES = f"""
<style>
  /* ===================================================================
     侧栏（唯一使用 data-testid 的地方，见模块 docstring）
     =================================================================== */
  [data-testid="stSidebar"] {{
    background: {NAVY_900};
    border-right: none;
  }}
  [data-testid="stSidebar"] > div:first-child {{ background: transparent; }}
  [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{
    padding-top: 4px;
  }}
  /* 侧栏里所有分隔线调成半透明白 */
  [data-testid="stSidebar"] hr {{
    border-color: rgba(255,255,255,.10);
    margin: 14px 0;
  }}
  /* 侧栏里的基础文字色 */
  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] span,
  [data-testid="stSidebar"] li {{ color: {ON_NAVY}; }}

  /* 导航按钮：整块可点、左对齐、无边框 */
  [data-testid="stSidebar"] .stButton > button {{
    width: 100%;
    justify-content: flex-start;
    text-align: left;
    background: transparent;
    border: none;
    box-shadow: none;
    color: {ON_NAVY};
    font-weight: 500;
    padding: 9px 12px;
    border-radius: 9px;
    min-height: 40px;
    transition: background .14s ease, color .14s ease;
  }}
  [data-testid="stSidebar"] .stButton > button p {{
    color: inherit;
    font-size: 14.5px;
  }}
  [data-testid="stSidebar"] .stButton > button:hover {{
    background: rgba(255,255,255,.08);
    color: #FFFFFF;
  }}
  /* 当前页：用官方 primary 按钮态，颜色来自 config.toml 的 primaryColor */
  [data-testid="stSidebar"] .stButton > button[kind="primary"] {{
    background: {BRAND};
    color: #FFFFFF;
  }}
  [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {{
    background: {BRAND_DARK};
  }}
  /* 侧栏内按钮之间收紧间距 */
  [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: .25rem; }}

  /* ===================================================================
     页头
     =================================================================== */
  .zg-hero {{ margin: 2px 0 20px 0; }}
  .zg-hero h1 {{
    font-size: 27px; font-weight: 700; color: {INK};
    margin: 0 0 7px 0; letter-spacing: -.2px; line-height: 1.3;
  }}
  .zg-hero p {{
    color: {INK_SOFT}; font-size: 14.5px; margin: 0; line-height: 1.75;
    max-width: 880px;
  }}
  .zg-hero-row {{
    display: flex; justify-content: space-between; align-items: flex-end;
    gap: 20px; flex-wrap: wrap;
  }}

  /* ===================================================================
     区块标题
     =================================================================== */
  .zg-section {{
    display: flex; align-items: center; gap: 8px;
    font-size: 16.5px; font-weight: 650; color: {INK};
    margin: 26px 0 13px 0;
  }}
  .zg-section .zg-count {{
    font-size: 12.5px; font-weight: 500; color: {INK_SOFT};
    background: {LINE_SOFT}; padding: 1px 9px; border-radius: 999px;
  }}
  .zg-caption {{ color: {INK_SOFT}; font-size: 13.5px; line-height: 1.75; }}
  .zg-muted {{ color: {INK_FAINT}; font-size: 12.5px; }}

  /* ===================================================================
     卡片
     =================================================================== */
  .zg-card {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 12px;
    padding: 18px 20px; margin-bottom: 12px;
    box-shadow: {SHADOW};
  }}
  .zg-card.is-flat {{ box-shadow: none; }}
  .zg-card.is-accent {{ border-left: 3px solid {BRAND}; }}
  .zg-card.is-warn {{ border-left: 3px solid {WARN}; }}
  .zg-card-head {{
    display: flex; justify-content: space-between; align-items: flex-start;
    gap: 16px; margin-bottom: 12px;
  }}
  .zg-card-title {{
    font-size: 15.5px; font-weight: 650; color: {INK}; margin: 0 0 3px 0;
  }}
  .zg-card-sub {{ color: {INK_SOFT}; font-size: 13px; }}

  /* ===================================================================
     商品行的图标块（类别占位图）
     =================================================================== */
  .zg-thumb {{
    width: 52px; height: 52px; border-radius: 11px; flex-shrink: 0;
    background: {BRAND_50}; border: 1px solid {BRAND_100};
    display: flex; align-items: center; justify-content: center;
    color: {BRAND};
  }}
  .zg-thumb.is-lg {{ width: 62px; height: 62px; border-radius: 13px; }}

  /* ===================================================================
     商品行
     =================================================================== */
  .zg-row {{ display: flex; gap: 14px; align-items: flex-start; }}
  .zg-row-main {{ flex: 1; min-width: 0; }}
  .zg-row-name {{
    font-size: 15.5px; font-weight: 650; color: {INK};
    margin: 0 0 4px 0; line-height: 1.4;
  }}
  .zg-row-spec {{
    color: {INK_SOFT}; font-size: 13px; line-height: 1.6;
    margin-bottom: 8px;
  }}
  .zg-price {{
    font-size: 18px; font-weight: 700; color: {INK};
    font-variant-numeric: tabular-nums; white-space: nowrap;
  }}
  .zg-price small {{ font-size: 12px; font-weight: 400; color: {INK_SOFT}; }}
  .zg-row-score {{ text-align: right; flex-shrink: 0; min-width: 92px; }}
  .zg-score-num {{
    font-size: 25px; font-weight: 700; color: {INK};
    font-variant-numeric: tabular-nums; line-height: 1.1;
  }}
  .zg-score-num small {{ font-size: 12px; font-weight: 400; color: {INK_FAINT}; }}
  .zg-score-name {{ font-size: 11.5px; color: {INK_SOFT}; margin-top: 3px; }}

  /* 排名角标 */
  .zg-rank {{
    width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0;
    background: {BRAND}; color: #fff; font-size: 12.5px; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
    margin-top: 15px;
  }}
  .zg-rank.is-muted {{ background: {LINE}; color: {INK_SOFT}; }}

  /* ===================================================================
     标签
     =================================================================== */
  .zg-chip {{
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 9px; border-radius: 6px;
    font-size: 12px; font-weight: 500; white-space: nowrap;
  }}
  .zg-chip-ok      {{ background: {OK_BG};     color: {OK}; }}
  .zg-chip-warn    {{ background: {WARN_BG};   color: #B54708; }}
  .zg-chip-stop    {{ background: {DANGER_BG}; color: #B42318; }}
  .zg-chip-info    {{ background: {INFO_BG};   color: {INFO}; }}
  .zg-chip-brand   {{ background: {BRAND_50};  color: {BRAND}; }}
  .zg-chip-neutral {{ background: {LINE_SOFT}; color: {INK_SOFT}; }}

  /* 可选中的品牌标签（设置页） */
  .zg-chip-lg {{ padding: 6px 14px; border-radius: 8px; font-size: 13.5px; }}

  /* ===================================================================
     评分条
     =================================================================== */
  .zg-dim {{ margin: 9px 0; }}
  .zg-dim-head {{
    display: flex; justify-content: space-between; align-items: baseline;
    font-size: 13px; margin-bottom: 5px;
  }}
  .zg-dim-name {{ color: {INK}; font-weight: 500; }}
  .zg-dim-weight {{ color: {INK_FAINT}; font-size: 11.5px; margin-left: 5px; }}
  .zg-dim-score {{
    font-weight: 650; color: {INK}; font-variant-numeric: tabular-nums;
  }}
  .zg-bar {{
    height: 6px; background: {LINE_SOFT}; border-radius: 3px; overflow: hidden;
  }}
  .zg-bar-fill {{ height: 6px; border-radius: 3px; background: {BRAND}; }}
  .zg-dim-reason {{
    font-size: 12.5px; color: {INK_SOFT}; margin-top: 4px; line-height: 1.65;
  }}

  /* ===================================================================
     星级（只是系统匹配评分的可视化，不是用户评价）
     =================================================================== */
  .zg-stars {{ display: inline-flex; gap: 1.5px; vertical-align: middle; }}
  .zg-star-on  {{ color: {STAR}; }}
  .zg-star-off {{ color: {LINE}; }}

  /* ===================================================================
     状态提示条
     =================================================================== */
  .zg-notice {{
    display: flex; gap: 10px; align-items: flex-start;
    border-radius: 10px; padding: 12px 15px; margin-bottom: 10px;
    font-size: 13.5px; line-height: 1.75;
  }}
  .zg-notice .zg-notice-icon {{ flex-shrink: 0; margin-top: 2px; }}
  .zg-notice-info {{ background: {INFO_BG};   color: {INFO}; }}
  .zg-notice-warn {{ background: {WARN_BG};   color: #B54708; }}
  .zg-notice-stop {{ background: {DANGER_BG}; color: #B42318; }}
  .zg-notice-ok   {{ background: {OK_BG};     color: #027A48; }}

  /* ===================================================================
     键值清单
     =================================================================== */
  .zg-facts {{ margin: 0; }}
  .zg-fact {{
    display: flex; gap: 12px; font-size: 13.5px;
    padding: 7px 0; line-height: 1.65; border-bottom: 1px solid {LINE_SOFT};
  }}
  .zg-fact:last-child {{ border-bottom: none; }}
  .zg-fact-key {{ color: {INK_SOFT}; min-width: 74px; flex-shrink: 0; }}
  .zg-fact-val {{ color: {INK}; font-weight: 500; }}

  /* ===================================================================
     列表
     =================================================================== */
  .zg-list {{ margin: 2px 0 0 0; padding-left: 0; list-style: none; }}
  .zg-list li {{
    font-size: 13.5px; color: {INK}; line-height: 1.85;
    padding-left: 16px; position: relative;
  }}
  .zg-list li:before {{
    content: ""; position: absolute; left: 3px; top: 10px;
    width: 4px; height: 4px; border-radius: 50%; background: {BRAND};
  }}
  .zg-list-con li:before {{ background: {DANGER}; }}

  /* ===================================================================
     统计带（首页）
     ===================================================================
     刻意做成**一条轻量数字带**而不是四张卡：上面紧挨着功能卡，
     再排四张同样带边框的卡会显得重复，整页变成两排盒子。
     这里只在整条上给一层白底，格子之间不加任何框。 */
  .zg-statstrip {{
    display: grid; grid-template-columns: repeat(4, 1fr);
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 12px;
    box-shadow: {SHADOW}; overflow: hidden;
  }}
  .zg-stat {{
    display: flex; align-items: center; gap: 13px;
    padding: 18px 20px;
    border-right: 1px solid {LINE_SOFT};
  }}
  .zg-stat:last-child {{ border-right: none; }}
  .zg-stat-icon {{
    width: 38px; height: 38px; border-radius: 10px; flex-shrink: 0;
    background: {BRAND_50}; color: {BRAND};
    display: flex; align-items: center; justify-content: center;
  }}
  .zg-stat-value {{
    font-size: 25px; font-weight: 700; color: {INK};
    line-height: 1.1; font-variant-numeric: tabular-nums;
  }}
  .zg-stat-label {{ font-size: 12.5px; color: {INK_SOFT}; margin-top: 2px; }}

  @media (max-width: 900px) {{
    .zg-statstrip {{ grid-template-columns: repeat(2, 1fr); }}
    .zg-stat:nth-child(2) {{ border-right: none; }}
    .zg-stat:nth-child(-n + 2) {{ border-bottom: 1px solid {LINE_SOFT}; }}
  }}

  /* ===================================================================
     功能卡（首页「快速开始」）
     =================================================================== */
  .zg-feature {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 12px;
    padding: 18px; box-shadow: {SHADOW}; height: 100%;
  }}
  .zg-feature-icon {{
    width: 40px; height: 40px; border-radius: 10px; background: {BRAND_50};
    color: {BRAND}; display: flex; align-items: center; justify-content: center;
    margin-bottom: 12px;
  }}
  .zg-feature-title {{
    font-size: 15px; font-weight: 650; color: {INK}; margin-bottom: 5px;
  }}
  .zg-feature-desc {{ font-size: 13px; color: {INK_SOFT}; line-height: 1.7; }}

  /* ===================================================================
     圆环进度
     =================================================================== */
  .zg-ring-wrap {{ display: flex; align-items: center; gap: 16px; }}
  .zg-ring {{ position: relative; flex-shrink: 0; }}
  .zg-ring-value {{
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
  }}
  .zg-ring-num {{
    font-size: 20px; font-weight: 700; color: {INK}; line-height: 1;
    font-variant-numeric: tabular-nums;
  }}
  .zg-ring-unit {{ font-size: 10.5px; color: {INK_FAINT}; margin-top: 1px; }}
  .zg-ring-text {{ min-width: 0; }}
  .zg-ring-title {{ font-size: 14px; font-weight: 600; color: {INK}; margin-bottom: 3px; }}
  .zg-ring-desc {{ font-size: 12.5px; color: {INK_SOFT}; line-height: 1.65; }}

  /* ===================================================================
     比较页：商品概览网格
     ===================================================================
     用 CSS grid 而不是 st.columns：列数由容器宽度自动决定，每格有最小宽度
     保证中文名能正常换行。st.columns(N) 在 N=5 时每列只剩 ~180px，
     减去图标块后文字区不足 110px，中文会被一个字一行地竖排下来。 */
  .zg-compare-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(158px, 1fr));
    gap: 10px;
    margin-bottom: 4px;
  }}
  .zg-compare-cell {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 12px;
    padding: 16px 14px; box-shadow: {SHADOW};
    display: flex; flex-direction: column; align-items: center;
    text-align: center; gap: 0;
  }}
  .zg-compare-name {{
    font-size: 14.5px; font-weight: 650; color: {INK};
    line-height: 1.45; margin: 11px 0 3px 0;
    word-break: break-word;
  }}
  .zg-compare-brand {{ font-size: 12px; color: {INK_SOFT}; line-height: 1.5; }}
  .zg-compare-price {{
    font-size: 18px; font-weight: 700; color: {INK};
    margin: 9px 0 7px 0; font-variant-numeric: tabular-nums;
  }}
  .zg-compare-score {{
    font-size: 20px; font-weight: 700; color: {INK};
    font-variant-numeric: tabular-nums; line-height: 1.1;
  }}
  .zg-compare-score small {{ font-size: 11.5px; font-weight: 400; color: {INK_FAINT}; }}

  /* ===================================================================
     比较页：优缺点平铺网格
     =================================================================== */
  .zg-proscons {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
  }}
  .zg-proscons-card {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 12px;
    padding: 16px 18px; box-shadow: {SHADOW};
  }}
  .zg-proscons-title {{
    font-size: 14.5px; font-weight: 650; color: {INK};
    padding-bottom: 9px; margin-bottom: 11px; border-bottom: 1px solid {LINE_SOFT};
    display: flex; align-items: center; gap: 8px;
  }}
  .zg-proscons-sub {{
    font-size: 12.5px; font-weight: 600; color: {INK_SOFT};
    margin: 10px 0 4px 0;
  }}
  .zg-proscons-sub:first-of-type {{ margin-top: 0; }}

  /* ===================================================================
     数据来源脚注
     =================================================================== */
  .zg-source {{
    font-size: 12px; color: {INK_FAINT}; margin-top: 13px;
    padding-top: 11px; border-top: 1px dashed {LINE};
    line-height: 1.65;
  }}

  /* ===================================================================
     空状态
     =================================================================== */
  .zg-empty {{
    border: 1px dashed {LINE}; border-radius: 12px;
    padding: 40px 22px; text-align: center; color: {INK_SOFT};
    background: {SURFACE}; font-size: 14px; line-height: 1.85;
  }}
  .zg-empty-icon {{ color: {INK_FAINT}; margin-bottom: 10px; }}

  /* ===================================================================
     主区微调
     =================================================================== */
  .block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; }}
  [data-testid="stMainBlockContainer"] {{ max-width: 1280px; }}

  /* 收起 Streamlit 默认的输入框描边，统一成我们的线色 */
  [data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{
    border-radius: 9px !important;
  }}
</style>
"""


def inject_styles() -> None:
    """把全局样式注入页面。每个页面渲染前调用一次即可。"""
    import streamlit as st

    st.markdown(_STYLES, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# HTML 拼装辅助
# --------------------------------------------------------------------------


def esc(value: object) -> str:
    """转义要插进 HTML 的文本。

    商品名、优缺点等都来自数据文件，未来可能换成外部数据源，
    一律转义，避免内容里的尖括号把页面结构冲掉。
    """
    return html.escape(str(value), quote=True)


#: 语义色调 → CSS 后缀
_TONES = {"ok", "warn", "stop", "info", "brand", "neutral"}


def chip(text: str, tone: str = "neutral", *, large: bool = False) -> str:
    """小标签（徽章）。tone 取 ok / warn / stop / info / brand / neutral。"""
    suffix = tone if tone in _TONES else "neutral"
    size = " zg-chip-lg" if large else ""
    return f'<span class="zg-chip zg-chip-{suffix}{size}">{esc(text)}</span>'


#: 提示条色调 → 图标名
_NOTICE_ICON = {
    "info": "info",
    "warn": "alert",
    "stop": "alert",
    "ok": "check",
}


def notice(text: str, tone: str = "info") -> str:
    """提示条。tone 取 info / warn / stop / ok。"""
    from src.ui.icons import icon

    suffix = tone if tone in _NOTICE_ICON else "info"
    glyph = icon(_NOTICE_ICON[suffix], size=17)
    return (
        f'<div class="zg-notice zg-notice-{suffix}">'
        f'<span class="zg-notice-icon">{glyph}</span>'
        f"<span>{esc(text)}</span></div>"
    )


def facts(pairs: list[tuple[str, str]]) -> str:
    """把 (键, 值) 列表渲染成对齐的清单。"""
    rows = "".join(
        f'<div class="zg-fact">'
        f'<span class="zg-fact-key">{esc(key)}</span>'
        f'<span class="zg-fact-val">{esc(value)}</span>'
        f"</div>"
        for key, value in pairs
    )
    return f'<div class="zg-facts">{rows}</div>'


def bullet_list(items: list[str], tone: str = "") -> str:
    """项目符号清单。tone='con' 时圆点变红。"""
    if not items:
        return '<div class="zg-caption">（无）</div>'
    rows = "".join(f"<li>{esc(item)}</li>" for item in items)
    css = "zg-list zg-list-con" if tone == "con" else "zg-list"
    return f'<ul class="{css}">{rows}</ul>'


def section(title: str, count: int | None = None) -> str:
    """区块标题，可带一个数量角标。"""
    badge = f'<span class="zg-count">{count}</span>' if count is not None else ""
    return f'<div class="zg-section">{esc(title)}{badge}</div>'

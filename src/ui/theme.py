"""配色常量与全局样式。

样式策略（design.md D9）
-----------------------
只做两件事：

1. `.streamlit/config.toml` 里的官方 `[theme]` 配置——稳定、跨版本可用。
2. 本模块注入的 CSS，**全部挂在自有 class 上**（`.zg-*`）。

**不覆盖 Streamlit 的内部类名**（`st-emotion-cache-*` 之类）。那些名字
每次发版都可能变，绑上去等于给升级埋雷——需求里也明确禁止了。

所以视觉重点放在我们自己渲染的内容上：卡片、评分条、徽章、提示条。
"""

from __future__ import annotations

import html

# --------------------------------------------------------------------------
# 配色
# --------------------------------------------------------------------------

INK = "#1F2933"          # 正文
INK_SOFT = "#5A6472"     # 次要文字
NAVY = "#1B3A6B"         # 主色：深蓝
NAVY_SOFT = "#4A6FA5"    # 主色浅一档
LINE = "#E3E8EF"         # 描边
SURFACE = "#FFFFFF"      # 卡片底
SURFACE_ALT = "#F4F6F9"  # 浅灰底
OK_BG, OK_FG = "#E8F1EA", "#25603A"
WARN_BG, WARN_FG = "#FDF3E2", "#8A5A12"
STOP_BG, STOP_FG = "#FBEBEB", "#9B2C2C"
INFO_BG, INFO_FG = "#EAF0F8", "#1B3A6B"

_STYLES = f"""
<style>
  /* --- 页头 --- */
  .zg-hero {{
    border-left: 4px solid {NAVY};
    padding: 4px 0 4px 16px;
    margin: 4px 0 22px 0;
  }}
  .zg-hero h1 {{
    font-size: 26px; font-weight: 700; color: {NAVY};
    margin: 0 0 6px 0; letter-spacing: 0.2px;
  }}
  .zg-hero p {{
    color: {INK_SOFT}; font-size: 14px; margin: 0; line-height: 1.7;
  }}

  /* --- 区块标题 --- */
  .zg-section {{
    font-size: 17px; font-weight: 600; color: {NAVY};
    margin: 26px 0 12px 0; padding-bottom: 7px;
    border-bottom: 1px solid {LINE};
  }}
  .zg-caption {{ color: {INK_SOFT}; font-size: 13px; line-height: 1.7; }}

  /* --- 卡片 --- */
  .zg-card {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 10px;
    padding: 18px 20px; margin-bottom: 14px;
  }}
  .zg-card.is-top {{ border-left: 4px solid {NAVY}; }}
  .zg-card-head {{
    display: flex; justify-content: space-between; align-items: flex-start;
    gap: 16px; margin-bottom: 12px;
  }}
  .zg-card-title {{
    font-size: 17px; font-weight: 650; color: {INK}; margin: 0 0 3px 0;
  }}
  .zg-card-sub {{ color: {INK_SOFT}; font-size: 13px; }}
  .zg-price {{
    font-size: 21px; font-weight: 700; color: {NAVY};
    white-space: nowrap; line-height: 1.2;
  }}
  .zg-price small {{ font-size: 12px; font-weight: 400; color: {INK_SOFT}; }}

  /* --- 徽章 --- */
  .zg-badge {{
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: 12px; font-weight: 500; margin-right: 6px; white-space: nowrap;
  }}
  .zg-badge-ok      {{ background: {OK_BG};   color: {OK_FG}; }}
  .zg-badge-warn    {{ background: {WARN_BG}; color: {WARN_FG}; }}
  .zg-badge-stop    {{ background: {STOP_BG}; color: {STOP_FG}; }}
  .zg-badge-info    {{ background: {INFO_BG}; color: {INFO_FG}; }}
  .zg-badge-neutral {{ background: {SURFACE_ALT}; color: {INK_SOFT}; }}

  /* --- 评分条 --- */
  .zg-dim {{ margin: 7px 0; }}
  .zg-dim-head {{
    display: flex; justify-content: space-between;
    font-size: 13px; color: {INK}; margin-bottom: 4px;
  }}
  .zg-dim-head .zg-dim-name {{ color: {INK_SOFT}; }}
  .zg-dim-head .zg-dim-score {{ font-weight: 600; font-variant-numeric: tabular-nums; }}
  .zg-bar {{ height: 6px; background: #EDF0F4; border-radius: 3px; overflow: hidden; }}
  .zg-bar-fill {{ height: 6px; border-radius: 3px; background: {NAVY}; }}
  .zg-dim-reason {{ font-size: 12px; color: {INK_SOFT}; margin-top: 3px; line-height: 1.6; }}

  /* --- 提示条 --- */
  .zg-notice {{
    border-radius: 8px; padding: 11px 15px; margin-bottom: 10px;
    font-size: 13.5px; line-height: 1.75;
  }}
  .zg-notice-info {{ background: {INFO_BG}; border-left: 3px solid {NAVY}; color: {INFO_FG}; }}
  .zg-notice-warn {{ background: {WARN_BG}; border-left: 3px solid #B8791C; color: {WARN_FG}; }}
  .zg-notice-stop {{ background: {STOP_BG}; border-left: 3px solid #B33A3A; color: {STOP_FG}; }}
  .zg-notice-ok   {{ background: {OK_BG};   border-left: 3px solid #2F7A4A; color: {OK_FG}; }}

  /* --- 键值清单 --- */
  .zg-facts {{ margin: 2px 0 0 0; }}
  .zg-fact {{ display: flex; gap: 10px; font-size: 13.5px; padding: 3px 0; line-height: 1.7; }}
  .zg-fact-key {{ color: {INK_SOFT}; min-width: 76px; flex-shrink: 0; }}
  .zg-fact-val {{ color: {INK}; }}

  /* --- 列表 --- */
  .zg-list {{ margin: 4px 0 0 0; padding-left: 0; list-style: none; }}
  .zg-list li {{
    font-size: 13.5px; color: {INK}; line-height: 1.8;
    padding-left: 15px; position: relative;
  }}
  .zg-list li:before {{
    content: ""; position: absolute; left: 3px; top: 10px;
    width: 4px; height: 4px; border-radius: 50%; background: {NAVY_SOFT};
  }}
  .zg-list-con li:before {{ background: #B33A3A; }}

  /* --- 数据来源脚注 --- */
  .zg-source {{
    font-size: 12px; color: {INK_SOFT}; margin-top: 12px;
    padding-top: 10px; border-top: 1px dashed {LINE};
  }}

  /* --- 评分总览 --- */
  .zg-score-top {{ text-align: right; white-space: nowrap; }}
  .zg-score-num {{
    font-size: 24px; font-weight: 700; color: {NAVY};
    font-variant-numeric: tabular-nums;
  }}
  .zg-score-num small {{ font-size: 12px; font-weight: 400; color: {INK_SOFT}; }}
  .zg-score-level {{ font-size: 12px; color: {INK_SOFT}; margin-top: 2px; }}

  /* --- 空状态 --- */
  .zg-empty {{
    border: 1px dashed {LINE}; border-radius: 10px;
    padding: 34px 20px; text-align: center; color: {INK_SOFT};
    background: {SURFACE_ALT}; font-size: 14px; line-height: 1.8;
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


def badge(text: str, tone: str = "neutral") -> str:
    """返回一个徽章的 HTML 片段。tone 取 ok / warn / stop / info / neutral。"""
    return f'<span class="zg-badge zg-badge-{tone}">{esc(text)}</span>'


def notice(text: str, tone: str = "info") -> str:
    """返回一个提示条的 HTML 片段。tone 取 info / warn / stop / ok。"""
    return f'<div class="zg-notice zg-notice-{tone}">{esc(text)}</div>'


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
    """把字符串列表渲染成项目符号清单。tone='con' 时圆点变红。"""
    if not items:
        return '<div class="zg-caption">（无）</div>'
    rows = "".join(f"<li>{esc(item)}</li>" for item in items)
    css = "zg-list zg-list-con" if tone == "con" else "zg-list"
    return f'<ul class="{css}">{rows}</ul>'

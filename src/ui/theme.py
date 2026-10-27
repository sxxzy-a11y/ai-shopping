"""配色令牌与全局样式。

样式策略
--------
分三层，按「稳定性」排序使用：

1. `.streamlit/config.toml` 的官方 `[theme]` —— 最稳，跨版本可用。
2. 标准 HTML 标签与稳定类名（`label`、`button[kind]`、`.stButton`）上的自定义
   样式 —— 这些不是 Streamlit 生成的哈希类名，改版不会失效。
3. 少量 `[data-testid="..."]` 选择器 —— 深色侧栏、折叠面板、表单、带边框容器、
   数据表格等 Streamlit 没有官方 API 的部件。**侧栏底色仍然是其中最要紧的一处**。

关于第 3 层的说明
-----------------
Streamlit 没有官方 API 能改侧栏底色，只能用 `[data-testid="stSidebar"]`。
这确实是在依赖非公开结构。缓解措施有三条：

- 需求里已经把这个风险写明了，这里不装作没有
- `requirements.txt` 锁定 Streamlit 版本到实测通过的那一版
- `tests/test_app.py` 里有一条断言检查侧栏确实是深色 —— 将来升级把它改坏了，
  测试会失败，而不是悄悄退化成浅色

控件样式尽量走 `data-baseweb`、`button[kind]` 和标准标签；只有确实没有官方
入口时才加一条 `data-testid`。绝不使用 `st-emotion-cache-*` 这类哈希类名：
那是每次发版都会变的东西。

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

# 深色侧栏：从品牌深蓝换成登录页同源的暖黑
NAVY_900 = "#171714"
NAVY_800 = "#201F1B"
SIDEBAR_TEXT = "#F4F0E6"
ON_NAVY = "#D8D2C4"        # 深色侧栏上的次级文字
SIDEBAR_MUTED = "#9A9385"  # 深色侧栏上的弱化文字

# 主操作色：深琥珀用于文字/图标，亮琥珀用于按钮与选中态
BRAND = "#A86412"
BRAND_SOLID = "#D3923C"
BRAND_DARK = "#C07F2A"
BRAND_50 = "#F6EBD9"
BRAND_100 = "#EAD8BC"
ON_BRAND = "#1D1407"

# 页面与卡片：参考站浅色模式的暖纸色
BG = "#F5F3EE"
SURFACE = "#FFFEFA"
SURFACE_ALT = "#FBF8F1"
LINE = "#E1DACD"
LINE_SOFT = "#EFEAE0"

# 文字
INK = "#1F1D18"
INK_SOFT = "#6F6A5E"
INK_FAINT = "#7C766A"

# 语义色（统一暖化，避免蓝绿和暖琥珀打架）
OK = "#2F7D5B"
OK_BG = "#EAF3ED"
WARN = "#B26A00"
WARN_BG = "#FBF1E2"
DANGER = "#B23A2E"
DANGER_BG = "#F8E9E6"
INFO = "#5D5A52"
INFO_BG = "#F0EDE6"
STAR = "#B8791F"

# 字体：标题宋体，正文苹方/雅黑
SERIF = "'Songti SC', 'Noto Serif SC', 'Source Han Serif SC', 'STSong', 'SimSun', '宋体', serif"
SANS = "'PingFang SC', 'Microsoft YaHei', 'Segoe UI', sans-serif"
MONO = "'Cascadia Mono', 'SF Mono', 'Consolas', 'Liberation Mono', monospace"

#: 卡片阴影。克制的一层，不用大扩散。
SHADOW = "0 1px 2px rgba(31,29,24,.035), 0 2px 10px rgba(31,29,24,.035)"

_STYLES = f"""
<style>
  /* ===================================================================
     全局底子：登录页 / 工作台两种底色，共用同一套暖色与字体
     ===================================================================
     没有侧栏 = 登录页还没渲染完或未登录：保持暖黑，避免先闪一块浅色。
     有侧栏 = 已进入工作台：换成暖纸色。 */
  [data-testid="stAppViewContainer"] {{
    font-family: {SANS};
    background: #161511;
  }}
  [data-testid="stAppViewContainer"]:has([data-testid="stSidebar"]) {{
    background:
      radial-gradient(1200px 520px at 88% -8%, rgba(211, 146, 60, .065), transparent 62%),
      radial-gradient(900px 500px at -6% 105%, rgba(120, 100, 70, .045), transparent 60%),
      {BG};
  }}
  [data-testid="stAppViewContainer"] a {{ color: {BRAND}; }}

  /* Streamlit 会往每个标题后面挂一个 16px 的锚点图标。这里的标题是大字号自定义
     排版，图标会贴着标题右下角悬空，看起来像凭空多出一个错位的小方块——隐藏。 */
  [data-testid="stMarkdownContainer"] a[href^="#"] {{ display: none; }}

  /* 分隔线：默认的 #EFEAE0 放在暖纸底上几乎看不见，页面上只剩一大段空白。
     给它一点对比度，并把 32px 的上下留白收到 18px。 */
  [data-testid="stMain"] hr {{
    border: 0; border-top: 1px solid {LINE}; margin: 18px 0;
  }}

  /* Streamlit 会在输入框右下角渲染「Press Enter to apply / submit form」。
     密码框那里它正好压在显示密码的眼睛图标上，两行字叠在一起。 */
  [data-testid="InputInstructions"] {{ display: none; }}

  /* ===================================================================
     侧栏（唯一使用 data-testid 的地方，见模块 docstring）
     =================================================================== */
  [data-testid="stSidebar"] {{
    background: {NAVY_900};
    border-right: 1px solid rgba(242, 238, 228, .10);
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
    padding: 9px 11px;
    border-radius: 4px;
    min-height: 38px;
    transition: background .16s ease, color .16s ease;
  }}
  [data-testid="stSidebar"] .stButton > button p {{
    color: inherit;
    font-size: 13.5px;
    letter-spacing: .01em;
  }}
  [data-testid="stSidebar"] .stButton > button:hover {{
    background: rgba(242, 238, 228, .07);
    color: {SIDEBAR_TEXT};
  }}
  /* 当前页：亮琥珀底 + 深色字，和登录页主按钮同源 */
  [data-testid="stSidebar"] .stButton > button[kind="primary"] {{
    background: {BRAND_SOLID};
    color: {ON_BRAND};
  }}
  [data-testid="stSidebar"] .stButton > button[kind="primary"] p,
  [data-testid="stSidebar"] .stButton > button[kind="primary"] span {{
    color: {ON_BRAND};
  }}
  [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {{
    background: {BRAND_DARK};
    color: {ON_BRAND};
  }}
  /* 侧栏内按钮之间收紧间距 */
  [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: .25rem; }}

  /* ===================================================================
     页头
     =================================================================== */
  .zg-hero {{ margin: 0 0 22px 0; }}
  .zg-hero h1 {{
    position: relative; padding-top: 15px;
    font-family: {SERIF};
    font-size: 32px; font-weight: 600; color: {INK};
    margin: 0 0 8px 0; letter-spacing: -.4px; line-height: 1.28;
  }}
  .zg-hero h1::before {{
    content: ""; position: absolute; left: 1px; top: 0;
    width: 26px; height: 1px; background: {BRAND_SOLID};
  }}
  .zg-hero p {{
    color: {INK_SOFT}; font-size: 14px; margin: 0; line-height: 1.75;
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
    display: flex; align-items: center; gap: 10px;
    font-family: {SERIF};
    font-size: 19px; font-weight: 600; color: {INK};
    margin: 28px 0 13px 0; letter-spacing: .01em;
  }}
  .zg-section::before {{
    content: ""; width: 12px; height: 1px; background: {BRAND_SOLID};
    flex-shrink: 0;
  }}
  .zg-section .zg-count {{
    font-family: {MONO};
    font-size: 11px; font-weight: 500; color: {INK_SOFT};
    background: {LINE_SOFT}; padding: 1px 8px; border-radius: 3px;
  }}
  .zg-caption {{ color: {INK_SOFT}; font-size: 13px; line-height: 1.75; }}
  .zg-muted {{ color: {INK_FAINT}; font-size: 12px; }}

  /* ===================================================================
     决策台：masthead / 编号脚注 / verdict
     =================================================================== */
  .zg-kicker {{
    font-family: {MONO}; font-size: 10px; letter-spacing: .18em;
    text-transform: uppercase; color: {BRAND};
  }}
  .zg-hero-kicker {{
    display: flex; justify-content: space-between; align-items: center; gap: 16px;
    font-family: {MONO}; font-size: 10px; letter-spacing: .16em;
    text-transform: uppercase; color: {BRAND};
    padding-bottom: 9px; margin-bottom: 12px; border-bottom: 1px solid {LINE};
  }}
  .zg-hero-kicker .zg-hero-status {{
    color: {INK_FAINT}; letter-spacing: .08em;
  }}

  .zg-home-masthead {{
    position: relative; overflow: hidden;
    margin: 0 0 26px 0; padding: 26px 30px 24px;
    border-radius: 4px; color: {SIDEBAR_TEXT};
    background:
      radial-gradient(70% 130% at 86% 0%, rgba(211, 146, 60, .18), transparent 60%),
      #171714;
    border: 1px solid rgba(242, 238, 228, .08);
  }}
  .zg-masthead-top {{
    display: flex; justify-content: space-between; align-items: center; gap: 20px;
    font-family: {MONO}; font-size: 10px; letter-spacing: .18em;
    color: #9A9385; padding-bottom: 12px;
    border-bottom: 1px solid rgba(242, 238, 228, .14);
  }}
  .zg-masthead-top b {{ color: #D3923C; font-weight: 500; }}
  .zg-masthead-top .zg-chip {{
    background: rgba(242, 238, 228, .06) !important;
    color: #D8D2C4 !important;
    border: 1px solid rgba(242, 238, 228, .14);
  }}
  .zg-masthead-title {{
    margin: 26px 0 12px 0;
    font-family: {SERIF}; font-size: 54px; font-weight: 600;
    line-height: 1.02; letter-spacing: -1.2px; color: #F4F0E6;
  }}
  .zg-masthead-sub {{
    margin: 0; max-width: 760px;
    color: #B5B0A5; font-size: 14px; line-height: 1.85;
  }}
  .zg-masthead-steps {{
    display: flex; flex-wrap: wrap; gap: 10px 30px;
    margin-top: 24px; padding-top: 14px;
    border-top: 1px solid rgba(242, 238, 228, .14);
    font-family: {MONO}; font-size: 10.5px; letter-spacing: .08em; color: #9A9385;
  }}
  .zg-masthead-steps b {{
    color: #D3923C; font-weight: 500; margin-right: 7px;
  }}

  .zg-rail-note {{
    display: grid; grid-template-columns: 30px minmax(0, 1fr); gap: 12px;
    padding: 13px 0; border-top: 1px solid {LINE};
  }}
  .zg-rail-note:last-child {{ border-bottom: 1px solid {LINE}; }}
  .zg-rail-index {{
    font-family: {MONO}; font-size: 10.5px; color: {BRAND}; padding-top: 3px;
  }}
  .zg-rail-note b {{
    display: block; font-family: {SERIF};
    font-size: 15.5px; font-weight: 600; color: {INK};
  }}
  .zg-rail-note p {{
    margin: 4px 0 0; font-size: 12.5px; line-height: 1.7; color: {INK_SOFT};
  }}

  .zg-brief-label {{
    display: flex; align-items: center; gap: 10px;
    margin: 0 0 8px 0;
    font-family: {MONO}; font-size: 10px; letter-spacing: .16em;
    text-transform: uppercase; color: {BRAND};
  }}
  .zg-brief-label::after {{
    content: ""; flex: 1; height: 1px; background: {LINE};
  }}
  [data-testid="stVerticalBlockBorderWrapper"]:has(.zg-brief-label) {{
    border-left: 2px solid {BRAND_SOLID} !important;
  }}

  .zg-card.zg-dossier {{ border-left: 2px solid {BRAND_SOLID}; }}
  .zg-card.zg-dossier .zg-fact-key {{
    font-family: {MONO}; font-size: 10px; letter-spacing: .08em; text-transform: uppercase;
  }}

  .zg-verdict {{
    position: relative; overflow: hidden;
    margin: 4px 0 20px 0; padding: 20px 22px 18px;
    border-radius: 4px; color: #F4F0E6;
    background:
      radial-gradient(80% 140% at 85% 0%, rgba(211, 146, 60, .16), transparent 60%),
      #171714;
    border-top: 1px solid rgba(211, 146, 60, .75);
  }}
  .zg-verdict-kicker {{
    font-family: {MONO}; font-size: 9.5px; letter-spacing: .2em;
    text-transform: uppercase; color: #D3923C;
  }}
  .zg-verdict-main {{
    display: flex; justify-content: space-between; align-items: flex-end;
    gap: 20px; margin-top: 10px;
  }}
  .zg-verdict-name {{
    font-family: {SERIF}; font-size: 23px; font-weight: 600;
    line-height: 1.3; letter-spacing: .01em;
  }}
  .zg-verdict-score {{
    font-family: {MONO}; font-size: 36px; line-height: 1;
    color: #D3923C; white-space: nowrap;
  }}
  .zg-verdict-score small {{ font-size: 10px; color: #9A9385; margin-left: 3px; }}
  .zg-verdict-meta {{
    margin-top: 9px; font-family: {MONO}; font-size: 10px;
    letter-spacing: .06em; color: #B5B0A5;
  }}
  .zg-verdict-dims {{ display: flex; flex-wrap: wrap; gap: 7px; margin-top: 13px; }}
  .zg-verdict-dims span {{
    padding: 3px 8px; border: 1px solid rgba(242, 238, 228, .16);
    border-radius: 2px; font-family: {MONO}; font-size: 10px; color: #D8D2C4;
  }}
  .zg-verdict-dims b {{ color: #F0B35E; font-weight: 500; }}

  @keyframes zgBriefIn {{
    from {{ opacity: 0; transform: translateY(12px); }}
    to   {{ opacity: 1; transform: none; }}
  }}
  @keyframes zgRailIn {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to   {{ opacity: 1; transform: none; }}
  }}
  .zg-enter .zg-masthead-title,
  .zg-enter.zg-hero h1 {{
    animation: zgBriefIn .7s cubic-bezier(.16, 1, .3, 1) both;
  }}
  .zg-enter .zg-masthead-sub,
  .zg-enter .zg-masthead-steps,
  .zg-enter.zg-hero p {{
    animation: zgBriefIn .6s .08s cubic-bezier(.16, 1, .3, 1) both;
  }}
  .zg-enter .zg-rail-note {{
    animation: zgRailIn .55s cubic-bezier(.16, 1, .3, 1) both;
  }}
  .zg-enter .zg-rail-note:nth-child(2) {{ animation-delay: .05s; }}
  .zg-enter .zg-rail-note:nth-child(3) {{ animation-delay: .1s; }}
  .zg-enter .zg-rail-note:nth-child(4) {{ animation-delay: .15s; }}
  .zg-enter .zg-verdict {{
    animation: zgBriefIn .55s cubic-bezier(.16, 1, .3, 1) both;
  }}

  /* ===================================================================
     卡片
     =================================================================== */
  .zg-card {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 4px;
    padding: 18px 20px; margin-bottom: 12px;
    box-shadow: {SHADOW};
  }}
  .zg-card.is-flat {{ box-shadow: none; }}
  .zg-card.is-accent {{ border-left: 2px solid {BRAND_SOLID}; }}
  .zg-card.is-warn {{ border-left: 2px solid {WARN}; }}
  .zg-card-head {{
    display: flex; justify-content: space-between; align-items: flex-start;
    gap: 16px; margin-bottom: 12px;
  }}
  .zg-card-title {{
    font-size: 15px; font-weight: 600; color: {INK}; margin: 0 0 3px 0;
  }}
  .zg-card-sub {{ color: {INK_SOFT}; font-size: 13px; }}

  /* ===================================================================
     商品行的图标块（类别占位图）
     =================================================================== */
  .zg-thumb {{
    width: 52px; height: 52px; border-radius: 3px; flex-shrink: 0;
    background: {BRAND_50}; border: 1px solid {BRAND_100};
    display: flex; align-items: center; justify-content: center;
    color: {BRAND};
    /* 图片叠在类别图标之上；图片加载失败时把它藏掉，
       下面垫着的图标就露出来了——不需要 JS 回调整理状态。 */
    position: relative; overflow: hidden;
  }}
  .zg-thumb.is-lg {{ width: 62px; height: 62px; border-radius: 4px; }}
  .zg-thumb img {{
    position: absolute; inset: 0;
    width: 100%; height: 100%; object-fit: cover;
    background: {SURFACE};
  }}

  /* ===================================================================
     商品行
     =================================================================== */
  .zg-row {{ display: flex; gap: 14px; align-items: flex-start; }}
  .zg-row-main {{ flex: 1; min-width: 0; }}
  .zg-row-name {{
    font-family: {SERIF};
    font-size: 16.5px; font-weight: 600; color: {INK};
    margin: 0 0 4px 0; line-height: 1.4;
  }}
  .zg-row-spec {{
    color: {INK_SOFT}; font-size: 13px; line-height: 1.6;
    margin-bottom: 8px;
  }}
  .zg-price {{
    font-family: {MONO};
    font-size: 15px; font-weight: 500; color: {INK};
    font-variant-numeric: tabular-nums; white-space: nowrap;
  }}
  .zg-price small {{ font-size: 12px; font-weight: 400; color: {INK_SOFT}; }}
  .zg-row-score {{ text-align: right; flex-shrink: 0; min-width: 92px; }}
  .zg-score-num {{
    font-family: {MONO};
    font-size: 23px; font-weight: 500; color: {INK};
    font-variant-numeric: tabular-nums; line-height: 1.1;
  }}
  .zg-score-num small {{ font-size: 12px; font-weight: 400; color: {INK_FAINT}; }}
  .zg-score-name {{ font-size: 11.5px; color: {INK_SOFT}; margin-top: 3px; }}

  /* 排名角标 */
  .zg-rank {{
    width: 22px; height: 22px; border-radius: 2px; flex-shrink: 0;
    background: {BRAND_SOLID}; color: {ON_BRAND};
    font-family: {MONO}; font-size: 11.5px; font-weight: 500;
    display: flex; align-items: center; justify-content: center;
    margin-top: 15px;
  }}
  .zg-rank.is-muted {{ background: {LINE}; color: {INK_SOFT}; }}

  /* ===================================================================
     标签
     =================================================================== */
  .zg-chip {{
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 8px; border-radius: 3px;
    font-size: 12px; font-weight: 500; white-space: nowrap;
  }}
  .zg-chip-ok      {{ background: {OK_BG};     color: {OK}; }}
  .zg-chip-warn    {{ background: {WARN_BG};   color: #B54708; }}
  .zg-chip-stop    {{ background: {DANGER_BG}; color: #B42318; }}
  .zg-chip-info    {{ background: {INFO_BG};   color: {INFO}; }}
  .zg-chip-brand   {{ background: {BRAND_50};  color: {BRAND}; }}
  .zg-chip-neutral {{ background: {LINE_SOFT}; color: {INK_SOFT}; }}

  /* 可选中的品牌标签（设置页） */
  .zg-chip-lg {{ padding: 6px 12px; border-radius: 3px; font-size: 13px; }}

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
    font-family: {MONO}; font-weight: 500; color: {INK};
    font-variant-numeric: tabular-nums;
  }}
  .zg-bar {{
    height: 6px; background: {LINE_SOFT}; border-radius: 2px; overflow: hidden;
  }}
  .zg-bar-fill {{ height: 6px; border-radius: 2px; background: {BRAND_SOLID}; }}
  .zg-dim-reason {{
    font-size: 12.5px; color: {INK_SOFT}; margin-top: 4px; line-height: 1.65;
  }}

  /* ===================================================================
     星级（只是系统匹配评分的可视化，不是用户评价）
     =================================================================== */
  .zg-stars {{ display: inline-flex; gap: 1.5px; vertical-align: middle; }}
  .zg-star-on  {{ color: {STAR}; }}
  .zg-star-off {{ color: #D8D0C0; }}

  /* ===================================================================
     状态提示条
     =================================================================== */
  .zg-notice {{
    display: flex; gap: 10px; align-items: flex-start;
    border-radius: 3px; padding: 12px 15px; margin-bottom: 10px;
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
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 4px;
    box-shadow: {SHADOW}; overflow: hidden;
  }}
  .zg-stat {{
    display: flex; align-items: center; gap: 13px;
    padding: 18px 20px;
    border-right: 1px solid {LINE_SOFT};
  }}
  .zg-stat:last-child {{ border-right: none; }}
  .zg-stat-icon {{
    width: 38px; height: 38px; border-radius: 3px; flex-shrink: 0;
    background: {BRAND_50}; color: {BRAND};
    display: flex; align-items: center; justify-content: center;
  }}
  .zg-stat-value {{
    font-family: {MONO};
    font-size: 24px; font-weight: 500; color: {INK};
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
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 4px;
    padding: 18px; box-shadow: {SHADOW}; height: 100%;
  }}
  .zg-feature-icon {{
    width: 40px; height: 40px; border-radius: 3px; background: {BRAND_50};
    color: {BRAND}; display: flex; align-items: center; justify-content: center;
    margin-bottom: 12px;
  }}
  .zg-feature-title {{
    font-family: {SERIF};
    font-size: 16px; font-weight: 600; color: {INK}; margin-bottom: 5px;
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
    font-family: {MONO};
    font-size: 20px; font-weight: 500; color: {INK}; line-height: 1;
    font-variant-numeric: tabular-nums;
  }}
  .zg-ring-unit {{ font-size: 10.5px; color: {INK_FAINT}; margin-top: 1px; }}
  .zg-ring-text {{ min-width: 0; }}
  .zg-ring-title {{ font-size: 14px; font-weight: 600; color: {INK}; margin-bottom: 3px; }}
  .zg-ring-desc {{ font-size: 12.5px; color: {INK_SOFT}; line-height: 1.65; }}

  /* ===================================================================
     比较页：商品概览行
     ===================================================================
     商品**固定横向单行**：grid-auto-flow: column 让所有概览格排成
     一行，空间充足时等分加宽（minmax 的 1fr），不足时不折行、
     整行横向滚动——保证「参与比较的商品横向显示」永远成立。
     不用 st.columns：N=5 时每列只剩 ~180px，减去图标块后文字区
     不足 110px，中文会被一个字一行地竖排下来。 */
  .zg-compare-grid {{
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: minmax(158px, 1fr);
    gap: 10px;
    margin-bottom: 4px;
    overflow-x: auto;
    padding-bottom: 6px;
  }}
  .zg-compare-cell {{
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 4px;
    padding: 16px 14px; box-shadow: {SHADOW};
    display: flex; flex-direction: column; align-items: center;
    text-align: center; gap: 0;
  }}
  .zg-compare-name {{
    font-family: {SERIF};
    font-size: 15px; font-weight: 600; color: {INK};
    line-height: 1.45; margin: 11px 0 3px 0;
    word-break: break-word;
  }}
  .zg-compare-brand {{ font-size: 12px; color: {INK_SOFT}; line-height: 1.5; }}
  .zg-compare-price {{
    font-family: {MONO};
    font-size: 16px; font-weight: 500; color: {INK};
    margin: 9px 0 7px 0; font-variant-numeric: tabular-nums;
  }}
  .zg-compare-score {{
    font-family: {MONO};
    font-size: 19px; font-weight: 500; color: {INK};
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
    background: {SURFACE}; border: 1px solid {LINE}; border-radius: 4px;
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
    font-family: {MONO};
    font-size: 10.5px; letter-spacing: .01em;
    color: {INK_FAINT}; margin-top: 13px;
    padding-top: 11px; border-top: 1px dashed {LINE};
    line-height: 1.65;
  }}

  /* ===================================================================
     空状态
     =================================================================== */
  .zg-empty {{
    border: 1px dashed {LINE}; border-radius: 4px;
    padding: 40px 22px; text-align: center; color: {INK_SOFT};
    background: {SURFACE}; font-size: 14px; line-height: 1.85;
  }}
  .zg-empty-icon {{ color: {INK_FAINT}; margin-bottom: 10px; }}

  /* 悬停：卡片只抬起 1px，边框变琥珀；不做夸张位移 */
  .zg-card, .zg-feature, .zg-compare-cell, .zg-proscons-card {{
    transition: border-color .16s ease, box-shadow .16s ease, transform .16s ease;
  }}
  .zg-card:hover, .zg-feature:hover,
  .zg-compare-cell:hover, .zg-proscons-card:hover {{
    border-color: rgba(211, 146, 60, .48);
    box-shadow: 0 8px 22px rgba(31, 29, 24, .06);
    transform: translateY(-1px);
  }}

  @media (prefers-reduced-motion: reduce) {{
    .zg-enter .zg-masthead-title,
    .zg-enter .zg-masthead-sub,
    .zg-enter .zg-masthead-steps,
    .zg-enter .zg-rail-note,
    .zg-enter .zg-verdict,
    .zg-enter.zg-hero h1,
    .zg-enter.zg-hero p {{
      animation: none !important;
    }}
    .zg-card, .zg-feature, .zg-compare-cell, .zg-proscons-card {{
      transition: none !important;
    }}
  }}

  /* ===================================================================
     主区微调
     =================================================================== */
  .block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; }}
  [data-testid="stMainBlockContainer"] {{ max-width: 1280px; }}

  /* ===================================================================
     主区控件：按钮、输入、折叠面板、Tab、表单、表格
     ===================================================================
     只作用于主区（stMain），侧栏在上一节有自己的深色样式。 */
  [data-testid="stMain"] .stButton > button,
  [data-testid="stMain"] [data-testid="stBaseButton-secondaryFormSubmit"] {{
    border-radius: 2px !important;
    border: 1px solid {LINE} !important;
    background: {SURFACE} !important;
    color: {INK} !important;
    font-weight: 500;
    letter-spacing: .02em;
    transition: border-color .16s ease, color .16s ease, background .16s ease;
  }}
  [data-testid="stMain"] .stButton > button:hover,
  [data-testid="stMain"] [data-testid="stBaseButton-secondaryFormSubmit"]:hover {{
    border-color: {BRAND_SOLID} !important;
    color: {BRAND} !important;
    background: {SURFACE_ALT} !important;
  }}
  [data-testid="stMain"] .stButton > button[kind="primary"],
  [data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"] {{
    background: {BRAND_SOLID} !important;
    border: 1px solid {BRAND_SOLID} !important;
    color: {ON_BRAND} !important;
    border-radius: 2px !important;
    font-weight: 600;
  }}
  [data-testid="stMain"] .stButton > button[kind="primary"]:hover,
  [data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
    background: {BRAND_DARK} !important;
    border-color: {BRAND_DARK} !important;
    color: {ON_BRAND} !important;
  }}

  /* 输入框：暖白底 + 发丝边，聚焦时琥珀描边 */
  [data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {{
    border-radius: 3px !important;
    background: {SURFACE} !important;
    border: 1px solid {LINE} !important;
  }}
  [data-baseweb="input"]:focus-within,
  [data-baseweb="select"] > div:focus-within,
  [data-baseweb="textarea"]:focus-within {{
    border-color: {BRAND_SOLID} !important;
    box-shadow: 0 0 0 1px rgba(211, 146, 60, .25) !important;
  }}

  /* 折叠面板：与卡片同一套发丝边 */
  [data-testid="stExpander"] {{
    border: 1px solid {LINE} !important;
    border-radius: 4px !important;
    background: {SURFACE};
    overflow: hidden;
  }}
  [data-testid="stExpander"] summary {{
    color: {INK} !important;
    font-size: 13.5px;
  }}
  [data-testid="stExpander"] summary:hover {{ color: {BRAND} !important; }}

  /* Tab：去掉默认蓝条，换成琥珀短发丝 */
  [data-baseweb="tab-list"] {{
    gap: 4px;
    border-bottom: 1px solid {LINE};
  }}
  [data-baseweb="tab"] {{
    font-size: 13.5px; color: {INK_SOFT};
  }}
  [data-baseweb="tab"][aria-selected="true"] {{ color: {INK}; }}
  [data-baseweb="tab-highlight"] {{
    background: {BRAND_SOLID} !important;
    height: 2px !important;
  }}

  /* 表单与带边框容器 */
  [data-testid="stForm"] {{
    border: 1px solid {LINE};
    border-radius: 4px;
    background: {SURFACE};
    padding: 18px 18px 8px 18px;
  }}
  [data-testid="stVerticalBlockBorderWrapper"] {{
    border-color: {LINE} !important;
    border-radius: 4px !important;
    background: {SURFACE};
  }}

  /* 表格容器 */
  [data-testid="stDataFrame"] {{
    border: 1px solid {LINE};
    border-radius: 4px;
    overflow: hidden;
  }}
  [data-testid="stAlert"] {{ border-radius: 3px; }}
  [data-testid="stMain"] hr {{ border-color: {LINE_SOFT}; }}
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


def chip(
    text: str, tone: str = "neutral", *, large: bool = False, title: str = ""
) -> str:
    """小标签（徽章）。tone 取 ok / warn / stop / info / brand / neutral。

    `title` 可选，渲染成悬停提示。用于「资料存疑」这类需要能看到原因、
    但不该让原因占满版面的标记。
    """
    suffix = tone if tone in _TONES else "neutral"
    size = " zg-chip-lg" if large else ""
    tip = f' title="{esc(title)}"' if title else ""
    return f'<span class="zg-chip zg-chip-{suffix}{size}"{tip}>{esc(text)}</span>'


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

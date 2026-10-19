"""后台专属视觉层：暖金玻璃工作台。

这里的所有选择器都挂在登录后才存在的结构上（侧栏 / stMain / 后台自定义类），
并且只在用户通过鉴权后注入。登录页走不到这里，也不会被这些样式污染。
"""

from __future__ import annotations

import streamlit as st

# 品牌色：只用于后台，不写进全局 config.toml
BROWN = "#211D18"
BROWN_SOFT = "#4A3B2C"
MUTED = "#78644B"
MUTED_LIGHT = "#9A8A73"
GOLD = "#C99A4A"
GOLD_DEEP = "#A9772E"
GOLD_LIGHT = "#E7C98F"
IVORY = "#FFF9EE"
PAPER = "#F5F0E7"
LINE = "rgba(120, 100, 75, .18)"
SANS = "'PingFang SC', 'Microsoft YaHei', 'Segoe UI', sans-serif"
MONO = "'Cascadia Mono', 'SF Mono', 'Consolas', 'Liberation Mono', monospace"

_SCOPE = '[data-testid="stAppViewContainer"]:has([data-testid="stSidebar"])'
_SIDEBAR = '[data-testid="stSidebar"]'

_STYLES = f"""
<style>
  /* ===================================================================
     后台底色：暖象牙 + 金色光晕；登录页没有侧栏，匹配不到这里
     =================================================================== */
  {_SCOPE} {{
    font-family: {SANS};
    color: {BROWN_SOFT};
    background:
      radial-gradient(1100px 720px at -4% 0%, rgba(201, 154, 74, .42), transparent 62%),
      radial-gradient(950px 700px at 104% 0%, rgba(231, 201, 143, .58), transparent 64%),
      radial-gradient(900px 650px at 62% 16%, rgba(231, 201, 143, .32), transparent 68%),
      radial-gradient(850px 620px at 48% 10%, rgba(231, 201, 143, .30), transparent 68%),
      radial-gradient(600px 500px at 58% 52%, rgba(201, 154, 74, .14), transparent 70%),
      radial-gradient(520px 700px at 2% 45%, rgba(201, 154, 74, .34), transparent 70%),
      radial-gradient(820px 620px at 78% 86%, rgba(201, 154, 74, .26), transparent 70%),
      radial-gradient(700px 560px at 20% 102%, rgba(231, 201, 143, .30), transparent 70%),
      {PAPER} !important;
  }}
  {_SCOPE} a {{ color: {GOLD_DEEP}; }}

  /* ===================================================================
     左侧导航：半透明暖象牙玻璃
     =================================================================== */
  {_SIDEBAR} {{
    background: linear-gradient(180deg, rgba(255, 250, 242, .50), rgba(245, 237, 224, .30)) !important;
    backdrop-filter: blur(28px) saturate(130%);
    -webkit-backdrop-filter: blur(28px) saturate(130%);
    border-right: 1px solid rgba(201, 154, 74, .22);
    box-shadow: 8px 0 32px rgba(120, 100, 75, .07);
  }}
  {_SIDEBAR} > div:first-child {{ background: transparent; }}
  {_SIDEBAR} [data-testid="stSidebarUserContent"] {{ padding-top: 8px; padding-bottom: 22px; }}
  {_SIDEBAR} hr {{
    border-color: rgba(120, 100, 75, .14);
    margin: 13px 0;
  }}
  {_SIDEBAR} p,
  {_SIDEBAR} span,
  {_SIDEBAR} li {{ color: {BROWN_SOFT} !important; }}
  {_SIDEBAR} .stButton > button {{
    width: 100%;
    justify-content: flex-start;
    text-align: left;
    min-height: 40px;
    padding: 9px 12px;
    border: 1px solid transparent !important;
    border-radius: 12px;
    background: transparent !important;
    box-shadow: none !important;
    color: {BROWN_SOFT} !important;
    font-weight: 500;
    transition: background .22s ease, border-color .22s ease, color .22s ease, transform .22s ease;
  }}
  {_SIDEBAR} .stButton > button p {{
    color: inherit !important;
    font-size: 14px;
  }}
  {_SIDEBAR} .stButton > button:hover {{
    background: rgba(255, 250, 242, .62);
    border-color: rgba(201, 154, 74, .28);
    color: {BROWN} !important;
    transform: translateX(2px);
  }}
  {_SIDEBAR} .stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, #E7C27A, {GOLD}) !important;
    border-color: rgba(169, 119, 46, .34) !important;
    color: {BROWN} !important;
    box-shadow: 0 8px 20px rgba(169, 119, 46, .24), inset 0 1px 0 rgba(255,255,255,.45);
  }}
  {_SIDEBAR} .stButton > button[kind="primary"] p,
  {_SIDEBAR} .stButton > button[kind="primary"] span {{
    color: {BROWN} !important;
  }}
  {_SIDEBAR} .stButton > button[kind="primary"]:hover {{
    background: linear-gradient(135deg, #F0D094, #D6A957) !important;
    color: {BROWN} !important;
  }}
  {_SIDEBAR} [data-testid="stVerticalBlock"] {{ gap: .25rem; }}
  {_SIDEBAR} [data-testid="stSidebarCollapseButton"] button {{
    color: {MUTED} !important;
  }}

  /* ===================================================================
     顶部工作台条（真实页面名 + 当前模式，不做假搜索）
     =================================================================== */
  {_SCOPE} .zg-topbar {{
    display: flex; justify-content: space-between; align-items: center; gap: 18px;
    margin: 0 0 18px 0; padding: 10px 16px;
    border: 1px solid rgba(201, 154, 74, .24);
    border-radius: 16px;
    background: linear-gradient(120deg, rgba(255, 250, 242, .38), rgba(255, 250, 242, .20));
    backdrop-filter: blur(22px) saturate(128%);
    -webkit-backdrop-filter: blur(22px) saturate(128%);
    box-shadow: 0 12px 34px rgba(120, 100, 75, .10), inset 0 1px 0 rgba(255,255,255,.65);
  }}
  .zg-topbar-left, .zg-topbar-right {{
    display: flex; align-items: center; gap: 10px; min-width: 0;
  }}
  .zg-topbar-brand {{
    font-size: 14px; font-weight: 700; color: {BROWN};
    letter-spacing: .02em; white-space: nowrap;
  }}
  .zg-topbar-sep {{ color: rgba(120, 100, 75, .35); }}
  .zg-topbar-page {{ font-size: 12.5px; color: {MUTED}; white-space: nowrap; }}
  .zg-topbar .zg-chip {{
    border-radius: 999px !important;
    background: rgba(201, 154, 74, .10) !important;
    color: {GOLD_DEEP} !important;
    border: 1px solid rgba(201, 154, 74, .20);
  }}
  .zg-topbar-user {{
    font-family: {MONO}; font-size: 11px; color: {MUTED};
    padding-left: 10px; border-left: 1px solid rgba(120, 100, 75, .16);
  }}

  /* ===================================================================
     标题与文字层级
     =================================================================== */
  {_SCOPE} .zg-hero {{ margin: 0 0 22px 0; }}
  {_SCOPE} .zg-hero-kicker {{
    display: none !important;
    align-items: center; gap: 10px;
    font-family: {SANS}; font-size: 10.5px; letter-spacing: .14em;
    text-transform: none; color: {GOLD_DEEP};
    padding-bottom: 9px; margin-bottom: 12px;
    border-bottom: 1px solid rgba(201, 154, 74, .18);
  }}
  {_SCOPE} .zg-hero-kicker::before {{
    content: ""; width: 14px; height: 1px; background: {GOLD};
  }}
  {_SCOPE} .zg-hero h1 {{
    font-family: {SANS} !important;
    font-size: 32px; font-weight: 700; color: {BROWN};
    letter-spacing: -.5px; line-height: 1.3;
    margin: 0 0 7px 0; padding: 0;
  }}
  {_SCOPE} .zg-hero h1::before {{ display: none; }}
  {_SCOPE} .zg-hero p {{
    color: {MUTED}; font-size: 14px; line-height: 1.8;
    max-width: 880px;
  }}
  {_SCOPE} .zg-section {{
    font-family: {SANS} !important;
    font-size: 18px; font-weight: 700; color: {BROWN};
    letter-spacing: .01em; gap: 9px;
    margin: 26px 0 12px 0;
  }}
  {_SCOPE} .zg-section::before {{
    width: 14px; height: 2px; border-radius: 2px; background: {GOLD};
  }}
  {_SCOPE} .zg-section .zg-count {{
    font-family: {MONO}; font-size: 10.5px; color: {GOLD_DEEP};
    background: rgba(201, 154, 74, .10);
    border: 1px solid rgba(201, 154, 74, .16);
  }}
  {_SCOPE} .zg-caption {{ color: {MUTED}; font-size: 12.5px; line-height: 1.75; }}
  {_SCOPE} .zg-muted {{ color: {MUTED_LIGHT}; font-size: 11.5px; }}
  {_SCOPE} .zg-kicker,
  {_SCOPE} .zg-brief-label {{
    font-family: {SANS}; font-size: 10.5px; letter-spacing: .12em;
    text-transform: none; color: {GOLD_DEEP};
  }}
  {_SCOPE} .zg-brief-label::after {{ background: rgba(201, 154, 74, .18); }}

  /* ===================================================================
     玻璃表面：不同层级使用不同透明度和模糊强度
     =================================================================== */
  {_SCOPE} .zg-card,
  {_SCOPE} .zg-feature,
  {_SCOPE} .zg-statstrip,
  {_SCOPE} .zg-compare-cell,
  {_SCOPE} .zg-proscons-card {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .42), rgba(255, 250, 242, .20)) !important;
    border: 1px solid rgba(201, 154, 74, .22) !important;
    border-radius: 14px !important;
    backdrop-filter: blur(22px) saturate(130%);
    -webkit-backdrop-filter: blur(22px) saturate(130%);
    box-shadow:
      0 18px 42px rgba(120, 100, 75, .11),
      inset 0 1px 0 rgba(255, 255, 255, .62);
  }}
  {_SCOPE} .zg-card {{ padding: 18px 20px; }}
  {_SCOPE} .zg-card.is-flat {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .34), rgba(255, 250, 242, .18)) !important;
    box-shadow: 0 12px 30px rgba(120, 100, 75, .08), inset 0 1px 0 rgba(255,255,255,.55);
  }}
  {_SCOPE} .zg-card.is-accent,
  {_SCOPE} .zg-card.zg-dossier {{
    border-left: 2px solid {GOLD} !important;
  }}
  {_SCOPE} .zg-feature,
  {_SCOPE} .zg-statstrip,
  {_SCOPE} .zg-compare-cell,
  {_SCOPE} .zg-proscons-card {{
    border-radius: 16px !important;
  }}
  {_SCOPE} .zg-empty {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .40), rgba(255, 250, 242, .20)) !important;
    border: 1px dashed rgba(201, 154, 74, .32) !important;
    border-radius: 16px !important;
    color: {MUTED} !important;
    backdrop-filter: blur(14px);
  }}
  {_SCOPE} .zg-notice {{
    border-radius: 10px !important;
    border: 1px solid rgba(201, 154, 74, .18);
    backdrop-filter: blur(12px);
  }}
  {_SCOPE} .zg-notice-info,
  {_SCOPE} .zg-notice-ok,
  {_SCOPE} .zg-notice-warn,
  {_SCOPE} .zg-notice-stop {{
    background: rgba(255, 250, 242, .58) !important;
    color: {BROWN_SOFT} !important;
  }}
  {_SCOPE} .zg-notice-warn {{ border-color: rgba(178, 106, 0, .30); }}
  {_SCOPE} .zg-notice-stop {{ border-color: rgba(178, 58, 46, .28); }}
  {_SCOPE} .zg-notice-ok {{ border-color: rgba(47, 125, 91, .26); }}

  /* 商品卡：更高不透明度，价格与名称优先 */
  {_SCOPE} .zg-card {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .60), rgba(255, 250, 242, .34)) !important;
  }}
  {_SCOPE} .zg-thumb {{
    width: 68px; height: 68px; border-radius: 14px;
    background: rgba(255, 250, 242, .50);
    border: 1px solid rgba(201, 154, 74, .20);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.6);
  }}
  {_SCOPE} .zg-thumb.is-lg {{ width: 78px; height: 78px; border-radius: 16px; }}
  {_SCOPE} .zg-row-name {{
    font-family: {SANS} !important;
    font-size: 16px; font-weight: 650; color: {BROWN};
    letter-spacing: 0;
  }}
  {_SCOPE} .zg-row-spec {{ color: {MUTED}; font-size: 12.5px; }}
  {_SCOPE} .zg-row-reason {{
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
    margin: 7px 0 2px 0; font-size: 12px; line-height: 1.65; color: {BROWN_SOFT};
  }}
  {_SCOPE} .zg-price {{
    font-family: {MONO}; font-size: 16px; font-weight: 500; color: {GOLD_DEEP};
  }}
  {_SCOPE} .zg-price small {{ color: {MUTED_LIGHT}; }}
  {_SCOPE} .zg-score-num {{
    font-family: {MONO}; font-size: 22px; font-weight: 500; color: {BROWN};
  }}
  {_SCOPE} .zg-score-name {{ color: {MUTED_LIGHT}; font-size: 10.5px; }}
  {_SCOPE} .zg-rank {{
    background: linear-gradient(135deg, #E7C27A, {GOLD});
    color: {BROWN}; border-radius: 7px;
    box-shadow: 0 5px 12px rgba(169, 119, 46, .20);
  }}
  {_SCOPE} .zg-rank.is-muted {{
    background: rgba(201, 154, 74, .12); color: {MUTED};
    box-shadow: none;
  }}
  {_SCOPE} .zg-source {{
    color: {MUTED_LIGHT} !important; border-top-color: rgba(120, 100, 75, .16);
  }}
  {_SCOPE} .zg-source a {{ color: {GOLD_DEEP}; }}

  /* 标签：只保留轻量暖金/语义色，不喧宾夺主 */
  {_SCOPE} .zg-chip {{
    border-radius: 999px !important;
    background: rgba(201, 154, 74, .10) !important;
    color: {GOLD_DEEP} !important;
    border: 1px solid rgba(201, 154, 74, .18);
    font-size: 10.5px; padding: 2px 8px;
  }}
  {_SCOPE} .zg-chip-ok {{
    background: rgba(47, 125, 91, .09) !important; color: #2F6B50 !important;
    border-color: rgba(47, 125, 91, .18);
  }}
  {_SCOPE} .zg-chip-warn {{
    background: rgba(178, 106, 0, .09) !important; color: #8A5700 !important;
    border-color: rgba(178, 106, 0, .20);
  }}
  {_SCOPE} .zg-chip-stop {{
    background: rgba(178, 58, 46, .08) !important; color: #96352A !important;
    border-color: rgba(178, 58, 46, .18);
  }}
  {_SCOPE} .zg-chip-neutral {{
    background: rgba(120, 100, 75, .07) !important; color: {MUTED} !important;
    border-color: rgba(120, 100, 75, .16);
  }}
  {_SCOPE} .zg-chip-info {{ background: rgba(201, 154, 74, .10) !important; color: {GOLD_DEEP} !important; }}

  /* 评分条、星级、事实表 */
  {_SCOPE} .zg-bar {{ background: rgba(120, 100, 75, .10); height: 5px; border-radius: 999px; }}
  {_SCOPE} .zg-bar-fill {{ background: linear-gradient(90deg, {GOLD_DEEP}, {GOLD_LIGHT}); border-radius: 999px; }}
  {_SCOPE} .zg-dim-name {{ color: {BROWN}; }}
  {_SCOPE} .zg-dim-weight, {_SCOPE} .zg-dim-reason {{ color: {MUTED}; }}
  {_SCOPE} .zg-dim-score {{ color: {BROWN}; }}
  {_SCOPE} .zg-star-on {{ color: {GOLD}; }}
  {_SCOPE} .zg-star-off {{ color: rgba(120, 100, 75, .22); }}
  {_SCOPE} .zg-fact {{ border-bottom-color: rgba(120, 100, 75, .12); }}
  {_SCOPE} .zg-fact-key {{ color: {MUTED}; }}
  {_SCOPE} .zg-fact-val {{ color: {BROWN}; }}
  {_SCOPE} .zg-list li {{ color: {BROWN_SOFT}; }}
  {_SCOPE} .zg-list li:before {{ background: {GOLD}; }}
  {_SCOPE} .zg-list-con li:before {{ background: #B23A2E; }}
  {_SCOPE} .zg-source {{ font-family: {MONO}; }}

  /* 首页深色刊头 -> 暖金玻璃刊头 */
  {_SCOPE} .zg-home-masthead {{
    background:
      radial-gradient(60% 120% at 88% 0%, rgba(231, 201, 143, .62), transparent 62%),
      radial-gradient(50% 90% at 10% 100%, rgba(201, 154, 74, .18), transparent 70%),
      linear-gradient(135deg, rgba(255, 250, 242, .58), rgba(245, 237, 224, .34)) !important;
    border: 1px solid rgba(201, 154, 74, .28) !important;
    border-radius: 20px !important;
    color: {BROWN} !important;
    box-shadow: 0 24px 60px rgba(120, 100, 75, .14), inset 0 1px 0 rgba(255,255,255,.7);
    backdrop-filter: blur(20px) saturate(120%);
  }}
  {_SCOPE} .zg-masthead-top {{
    color: {MUTED} !important; border-bottom-color: rgba(120, 100, 75, .16) !important;
  }}
  {_SCOPE} .zg-masthead-top b {{ color: {GOLD_DEEP} !important; }}
  {_SCOPE} .zg-masthead-title {{
    font-family: {SANS} !important; font-size: 44px; font-weight: 700;
    color: {BROWN} !important; letter-spacing: -.8px;
  }}
  {_SCOPE} .zg-masthead-sub {{ color: {MUTED} !important; }}
  {_SCOPE} .zg-masthead-steps {{
    color: {MUTED} !important; border-top-color: rgba(120, 100, 75, .16) !important;
  }}
  {_SCOPE} .zg-masthead-steps b {{ color: {GOLD_DEEP} !important; }}
  {_SCOPE} .zg-masthead-top .zg-chip {{
    background: rgba(255, 250, 242, .55) !important;
    color: {GOLD_DEEP} !important;
    border-color: rgba(201, 154, 74, .24) !important;
  }}

  /* 编号脚注：去掉编号，留下轻量金线和标题 */
  {_SCOPE} .zg-rail-note {{
    grid-template-columns: 14px minmax(0, 1fr);
    border-top-color: rgba(120, 100, 75, .14);
  }}
  {_SCOPE} .zg-rail-note:last-child {{ border-bottom-color: rgba(120, 100, 75, .14); }}
  {_SCOPE} .zg-rail-index {{
    display: block; width: 12px; height: 1px; padding: 0;
    margin-top: 11px; background: {GOLD}; color: transparent; overflow: hidden;
  }}
  {_SCOPE} .zg-rail-note b {{
    font-family: {SANS} !important; font-size: 14.5px; font-weight: 650; color: {BROWN};
  }}
  {_SCOPE} .zg-rail-note p {{ color: {MUTED}; font-size: 12px; }}
  {_SCOPE} .zg-rail {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .40), rgba(255, 250, 242, .22));
    border: 1px solid rgba(201, 154, 74, .22);
    border-radius: 16px;
    padding: 4px 16px;
    backdrop-filter: blur(20px) saturate(128%);
    -webkit-backdrop-filter: blur(20px) saturate(128%);
    box-shadow: 0 16px 36px rgba(120, 100, 75, .10), inset 0 1px 0 rgba(255,255,255,.62);
  }}

  /* 分析页结论条：暖金玻璃，不再用深色块 */
  {_SCOPE} .zg-verdict {{
    background:
      radial-gradient(80% 140% at 90% 0%, rgba(231, 201, 143, .52), transparent 62%),
      linear-gradient(135deg, rgba(255, 249, 238, .66), rgba(244, 226, 193, .34)) !important;
    border: 1px solid rgba(201, 154, 74, .34) !important;
    border-top: 2px solid {GOLD} !important;
    border-radius: 16px !important;
    color: {BROWN} !important;
    box-shadow: 0 20px 46px rgba(120, 100, 75, .14), inset 0 1px 0 rgba(255,255,255,.72);
    backdrop-filter: blur(18px) saturate(120%);
  }}
  {_SCOPE} .zg-verdict-kicker {{ color: {GOLD_DEEP} !important; font-family: {SANS}; letter-spacing: .12em; }}
  {_SCOPE} .zg-verdict-name {{ font-family: {SANS} !important; color: {BROWN} !important; }}
  {_SCOPE} .zg-verdict-score {{ color: {GOLD_DEEP} !important; }}
  {_SCOPE} .zg-verdict-score small {{ color: {MUTED_LIGHT} !important; }}
  {_SCOPE} .zg-verdict-meta {{ color: {MUTED} !important; }}
  {_SCOPE} .zg-verdict-dims span {{
    border-color: rgba(201, 154, 74, .28) !important;
    color: {BROWN_SOFT} !important;
    background: rgba(255, 250, 242, .42);
  }}
  {_SCOPE} .zg-verdict-dims b {{ color: {GOLD_DEEP} !important; }}

  /* 需求摘要：一个玻璃 dossier，减少重复边框 */
  {_SCOPE} .zg-dossier-head {{
    display: flex; justify-content: space-between; align-items: center;
    font-size: 13px; font-weight: 700; color: {BROWN};
    padding-bottom: 10px; margin-bottom: 4px;
    border-bottom: 1px solid rgba(120, 100, 75, .14);
  }}
  {_SCOPE} .zg-dossier-sub {{
    font-family: {MONO}; font-size: 9.5px; color: {GOLD_DEEP};
    text-transform: uppercase; letter-spacing: .08em;
  }}
  {_SCOPE} .zg-dossier-divider {{
    height: 1px; margin: 14px 0; background: rgba(120, 100, 75, .12);
  }}
  {_SCOPE} .zg-dossier .zg-fact-key {{
    font-family: {MONO}; font-size: 10px; letter-spacing: .04em;
    text-transform: none; color: {MUTED_LIGHT};
  }}
  {_SCOPE} .zg-dossier .zg-fact-val {{ font-weight: 600; }}
  {_SCOPE} .zg-dossier .zg-ring-desc, {_SCOPE} .zg-dossier .zg-ring-title {{ color: {MUTED}; }}
  {_SCOPE} .zg-dossier .zg-ring-num {{ color: {BROWN}; }}

  /* 输入卡 / 侧栏说明卡 */
  {_SCOPE} .zg-input-card-note {{
    font-size: 12px; line-height: 1.7; color: {MUTED};
  }}
  {_SCOPE} .zg-insight-list {{ display: grid; gap: 10px; }}
  {_SCOPE} .zg-insight-row {{
    display: flex; justify-content: space-between; gap: 12px;
    padding-bottom: 9px; border-bottom: 1px solid rgba(120, 100, 75, .12);
    font-size: 12px; color: {MUTED};
  }}
  {_SCOPE} .zg-insight-row b {{
    font-family: {MONO}; font-weight: 500; color: {BROWN};
  }}
  {_SCOPE} .zg-insight-pick {{
    margin-top: 14px; padding: 14px;
    border-radius: 12px;
    background: linear-gradient(135deg, rgba(231, 201, 143, .30), rgba(255, 250, 242, .45));
    border: 1px solid rgba(201, 154, 74, .24);
  }}
  {_SCOPE} .zg-insight-pick small {{
    display: block; font-family: {MONO}; font-size: 9.5px; color: {GOLD_DEEP};
    letter-spacing: .08em; margin-bottom: 6px;
  }}
  {_SCOPE} .zg-insight-pick b {{ font-size: 13px; color: {BROWN}; line-height: 1.5; }}
  {_SCOPE} .zg-insight-pick span {{
    display: block; font-family: {MONO}; font-size: 11px; color: {GOLD_DEEP}; margin-top: 5px;
  }}

  /* ===================================================================
     Streamlit 控件：暖金玻璃输入、按钮、Tab、折叠面板、表单
     =================================================================== */
  {_SCOPE} label p,
  {_SCOPE} [data-testid="stWidgetLabel"] p {{
    color: {BROWN_SOFT} !important;
    font-size: 12.5px; font-weight: 500;
  }}
  {_SCOPE} [data-testid="stWidgetLabel"] svg,
  {_SCOPE} [data-testid="stTooltipIcon"] svg {{ color: {MUTED_LIGHT} !important; }}
  {_SCOPE} .stMarkdown p,
  {_SCOPE} [data-testid="stMarkdownContainer"] p {{ color: {BROWN_SOFT}; }}
  {_SCOPE} [data-testid="stCaptionContainer"],
  {_SCOPE} .stCaptionContainer {{ color: {MUTED} !important; }}

  {_SCOPE} [data-baseweb="input"],
  {_SCOPE} [data-baseweb="select"] > div,
  {_SCOPE} [data-baseweb="textarea"] {{
    background: rgba(255, 250, 242, .32) !important;
    border: 1px solid rgba(201, 154, 74, .24) !important;
    border-radius: 10px !important;
    color: {BROWN} !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.55);
    transition: border-color .22s ease, box-shadow .22s ease, background .22s ease;
  }}
  {_SCOPE} [data-baseweb="input"] > div,
  {_SCOPE} [data-baseweb="input"] > div > div,
  {_SCOPE} [data-baseweb="select"] > div > div {{
    background: transparent !important;
    border: none !important;
  }}
  {_SCOPE} [data-baseweb="input"]:focus-within,
  {_SCOPE} [data-baseweb="select"] > div:focus-within,
  {_SCOPE} [data-baseweb="textarea"]:focus-within {{
    border-color: {GOLD} !important;
    background: rgba(255, 250, 242, .58) !important;
    box-shadow: 0 0 0 3px rgba(201, 154, 74, .13), inset 0 1px 0 rgba(255,255,255,.7) !important;
  }}
  {_SCOPE} input, {_SCOPE} textarea {{
    color: {BROWN} !important;
    caret-color: {GOLD_DEEP};
  }}
  {_SCOPE} input::placeholder, {_SCOPE} textarea::placeholder {{
    color: {MUTED_LIGHT} !important;
  }}
  {_SCOPE} [data-baseweb="select"] [role="combobox"],
  {_SCOPE} [data-baseweb="select"] span {{ color: {BROWN} !important; }}

  /* 下拉弹层在 portal 里，无法用侧栏作用域覆盖；后台 CSS 只在登录后注入 */
  [data-baseweb="popover"] {{
    background: {IVORY} !important;
    border: 1px solid rgba(201, 154, 74, .26) !important;
    border-radius: 12px !important;
    box-shadow: 0 18px 40px rgba(120, 100, 75, .18) !important;
  }}
  [data-baseweb="popover"] [role="option"] {{ color: {BROWN} !important; }}
  [data-baseweb="popover"] [role="option"]:hover,
  [data-baseweb="popover"] [aria-selected="true"] {{
    background: rgba(201, 154, 74, .14) !important;
  }}

  {_SCOPE} .stButton > button,
  {_SCOPE} [data-testid="stBaseButton-secondaryFormSubmit"],
  {_SCOPE} [data-testid="stBaseButton-secondary"] {{
    min-height: 40px;
    border: 1px solid rgba(201, 154, 74, .30) !important;
    border-radius: 10px !important;
    background: rgba(255, 250, 242, .34) !important;
    color: {BROWN} !important;
    font-weight: 600;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.55);
    transition: background .22s ease, border-color .22s ease, color .22s ease, transform .22s ease, box-shadow .22s ease;
  }}
  {_SCOPE} [data-testid="stMain"] .stButton > button p {{ color: inherit !important; white-space: nowrap; }}
  {_SCOPE} .stButton > button:hover,
  {_SCOPE} [data-testid="stBaseButton-secondaryFormSubmit"]:hover {{
    background: rgba(255, 250, 242, .62) !important;
    border-color: {GOLD} !important;
    color: {GOLD_DEEP} !important;
    transform: translateY(-1px);
    box-shadow: 0 10px 22px rgba(120, 100, 75, .12), inset 0 1px 0 rgba(255,255,255,.7);
  }}
  {_SCOPE} .stButton > button[kind="primary"],
  {_SCOPE} [data-testid="stBaseButton-primary"],
  {_SCOPE} [data-testid="stBaseButton-primaryFormSubmit"] {{
    background: linear-gradient(135deg, #E7C27A, {GOLD}) !important;
    border-color: rgba(169, 119, 46, .34) !important;
    color: {BROWN} !important;
    border-radius: 10px !important;
    box-shadow: 0 10px 24px rgba(169, 119, 46, .24), inset 0 1px 0 rgba(255,255,255,.45);
  }}
  {_SCOPE} .stButton > button[kind="primary"]:hover,
  {_SCOPE} [data-testid="stBaseButton-primary"]:hover,
  {_SCOPE} [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
    background: linear-gradient(135deg, #F0D094, #D6A957) !important;
    color: {BROWN} !important;
    transform: translateY(-1px);
    box-shadow: 0 14px 30px rgba(169, 119, 46, .28);
  }}
  {_SCOPE} .stButton > button:focus-visible,
  {_SCOPE} [data-testid="stBaseButton-primary"]:focus-visible,
  {_SCOPE} [data-testid="stBaseButton-secondary"]:focus-visible {{
    outline: 2px solid rgba(201, 154, 74, .55);
    outline-offset: 2px;
  }}
  /* 导出按钮降低权重 */
  {_SCOPE} [data-testid="stDownloadButton"] button {{
    min-height: 36px;
    background: transparent !important;
    border-color: rgba(201, 154, 74, .24) !important;
    color: {MUTED} !important;
    box-shadow: none;
    font-weight: 500;
  }}
  {_SCOPE} [data-testid="stDownloadButton"] button:hover {{
    background: rgba(255, 250, 242, .55) !important;
    color: {GOLD_DEEP} !important;
  }}

  {_SCOPE} [data-testid="stForm"] {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .42), rgba(255, 250, 242, .22)) !important;
    border: 1px solid rgba(201, 154, 74, .22) !important;
    border-radius: 16px !important;
    padding: 18px 18px 8px 18px;
    backdrop-filter: blur(18px) saturate(120%);
    box-shadow: 0 18px 40px rgba(120, 100, 75, .10), inset 0 1px 0 rgba(255,255,255,.6);
  }}
  {_SCOPE} [data-testid="stVerticalBlockBorderWrapper"] {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .44), rgba(255, 250, 242, .24)) !important;
    border: 1px solid rgba(201, 154, 74, .22) !important;
    border-radius: 16px !important;
    backdrop-filter: blur(18px) saturate(120%);
    box-shadow: 0 18px 40px rgba(120, 100, 75, .10), inset 0 1px 0 rgba(255,255,255,.6);
  }}
  {_SCOPE} [data-testid="stVerticalBlockBorderWrapper"]:has(.zg-brief-label) {{
    border-left: 2px solid {GOLD} !important;
  }}

  {_SCOPE} [data-testid="stExpander"] {{
    background: rgba(255, 250, 242, .26) !important;
    border: 1px solid rgba(201, 154, 74, .20) !important;
    border-radius: 12px !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.55);
    backdrop-filter: blur(12px);
    overflow: hidden;
  }}
  {_SCOPE} [data-testid="stExpander"] summary {{
    color: {BROWN_SOFT} !important; font-size: 12.5px; font-weight: 500;
  }}
  {_SCOPE} [data-testid="stExpander"] summary:hover {{ color: {GOLD_DEEP} !important; }}
  {_SCOPE} [data-testid="stExpander"] svg {{ color: {MUTED} !important; }}

  {_SCOPE} [data-baseweb="tab-list"] {{
    gap: 4px; border-bottom: 1px solid rgba(120, 100, 75, .16);
  }}
  {_SCOPE} [data-baseweb="tab"] {{
    color: {MUTED} !important; font-size: 13px;
    border-radius: 8px 8px 0 0;
  }}
  {_SCOPE} [data-baseweb="tab"][aria-selected="true"] {{ color: {BROWN} !important; font-weight: 600; }}
  {_SCOPE} [data-baseweb="tab-highlight"] {{
    background: {GOLD} !important; height: 2px !important;
  }}
  {_SCOPE} [data-testid="stAlert"] {{
    border-radius: 10px;
    background: rgba(255, 250, 242, .34) !important;
    border: 1px solid rgba(201, 154, 74, .20);
    color: {BROWN_SOFT} !important;
  }}

  /* 表格：深色工作台里的“浅色账本”，保证表格画布可读 */
  {_SCOPE} [data-testid="stDataFrame"] {{
    background: {IVORY} !important;
    border: 1px solid rgba(201, 154, 74, .28) !important;
    border-radius: 12px !important;
    overflow: hidden;
    box-shadow: 0 14px 34px rgba(120, 100, 75, .10), inset 0 1px 0 rgba(255,255,255,.6);
  }}

  /* Radio / checkbox / toggle 的标签与说明 */
  {_SCOPE} [data-testid="stRadio"] label,
  {_SCOPE} [data-testid="stCheckbox"] label,
  {_SCOPE} [data-testid="stToggle"] label {{
    color: {BROWN_SOFT} !important;
  }}
  {_SCOPE} [data-testid="stRadio"] label p,
  {_SCOPE} [data-testid="stCheckbox"] label p,
  {_SCOPE} [data-testid="stToggle"] label p {{ color: {BROWN_SOFT} !important; }}

  /* 聊天气泡 / 输入 */
  {_SCOPE} [data-testid="stChatMessage"] {{
    background: rgba(255, 250, 242, .42) !important;
    border: 1px solid rgba(201, 154, 74, .18);
    border-radius: 14px;
    backdrop-filter: blur(12px);
  }}
  {_SCOPE} [data-testid="stChatInput"] {{
    background: rgba(255, 250, 242, .44) !important;
    border: 1px solid rgba(201, 154, 74, .24) !important;
    border-radius: 14px !important;
  }}

  /* 侧栏按钮需要压过主区通用按钮样式（主区规则也匹配到侧栏） */
  {_SCOPE} {_SIDEBAR} .stButton > button {{
    background: transparent !important;
    border: 1px solid transparent !important;
    box-shadow: none !important;
    color: {BROWN_SOFT} !important;
  }}
  {_SCOPE} {_SIDEBAR} .stButton > button p,
  {_SCOPE} {_SIDEBAR} .stButton > button span {{ color: inherit !important; }}
  {_SCOPE} {_SIDEBAR} .stButton > button:hover {{
    background: rgba(255, 250, 242, .34) !important;
    border-color: rgba(201, 154, 74, .28) !important;
    color: {BROWN} !important;
  }}
  {_SCOPE} {_SIDEBAR} .stButton > button[kind=primary] {{
    background: linear-gradient(135deg, #E7C27A, {GOLD}) !important;
    border-color: rgba(169, 119, 46, .34) !important;
    color: {BROWN} !important;
    box-shadow: 0 8px 20px rgba(169, 119, 46, .24), inset 0 1px 0 rgba(255,255,255,.45) !important;
  }}
  {_SCOPE} {_SIDEBAR} .stButton > button[kind=primary] p,
  {_SCOPE} {_SIDEBAR} .stButton > button[kind=primary] span {{ color: {BROWN} !important; }}

  /* st.container(border=True) 在当前 Streamlit 里是 stLayoutWrapper > stVerticalBlock */
  {_SCOPE} [data-testid=stLayoutWrapper] > [data-testid=stVerticalBlock] {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .42), rgba(255, 250, 242, .22)) !important;
    border: 1px solid rgba(201, 154, 74, .24) !important;
    border-radius: 16px !important;
    padding: 18px !important;
    backdrop-filter: blur(18px) saturate(120%);
    -webkit-backdrop-filter: blur(18px) saturate(120%);
    box-shadow: 0 18px 40px rgba(120, 100, 75, .10), inset 0 1px 0 rgba(255,255,255,.62) !important;
  }}
  {_SCOPE} [data-testid=stLayoutWrapper] > [data-testid=stVerticalBlock]:has(.zg-brief-label) {{
    border-left: 2px solid {GOLD} !important;
  }}
  /* 文本域内层不要再用 Streamlit 的纯白底，否则会盖掉玻璃 */
  {_SCOPE} [data-testid=stTextAreaRootElement] > div,
  {_SCOPE} [data-testid=stTextAreaRootElement] textarea {{
    background: transparent !important;
  }}

  /* ===================================================================
     动效：只作用于后台，登录页不受影响
     =================================================================== */
  @keyframes zgBackendIn {{
    from {{ opacity: 0; transform: translateY(10px); }}
    to   {{ opacity: 1; transform: none; }}
  }}
  {_SCOPE} .zg-enter .zg-masthead-title,
  {_SCOPE} .zg-enter.zg-hero h1 {{
    animation: zgBackendIn .38s cubic-bezier(.22, .61, .36, 1) both;
  }}
  {_SCOPE} .zg-enter .zg-masthead-sub,
  {_SCOPE} .zg-enter .zg-masthead-steps,
  {_SCOPE} .zg-enter.zg-hero p {{
    animation: zgBackendIn .35s .04s cubic-bezier(.22, .61, .36, 1) both;
  }}
  {_SCOPE} .zg-enter .zg-rail-note {{
    animation: zgBackendIn .32s cubic-bezier(.22, .61, .36, 1) both;
  }}
  {_SCOPE} .zg-enter .zg-rail-note:nth-child(2) {{ animation-delay: .04s; }}
  {_SCOPE} .zg-enter .zg-rail-note:nth-child(3) {{ animation-delay: .08s; }}
  {_SCOPE} .zg-enter .zg-rail-note:nth-child(4) {{ animation-delay: .12s; }}
  {_SCOPE} .zg-enter .zg-verdict {{
    animation: zgBackendIn .35s cubic-bezier(.22, .61, .36, 1) both;
  }}
  {_SCOPE} .zg-card,
  {_SCOPE} .zg-feature,
  {_SCOPE} .zg-compare-cell,
  {_SCOPE} .zg-proscons-card {{
    transition: transform .24s ease, box-shadow .24s ease, border-color .24s ease !important;
  }}
  {_SCOPE} .zg-card:hover,
  {_SCOPE} .zg-feature:hover,
  {_SCOPE} .zg-compare-cell:hover,
  {_SCOPE} .zg-proscons-card:hover {{
    transform: translateY(-3px);
    border-color: rgba(201, 154, 74, .48) !important;
    box-shadow: 0 24px 52px rgba(120, 100, 75, .16), inset 0 1px 0 rgba(255,255,255,.75) !important;
  }}

  {_SCOPE} [data-testid="stMain"] .stButton > button:disabled,
  {_SCOPE} [data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"]:disabled {{
    opacity: .45 !important;
    cursor: not-allowed !important;
    transform: none !important;
    box-shadow: none !important;
  }}

  /* ===================================================================
     最终磨砂玻璃层：控件也要有白色玻璃体，而不是只降低透明度
     =================================================================== */
  {_SIDEBAR} {{
    margin: 14px 0 14px 14px !important;
    height: calc(100vh - 28px) !important;
    border: 1px solid rgba(201, 154, 74, .30) !important;
    border-radius: 24px !important;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, .12), rgba(255, 255, 255, 0) 24%),
      linear-gradient(180deg, rgba(255, 250, 242, .38), rgba(245, 237, 224, .18)) !important;
    backdrop-filter: blur(40px) saturate(165%) !important;
    -webkit-backdrop-filter: blur(40px) saturate(165%) !important;
    border-color: rgba(255, 252, 244, .42) !important;
    box-shadow:
      0 26px 64px rgba(120, 100, 75, .18),
      inset 0 1px 0 rgba(255, 255, 255, .92),
      inset 0 0 0 1px rgba(255, 255, 255, .14) !important;
    overflow: hidden !important;
  }}
  {_SIDEBAR} > div:first-child {{
    height: 100%; border-radius: 24px; overflow-y: auto;
  }}

  {_SCOPE} .zg-topbar {{
    background: linear-gradient(120deg, rgba(255, 250, 242, .70), rgba(255, 250, 242, .46)) !important;
    border: 1px solid rgba(201, 154, 74, .28) !important;
    border-radius: 18px !important;
    backdrop-filter: blur(26px) saturate(138%) !important;
    -webkit-backdrop-filter: blur(26px) saturate(138%) !important;
    box-shadow: 0 18px 44px rgba(120, 100, 75, .14), inset 0 1px 0 rgba(255,255,255,.85) !important;
  }}

  {_SCOPE} .zg-card,
  {_SCOPE} .zg-feature,
  {_SCOPE} .zg-statstrip,
  {_SCOPE} .zg-compare-cell,
  {_SCOPE} .zg-proscons-card {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .68), rgba(255, 250, 242, .46)) !important;
    border: 1px solid rgba(201, 154, 74, .26) !important;
    border-radius: 18px !important;
    backdrop-filter: blur(26px) saturate(138%) !important;
    -webkit-backdrop-filter: blur(26px) saturate(138%) !important;
    box-shadow: 0 24px 54px rgba(120, 100, 75, .15), inset 0 1px 0 rgba(255,255,255,.80) !important;
  }}
  {_SCOPE} .zg-card:has(.zg-row) {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .84), rgba(255, 250, 242, .62)) !important;
    border-radius: 16px !important;
    box-shadow: 0 22px 48px rgba(120, 100, 75, .16), inset 0 1px 0 rgba(255,255,255,.88) !important;
  }}
  {_SCOPE} .zg-card.is-flat,
  {_SCOPE} .zg-card.zg-dossier {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .58), rgba(255, 250, 242, .38)) !important;
    border-radius: 16px !important;
    box-shadow: 0 18px 40px rgba(120, 100, 75, .12), inset 0 1px 0 rgba(255,255,255,.78) !important;
  }}
  {_SCOPE} .zg-rail {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .64), rgba(255, 250, 242, .46)) !important;
    border-radius: 18px !important;
    backdrop-filter: blur(24px) saturate(135%) !important;
    -webkit-backdrop-filter: blur(24px) saturate(135%) !important;
    box-shadow: 0 20px 46px rgba(120, 100, 75, .13), inset 0 1px 0 rgba(255,255,255,.82) !important;
  }}
  {_SCOPE} .zg-home-masthead {{
    background:
      radial-gradient(60% 120% at 88% 0%, rgba(231, 201, 143, .55), transparent 62%),
      linear-gradient(135deg, rgba(255, 250, 242, .78), rgba(245, 237, 224, .56)) !important;
    border-radius: 22px !important;
    backdrop-filter: blur(28px) saturate(140%) !important;
    -webkit-backdrop-filter: blur(28px) saturate(140%) !important;
    box-shadow: 0 28px 64px rgba(120, 100, 75, .16), inset 0 1px 0 rgba(255,255,255,.85) !important;
  }}
  {_SCOPE} .zg-verdict {{
    background:
      radial-gradient(80% 140% at 90% 0%, rgba(231, 201, 143, .48), transparent 62%),
      linear-gradient(135deg, rgba(255, 249, 238, .84), rgba(244, 226, 193, .56)) !important;
    border-radius: 18px !important;
    backdrop-filter: blur(24px) saturate(135%) !important;
    -webkit-backdrop-filter: blur(24px) saturate(135%) !important;
    box-shadow: 0 22px 52px rgba(120, 100, 75, .15), inset 0 1px 0 rgba(255,255,255,.88) !important;
  }}

  /* 表单/输入大卡：明显的磨砂白玻璃体 */
  {_SCOPE} [data-testid="stForm"],
  {_SCOPE} [data-testid="stVerticalBlockBorderWrapper"],
  {_SCOPE} [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .70), rgba(255, 250, 242, .48)) !important;
    border: 1px solid rgba(201, 154, 74, .28) !important;
    border-radius: 18px !important;
    backdrop-filter: blur(26px) saturate(138%) !important;
    -webkit-backdrop-filter: blur(26px) saturate(138%) !important;
    box-shadow: 0 24px 52px rgba(120, 100, 75, .15), inset 0 1px 0 rgba(255,255,255,.85) !important;
  }}

  /* 输入框、下拉框、文本域：玻璃控件，不是一条淡淡的线 */
  {_SCOPE} [data-baseweb="input"],
  {_SCOPE} [data-baseweb="select"] > div,
  {_SCOPE} [data-baseweb="textarea"] {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .82), rgba(255, 250, 242, .60)) !important;
    border: 1px solid rgba(201, 154, 74, .30) !important;
    border-radius: 12px !important;
    backdrop-filter: blur(16px) saturate(135%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(135%) !important;
    box-shadow: 0 8px 20px rgba(120, 100, 75, .08), inset 0 1px 0 rgba(255,255,255,.88) !important;
  }}
  {_SCOPE} [data-baseweb="input"]:focus-within,
  {_SCOPE} [data-baseweb="select"] > div:focus-within,
  {_SCOPE} [data-baseweb="textarea"]:focus-within {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .94), rgba(255, 250, 242, .76)) !important;
    border-color: {GOLD} !important;
    box-shadow: 0 0 0 3px rgba(201, 154, 74, .16), 0 10px 24px rgba(120, 100, 75, .10), inset 0 1px 0 rgba(255,255,255,.9) !important;
  }}

  /* 次级按钮也做成磨砂玻璃；主按钮保持香槟金 */
  {_SCOPE} [data-testid="stMain"] .stButton > button,
  {_SCOPE} [data-testid="stMain"] [data-testid="stBaseButton-secondaryFormSubmit"],
  {_SCOPE} [data-testid="stMain"] [data-testid="stBaseButton-secondary"] {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .82), rgba(255, 250, 242, .58)) !important;
    border: 1px solid rgba(201, 154, 74, .30) !important;
    border-radius: 10px !important;
    backdrop-filter: blur(14px) saturate(132%) !important;
    -webkit-backdrop-filter: blur(14px) saturate(132%) !important;
    box-shadow: 0 8px 20px rgba(120, 100, 75, .10), inset 0 1px 0 rgba(255,255,255,.85) !important;
  }}
  {_SCOPE} [data-testid="stMain"] .stButton > button:hover {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .94), rgba(255, 250, 242, .72)) !important;
    border-color: {GOLD} !important;
    color: {GOLD_DEEP} !important;
  }}
  {_SCOPE} [data-testid="stMain"] .stButton > button[kind="primary"],
  {_SCOPE} [data-testid="stMain"] [data-testid="stBaseButton-primary"],
  {_SCOPE} [data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"] {{
    background: linear-gradient(135deg, #EBCB8D, {GOLD}) !important;
    border: 1px solid rgba(169, 119, 46, .40) !important;
    border-radius: 10px !important;
    color: {BROWN} !important;
    box-shadow: 0 12px 26px rgba(169, 119, 46, .24), inset 0 1px 0 rgba(255,255,255,.55) !important;
  }}
  {_SCOPE} [data-testid="stMain"] .stButton > button[kind="primary"]:hover,
  {_SCOPE} [data-testid="stMain"] [data-testid="stBaseButton-primary"]:hover,
  {_SCOPE} [data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
    background: linear-gradient(135deg, #F4D9A9, #D8AC5D) !important;
  }}

  {_SCOPE} [data-testid="stExpander"] {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .56), rgba(255, 250, 242, .36)) !important;
    border-radius: 12px !important;
    backdrop-filter: blur(18px) saturate(130%) !important;
    -webkit-backdrop-filter: blur(18px) saturate(130%) !important;
    box-shadow: 0 12px 28px rgba(120, 100, 75, .08), inset 0 1px 0 rgba(255,255,255,.78) !important;
  }}
  {_SCOPE} [data-testid="stChatMessage"] {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .60), rgba(255, 250, 242, .40)) !important;
    border-radius: 14px !important;
    backdrop-filter: blur(16px) !important;
    box-shadow: 0 12px 28px rgba(120, 100, 75, .08), inset 0 1px 0 rgba(255,255,255,.78) !important;
  }}
  {_SCOPE} [data-testid="stChatInput"] {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .82), rgba(255, 250, 242, .60)) !important;
    border: 1px solid rgba(201, 154, 74, .30) !important;
    border-radius: 14px !important;
    backdrop-filter: blur(16px) !important;
    box-shadow: 0 8px 20px rgba(120, 100, 75, .08), inset 0 1px 0 rgba(255,255,255,.85) !important;
  }}

  /* 不支持 backdrop-filter 时退回不透明暖象牙表面，保证对比度 */
  @supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {{
    {_SIDEBAR},
    {_SCOPE} .zg-topbar,
    {_SCOPE} .zg-card,
    {_SCOPE} .zg-feature,
    {_SCOPE} .zg-statstrip,
    {_SCOPE} .zg-compare-cell,
    {_SCOPE} .zg-proscons-card,
    {_SCOPE} .zg-rail,
    {_SCOPE} .zg-home-masthead,
    {_SCOPE} .zg-verdict,
    {_SCOPE} .zg-empty,
    {_SCOPE} [data-testid="stForm"],
    {_SCOPE} [data-testid="stExpander"],
    {_SCOPE} [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] {{
      background: {IVORY} !important;
    }}
    {_SCOPE} [data-baseweb="input"],
    {_SCOPE} [data-baseweb="select"] > div,
    {_SCOPE} [data-baseweb="textarea"] {{
      background: {IVORY} !important;
    }}
  }}

  @media (prefers-reduced-motion: reduce) {{
    {_SCOPE} .zg-enter .zg-masthead-title,
    {_SCOPE} .zg-enter .zg-masthead-sub,
    {_SCOPE} .zg-enter .zg-masthead-steps,
    {_SCOPE} .zg-enter .zg-rail-note,
    {_SCOPE} .zg-enter .zg-verdict,
    {_SCOPE} .zg-enter.zg-hero h1,
    {_SCOPE} .zg-enter.zg-hero p {{
      animation: none !important;
    }}
    {_SCOPE} .zg-card,
    {_SCOPE} .zg-feature,
    {_SCOPE} .zg-compare-cell,
    {_SCOPE} .zg-proscons-card,
    {_SCOPE} .stButton > button {{
      transition: none !important;
    }}
    {_SCOPE} .zg-card:hover,
    {_SCOPE} .zg-feature:hover,
    {_SCOPE} .zg-compare-cell:hover,
    {_SCOPE} .zg-proscons-card:hover {{ transform: none !important; }}
  }}

  @media (max-width: 1000px) {{
    {_SCOPE} [data-testid="stHorizontalBlock"]:has(.zg-verdict) {{
      flex-wrap: wrap;
    }}
    {_SCOPE} [data-testid="stHorizontalBlock"]:has(.zg-verdict) > [data-testid="stColumn"] {{
      flex: 1 1 100% !important;
      width: 100% !important;
      min-width: 100% !important;
    }}
  }}
  @media (max-width: 900px) {{
    {_SCOPE} [data-testid="stHorizontalBlock"]:has(.zg-rail) {{
      flex-wrap: wrap;
    }}
    {_SCOPE} [data-testid="stHorizontalBlock"]:has(.zg-rail) > [data-testid="stColumn"] {{
      flex: 1 1 100% !important;
      width: 100% !important;
      min-width: 100% !important;
    }}
  }}
  @media (max-width: 760px) {{
    {_SCOPE} .zg-topbar {{ align-items: flex-start; flex-direction: column; }}
    {_SCOPE} .zg-topbar-right {{ width: 100%; justify-content: space-between; }}
    {_SCOPE} .zg-masthead-title {{ font-size: 34px; }}
    {_SCOPE} .zg-hero h1 {{ font-size: 28px; }}
  }}
</style>
"""


def inject() -> None:
    """只在登录后的后台注入；登录页不调用。"""
    st.markdown(_STYLES, unsafe_allow_html=True)

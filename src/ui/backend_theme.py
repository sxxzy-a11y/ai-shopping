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
  /* Streamlit 新版文本输入 DOM */
  {_SCOPE} [data-testid="stTextInputRootElement"] {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .82), rgba(255, 250, 242, .60)) !important;
    border: 1px solid rgba(201, 154, 74, .30) !important;
    border-radius: 12px !important;
    backdrop-filter: blur(16px) saturate(135%) !important;
    -webkit-backdrop-filter: blur(16px) saturate(135%) !important;
    box-shadow: 0 8px 20px rgba(120, 100, 75, .08), inset 0 1px 0 rgba(255,255,255,.88) !important;
  }}
  {_SCOPE} [data-testid="stTextInputRootElement"]:focus-within {{
    background: linear-gradient(145deg, rgba(255, 250, 242, .94), rgba(255, 250, 242, .76)) !important;
    border-color: {GOLD} !important;
    box-shadow: 0 0 0 3px rgba(201, 154, 74, .16), 0 10px 24px rgba(120, 100, 75, .10), inset 0 1px 0 rgba(255,255,255,.9) !important;
  }}
  {_SCOPE} [data-testid="stTextInputRootElement"] input {{
    color: {BROWN} !important;
    background: transparent !important;
    caret-color: {GOLD_DEEP};
  }}
  {_SCOPE} [data-testid="stTextInputRootElement"] input::placeholder {{
    color: {MUTED_LIGHT} !important;
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
  /* ------------------------------------------------------------------
     悬停按钮：magicui「Interactive Hover Button」的 Streamlit 版
     ------------------------------------------------------------------
     由 src/ui/hover_button.py 使用：按钮 key 以 `zg-hover-` 开头才会命中，
     其余按钮保持上面的常规样式，不会被这条规则波及。

     原组件是 React 版——一枚圆点膨胀铺满整颗按钮，旧文字滑走、新一层
     「文字 + 箭头」滑入。Streamlit 的按钮只有一层标签，所以这里保留两拍
     最容易感知的动效：圆点膨胀成金色填充，箭头从右侧滑入；
     文字留在原位换成深色，hover 时仍然读得出来。 */
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button {{
    position: relative;
    isolation: isolate;
    overflow: hidden;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-height: 42px;
    /* 标签一律不换行、不被压扁：中文按钮被挤成「开始分…」比溢出更难看 */
    min-width: max-content;
    max-width: none;
    /* 右边留出箭头的位置（箭头是绝对定位的，不占布局），左边只留圆点的间距 */
    padding: 0 26px 0 18px !important;
    border-radius: 999px !important;
    border: 1px solid rgba(201, 154, 74, .42) !important;
    background: rgba(255, 250, 242, .30) !important;
    color: {BROWN} !important;
    font-weight: 600;
    letter-spacing: .02em;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, .55);
    transition: color .3s ease, border-color .3s ease, box-shadow .3s ease,
                transform .3s ease;
  }}
  /* 圆点：和文字一起居中（flex 里的第一个元素，不用绝对定位，宽按钮也不会
     把点甩到最左边）；hover 时原地放大到铺满整颗按钮，overflow 裁掉多余 */
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button::before {{
    content: "";
    flex: 0 0 auto;
    width: 7px;
    height: 7px;
    border-radius: 999px;
    background: linear-gradient(135deg, {GOLD_LIGHT}, {GOLD});
    transform: scale(1);
    transform-origin: center;
    transition: transform .45s cubic-bezier(.3, .9, .3, 1);
    pointer-events: none;
    z-index: 0;
  }}
  /* 箭头：Lucide ArrowRight 的 mask，颜色跟随 currentColor，不用额外图标库。
     绝对定位在右侧留白里，不参与布局——按钮宽度不会因为 hover 变宽而跳动，
     也就不会在窄列里把标签挤掉。 */
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button::after {{
    content: "";
    position: absolute;
    right: 10px;
    top: 50%;
    width: 14px;
    height: 14px;
    margin-top: -7px;
    background-color: currentColor;
    -webkit-mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M5 12h14'/><path d='m12 5 7 7-7 7'/></svg>") center / 14px 14px no-repeat;
    mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M5 12h14'/><path d='m12 5 7 7-7 7'/></svg>") center / 14px 14px no-repeat;
    opacity: 0;
    transform: translateX(-5px);
    transition: opacity .24s ease, transform .34s cubic-bezier(.3, .9, .3, 1);
    pointer-events: none;
    z-index: 2;
  }}
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button [data-testid="stMarkdownContainer"] {{
    position: relative;
    z-index: 1;
  }}
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button p {{
    color: inherit !important;
    font-weight: 600;
  }}
  /* hover / 键盘聚焦：同一个状态，键盘用户也看得到箭头 */
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button:hover,
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button:focus-visible {{
    background: rgba(255, 250, 242, .30) !important;
    border-color: transparent !important;
    color: {BROWN} !important;
    transform: translateY(-1px);
    box-shadow: 0 12px 26px rgba(169, 119, 46, .26);
  }}
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button:hover::before,
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button:focus-visible::before {{
    transform: scale(160);
  }}
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button:hover::after,
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button:focus-visible::after {{
    opacity: 1;
    transform: translateX(0);
  }}
  /* ------------------------------------------------------------------
     侧栏导航：同一套悬停动效，按「导航行」适配
     ------------------------------------------------------------------
     导航不是药丸 CTA——整行左对齐、带图标，所以圆点缩到 6px，
     hover 铺开的是浅金（深金留给当前页），箭头贴右边。
     当前页仍走 [kind="primary"] 的金色渐变，动效关掉，不和选中态打架。 */
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button {{
    position: relative;
    isolation: isolate;
    overflow: hidden;
    justify-content: flex-start;
    text-align: left;
    padding: 0 34px 0 30px !important;
    border-radius: 12px !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    color: {BROWN_SOFT} !important;
    box-shadow: none !important;
    transition: color .25s ease;
  }}
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button::before {{
    content: "";
    position: absolute;
    left: 13px;
    top: 50%;
    width: 6px;
    height: 6px;
    margin-top: -3px;
    border-radius: 999px;
    background: {GOLD};
    opacity: 0;
    transform: scale(1);
    transform-origin: center;
    transition: transform .42s cubic-bezier(.3, .9, .3, 1), opacity .18s ease, background .12s linear;
    pointer-events: none;
    z-index: 0;
  }}
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button::after {{
    content: "";
    position: absolute;
    right: 13px;
    top: 50%;
    width: 14px;
    height: 14px;
    margin-top: -7px;
    background-color: currentColor;
    -webkit-mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M5 12h14'/><path d='m12 5 7 7-7 7'/></svg>") center / 14px 14px no-repeat;
    mask: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M5 12h14'/><path d='m12 5 7 7-7 7'/></svg>") center / 14px 14px no-repeat;
    opacity: 0;
    transform: translateX(-5px);
    transition: opacity .2s ease, transform .3s cubic-bezier(.3, .9, .3, 1);
    pointer-events: none;
    z-index: 2;
  }}
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button [data-testid="stMarkdownContainer"] {{
    position: relative;
    z-index: 1;
  }}
  /* 图标是按钮的另一个子元素，不抬高就会被铺开的金色盖住（描边图标尤其明显） */
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button > * {{
    position: relative;
    z-index: 1;
  }}
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button p {{
    color: inherit !important;
  }}
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button:hover {{
    background: transparent !important;
    border-color: transparent !important;
    box-shadow: none !important;
    color: {BROWN} !important;
  }}
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button:hover::before {{
    background: linear-gradient(135deg, #F8EACD, #EACF9C);
    opacity: 1;
    transform: scale(170);
  }}
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button:hover::after {{
    opacity: 1;
    transform: translateX(0);
  }}
  /* 当前页：保留原来的深金渐变，圆点和箭头都收起来 */
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, #E7C27A, {GOLD}) !important;
    border-color: rgba(169, 119, 46, .34) !important;
    color: {BROWN} !important;
    box-shadow: 0 8px 20px rgba(169, 119, 46, .24), inset 0 1px 0 rgba(255,255,255,.45) !important;
  }}
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button[kind="primary"]::before,
  {_SCOPE} [data-testid="stSidebar"] [class*="st-key-zg-hover-nav-"] .stButton > button[kind="primary"]::after {{
    opacity: 0;
    transform: scale(1);
  }}
  /* 带悬停按钮的一行：按钮列按内容宽度走，窄屏时右边的说明换到下一行，
     而不是把中文标签挤成「开始分…」（st.columns 默认 min-width: 0，会一直压）。 */
  {_SCOPE} [data-testid="stMain"] [data-testid="stHorizontalBlock"]:has([class*="st-key-zg-hover-"]) {{
    flex-wrap: wrap;
  }}
  {_SCOPE} [data-testid="stMain"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has([class*="st-key-zg-hover-"]) {{
    flex: 0 0 auto;
    width: max-content !important;
    min-width: max-content;
  }}
  /* 触屏没有 hover：直接落到填充态，别让主操作看起来是灰的 */
  @media (hover: none) {{    {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button {{
      background: linear-gradient(135deg, {GOLD_LIGHT}, {GOLD}) !important;
      border-color: transparent !important;
    }}
    {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button::before {{ display: none; }}
    {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button::after {{
      opacity: 1; transform: translateX(0);
    }}
  }}
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button:disabled {{
    opacity: .45;
    cursor: not-allowed;
    color: {MUTED} !important;
    background: rgba(255, 250, 242, .30) !important;
    transform: none;
    box-shadow: none;
  }}
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button:disabled::before {{
    background: {MUTED_LIGHT};
    transform: scale(1);
  }}
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button:disabled::after {{
    opacity: 0;
  }}
  /* 次操作（variant="secondary"）：动效一样，填充换成浅金，不和主操作抢视线 */
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button[kind="secondary"] {{
    background: rgba(255, 250, 242, .18) !important;
    border-color: rgba(201, 154, 74, .30) !important;
  }}
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button[kind="secondary"]::before {{
    background: linear-gradient(135deg, {GOLD_LIGHT}, rgba(201, 154, 74, .55));
  }}
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button[kind="secondary"]:hover,
  {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button[kind="secondary"]:focus-visible {{
    border-color: transparent !important;
    color: {BROWN} !important;
    box-shadow: 0 10px 22px rgba(120, 100, 75, .14);
  }}
  /* 无障碍：系统开启「减少动态效果」时不做膨胀和位移，只留颜色变化。
     这一节在样式表末尾、权重又高于上面的全局 reduced-motion 规则，
     所以必须在这里单独关掉过渡。 */
  @media (prefers-reduced-motion: reduce) {{
    {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button,
    {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button::before,
    {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button::after,
    {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button [data-testid="stMarkdownContainer"] {{
      transition: none !important;
    }}
    {_SCOPE} [data-testid="stMain"] [class*="st-key-zg-hover-"] .stButton > button:hover [data-testid="stMarkdownContainer"] {{
      transform: none !important;
    }}
  }}

  /* ===================================================================
     visionOS 外壳：暖灰石墙 + 浮起的玻璃窗
     -------------------------------------------------------------------
     玻璃感靠三件事，缺一件就退化成「白卡片」：
       1. 背后有层次 —— 底色得有明显的光斑/暗块，透过去才看得见；
       2. 透得够多   —— 窗口 40% 左右、卡片 32% 左右，太实就成纸；
       3. 边缘有光   —— 上沿 1px 高光、下沿内阴影、外侧大投影。
     =================================================================== */
  {_SCOPE} {{
    /* 底座是一张程序生成的暖灰石墙（多倍频噪声 + 窗口光），
       玻璃只有在这种有明暗起伏的底上才「透」得出来 */
    background-color: #b3aca1 !important;
    background-image:
      radial-gradient(620px 900px at 4% 20%, rgba(255, 250, 238, .55), rgba(255, 250, 238, 0) 62%),
      linear-gradient(102deg, rgba(255, 249, 238, .34) 0%, rgba(255, 249, 238, 0) 40%),
      radial-gradient(1000px 720px at 52% 120%, rgba(36, 30, 25, .50), rgba(36, 30, 25, 0) 66%),
      url("data:image/jpeg;base64,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JEMIJNOMOHDLELGEkkmkpuuhooghpkqtFqjrj3da810vp95/80VS34x7w/ZRTVfQXRZddeeYbeVVfcZdcWTcTaIPPPJIDKACJBCIIBKNIJCHDCilpsqtuoriqqlsustomhg5s5rvpr7x7617TY5y8y5abbdfcQedQQZYYfQeYbVYbdaTRUaPIONKGJLGGIKANEDICMFNBLPBisukpmproppmpphusihspKunipp7w86691ZSbeWTbXVZRaUZTReWUVYYZaaVURZfTQUTRPIGMBAIANJBKCFMBFMIOFEACP60oisritniqvtioqhvggruqihw+094201+1XfZ1WddaacaWRbXSZeYWRQZRYfZTfRdfXCMFFBALCOLNPMEGEHDFCFDECGH71oinpnthtppjnsjvvmiqtukjn462www1/4US67cbTdZcRdZUVVVWRRfadeYZYZfdfXQDEOOGLMKAIIOABNKEGJJGEEBDM09/wA74Z54rYprJZ7JYppo4uufu9Ndc9Pe/dsHWE10nUEmlHnEmGnHnX1GUU3k11F00whQwyDxBCwTxiCDiADCjSxhzRQRCuve+qI4YZKar6q9sLLpqf8A/vb7bfD/AH2x8/1afbVUWcRTZXeVfafXTYWXaQQbdTZXWXcEJNDAHEKMLAEBOMGEDNOEHBODBDz2zrlrrqnsknrq4+w78qjyz0z2x2w98w25RTWaRbZQSYWfTdUcXfbUVYXbQeXeeeTIbBKGIJGAMGBODJMLPCBLNELDOAJK63ggqugp2kiuistrztqtmngt621+52/23zYWdUcUWVbaecWYebQUXfaQWYdYZeddXaLIFDIPJENAJOHEEADEBGCGGAKPGKw24jjnkj24/umvtvujilrgm1y6xyz4y30UbbXZdYVSQWbbTccURdacRXeQbeVfbVKMPBAOAANBLGOMDGAAGMDGJKDJFDCA3m1trtq13vz237hivvsktmlw/wCduf8AXnLfZxtBx9ZVNpVBRtZdlRt5tZx5xxt5tc480cscg0YoYAIsUgMQMwgM8kco8UQsrCHWu6ffvHbDL3KiO6e+S+KnzvPX3bz3/X9tV5h9ZJVh9ttZhJZ1FFVZRZ9ldNpkkAooQ0Yoc0oE0oI4sMYUwwIIk0cAwsHDi26vbTXTzzrTX+S2eeu2i/X73zHTP3JvB9Zt9hJ5RN9FR1F1tJZ995h5pphN99YYY0oMIkscAUQ48AMYYgw4oY8ssQgY3zqOLDb7rnz3/LDnj2OG3OmT/f3jn77NxRJlBV1dZ9Jxx1Z99t9FNNB1RRVZxxQ04AcsAA448MwYE4okYw0QIwkkIQIEYQTzLzPb3PLHvzfnnfH7zrjv3XXnTTXffBlJFlttpxtJdVtttB1ZVBNdZ9FllB8UQ4ckE8YI4wQ8A08Ic4oYwQkgsUgkc0g4j3XTDvxv5LbrjfrvLr3/AL+77770w59UVYdbcZaccVSZeaRZeUcXRQaTdRUbSBOHGLFDNCLJKANIFMCJAICCEIMDIDCIHBDN6x312wxbSR0138+0306yy1x95y3ReeRUeSaaUUUeSecVRUcRUeSSVdefRRLNJJDCMAOCODJCAEPJLOOKLOKPCOBPFJIJKA7x853+XYUQdW+/86y1z1191++bRRbefRYcffcTTQZUbbWXQYWTRbeYYcaeCDIAPCDBNBOPMJBDAGMDGIBKGENLGMAANOLBd93x2wcWecS+b8/9+32wT6/6QRZV5YXfReUbZfRYRWZeadYXYWZQdZSYbMBMFHGKFPADBEIDNIEOABCJLEMICHFAOIIHMLbR5xw4bTRbbWXyzfdb9UXfceYabUSVYeXZUdRbXcQSTZSecZbQZaRSTBDIDFFLPMJHIOFKELLCMNBANOIFIECFAMOIGNOERVccQaefVRTf5/S6VcWWSWWRRcQRUaQcZYVWfWVYeWZVVWaTeeTfbVbLBDJIKHIHJCNECLCBHDCJAKMPNDEDDEDLOEIALPeWZaWYdcfRe0WXf1YTdecbVVcXRabXRSVWaYfbSfaYVXSTVXXTfcfNDECKCKHIHEDKDABFOEMHLNNMAHJMLHCOFLLONNKAdfUZSSeRbbYYccbbbfWdWfUdYabWQTXQQcXWVZYefYeRabbWSZaYfNAGABIIPJDNFMDDOJJGANNCAPIBAFLAAFFJGJIPAESdceRfSaRSabc46cRfXUYeZSSZYaWVWQYZWfbYVeUSaXfUdZeRcQHEJBNEBGLIGIBHNJGDPKHHPIvrEBACJBGNACJGCMDHVZdeXWVeWWRZWUYRdbYTVWUXWaecWXReWWXVabZXZUbZSVQSZeWGBPNJKKGOMMJPDDOLBLNBIHHLssKLACANIIPFFIJFNEVTabWYfRRceeTZbYTfSXZbXfbXYUXfeZRaYfZRfWeYYVWTYUVNJMONOCMCGLEGDDNENHJFDOHBOivigFMLHHIPHMJGKFKAYTfccTZVTeeVUaeZaUfWaURbedRWfQaRYYcfZabZWSRUQeVSYJJIALAKHMIHNBDJIALKlmnvPJMtgnkqtAIoqOAPGEECFgTfadeXRecTYXZdecSQfSWXRQbYXSQbUacdfUaWfWabYWVZRHGGKKJLBPIBFEBLAIIGPpuvipmunovrgkkNjumiuJnijPEBZRbRWYSRZebTRQcZdVefdRcWdaQXfVVcecdZXZQWVUWZZSUEMAHPEKJMHJBNKNBNBFFtgmvjhrhnstjnprivqklupiuJjIaQSTdbaWdWVaWTWXbebcYdaYdRdecaTdRXSbeecQVcdbaKGOODDGGMHGJGJPMLAEFDnorjoskjnkrsoilnrkhhrjgupjmsVZUTUfYSVedXRaeZXXSYXeYdfXeRXRTebQWQYbUVSVYXFPCILNICAIFDLMIGDNHHHoNqqjjnqslkqtoqissgpkspiutgmiXSXfWSQWaVQeUTbdbeadTfVaZbSfWVfZfSSVUXWUHSbMHPNHCHOKHJNNJGIKBFKEOJhhmptptvvskgiggqipthskgojvijZXTWWeVRdZeVVUTbUdSVWcbdQVRXXZZZRbeZXZQVBFDNBBOBCJKLGBHIBBALHJOOIEvomsishsgmtimrsskrkjnstsptphYXSXVedVXTVXWXdXceYfUeXaWXSbRVZebVcQfZLOIFOMJFJKDAOFABMKFOCGHCIGIpvjvtonihvtimnmmksmkhtrjjouuvSdXRffccXSdWVReRafWVbfdXVVWWTcRQSccffOPEEEKOKOILNIBKGMHDNADNBjksKkkpkqklnlvtgonlokjjrumgtqnilsZdUabfbTYfdRUSSZSXVWWbWVdURbXcXYfbecLBNPGLDNPJFFGBDKNKCKFHIDPGokummpmsojqpqtjijqjnjlgmtipiqhkhddbddSXYUcdefQdXTQTUeTVUXfQUfYTSRReCBYBJEBLNPAJJELPGFELEDEEEOmhkrismmpotshkrgpvpkqmqpsnohpigvldedaTQTaXeQeTWWddZUVXSRWWeXdWWUScaAFDHEBDGLINFBGLIOEMHGIICELmjutvmnqjgjsounohrgtkqmtnsrrtvppsiYbeadXZRXXQUZWVRSZRdbbfcfWWQYSbeWREOEBGCMAMNBPPGJAKEHILNPAngtqvtqoptpiupkrlkrjggkksklmrkgmqsgnZVSaXfYUeWSaVRXSTVWTYXfZYUXTWdUSOcMELGHNACBLMCMCPCKJJNIJpCrnvqhvugrorothpvvhoktiokrsksrussujskSReRQWeXVYeeXVaRXZbUfbZeQTeRXTbdFLLFMPKOIPGAPHJEKMMGFAGLKNskstgstppquuvmronvoojvsuousngsvkvjpiQWRSTZYXdTecVUVVXRccWSXdQefTJVcHELGIKLFFMBAELFNFNMNFALCIrDClgvmujmmunrjotsiltsqvhnnoqvsmnssgklHSZVSTfVQfZFMQbfZeXQRbcTWZTAHKBICOFDLLDLGHLIPLBFCFNMLFKCquCllpouirtlpgltvluirsvCEilgmhpttgkluhUXaRaTdXaVWefdVWSWWaWVUfaRYCJEMGNJHHIFFCAIIAOBMBLPGCANJDthsptkhvugojpjjgrivtjjBIMvupgupliklkkkQYebRbXdafeIHMPPMDcWbWfPbPOKPEEJBGKMDMFJMMHNFHOBGILEKNIimollhiolkurhsrjvtvnhmlkrLIMkovguhsNtmsTcdeUQUUcaJSKHICBGETZWbPPLHLNCJOLAKGGPNLOJEFMOAEHJBEONmgggnipvjuorqkqjogrvoouhgqjEAjprlrrjDqliRaXLZddWQTfZFJPOeBESJcOEPELBJJGPEEHPIFGCHOGCFBtHnPFABIFFMhtkjvtoijrnpovtnmolioAKONDmhmioDMKFrqcWVYcQBQebGNHGTSXCBUZGPNGFLKGAONDBJLAAMPOCHOFBtutnrNPFANDqvqumvnovhkjgtqjujhrEPMKmqDvslINKPNtoDHGNZaNNeJJMAOcLIFPECJDKJBHAIHAEHFCAAEONOmEBAglvhknnPLGHKkjjhuhokqkjnnjmilmmCIHPKJBAlDjFINHKAKJNAEHBSQSDOHLPXLNBHNIGBENGPCJDFAGDHODOEFvpOCLDvslmkpnntgunqovvrlrmhrnhllgnhoIEKKCMDDoOKMEOLAAPFFAQMEaEJEMMLCCPLDEIMPOODJNMDPBEFDFFHPGIPBAGDmslgonllmvolmoivinrjurpvqgrkjsH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") !important;
    background-size: auto, auto, auto, cover !important;
    background-position: center center !important;
    background-repeat: no-repeat !important;
  }}

  /* 主窗口：一整块浮起来的玻璃 */
  {_SCOPE} [data-testid="stMain"] {{
    overflow: hidden !important;
    padding: 0 clamp(8px, 1.1vw, 18px) !important;
  }}
  {_SCOPE} [data-testid="stMain"] .block-container {{
    width: min(1060px, calc(100% - clamp(16px, 2vw, 30px))) !important;
    max-width: none !important;
    height: calc(100vh - clamp(24px, 2.6vw, 40px)) !important;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    margin: clamp(10px, 1.2vw, 20px) auto clamp(12px, 1.4vw, 20px) !important;
    padding: clamp(28px, 2.8vw, 42px) clamp(18px, 1.9vw, 34px) clamp(22px, 2vw, 38px) !important;
    border-radius: clamp(20px, 2vw, 34px) !important;
    background:
      url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='g'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23g)' opacity='.05'/%3E%3C/svg%3E") repeat,
      linear-gradient(112deg, rgba(255, 255, 255, .22) 0%, rgba(255, 255, 255, 0) 26%, rgba(255, 255, 255, 0) 62%, rgba(255, 255, 255, .10) 78%, rgba(255, 255, 255, 0) 92%),
      linear-gradient(180deg, rgba(255, 255, 255, .30), rgba(255, 255, 255, .04) 24%, rgba(255, 255, 255, 0) 48%),
      linear-gradient(180deg, rgba(250, 248, 243, .30), rgba(230, 225, 217, .20)) !important;
    box-shadow:
      inset 0 0 0 1px rgba(255, 255, 255, .50),
      inset 0 1.5px 0 rgba(255, 255, 255, .95),
      inset 0 -1px 0 rgba(255, 255, 255, .45),
      inset 0 -40px 70px rgba(120, 104, 86, .07),
      0 2px 6px rgba(45, 38, 32, .14),
      0 44px 96px rgba(45, 38, 32, .38) !important;
    backdrop-filter: blur(34px) saturate(1.45) brightness(1.06) !important;
    -webkit-backdrop-filter: blur(34px) saturate(1.45) brightness(1.06) !important;
    scrollbar-width: none;
  }}
  {_SCOPE} [data-testid="stMain"] .block-container::-webkit-scrollbar {{ width: 0; height: 0; }}

  /* 侧栏：同材质的竖排玻璃条 */
  {_SIDEBAR} {{
    margin: clamp(10px, 1.2vw, 20px) 0 clamp(12px, 1.4vw, 20px) clamp(10px, 1.2vw, 20px) !important;
    border-right: none !important;
    border-radius: clamp(18px, 1.8vw, 26px) !important;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, .34), rgba(255, 255, 255, .04) 30%, rgba(255, 255, 255, 0) 52%),
      linear-gradient(180deg, rgba(250, 248, 243, .44), rgba(234, 229, 221, .34)) !important;
    box-shadow:
      inset 0 0 0 1px rgba(255, 255, 255, .48),
      inset 0 1.5px 0 rgba(255, 255, 255, .92),
      inset 0 -1px 0 rgba(255, 255, 255, .40),
      0 2px 5px rgba(45, 38, 32, .12),
      0 26px 60px rgba(45, 38, 32, .30) !important;
    backdrop-filter: blur(30px) saturate(1.35) brightness(1.04) !important;
    -webkit-backdrop-filter: blur(30px) saturate(1.35) brightness(1.04) !important;
    overflow: hidden;
  }}

  /* 卡片容器：更薄的一层玻璃，比窗口亮一档，靠亮度差分层 */
  {_SCOPE} [data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"] {{
    background:
      linear-gradient(180deg, rgba(255, 255, 255, .42), rgba(255, 255, 255, .06) 30%, rgba(255, 255, 255, 0) 60%),
      rgba(255, 255, 255, .26) !important;
    border: 1px solid rgba(255, 255, 255, .52) !important;
    box-shadow:
      inset 0 1.5px 0 rgba(255, 255, 255, .9),
      inset 0 -1px 0 rgba(255, 255, 255, .35),
      0 2px 5px rgba(45, 38, 32, .08),
      0 18px 40px rgba(45, 38, 32, .16) !important;
    border-radius: 20px !important;
    backdrop-filter: blur(22px) saturate(1.25) !important;
    -webkit-backdrop-filter: blur(22px) saturate(1.25) !important;
  }}

  /* 顶栏做成胶囊 */
  {_SCOPE} .zg-topbar {{
    border-radius: 999px !important;
    border: 1px solid rgba(255, 255, 255, .48) !important;
    background:
      linear-gradient(180deg, rgba(255, 255, 255, .38), rgba(255, 255, 255, .04) 55%, rgba(255, 255, 255, 0)),
      rgba(255, 255, 255, .16) !important;
    box-shadow:
      inset 0 1.5px 0 rgba(255, 255, 255, .9),
      inset 0 -1px 0 rgba(255, 255, 255, .30),
      0 2px 4px rgba(45, 38, 32, .08),
      0 14px 30px rgba(45, 38, 32, .16) !important;
    backdrop-filter: blur(24px) saturate(1.3) !important;
    -webkit-backdrop-filter: blur(24px) saturate(1.3) !important;
  }}

  /* 输入类控件换冷白玻璃，免得在灰石墙前发黄 */
  {_SCOPE} [data-testid="stTextInputRootElement"],
  {_SCOPE} [data-baseweb="input"],
  {_SCOPE} [data-testid="stTextAreaRootElement"] > div {{
    background: rgba(255, 255, 255, .62) !important;
    border: 1px solid rgba(255, 255, 255, .72) !important;
    box-shadow:
      inset 0 1px 0 rgba(255, 255, 255, .9),
      0 6px 16px rgba(48, 41, 34, .08) !important;
  }}

  /* 页面里的暖奶油卡片统一降一档温度，跟石墙同族 */
  {_SCOPE} .zg-home-masthead,
  {_SCOPE} .zg-rail,
  {_SCOPE} .zg-statstrip {{
    background:
      linear-gradient(180deg, rgba(255, 255, 255, .40), rgba(255, 255, 255, .05) 32%, rgba(255, 255, 255, 0) 60%),
      rgba(255, 255, 255, .22) !important;
    border-color: rgba(255, 255, 255, .50) !important;
    box-shadow:
      inset 0 1.5px 0 rgba(255, 255, 255, .9),
      inset 0 -1px 0 rgba(255, 255, 255, .32),
      0 2px 5px rgba(45, 38, 32, .08),
      0 20px 44px rgba(45, 38, 32, .16) !important;
    backdrop-filter: blur(22px) saturate(1.25) !important;
    -webkit-backdrop-filter: blur(22px) saturate(1.25) !important;
  }}
  /* 侧栏内容多时自己滚，别被 overflow:hidden 截掉 */
  {_SIDEBAR} {{
    overflow-y: auto !important;
    scrollbar-width: none;
  }}
  {_SIDEBAR}::-webkit-scrollbar {{ width: 0; height: 0; }}

  /* 窄屏：顶栏会折行，胶囊形状就不成立了，退回圆角矩形 */
  @media (max-width: 900px) {{
    {_SCOPE} .zg-topbar {{ border-radius: 18px !important; }}
    {_SCOPE} [data-testid="stMain"] .block-container {{
      padding: 24px 16px 26px !important;
      height: calc(100vh - 16px) !important;
    }}
  }}

</style>
"""


def inject() -> None:
    """只在登录后的后台注入；登录页不调用。"""
    st.markdown(_STYLES, unsafe_allow_html=True)

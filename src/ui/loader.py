"""载入态：三颗小球轮流弹跳。

动效来自 Uiverse 的 `grumpy-turtle-41`（作者 mobinkakei，MIT）：三颗球在
15% / 45% / 右侧 15% 的位置，间隔 0.2s 交替起落，落下时压扁、影子跟着缩小。
原版是白球配黑投影，给浅色底用的；这里换成品牌金 + 暖色投影，深浅两种底都能看。

登录过场（`pages/login.py`）和页面内的耗时操作（智能分析、AI 问答）共用这一份
CSS 和结构，避免同一套动效在两处各写一遍、改一处忘一处。

用法：

    from src.ui.loader import loading

    with loading("正在解析需求…"):
        result = run_something_slow()
"""

from __future__ import annotations

import contextlib
import html

import streamlit as st

#: 球和影子的关键帧 + 结构样式。放这里而不是各页面里，登录过场直接拼进自己的 <style>。
LOADER_CSS = """
  @keyframes zgLoaderBounce {
    0%   { top: 82px; height: 8px; border-radius: 50px 50px 28px 28px; transform: scaleX(1.6); }
    40%  { height: 32px; border-radius: 50%; transform: scaleX(1); }
    100% { top: 0; }
  }
  @keyframes zgLoaderShadow {
    0%   { transform: scaleX(1.5); }
    40%  { transform: scaleX(1); opacity: .78; }
    100% { transform: scaleX(.2); opacity: .36; }
  }
  .zg-loader {
    position: relative;
    width: 320px; height: 108px;
    margin: 0 auto;
    z-index: 1;
  }
  .zg-loader span { position: absolute; display: block; }
  /* 三颗球：位置和延迟照原版（15% / 45% / 右 15%，各错开 0.1s~0.3s） */
  .zg-loader .zg-loader-dot {
    left: 15%;
    width: 32px; height: 32px;
    border-radius: 50%;
    background: linear-gradient(180deg, #EDCB92, #C0812B);
    box-shadow: 0 0 22px rgba(201, 154, 74, .38);
    transform-origin: 50%;
    animation: zgLoaderBounce .5s alternate infinite ease;
  }
  .zg-loader .zg-loader-dot:nth-child(2) { left: 45%; animation-delay: .2s; }
  .zg-loader .zg-loader-dot:nth-child(3) { left: auto; right: 15%; animation-delay: .3s; }
  /* 三块投影：跟着球缩放，落下时最大最实 */
  .zg-loader .zg-loader-shadow {
    top: 96px; left: 15%;
    width: 32px; height: 6px;
    border-radius: 50%;
    background: rgba(169, 119, 46, .55);
    filter: blur(3px);
    transform-origin: 50%;
    z-index: -1;
    animation: zgLoaderShadow .5s alternate infinite ease;
  }
  .zg-loader .zg-loader-shadow:nth-child(5) { left: 45%; animation-delay: .2s; }
  .zg-loader .zg-loader-shadow:nth-child(6) { left: auto; right: 15%; animation-delay: .3s; }
"""

#: 全屏载入幕布。浅色纸底 + 轻微模糊，盖住半成品页面；`cursor: progress` 给出等待感。
OVERLAY_CSS = """
  @keyframes zgLoadingFade { from { opacity: 0; } to { opacity: 1; } }
  .zg-loading-overlay {
    position: fixed; inset: 0; z-index: 2147483000;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 4px;
    background: rgba(245, 243, 238, .90);
    -webkit-backdrop-filter: blur(7px) saturate(115%);
    backdrop-filter: blur(7px) saturate(115%);
    cursor: progress;
    /* 延迟 0.22s 再出现：快操作（本地筛选、切页）不会闪一下白幕 */
    animation: zgLoadingFade .18s ease .22s both;
  }
  .zg-loading-label {
    font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 12px; letter-spacing: .18em;
    color: #6F6A5E;
  }
  /* 系统开启「减少动态效果」时停在静止状态，靠文字说明进度 */
  @media (prefers-reduced-motion: reduce) {
    .zg-loader .zg-loader-dot { animation: none !important; top: 18px; }
    .zg-loader .zg-loader-shadow { animation: none !important; opacity: .5; }
    .zg-loading-overlay { animation: none !important; }
  }
"""


def loader_markup() -> str:
    """三颗球 + 三块影子的结构，和 LOADER_CSS 里的 nth-child 一一对应。"""
    dots = "".join('<span class="zg-loader-dot"></span>' for _ in range(3))
    shadows = "".join('<span class="zg-loader-shadow"></span>' for _ in range(3))
    return f'<div class="zg-loader" aria-hidden="true">{dots}{shadows}</div>'


def overlay_html(label: str = "正在载入…") -> str:
    """全屏载入层。**每次都要把样式一起发**：Streamlit 不保证上一次的 <style> 还在。"""
    return (
        f"<style>{LOADER_CSS}{OVERLAY_CSS}</style>"
        f'<div class="zg-loading-overlay" role="status" aria-live="polite">'
        f"{loader_markup()}"
        f'<div class="zg-loading-label">{html.escape(label)}</div>'
        f"</div>"
    )


@contextlib.contextmanager
def loading(label: str = "正在载入…"):
    """在耗时操作期间铺一层载入幕布，结束时收掉。

    Streamlit 会立刻把 `st.markdown` 的增量推给前端，所以幕布在阻塞调用
    开始之前就能出现——和 `st.spinner` 的时序一致，只是换成自家的动效。
    """
    slot = st.empty()
    slot.markdown(overlay_html(label), unsafe_allow_html=True)
    try:
        yield
    finally:
        slot.empty()

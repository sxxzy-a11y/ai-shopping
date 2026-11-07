"""Vue 版浏览器真人验证（L0）：登录 → 分析 → 12 页面巡检 → 手机视口。

前置：后端已启动并托管前端（`npm --prefix frontend run build` 后再 `python backend/run.py`），
并安装 Playwright（`pip install -r requirements-dev.txt`）。

    $env:ZHIGOU_SMOKE_PASSWORD = "管理员密码"
    python scripts/vue_browser_check.py

可覆盖：`ZHIGOU_BASE_URL`、`ZHIGOU_SMOKE_USER`、`ZHIGOU_BROWSER_CHANNEL`
（默认 msedge，复用系统 Edge；设为空字符串则用 Playwright 自带 Chromium）。
截图写入 `.tmp/shots/vue/`（已 gitignore）。退出码：0 = 全通过；1 = 有失败；2 = 缺少凭据。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.getenv("ZHIGOU_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USER = os.getenv("ZHIGOU_SMOKE_USER", "admin")
PASSWORD = os.getenv("ZHIGOU_SMOKE_PASSWORD", "")
CHANNEL = os.getenv("ZHIGOU_BROWSER_CHANNEL", "msedge") or None
ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / ".tmp" / "shots" / "vue"

PAGES = [
    "首页",
    "智能分析",
    "商品比较",
    "AI 问答",
    "历史记录",
    "商品维护",
    "知识库管理",
    "全站概览",
    "用户管理",
    "效果评测",
    "个人设置",
    "关于",
]
ERROR_HINTS = (
    "Uncaught",
    "TypeError",
    "ReferenceError",
    "is not a function",
    "Failed to fetch",
)

# 旧版能力搬到 Vue 后的界面标记；缺失即视为该能力没接上。
FEATURES: dict[str, str] = {
    "智能分析": "开始分析",
    "AI 问答": "Ctrl + Enter 快速提交",
    "历史记录": "我的收藏",
    "商品维护": "新增商品",
    "知识库管理": "检索效果检查",
    "全站概览": "全站分析记录",
    "用户管理": "新建账号",
    "个人设置": "测试对话连接",
}


def main() -> int:
    if not PASSWORD:
        print(
            "请先设置环境变量 ZHIGOU_SMOKE_PASSWORD（演示账号密码），本脚本不内置任何凭据。"
        )
        return 2

    SHOTS.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    results: list[tuple[str, int, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel=CHANNEL)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on(
            "console",
            lambda m: (
                console_errors.append(m.text)
                if m.type == "error" and any(h in m.text for h in ERROR_HINTS)
                else None
            ),
        )

        page.goto(BASE, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(1_500)
        page.screenshot(path=str(SHOTS / "00-login.png"))

        page.locator("#username").fill(USER)
        page.locator("#password").fill(PASSWORD)
        page.get_by_role("button", name="登录").click()
        page.get_by_text("选购工作台").wait_for(state="visible", timeout=20_000)
        page.wait_for_timeout(1_000)
        page.screenshot(path=str(SHOTS / "01-home.png"))
        results.append(("登录 → 首页", len(page.inner_text("body")), "OK"))

        # 核心链路：填需求 → 指定品类与预算 → 出首选方案
        page.locator("aside").get_by_role("link", name="智能分析").click()
        page.wait_for_timeout(800)
        page.locator("#demand").fill("5000 元以内，主要写代码，需要便携，14 寸左右")
        if page.locator("#cat option").count() > 1:
            page.locator("#cat").select_option(index=1)
        page.locator("#budget").fill("5000")
        page.get_by_role("button", name="开始分析").click()

        try:
            page.get_by_text("首选方案").wait_for(state="visible", timeout=60_000)
            body = page.inner_text("body")
            results.append(
                ("分析 → 首选方案", len(body), "OK" if "首选方案" in body else "EMPTY")
            )
        except Exception:  # noqa: BLE001 - 巡检要把失败报成一句话
            body = page.inner_text("body")
            results.append(
                ("分析 → 首选方案", len(body), "FAIL: 未出现结果 | " + body[:180])
            )
        page.screenshot(path=str(SHOTS / "02-analysis-result.png"), full_page=True)

        for index, name in enumerate(PAGES, start=3):
            try:
                # 侧栏内定位，避免与首页卡片「前往智能分析」等链接同名冲突
                page.locator("aside").get_by_role("link", name=name).first.click()
                page.wait_for_timeout(1_100)
                body = page.inner_text("body")
                length = len(body.strip())
                page.screenshot(path=str(SHOTS / f"{index:02d}-{name}.png"))
                marker = FEATURES.get(name)
                if marker and marker not in body:
                    results.append((name, length, f"FAIL: 缺少功能标记「{marker}」"))
                else:
                    results.append((name, length, "OK" if length > 80 else "EMPTY?"))
            except Exception as exc:  # noqa: BLE001
                results.append((name, 0, f"FAIL: {type(exc).__name__}"))

        mobile = browser.new_page(viewport={"width": 375, "height": 812})
        mobile.goto(BASE, wait_until="domcontentloaded", timeout=60_000)
        mobile.wait_for_timeout(1_500)
        width = mobile.evaluate("document.body.scrollWidth")
        mobile.screenshot(path=str(SHOTS / "20-mobile-login.png"))
        results.append(
            ("375px 登录页", width, "OK" if width <= 420 else f"横向溢出 {width}px")
        )
        mobile.close()
        browser.close()

    print(f"{'检查项':<20} {'内容长度':>8}  状态")
    for name, length, status in results:
        print(f"{name:<20} {length:>8}  {status}")
    print(f"\n控制台致命错误: {len(console_errors)}")
    for text in console_errors[:6]:
        print(f"  · {text[:160]}")
    print(f"\n截图目录: {SHOTS}")

    failed = [r for r in results if not r[2].startswith("OK")]
    return 1 if failed or console_errors else 0


if __name__ == "__main__":
    sys.exit(main())

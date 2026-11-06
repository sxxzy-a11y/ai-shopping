"""真实浏览器冒烟断言。

为什么需要它：`tests/` 里的 1098 条用例全部跑在 Streamlit 的 AppTest 里，
它验证的是 session_state 与组件树，**不渲染真实 DOM**。登录页曾两次出现
「重影 / 错位」，`backend_theme.py` 又依赖 `:has()` 选择器——这类问题只有
真实浏览器能发现。

这个脚本只做冒烟：打得开、登录得进、分析出得来、手机视口不塌、控制台不报错。
它不是替代 AppTest，而是补上「有没有渲染出来」这一层。

前置条件：
    pip install -r requirements-dev.txt
    playwright install chromium
    streamlit run app.py          # 另开一个终端，保持运行

用法：
    python submission/smoke_test.py
    python submission/smoke_test.py --url http://localhost:8501 --mobile
    python submission/smoke_test.py --user admin --password <你的密码>

实测（2026-11-07，Windows + 系统 Edge 通道 `msedge`）：桌面与 375px 视口各 4 项断言
全部通过。本地规则模式下「分析」实测约 14 秒，脚本用 45 秒**条件等待**，不赌固定 sleep。

首次使用：优先 `--channel msedge`（Windows 自带 Edge，无需下载）；非 Windows，或想用
Playwright 自带 chromium 时，先 `playwright install chromium`，再传 `--channel ""`。
断言失败也会在 `submission/screenshots/` 留一张全页截图（已 gitignore）。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - 只有没装 Playwright 时走到
    print(
        "未安装 Playwright：pip install -r requirements-dev.txt && playwright install chromium"
    )
    raise SystemExit(2)

SHOTS = Path(__file__).resolve().parent / "screenshots"
#: 控制台里不该出现的错误特征。Streamlit 自身偶发无关警告，只挡硬错误。
CONSOLE_ERROR_HINTS = (
    "Uncaught",
    "TypeError",
    "ReferenceError",
    "is not a function",
)


def _check(condition: bool, message: str, failures: list[str]) -> None:
    if condition:
        print(f"  OK   {message}")
    else:
        print(f"  FAIL {message}")
        failures.append(message)


def run(url: str, user: str, password: str, mobile: bool, channel: str | None) -> int:
    failures: list[str] = []
    console_errors: list[str] = []
    SHOTS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True, channel=channel)
        except Exception as exc:  # noqa: BLE001 - 启动失败要给出可操作的提示
            print(f"启动浏览器失败（channel={channel or '自带 chromium'}）：{exc}")
            print("提示：Windows 可用 --channel msedge 复用系统 Edge；")
            print("      或先执行 playwright install chromium 再留空 --channel。")
            return 2
        viewport = (
            {"width": 375, "height": 812} if mobile else {"width": 1440, "height": 900}
        )
        page = browser.new_page(viewport=viewport)
        page.on(
            "console",
            lambda message: (
                console_errors.append(message.text)
                if message.type == "error"
                and any(hint in message.text for hint in CONSOLE_ERROR_HINTS)
                else None
            ),
        )

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(3_000)
            _check(
                page.locator("input").count() >= 2,
                "登录页出现账号与密码输入框",
                failures,
            )

            page.locator("input").nth(0).fill(user)
            page.locator("input").nth(1).fill(password)
            page.locator("button").nth(1).click()
            page.wait_for_timeout(4_000)
            _check(
                page.get_by_role("button", name="智能分析").count() > 0,
                "登录成功并出现侧栏导航",
                failures,
            )

            if not mobile:
                page.get_by_role("button", name="智能分析").click()
                page.wait_for_timeout(1_500)
                page.locator("textarea").first.fill("2000 元以内的手机，主要拍照")
                page.get_by_role("button", name="开始分析", exact=True).click()
                # 本地规则模式下分析实测约 14 秒；用条件等待，不用固定 sleep 赌时间。
                rendered = True
                try:
                    page.get_by_text("首选方案").first.wait_for(
                        state="visible", timeout=45_000
                    )
                except Exception:  # noqa: BLE001 - 超时即视为未渲染
                    rendered = False
                _check(rendered, "分析完成并渲染出首选方案", failures)
            else:
                # 手机视口只验证不塌：正文容器有宽度、没有横向溢出。
                width = page.evaluate("document.body.scrollWidth")
                _check(width <= 420, "375px 视口无横向溢出", failures)
                page.screenshot(path=str(SHOTS / "smoke-mobile.png"), full_page=False)
        except Exception as exc:  # noqa: BLE001 - 冒烟脚本要把任何失败都报成一句话
            failures.append(f"执行中断：{type(exc).__name__}: {exc}")
            try:
                page.screenshot(path=str(SHOTS / "smoke-failure.png"), full_page=False)
            except Exception:  # noqa: BLE001
                pass
        finally:
            _check(not console_errors, "控制台无致命错误", failures)
            if console_errors:
                for text in console_errors[:3]:
                    print(f"       {text[:160]}")
            if failures:
                # 断言失败也要留证据；只在异常分支截图会漏掉「判断错了」这类失败。
                try:
                    shot = SHOTS / "smoke-failure.png"
                    page.screenshot(path=str(shot), full_page=True)
                    print(f"       失败截图：{shot}")
                except Exception:  # noqa: BLE001 - 截图失败不该盖掉真正的失败
                    pass
            browser.close()

    if failures:
        print(f"\n冒烟未通过（{len(failures)} 项）：")
        for item in failures:
            print(f"  · {item}")
        return 1

    print("\n冒烟通过。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="真实浏览器冒烟断言")
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--user", default=os.environ.get("ZHIGOU_DEMO_USER", "admin"))
    parser.add_argument(
        "--password", default=os.environ.get("ZHIGOU_DEMO_PASSWORD", "12345678")
    )
    parser.add_argument("--mobile", action="store_true", help="按 375px 手机视口跑")
    parser.add_argument(
        "--channel",
        default="msedge",
        help="浏览器通道：msedge（默认，复用系统 Edge）/ chrome / 留空用自带 chromium",
    )
    args = parser.parse_args(argv)

    return run(args.url, args.user, args.password, args.mobile, args.channel or None)


if __name__ == "__main__":
    raise SystemExit(main())

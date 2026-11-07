"""Vue 版 API 冒烟：真实 HTTP 调用，覆盖成功与拒绝两态。

前置：后端已启动（`python backend/run.py`），并设置演示账号密码。

    $env:ZHIGOU_SMOKE_PASSWORD = "管理员密码"
    python scripts/api_smoke.py

可覆盖：`ZHIGOU_BASE_URL`（默认 http://127.0.0.1:8000）、`ZHIGOU_SMOKE_USER`（默认 admin）。
退出码：0 = 全部符合预期；1 = 有用例不符合预期；2 = 缺少凭据。
"""

from __future__ import annotations

import os
import sys

import httpx

BASE = os.getenv("ZHIGOU_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USER = os.getenv("ZHIGOU_SMOKE_USER", "admin")
PASSWORD = os.getenv("ZHIGOU_SMOKE_PASSWORD", "")

results: list[tuple[str, int, int, str]] = []


def check(name: str, response: httpx.Response, expected: int, note: str = "") -> None:
    ok = response.status_code == expected
    try:
        snippet = str(response.json())[:110]
    except ValueError:
        snippet = response.text[:110]
    status = "OK" if ok else f"FAIL {snippet}"
    results.append(
        (name, response.status_code, expected, f"{status} | {note}" if note else status)
    )


def main() -> int:
    if not PASSWORD:
        print(
            "请先设置环境变量 ZHIGOU_SMOKE_PASSWORD（演示账号密码），本脚本不内置任何凭据。"
        )
        return 2

    with httpx.Client(base_url=BASE, timeout=60.0) as client:
        check("health", client.get("/api/health"), 200)
        check("未登录访问 meta", client.get("/api/meta"), 401)
        check(
            "错误密码登录",
            client.post(
                "/api/auth/login", json={"username": USER, "password": "wrong-pass"}
            ),
            401,
        )

        login = client.post(
            "/api/auth/login", json={"username": USER, "password": PASSWORD}
        )
        check("正确密码登录", login, 200)
        if login.status_code != 200:
            print("登录失败，后续用例无法继续。")
            return 1

        check("me", client.get("/api/auth/me"), 200)
        meta = client.get("/api/meta")
        check("meta", meta, 200)
        products = client.get("/api/products")
        check(
            "products",
            products,
            200,
            f"商品数={products.json().get('total')}"
            if products.status_code == 200
            else "",
        )

        analysis = client.post(
            "/api/analysis",
            json={"text": "5000 元以内，主要写代码，需要便携，14 寸左右"},
        )
        check("analysis 正常", analysis, 200)
        check("analysis 空输入", client.post("/api/analysis", json={"text": ""}), 400)

        if products.status_code == 200:
            ids = [p["id"] for p in products.json()["products"][:2]]
            check(
                "compare 两件",
                client.post("/api/compare", json={"product_ids": ids}),
                200,
            )
        check(
            "compare 不足两件",
            client.post("/api/compare", json={"product_ids": ["x"]}),
            400,
        )

        check(
            "qa", client.post("/api/qa", json={"question": "适合写代码的轻薄本"}), 200
        )
        check("qa 空问题", client.post("/api/qa", json={"question": ""}), 422)
        check("history", client.get("/api/history"), 200)
        check("preferences", client.get("/api/preferences"), 200)
        check("admin/overview", client.get("/api/admin/overview"), 200)
        check("eval", client.get("/api/eval"), 200)
        check("about", client.get("/api/about"), 200)
        check("logout", client.post("/api/auth/logout"), 200)
        check("登出后访问 meta", client.get("/api/meta"), 401)

    print(f"{'用例':<22} {'实际':>5} {'预期':>5}  结果")
    for name, actual, expected, note in results:
        print(f"{name:<22} {actual:>5} {expected:>5}  {note}")
    failed = [r for r in results if not r[3].startswith("OK")]
    print(f"\n通过 {len(results) - len(failed)}/{len(results)}，失败 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

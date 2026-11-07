"""管理员 API 写操作冒烟 —— **只在临时库实例上运行**。

本脚本会创建/修改/删除商品、账号、知识文档和 API 配置。
为防误伤真实数据，**必须显式指定临时实例地址**，没有默认值：

    $env:ZHIGOU_SMOKE_BASE_URL = "http://127.0.0.1:8001"
    $env:ZHIGOU_SMOKE_PASSWORD = "临时库管理员密码"
    python scripts/admin_api_smoke.py

临时实例的启动方式见 `docs/VUE_MIGRATION.md`。退出码：0 全通过 / 1 有失败 / 2 缺少配置。
"""

from __future__ import annotations

import os
import sys

import httpx

BASE = os.getenv("ZHIGOU_SMOKE_BASE_URL", "").rstrip("/")
USER = os.getenv("ZHIGOU_SMOKE_USER", "admin")
PASSWORD = os.getenv("ZHIGOU_SMOKE_PASSWORD", "")

results: list[tuple[str, int, int, str]] = []


def check(name: str, response: httpx.Response, expected: int, note: str = "") -> None:
    ok = response.status_code == expected
    try:
        snippet = str(response.json())[:120]
    except ValueError:
        snippet = response.text[:120]
    status = "OK" if ok else f"FAIL {snippet}"
    results.append(
        (name, response.status_code, expected, f"{status} | {note}" if note else status)
    )


def main() -> int:
    if not BASE or not PASSWORD:
        print("必须设置 ZHIGOU_SMOKE_BASE_URL（临时实例）与 ZHIGOU_SMOKE_PASSWORD；")
        print("本脚本会写入数据，拒绝在默认地址上运行。")
        return 2

    with httpx.Client(base_url=BASE, timeout=90.0) as client:
        check("未登录访问 api-config", client.get("/api/admin/api-config"), 401)
        login = client.post(
            "/api/auth/login", json={"username": USER, "password": PASSWORD}
        )
        check("登录", login, 200)
        if login.status_code != 200:
            return 1

        # --- AI 配置与连接检测 ---
        config_view = client.get("/api/admin/api-config")
        check("读取 API 配置", config_view, 200)
        if config_view.status_code == 200:
            body = config_view.json()
            assert "masked_keys" in body and "configured" in body, "配置结构不完整"
            assert body["values"]["llm_api_key"] != "", "密钥应已掩码或标注未配置"
        check(
            "保存 API 配置",
            client.put("/api/admin/api-config", json={"llm_model": "smoke-test-model"}),
            200,
        )
        check("清除 API 配置", client.delete("/api/admin/api-config"), 200)
        check(
            "AI 连接检测 / 对话模型",
            client.post("/api/admin/api-config/probe/llm", json={}),
            200,
        )
        check(
            "AI 连接检测 / 向量化",
            client.post("/api/admin/api-config/probe/embedding", json={}),
            200,
        )

        # --- 商品 CRUD ---
        check("商品清单", client.get("/api/admin/products"), 200)
        product = {
            "id": "SMOKE-VUE-001",
            "name": "冒烟测试笔记本",
            "brand": "测试品牌",
            "category": "laptop",
            "model": "SMOKE-1",
            "price": "4999",
            "specs": "内存=16GB",
            "use_cases": "编程",
            "pros": "轻便",
            "cons": "无",
        }
        created = client.post("/api/admin/products", json=product)
        check("新增商品", created, 200)
        check(
            "编辑商品",
            client.put(
                "/api/admin/products/SMOKE-VUE-001",
                json={**product, "name": "冒烟测试笔记本（已改）"},
            ),
            200,
        )
        check(
            "停用商品",
            client.put(
                "/api/admin/products/SMOKE-VUE-001/active", json={"is_active": False}
            ),
            200,
        )

        # --- 品类 / 品牌元信息 ---
        check("读取元信息", client.get("/api/admin/catalog-meta"), 200)
        check(
            "修改品类元信息",
            client.put(
                "/api/admin/catalog-meta/category/laptop",
                json={"display_label": "笔记本电脑", "sort_order": 1},
            ),
            200,
        )
        check(
            "修改品牌元信息",
            client.put(
                "/api/admin/catalog-meta/brand/测试品牌",
                json={"display_name": "测试品牌"},
            ),
            200,
        )

        # --- 用户管理 ---
        check("账号清单", client.get("/api/admin/users"), 200)
        check(
            "新建账号",
            client.post(
                "/api/admin/users",
                json={
                    "username": "smokeuser",
                    "password": "smoke-pass-12345",
                    "role": "user",
                },
            ),
            200,
        )
        check(
            "改角色",
            client.put("/api/admin/users/smokeuser/role", json={"role": "admin"}),
            200,
        )
        check(
            "重置密码",
            client.put(
                "/api/admin/users/smokeuser/password",
                json={"password": "new-smoke-pass"},
            ),
            200,
        )
        check(
            "停用账号",
            client.put("/api/admin/users/smokeuser/active", json={"is_active": False}),
            200,
        )
        check("删除账号", client.delete("/api/admin/users/smokeuser"), 200)

        # --- 知识库 ---
        docs = client.get("/api/admin/knowledge/documents")
        check("知识文档清单", docs, 200)
        new_doc = client.post(
            "/api/admin/knowledge/documents",
            json={
                "title": "冒烟测试文档",
                "doc_type": "service",
                "body": "这是一条用于冒烟测试的知识文档。",
            },
        )
        check("新增知识文档", new_doc, 200)
        if new_doc.status_code == 200 and docs.status_code == 200:
            before = {d["doc_id"] for d in docs.json()["documents"]}
            after = {d["doc_id"] for d in new_doc.json()["documents"]}
            added = list(after - before)
            if added:
                check(
                    "删除知识文档",
                    client.delete(f"/api/admin/knowledge/documents/{added[0]}"),
                    200,
                )
        check(
            "知识检索调试",
            client.post(
                "/api/admin/knowledge/retrieve", json={"query": "笔记本多重适合带出门"}
            ),
            200,
        )
        check("重建索引", client.post("/api/admin/knowledge/reindex", json={}), 200)

        # --- 全站记录 ---
        check("全站历史", client.get("/api/admin/analyses"), 200)

        # --- 完整问答链路 / 收藏 ---
        qa = client.post("/api/qa", json={"question": "2000 元以内拍照好的手机"})
        check("AI 问答完整链路", qa, 200)
        if qa.status_code == 200:
            body = qa.json()
            assert "source" in body and "citations" in body, "问答响应缺少来源标注"
        check("收藏清单", client.get("/api/favorites"), 200)
        check(
            "添加收藏",
            client.post("/api/favorites", json={"product_id": "SMOKE-VUE-001"}),
            200,
        )
        check("取消收藏", client.delete("/api/favorites/SMOKE-VUE-001"), 200)

    print(f"{'用例':<24} {'实际':>5} {'预期':>5}  结果")
    for name, actual, expected, note in results:
        print(f"{name:<24} {actual:>5} {expected:>5}  {note}")
    failed = [r for r in results if not r[3].startswith("OK")]
    print(f"\n通过 {len(results) - len(failed)}/{len(results)}，失败 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

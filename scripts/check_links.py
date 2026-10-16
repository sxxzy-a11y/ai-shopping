"""体检商品数据里的外链：图片能不能打开、来源页面还活着吗。

为什么值得单独做一个脚本：`image_url` 与 `source_url` 都是**外链**，
它们不归我们管，随时会失效。而失效是静默的——界面上图片会回落成
类别图标，看着一切正常，只有真去点来源链接的人才会发现指向了 404。
所以要在导入数据之后、演示之前各跑一次。

用法：

    python scripts/check_links.py                 # 体检默认商品库
    python scripts/check_links.py --db storage/products.db
    python scripts/check_links.py --seed data/products.json
    python scripts/check_links.py --proxy socks5://127.0.0.1:10808

默认直连。国内站点（京东图床、中关村在线图床、品牌官网）直连可达；
需要代理时用 `--proxy` 指定，脚本会**先直连、失败了再走代理**重试一次，
免得给本来就通的地址平白绕一圈。

退出码：全部通过 0，有失败 1——可以直接接在别的命令后面。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: 让脚本能直接 `python scripts/check_links.py` 跑起来
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from src import config, product_store  # noqa: E402

TIMEOUT = 12.0
#: 有些图床不认 HEAD，统一用 GET 但只读响应头就把连接关掉。
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}


#: 常见图片格式的文件头。有些图床把 content-type 写成 application/octet-stream，
#: 只看响应头会把这些**能正常显示的图**判成坏链——误报比漏报更费时间。
_MAGIC_NUMBERS: tuple[bytes, ...] = (
    b"\xff\xd8\xff",           # JPEG
    b"\x89PNG\r\n\x1a\n",      # PNG
    b"GIF87a", b"GIF89a",      # GIF
    b"BM",                     # BMP
)


def _looks_like_image(head: bytes) -> bool:
    if head.startswith(_MAGIC_NUMBERS):
        return True
    # WebP / AVIF / HEIC 都是 RIFF 或 ISO-BMFF 容器，靠内部标识判断
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return True
    return head[4:8] == b"ftyp"


def _probe(url: str, *, proxy: str | None = None) -> tuple[int, str, bytes]:
    """请求一个地址，返回 (状态码, content-type, 正文前若干字节)。

    失败时状态码为 0，不抛异常——体检工具不该因为一条坏链就中断。
    只读前几 KB 就断开：这里要判断的是「这是不是一张图」，不是把它下下来。
    """
    try:
        with httpx.Client(
            timeout=TIMEOUT, follow_redirects=True, headers=_HEADERS, proxy=proxy
        ) as client:
            with client.stream("GET", url) as response:
                head = b""
                for chunk in response.iter_bytes():
                    head += chunk
                    if len(head) >= 512:
                        break
                return response.status_code, response.headers.get("content-type", ""), head
    except httpx.HTTPError as exc:
        return 0, f"{type(exc).__name__}", b""


def check(url: str, *, proxy: str | None, expect_image: bool) -> tuple[bool, str]:
    """检查一个地址是否可用。返回 (是否通过, 说明)。

    先直连，失败且有配代理时再走代理重试——顺序很重要：
    国内图床走代理反而可能连不上。
    """
    status, note, head = _probe(url)
    if status == 0 and proxy:
        status, note, head = _probe(url, proxy=proxy)

    if status == 0:
        return False, f"连不上（{note}）"
    if status >= 400:
        return False, f"HTTP {status}"
    if expect_image and "image" not in note.lower() and not _looks_like_image(head):
        # 既不是 image/*，文件头也不是图片——这才多半是防盗链的 HTML 页面
        return False, f"不是图片（content-type: {note or '未知'}）"
    return True, f"HTTP {status}"


def _load_rows(args: argparse.Namespace) -> list[dict]:
    if args.seed:
        raw = json.loads(Path(args.seed).read_text(encoding="utf-8"))
        rows = raw if isinstance(raw, list) else raw.get("products", [])
        return [dict(row) for row in rows]
    path = Path(args.db) if args.db else config.products_db_path()
    return product_store.load_product_records(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="体检商品数据的外链可用性")
    parser.add_argument("--db", help="商品库路径，默认取项目配置")
    parser.add_argument("--seed", help="改为体检种子 JSON 文件")
    parser.add_argument("--proxy", help="直连失败后重试用的代理，如 socks5://127.0.0.1:10808")
    parser.add_argument("--only", choices=("image_url", "source_url"),
                        help="只体检其中一类链接")
    args = parser.parse_args(argv)

    rows = _load_rows(args)
    if not rows:
        print("商品库是空的，没有可体检的链接。", file=sys.stderr)
        return 1

    fields = [args.only] if args.only else ["image_url", "source_url"]

    broken: list[tuple[str, str, str]] = []
    missing: list[tuple[str, str]] = []
    total = 0
    print(f"共 {len(rows)} 条商品，体检 {len(fields)} 类链接……\n")

    for row in rows:
        product_id = str(row.get("id") or "?")
        for field in fields:
            url = str(row.get(field) or "").strip()
            if not url:
                # 没填不等于坏。`source_url` / `image_url` 都可空，
                # 界面与评分都按「缺数据不猜」的既有规则处理，
                # 所以这里只报数量，不当失败——否则「如实留空」反而会让体检不过。
                missing.append((product_id, field))
                continue
            total += 1
            ok, note = check(url, proxy=args.proxy, expect_image=field == "image_url")
            if not ok:
                broken.append((product_id, field, f"{note}  {url[:90]}"))

    print(f"实际请求 {total} 条链接。")
    if missing:
        by_field: dict[str, int] = {}
        for _, field in missing:
            by_field[field] = by_field.get(field, 0) + 1
        detail = "、".join(f"{field} {count} 条" for field, count in sorted(by_field.items()))
        print(f"未填写的链接：{detail}（留空是允许的，不计为失败）")

    if not broken:
        print("已填写的链接全部可用。")
        return 0

    print(f"\n有 {len(broken)} 条链接打不开：\n")
    for product_id, field, note in broken:
        print(f"  [{product_id}] {field}: {note}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

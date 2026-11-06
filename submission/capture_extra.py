# -*- coding: utf-8 -*-
"""Capture rule-mode analysis and populated comparison screenshots."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
import re

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "submission" / "screenshots"

# 演示账号：默认沿用原值以保持脚本行为不变；公开演示时用环境变量覆盖。
DEMO_USER = os.environ.get("ZHIGOU_DEMO_USER", "admin")
DEMO_PASSWORD = os.environ.get("ZHIGOU_DEMO_PASSWORD", "12345678")
SHOTS.mkdir(parents=True, exist_ok=True)
URL = "http://localhost:8501"


def shot(page, name):
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path), full_page=False)
    print("saved", path)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    page.locator("input").nth(0).fill(DEMO_USER)
    page.locator("input").nth(1).fill(DEMO_PASSWORD)
    page.locator("button").nth(1).click()
    page.wait_for_timeout(3000)

    # Rule-mode analysis: the fixed three-round numbers in the deck come from local rules.
    page.get_by_role("button", name=re.compile("智能分析")).click()
    page.wait_for_timeout(1200)
    page.locator("textarea").first.fill(
        "我想买一款 2000 元以内的手机，主要拍照，要拍得好看"
    )
    page.get_by_role("button", name="开始分析", exact=True).click()
    page.wait_for_timeout(8000)
    shot(page, "03-analysis-rule")

    # Populated comparison table: two phones, same category.
    page.get_by_role("button", name=re.compile("商品比较")).click()
    page.wait_for_timeout(1200)
    page.locator('input[aria-label*="商品类别"]').click()
    page.wait_for_timeout(300)
    page.get_by_text("手机", exact=True).last.click()
    page.wait_for_timeout(500)
    picker = page.locator('input[aria-label*="选择要比较的商品"]')
    picker.click()
    page.keyboard.type("真我 GT Neo6 SE")
    page.keyboard.press("Enter")
    page.wait_for_timeout(500)
    picker.click()
    page.keyboard.type("iQOO Z9 Turbo")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1200)
    shot(page, "05-compare-filled")

    browser.close()

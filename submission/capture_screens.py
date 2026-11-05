# -*- coding: utf-8 -*-
"""Capture a few real UI screenshots for the competition deck."""
from pathlib import Path
from playwright.sync_api import sync_playwright
import re

ROOT = Path(r"C:\Users\suchen\Desktop\ai shopping")
SHOTS = ROOT / "submission" / "screenshots"
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
    shot(page, "01-login")

    page.locator("input").nth(0).fill("admin")
    page.locator("input").nth(1).fill("12345678")
    page.locator("button").nth(1).click()
    page.wait_for_timeout(3500)
    shot(page, "02-home")

    page.get_by_role("button", name=re.compile("智能分析")).click()
    page.wait_for_timeout(1500)
    textarea = page.locator("textarea").first
    textarea.fill("我想买一款 2000 元以内的手机，主要拍照，要拍得好看")
    page.get_by_role("button", name="开始分析", exact=True).click()
    page.wait_for_timeout(18000)
    shot(page, "03-analysis")

    page.get_by_role("button", name=re.compile("AI 问答")).click()
    page.wait_for_timeout(1500)
    ai_box = page.locator("textarea").first
    ai_box.fill("2000 元以内手机推荐")
    ai_box.press("Control+Enter")
    page.wait_for_timeout(500)
    page.get_by_role("button", name="提问", exact=True).click()
    page.wait_for_timeout(18000)
    shot(page, "04-ai-qa")

    page.get_by_role("button", name=re.compile("商品比较")).click()
    page.wait_for_timeout(1500)
    shot(page, "05-compare")

    page.get_by_role("button", name=re.compile("知识库管理")).click()
    page.wait_for_timeout(1500)
    shot(page, "06-knowledge")

    browser.close()

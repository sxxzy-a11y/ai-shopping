# -*- coding: utf-8 -*-
from pathlib import Path
from playwright.sync_api import sync_playwright
import re

SHOTS = Path(r"C:\Users\suchen\Desktop\ai shopping") / "submission" / "screenshots"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    page.goto("http://localhost:8501", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    page.locator("input").nth(0).fill("admin")
    page.locator("input").nth(1).fill("12345678")
    page.locator("button").nth(1).click()
    page.wait_for_timeout(3000)

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
    page.wait_for_timeout(500)
    page.keyboard.press("Escape")
    page.mouse.click(1200, 220)
    page.wait_for_timeout(800)
    page.get_by_text("横向比较", exact=True).scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    page.screenshot(path=str(SHOTS / "05-compare-filled.png"), full_page=False)
    print("saved", SHOTS / "05-compare-filled.png")
    browser.close()

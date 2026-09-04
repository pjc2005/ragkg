# -*- coding: utf-8 -*-
"""验证: 点球弹浮层 -> 下一级下钻 / 详情出面板."""
import asyncio, json
from playwright.async_api import async_playwright

URL = "http://127.0.0.1:8123/graph.html"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome",
            args=["--no-sandbox", "--disable-gpu"])
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        logs = []
        page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
        await page.goto(URL, wait_until="load", timeout=40000)
        await page.wait_for_timeout(2000)

        async def st(tag):
            s = await page.evaluate("""() => ({
              nodes: cy.nodes().length,
              menuShown: document.getElementById('nodeMenu').style.display!=='none',
              menuNext: document.getElementById('nmNext').style.display,
              detailShown: document.getElementById('detailPanel').style.display!=='none',
              dpTitle: document.getElementById('dpTitle').textContent,
              dpSnippets: document.getElementById('dpSnippets').childElementCount,
              dpDocs: document.getElementById('dpDocs').childElementCount,
              crumb: document.getElementById('crumb').innerText.replace(/\\n/g,' ')
            })""")
            print(f"[{tag}]", json.dumps(s, ensure_ascii=False))

        # 点顶层第一个球 -> 应弹浮层(有 下一级 + 详情)
        await page.evaluate("()=>{ cy.nodes('.isTop')[0].emit('tap'); }")
        await page.wait_for_timeout(800)
        await st("点顶层球")
        # 点浮层 下一级 -> 下钻
        await page.evaluate("()=>{ menuNext(); }")
        await page.wait_for_timeout(1800)
        await st("下一级下钻后")
        # 点新中心的下钻视图里一个球 -> 弹浮层
        await page.evaluate("()=>{ const c=cy.nodes('.isChild')[0]; if(c)c.emit('tap'); }")
        await page.wait_for_timeout(800)
        await st("点子球")
        # 点浮层 详情 -> 出右侧面板
        await page.evaluate("()=>{ menuDetail(); }")
        await page.wait_for_timeout(1500)
        await st("详情面板")
        print("\n--- pageerrors ---")
        for l in logs:
            print(l)
        await browser.close()


asyncio.run(main())
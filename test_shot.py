"""在真实手机视口渲染 4 页面并截图, 供视觉核对."""
import asyncio
from playwright.async_api import async_playwright

CHROME="<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox","--disable-gpu"])
        c=await b.new_context(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True,
            device_scale_factor=2, user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)")
        for name in ["graph.html","ui.html","index.html"]:
            pg=await c.new_page()
            try:
                await pg.goto("http://127.0.0.1:8123/"+name, wait_until="domcontentloaded", timeout=30000)
                await pg.wait_for_timeout(4500)
                await pg.screenshot(path=f"/tmp/shot_{name}.png", full_page=False)
                print("saved", name)
            except Exception as e:
                print(name,"ERR",str(e)[:120])
            await pg.close()
        # graph 下钻一层的截图
        pg=await c.new_page()
        await pg.goto("http://127.0.0.1:8123/graph.html", wait_until="domcontentloaded", timeout=30000)
        await pg.wait_for_timeout(3500)
        try:
            await pg.evaluate("()=>{ cy.nodes('.isTop')[0].emit('tap'); }")
            await pg.wait_for_timeout(500)
            await pg.evaluate("()=>{ menuNext(); }")
            await pg.wait_for_timeout(2000)
            await pg.screenshot(path="/tmp/shot_graph_drilled.png")
            print("saved drill")
        except Exception as e:
            print("drill ERR",str(e)[:120])
        await b.close()
asyncio.run(main())
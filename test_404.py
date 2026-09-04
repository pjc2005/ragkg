"""确认 404 来源."""
import asyncio
from playwright.async_api import async_playwright
CHROME="<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox","--disable-gpu"])
        c=await b.new_context(viewport={"width":1280,"height":800})
        pg=await c.new_page()
        reqs=[]
        pg.on("response", lambda r: reqs.append(f"{r.status} {r.request.method} {r.url}") if r.status==404 else None)
        await pg.goto("http://127.0.0.1:8123/graph.html", wait_until="domcontentloaded", timeout=40000)
        await pg.wait_for_timeout(4000)
        await pg.evaluate("(id)=>{ loadCenter(id); }", 296)
        await pg.wait_for_timeout(3000)
        print("404 请求:")
        for x in reqs[-15:]: print("  ",x)
        # 抓当前所有 DOM 节点
        nd=await pg.evaluate("""()=>({nodes:cy.nodes().length, 
          parentN: cy.nodes('.isParent').length, childN: cy.nodes('.isChild').length})""")
        print("节点域:", nd)
        await b.close()
asyncio.run(main())
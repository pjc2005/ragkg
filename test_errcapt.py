"""捕获 loadCenter 内部异常."""
import asyncio
from playwright.async_api import async_playwright
CHROME="<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox","--disable-gpu"])
        c=await b.new_context(viewport={"width":1280,"height":800})
        pg=await c.new_page()
        errs=[]
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8123/graph.html", wait_until="domcontentloaded", timeout=40000)
        await pg.wait_for_timeout(4000)
        # 在浏览器里给 window 挂错误钩子, 再调 loadCenter
        await pg.evaluate("""()=>{ window.__errs=[]; window.addEventListener('error',e=>window.__errs.push(String(e.error||e.message))); }""")
        await pg.evaluate("(id)=>{ loadCenter(id); }", 296)
        await pg.wait_for_timeout(3000)
        print("window错误:", await pg.evaluate("()=>window.__errs"))
        print("pageerror:", errs)
        print("节点数:", await pg.evaluate("()=>cy.nodes().length"))
        # 看 place 是否被调用: 检查是否有 isChild 节点
        print("children节点:", await pg.evaluate("()=>cy.nodes('.isChild').length"))
        await b.close()
asyncio.run(main())
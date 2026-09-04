"""检查页面实际加载的 loadCenter 是否为新版."""
import asyncio
from playwright.async_api import async_playwright
CHROME="<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox","--disable-gpu"])
        c=await b.new_context()
        pg=await c.new_page()
        # 直接取静态文件源码
        await pg.goto("http://127.0.0.1:8123/graph.html", wait_until="domcontentloaded", timeout=30000)
        src=await pg.evaluate("()=> document.documentElement.outerHTML.length") 
        # 从页面取的 loadCenter
        fn=await pg.evaluate("()=>{ return loadCenter.toString().slice(0,150); }")
        print("loadCenter 源码开头:", fn)
        hasPlace=await pg.evaluate("()=> loadCenter.toString().includes('place')")
        hasNew=await pg.evaluate("()=> loadCenter.toString().includes('perRow')")
        print("含 place:", hasPlace, "含 perRow(新版):", hasNew)
        await b.close()
asyncio.run(main())
"""移动端竖屏(375x812 iPhone)验证: 主页/图谱/文档/问答 渲染 + 回主页入口."""
import asyncio, json
from playwright.async_api import async_playwright

CHROME = "<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
MOBILE = {"width": 375, "height": 812, "is_mobile": True, "has_touch": True, "device_scale_factor": 3}

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, executable_path=CHROME,
                                    args=["--no-sandbox","--disable-gpu"])
        ctx = await b.new_context(viewport={"width":375,"height":812}, is_mobile=True,
                                  has_touch=True, device_scale_factor=3,
                                  user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)")
        for path in ["/index.html","/graph.html","/doc.html?id=2","/ui.html"]:
            pg = await ctx.new_page()
            errs=[]
            pg.on("pageerror", lambda e: errs.append(str(e)))
            console=[]
            pg.on("console", lambda m: console.append(m.text) if m.type=="error" else None)
            try:
                await pg.goto("http://127.0.0.1:8123"+path, wait_until="domcontentloaded", timeout=30000)
                await pg.wait_for_timeout(4000)
            except Exception as e:
                print(path, "LOADERR", str(e)[:120]); await pg.close(); continue
            innerW = await pg.evaluate("()=>window.innerWidth")
            innerH = await pg.evaluate("()=>window.innerHeight")
            scrollH = await pg.evaluate("()=>document.documentElement.scrollHeight")
            # 找回主页链接
            home = await pg.evaluate("()=>{ const a=document.querySelector('a[href=\"/index.html\"]'); "
                "return a? (a.textContent.trim()||'logo') : null; }")
            # 检查横向溢出(竖屏必须无水平滚动)
            overflow = await pg.evaluate("()=> document.documentElement.scrollWidth > window.innerWidth+1")
            print(f"[{path}] innerW={innerW} innerH={innerH} scrollH={scrollH} "
                  f"回主页={home!r} 横向溢出={overflow} pageerr={len(errs)} consoleErr={len([c for c in console if 'ERR' in c or 'Failed' in c])}")
            await pg.close()
        await b.close()

asyncio.run(main())
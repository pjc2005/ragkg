"""诊断 loadCenter 为何不渲染."""
import asyncio
from playwright.async_api import async_playwright

CHROME="<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox","--disable-gpu"])
        c=await b.new_context(viewport={"width":1280,"height":800})
        pg=await c.new_page()
        console=[]
        pg.on("console", lambda m: console.append(f"{m.type}: {m.text}") if m.type in("error","warning") else None)
        await pg.goto("http://127.0.0.1:8123/graph.html", wait_until="domcontentloaded", timeout=40000)
        await pg.wait_for_timeout(4000)
        # 直接调 loadCenter 并捕获
        await pg.evaluate("async (id)=>{ try{ await new Promise(r=>{ loadCenter(id); setTimeout(r,2500); }); window.__after=cy.nodes().length; window.__nb=typeof nb; }catch(e){ window.__err=String(e); } }", 296)
        await pg.wait_for_timeout(3000)
        print("节点数:", await pg.evaluate("()=>window.__after"))
        print("err:", await pg.evaluate("()=>window.__err||'none'"))
        print("console(错误):")
        for x in console[-10:]: print("  ",x)
        # 手动 fetch 测试
        net = await pg.evaluate("async ()=>{ try{ const r=await fetch('/graph/node/296'); const d=await r.json(); return {ok:r.ok, total:(d.children?d.children.length:0)}; }catch(e){ return 'ERR '+e; } }")
        print("manual fetch:", net)
        await b.close()
asyncio.run(main())
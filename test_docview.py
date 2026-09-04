"""端到端验证: doc.html 渲染页 + 图谱详情来源文档点击跳转."""
import asyncio, json
from playwright.async_api import async_playwright

CHROME = "<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True, executable_path=CHROME,
                                    args=["--no-sandbox","--disable-gpu"])
        # 1) doc.html md 渲染
        pg = await b.new_page(viewport={"width":1280,"height":800})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("http://127.0.0.1:8123/doc.html?id=3", wait_until="load", timeout=40000)
        await pg.wait_for_timeout(800)
        h1 = await pg.evaluate("()=>document.getElementById('title').textContent")
        hasMd = await pg.evaluate("()=>!!document.getElementById('bodyMd')")
        hasRaw = await pg.evaluate("()=>document.getElementById('rawLink').style.display!=='none'")
        bodyHtml = await pg.evaluate("()=>document.getElementById('wrap').innerHTML.length")
        print("[doc.html?3]", json.dumps({"h1":h1,"mdRendered":hasMd,"rawLink":hasRaw,"wrapLen":bodyHtml}, ensure_ascii=False))
        # renderMd 是否处理了标题(有 <h1>)
        hCount = await pg.evaluate("()=>document.querySelectorAll('#bodyMd h1').length")
        codeCount = await pg.evaluate("()=>document.querySelectorAll('#bodyMd code').length")
        print("[doc.md结构]", "h1:",hCount," inlineCode:",codeCount)

        # 2) graph.html 详情面板 -> 来源文档点击 -> 新标签
        pg2 = await b.new_page(viewport={"width":1280,"height":800})
        errs2 = []
        pg2.on("pageerror", lambda e: errs2.append(str(e)))
        await pg2.goto("http://127.0.0.1:8123/graph.html", wait_until="load", timeout=40000)
        await pg2.wait_for_timeout(1500)
        # 点顶层球 -> 下一级 -> 点某个球 -> 详情
        await pg2.evaluate("()=>{ cy.nodes('.isTop')[0].emit('tap'); }")
        await pg2.wait_for_timeout(600)
        await pg2.evaluate("()=>{ menuNext(); }")
        await pg2.wait_for_timeout(1500)
        await pg2.evaluate("()=>{ const c=cy.nodes('.isChild')[0]; if(c)c.emit('tap'); }")
        await pg2.wait_for_timeout(500)
        await pg2.evaluate("()=>{ menuDetail(); }")
        await pg2.wait_for_timeout(1500)
        docs_n = await pg2.evaluate("()=>document.getElementById('dpDocs').childElementCount")
        print("[详情面板] 来源文档数:", docs_n)
        if docs_n>0:
            # 记录当前标签数, 点击第一个来源文档
            before = len(pg2.context.pages)
            await pg2.evaluate("()=>{ document.querySelector('#dpDocs .doc-row').click(); }")
            await pg2.wait_for_timeout(2000)
            after = len(pg2.context.pages)
            print("[跳转] 标签页", before,"->",after)
            if after>before:
                newp = pg2.context.pages[-1]
                url = newp.url
                ttl = await newp.title()
                print("[新标签]", json.dumps({"url":url,"title":ttl}, ensure_ascii=False))
        print("[pageerrors doc]", errs)
        print("[pageerrors graph]", errs2)
        await b.close()

asyncio.run(main())
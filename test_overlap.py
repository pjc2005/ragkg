"""测量下钻视图节点重叠情况."""
import asyncio, json
from playwright.async_api import async_playwright

CHROME="<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox","--disable-gpu"])
        c=await b.new_context(viewport={"width":1280,"height":800})
        pg=await c.new_page()
        pg.on("pageerror", lambda e: print("PAGEERR", e))
        await pg.goto("http://127.0.0.1:8123/graph.html", wait_until="domcontentloaded", timeout=40000)
        await pg.wait_for_timeout(4000)
        # 顶层第一个球(度数最高)
        await pg.evaluate("()=>{ cy.nodes('.isTop')[0].emit('tap'); }")
        await pg.wait_for_timeout(500)
        await pg.evaluate("()=>{ menuNext(); }")
        await pg.wait_for_timeout(2000)
        info = await pg.evaluate("""()=>({
          totalNodes: cy.nodes().length,
          parentN: cy.nodes('.isParent').length,
          childN: cy.nodes('.isChild').length,
          // 计算所有节点对的中心距离, 找重叠(<节点直径)
          positions: cy.nodes().map(n=>({id:n.id(), x:n.position('x'), y:n.position('y')}))
        })""")
        poss=info['positions']
        # 节点尺寸 max 52, 重叠判据: 中心距 < 45
        overlaps=[]
        for i in range(len(poss)):
            for j in range(i+1,len(poss)):
                a,b=poss[i],poss[j]
                d=((a['x']-b['x'])**2+(a['y']-b['y'])**2)**0.5
                if d<45: overlaps.append((a['id'],b['id'],round(d,1)))
        print("总节点:",info['totalNodes'],"父:",info['parentN'],"子:",info['childN'])
        print("重叠对数(中心距<45):",len(overlaps))
        for o in overlaps[:15]: print("  ",o)
        await pg.screenshot(path="/tmp/shot_overlap.png")
        await b.close()
asyncio.run(main())
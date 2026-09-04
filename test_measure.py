"""精确测量移动端各页面关键元素包围盒, 检测重叠/溢出."""
import asyncio, json
from playwright.async_api import async_playwright

CHROME="<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

async def boxes(pg, ids):
    return await pg.evaluate("""(ids)=>{const r={};for(const i of ids){const el=document.getElementById(i)||document.querySelector(i);
        if(!el){r[i]=null;continue;}const b=el.getBoundingClientRect();r[i]={x:b.x,y:b.y,w:b.width,h:b.height,right:b.right,bottom:b.bottom};}
        return r;}""", ids)

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox","--disable-gpu"])
        c=await b.new_context(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True,
            device_scale_factor=2, user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)")

        # ---- graph.html ----
        pg=await c.new_page()
        await pg.goto("http://127.0.0.1:8123/graph.html", wait_until="domcontentloaded", timeout=30000)
        await pg.wait_for_timeout(4000)
        g=await boxes(pg, ["search","results","legend","info","backBtn",".home-btn","hint","nodeMenu"])
        print("[graph.html] 390x844")
        print(json.dumps(g, ensure_ascii=False, indent=1))
        # 检查搜索框与图例重叠
        if g["search"] and g["legend"]:
            s,l=g["search"],g["legend"]
            horz_overlap = s["x"] < l["right"] and s["right"] > l["x"]
            vert_overlap = s["y"] < l["bottom"] and s["bottom"] > l["y"]
            print("  搜索框 vs 图例 重叠:", horz_overlap and vert_overlap)
        # 底部 home-btn 与 info 重叠
        hb,inf = g[".home-btn"], g["info"]
        if hb and inf:
            print("  home-btn vs info 重叠:", hb["x"]<inf["right"] and hb["right"]>inf["x"] and hb["y"]<inf["bottom"] and hb["bottom"]>inf["y"])
        # 溢出检查
        ow = await pg.evaluate("()=>document.documentElement.scrollWidth>window.innerWidth+1")
        print("  横向溢出:", ow)
        await pg.close()

        # ---- ui.html ----
        pg=await c.new_page()
        await pg.goto("http://127.0.0.1:8123/ui.html", wait_until="domcontentloaded", timeout=30000)
        await pg.wait_for_timeout(4000)
        u=await boxes(pg, ["layForce","layHiero","layCluster","askBtn","graphBtn","docBtn","q","anscol","graph"])
        print("\n[ui.html] 390x844")
        print(json.dumps(u, ensure_ascii=False, indent=1))
        lf,lh,lc=u["layForce"],u["layHiero"],u["layCluster"]
        if lf and lh and lc:
            print("  力导向 vs 层级 重叠:", lf["right"]>lh["x"])
            print("  层级 vs 聚簇 重叠:", lh["right"]>lc["x"])
        # 按钮宽度总和是否溢出(顶部工具栏4个:主页+3按钮)
        lay = await pg.evaluate("""()=>{const btns=[...document.querySelectorAll('.layout-bar>*')];return btns.map(x=>x.getBoundingClientRect().right - x.getBoundingClientRect().left);}""")
        print("  layout-bar 各按钮宽度:", lay, "总和:", sum(lay))
        ow=await pg.evaluate("()=>document.documentElement.scrollWidth>window.innerWidth+1")
        print("  横向溢出:", ow)
        await pg.close()
        await b.close()
asyncio.run(main())
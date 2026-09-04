"""验证新布局: 下钻高连接度节点后无重叠."""
import asyncio
from playwright.async_api import async_playwright

CHROME="<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox","--disable-gpu"])
        c=await b.new_context(viewport={"width":1280,"height":800})
        pg=await c.new_page()
        await pg.goto("http://127.0.0.1:8123/graph.html", wait_until="domcontentloaded", timeout=40000)
        await pg.wait_for_timeout(4000)
        # 直接搜索并下钻 'App' 节点
        await pg.evaluate("""()=>{ const q=document.getElementById('q'); const inputEvent=new Event('input',{bubbles:true}); 
          // 直接用 doSearch 找 App
          window.__appTest=null; fetch('/search_nodes?q=App').then(r=>r.json()).then(d=>{
            const n=d.results[0]; window.__appTest=n; });
        }""")
        await pg.wait_for_timeout(1500)
        aid = await pg.evaluate("()=>window.__appTest&&window.__appTest.id")
        print("App 节点 id:", aid)
        if aid:
            await pg.evaluate("(id)=>{ loadCenter(id); }", aid)
            await pg.wait_for_function("()=>cy.nodes().length>1", timeout=10000)
            await pg.wait_for_timeout(1500)
            info=await pg.evaluate("""()=>{
              const poss=cy.nodes().map(n=>({id:n.id(),x:n.position('x'),y:n.position('y')}));
              let ov=0,minD=999,minPair=null;
              for(let i=0;i<poss.length;i++)for(let j=i+1;j<poss.length;j++){
                const a=poss[i],b=poss[j];const d=Math.hypot(a.x-b.x,a.y-b.y);
                if(d<minD){minD=d;minPair=[a.id,b.id];}
                if(d<45)ov++;
              }
              return {total:poss.length,overlap:ov,minD:Math.round(minD),minPair,
                parents:cy.nodes('.isParent').length,children:cy.nodes('.isChild').length,
                cyW:cy.width(),cyH:cy.height()};
            }""")
            print("下钻统计:", info)
            await pg.screenshot(path="/tmp/shot_app_drill.png")
        await b.close()
asyncio.run(main())
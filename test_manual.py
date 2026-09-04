"""单测 place 布局函数 + 手动重建节点."""
import asyncio, json
from playwright.async_api import async_playwright
CHROME="<your-project-path>/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True, executable_path=CHROME, args=["--no-sandbox","--disable-gpu"])
        c=await b.new_context(viewport={"width":1280,"height":800})
        pg=await c.new_page()
        await pg.goto("http://127.0.0.1:8123/graph.html", wait_until="domcontentloaded", timeout=40000)
        await pg.wait_for_timeout(4000)
        # 1. 检查 loadCenter 函数是否被页面里的代码替换/存在
        hasFn=await pg.evaluate("()=>typeof loadCenter")
        print("typeof loadCenter:", hasFn)
        # 2. 直接手动 fetch + 用 place 逻辑添加, 看是否成功
        manual=await pg.evaluate("""async ()=>{ 
          const r=await fetch('/graph/node/296'); const nb=await r.json();
          const nb2={center:nb.center, parents:nb.parents, children:nb.children};
          if(typeof nb.parents==='undefined') return 'NO parents field';
          let added=0;
          const W=cy.width(),cx=cy.width()/2,cyMid=cy.height()/2,R=Math.min(cy.width(),cy.height())*0.30;
          const place=(items,up)=>{ const dir=up?-1:1;
            let perRow=Math.max(1,Math.min(6,Math.floor((W*0.92)/70))); if(perRow>=items.length)perRow=items.length||1;
            const rowGap=58,colGap=64;
            items.forEach((it,i)=>{ const rr=Math.floor(i/perRow),col=i%perRow,rowN=Math.min(perRow,items.length-rr*perRow);
              const frac=(rowN>1)?(col/(rowN-1)-0.5):0,depth=Math.abs(frac)*0.35;
              const x=cx+colGap*(col-(rowN-1)/2), y=cyMid+dir*(R+46+rr*rowGap)+dir*depth*rowGap;
              const nid='n'+it.id; if(cy.getElementById(nid).length===0){ cy.add({group:'nodes',data:{id:nid,label:it.name,kind:it.kind},position:{x:x,y:y}}); added++; }
            }); };
          place(nb2.parents,true); place(nb2.children,false);
          return {added, parents:typeof nb.parents, children:typeof nb.children, nbParents:nb.parents.length};
        }""")
        print("manual add:", json.dumps(manual, ensure_ascii=False))
        cnt=await pg.evaluate("()=>cy.nodes().length")
        print("cy 节点数:", cnt)
        await b.close()
asyncio.run(main())
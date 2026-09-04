# EDGE-WORKER.md — <your-worker> 免费云打点层

## 这页是什么
借鉴图吧工具箱「评分系统用 Cloudflare Worker 零成本」的思路，
给 RAG 加一个纯免费的**边缘用量统计层**。不碰主链路(隧道/8123/PG)。

线上地址:
- Worker: `<your-domain>`
- 打点: `GET https://<your-domain>/v1/hit?k=<key>`
- 统计: `GET https://<your-domain>/v1/stats`
- 健康: `GET https://<your-domain>/v1/health`

## 线上地址(已部署)
- Worker 名: `<your-worker>` (KV namespace id `6d8037...465`)
- 自定义域: `https://<your-domain>` (绑定到 <your-domain> zone)
- workers.dev 验证域: `https://<your-worker>.workers.dev`
  (workers.dev 平台域绕过 zone 的 Under Attack 门神, 便于脚本/服务器验证逻辑;
   真实用户走 <your-domain>)

打点/统计 API:
- 打点: `GET /v1/hit?k=<key>`  (key 白名单: ask search graph doc node home)
- 统计: `GET /v1/stats`  `GET /v1/stats?scope=<key>`  `GET /v1/stats?date=<YYYY-MM-DD>`
- 健康: `GET /v1/health`
- 其它路径转发回 <your-domain>

## 代码位置
- `<your-project-path>/ragkg/edge-worker/worker.js` — Worker 源码
- `<your-project-path>/ragkg/edge-worker/wrangler.toml` — 部署配置(KV id 已填)
- `<your-project-path>/ragkg/edge-worker/test-local.mjs` — 本地逻辑测试(Node, 已通过)
- `<your-project-path>/ragkg/web/pj.js` — 前端打点脚本(节流3s/静默失败)
- 埋点已挂进 `web/index.html`(home) / `web/ui.html`(ask,graph) / `web/graph.html`(graph,node)
- 仪表盘: `web/stats.html` (页面) + `app.py` (`GET /stats` 反代)

## 仪表盘(用量统计页面)
- 入口: 首页 `/index.html` 卡片「用量统计」→ `/stats.html`
- 页面: `<your-project-path>/ragkg/web/stats.html` — 纯 CSS 条形图, 无外部依赖
- 数据链路: stats.html 的 JS `fetch('/stats')` **同源** → 8123 FastAPI 反代 `app.py`
  `GET /stats` → 转发到 worker (workers.dev 域)。避开浏览器跨源 CORS + Under Attack。
- 两个视图 tab: 累计 / 今日(本地时区 CST)。

### 仪表盘踩坑
- `app.mount("/", StaticFiles)` 是 fallback, 必须放在 `/stats` 等 API 路由**之后**,
  否则 `/stats` 被 fallback mount 吞掉返回 404。
- 不要在 load() 里用 innerHTML 重建 `#total` 容器——`#totalNum` 子元素会被删除,
  render 时 `getElementById('totalNum')` 得 null 抛 TypeError。只改 textContent 即可。
- stats.html 没有 `$` 辅助函数(那是 ui.html 的), 别用 `$(...)`。
- 反代依赖: rag.service systemd Environment 必须含
  `HTTPS_PROXY=http://127.0.0.1:7890 HTTP_PROXY=... NO_PROXY=127.0.0.1,localhost`。
  否则服务端 urlopen 访问 workers.dev 直连出站不通 → Errno 101 Network is unreachable。
- 从 127.0.0.1:8123 本地打开时, pj.js 打点到跨源 <your-domain> 会被 CORS 拦(静默失败, 无害);
  公网经 <your-domain> 时浏览器已过 Access, 打点能通。

## KV key 设计
- `cnt:<k>` — 该 key 累计次数
- `total` — 总调用数
- `day:<YYYY-MM-DD>:<k>` — 当日次数, **按本地时区(UTC+8)记日**

key 白名单: `ask search graph doc node home`

## 踩坑记录(重要)
1. **KV 绑定走 env 参数, 不是全局变量**。
   wrangler 部署日志显示 `env.EDGE_KV`, worker.js 里必须用 `env.EDGE_KV`,
   不能全局引用 `EDGE_KV`。否则运行时报 Cloudflare error 1101 (worker threw JS exception);
   症状是 health/非法key(不碰KV)正常, 所有打点/stats 全 1101。
   本地 mock 用 globalThis 注入会掩盖此问题 → test.mjs 改用 `ENV={EDGE_KV:kvMock}` 传入。
2. **时区**: Worker 环境是 UTC, `toISOString()` 得 UTC 日期。打点记日必须
   `new Date(Date.now()+8*3600*1000).toISOString()` 偏移到 CST, 否则"今日分布"
   与本地 `date +%F` 对不上(差半天)。
3. **zone 开 Under Attack**: <your-domain> zone security_level=under_attack, 从数据中心
   IP/服务器 curl 直连 <your-domain> 会撞 Managed Challenge("Just a moment...")。
   Worker 逻辑不受影响, 只是在线脚本验证被拦。解决办法: 用 workers.dev 域
   (平台域不归 zone 管) 验证; 真实用户浏览器能过挑战。未改动安全设置。
4. curl 默认走本机 mihomo 代理(HTTPS_PROXY=127.0.0.1:7890)。workers.dev 域需走
   代理才能连上(直连--noproxy 卡连接); <your-domain> CF 边缘则全国可直连。
   验证时注意分清楚。

## 部署步骤(需 CF API token)
token 权限: Account·Workers Scripts·Edit, Account·Workers KV Storage·Edit,
Zone·<your-domain>·Workers Routes·Edit, (可选)Zone·<your-domain>·DNS·Edit。
```
export CLOUDFLARE_API_TOKEN='<TOKEN>'
cd <your-project-path>/ragkg/edge-worker
npx wrangler kv namespace create EDGE_KV   # 首次, 把 id 填进 wrangler.toml
npx wrangler deploy                        # 上传 worker + 绑 <your-domain> + workers.dev
```
验证:
```
curl --max-time 25 "https://<your-worker>.workers.dev/v1/health"
curl --max-time 25 "https://<your-worker>.workers.dev/v1/stats"
```

## 验证记录(2026-09-01, CST)
- health 正常 JSON
- 打点递增正确(home→3, ask→2, node→1, total→9), 非法 key 400
- stats 聚合一致: ask2 graph1 home3 node1 search2 = total 9
- 今日分布(CST 日期)含本地时区点, UTC 日期含旧点, 两侧可对上
- 回源转发逻辑本地 PASS(线上回源会撞 Under Attack, 属预期)
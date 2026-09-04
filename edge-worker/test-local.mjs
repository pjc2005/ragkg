// 本地验证 a<your-worker> worker 逻辑, 不依赖真实 KV/CF。
// Node 自带 Request/Response (v18+)。给全局挂一个内存 KV mock。
import { pathToFileURL } from 'node:url';
import { writeFileSync } from 'node:fs';

// ---- 内存 KV mock ----
const store = new Map();
const kvMock = {
  async get(k) { return store.get(k) ?? null; },
  async put(k, v) { store.set(k, String(v)); },
  async list({ prefix } = {}) {
    const keys = [];
    for (const k of store.keys()) {
      if (k.startsWith(prefix || '')) keys.push({ name: k });
    }
    return { keys };
  },
};
// 生产环境 KV 绑定走 fetch 的 env 参数, 与之一致:
const ENV = { EDGE_KV: kvMock };

const mod = await import(pathToFileURL('<your-project-path>/ragkg/edge-worker/worker.js').href);
const { fetch } = mod.default; // worker.js 用 export default

function assert(cond, msg) {
  if (!cond) { throw new Error('FAIL: ' + msg); }
  console.log('PASS: ' + msg);
}

async function req(path, opts = {}) {
  const r = new Request('https://<your-domain>' + path, opts);
  const res = await fetch(r, ENV);
  return res;
}

// 1. hit 打点
let res = await req('/v1/hit?k=ask');
let j = await res.json();
assert(res.status === 200, 'hit 200');
assert(j.ok === true && j.count === 1, `ask 计数=1 (got ${j.count})`);

res = await req('/v1/hit?k=ask');
j = await res.json();
assert(j.count === 2, 'ask 计数=2 递增');

// 2. 非法 key 拒绝
res = await req('/v1/hit?k=../../etc');
assert(res.status === 400, '非法 key 返回 400');

// 3. 多 key
await req('/v1/hit?k=search');
await req('/v1/hit?k=graph');
await req('/v1/hit?k=graph');

// 4. stats 聚合
res = await req('/v1/stats');
j = await res.json();
assert(res.status === 200, 'stats 200');
assert(j.ask === 2 && j.search === 1 && j.graph === 2, `聚合正确 ask=2 search=1 graph=2 (got ${JSON.stringify(j)})`);
assert(j.total === 5, `total=5 (got ${j.total})`);

// 5. scope 单查
res = await req('/v1/stats?scope=graph');
j = await res.json();
assert(j.scope === 'graph' && j.count === 2, 'scope=graph count=2');

// 6. health
res = await req('/v1/health');
j = await res.json();
assert(res.status === 200 && j.worker === '<your-worker>', 'health ok');

// 7. 其它路径 -> 转发回源。mock global fetch 拦截 <your-domain>。
globalThis.fetch = async (url, init) => {
  const u = String(url);
  if (u.startsWith('https://<your-domain>')) {
    return new Response('UPSTREAM:' + u, { status: 200, headers: { 'content-type': 'text/plain' } });
  }
  throw new Error('unexpected fetch: ' + u);
};
res = await req('/ask?q=test');
const t = await res.text();
assert(t.includes('UPSTREAM:https://<your-domain>/ask?q=test'), '非 /v1 路径正确转发回源');
assert(res.headers.get('x-<your-worker>') === 'proxy', '转发带 x-<your-worker> 头');

console.log('\n全部逻辑验证通过.');
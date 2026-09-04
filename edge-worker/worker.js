/**
 * <your-worker>: 免费云打点/统计层 (Cloudflare Worker + KV)
 *
 * 思路: 图吧工具箱 "评分系统用 Cloudflare Worker 零成本" 的借鉴。
 * 8123 上都是重请求(PG/LLM), 不值得分流; 真正有价值的是把
 * "调用计数/用量统计" 放到边缘 KV, 前端低频打点, 不碰主链路。
 *
 * 路由:
 *   GET   /v1/hit?k=<name>        打点+1 (k 白名单防刷表)
 *   POST  /v1/hit?k=<name>        打点(同上, POST 语义)
 *   GET   /v1/stats               聚合各接口总调用数(JSON)
 *   GET   /v1/stats?scope=<key>   单个 key 计数
 *   其它                          转发回 <your-domain>(隧道->8123)
 *
 * KV key 设计:
 *   cnt:<k>      -> 该 key 累计次数 (整数)
 *   total        -> 总调用数
 *   day:<YYYY-MM-DD>:<k> -> 当日次数 (用于简单时间分布, 可选)
 *
 * 注意: Worker 免费档 10 万请求/天, KV 免费额度足够小众用途。
 * 打点要低频非阻塞, 别在前端阻塞交互。
 */

const ALLOWED = new Set(['ask', 'search', 'graph', 'doc', 'node', 'home']);
const ORIGIN = 'https://<your-domain>';

const CORS = {
  headers: {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  },
};

function corsHeaders(extra = {}) {
  return { ...CORS.headers, ...extra };
}

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { ...corsHeaders({ 'Content-Type': 'application/json; charset=utf-8' }), ...extra },
  });
}

async function incKV(kv, k, amount = 1) {
  const cur = (await kv.get(`cnt:${k}`)) || '0';
  const next = (parseInt(cur, 10) || 0) + amount;
  await kv.put(`cnt:${k}`, String(next));

  const t = (await kv.get('total')) || '0';
  await kv.put('total', String((parseInt(t, 10) || 0) + amount));

  // 按本地时区(UTC+8/CST)记日, 与 `date +%F` 及用户直觉一致.
  // 前端打点查到分布时用本地日期. Worker 环境是 UTC, 需显式偏移.
  const cst = new Date(Date.now() + 8 * 3600 * 1000);
  const today = cst.toISOString().slice(0, 10);
  const dk = `day:${today}:${k}`;
  const dc = (await kv.get(dk)) || '0';
  await kv.put(dk, String((parseInt(dc, 10) || 0) + amount));
  return { key: k, count: next, total: parseInt(t, 10) + amount };
}

async function handleHit(kv, k, amount) {
  if (!k || !ALLOWED.has(k)) {
    return json({ error: `invalid or disallowed key '${k}'` }, 400);
  }
  const r = await incKV(kv, k, amount);
  return json({ ok: true, ...r });
}

async function handleStats(kv, scope, date) {
  const out = { total: 0 };
  const keys = await kv.list({ prefix: 'cnt:' });
  for (const { name } of keys.keys) {
    const k = name.slice(4); // strip 'cnt:'
    if (!ALLOWED.has(k)) continue;
    const v = await kv.get(name);
    out[k] = parseInt(v, 10) || 0;
    out.total += out[k];
  }
  // 也读一下 total 键(与实际累加对齐)
  const t = await kv.get('total');
  // 若 total 键更大取它
  out.total = Math.max(out.total, parseInt(t, 10) || 0);

  if (scope) {
    const cnt = await kv.get(`cnt:${scope}`);
    return json({ scope, count: parseInt(cnt, 10) || 0, total: out.total });
  }
  if (date) {
    // 当日各 key
    const dayStats = {};
    const dkeys = await kv.list({ prefix: `day:${date}:` });
    for (const { name } of dkeys.keys) {
      const k = name.split(':').pop();
      dayStats[k] = parseInt(await kv.get(name), 10) || 0;
    }
    return json({ date, counts: dayStats, total: out.total });
  }
  return json(out);
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // CORS preflight
    if (method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS.headers });
    }

    if (path === '/v1/hit') {
      const k = url.searchParams.get('k');
      const amt = parseInt(url.searchParams.get('n') || '1', 10) || 1;
      return handleHit(env.EDGE_KV, k, Math.max(1, Math.min(amt, 100)));
    }

    if (path === '/v1/stats') {
      const scope = url.searchParams.get('scope');
      const date = url.searchParams.get('date');
      return handleStats(env.EDGE_KV, scope, date);
    }

    if (path === '/v1/health') {
      return json({ ok: true, worker: '<your-worker>', time: new Date().toISOString() });
    }

    // 其它路径转发回源(向后兼容, 不破坏现有 <your-domain> 访问)
    try {
      const upstream = ORIGIN + url.pathname + url.search;
      const resp = await fetch(upstream, {
        method,
        headers: request.headers,
        body: method !== 'GET' && method !== 'HEAD' ? request.body : undefined,
        redirect: 'manual',
      });
      const headers = new Headers(resp.headers);
      headers.set('x-<your-worker>', 'proxy');
      return new Response(resp.body, { status: resp.status, headers });
    } catch (e) {
      return json({ error: 'upstream unreachable', detail: String(e && e.message) }, 502);
    }
  },
};
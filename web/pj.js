/**
 * pj.js — 边缘打点 (轻量, 非阻塞, 静默失败)
 * 用法: on each page include <script src="/pj.js"></script>
 *   window.pj('home')   一次页面浏览
 *   window.pj('ask')    一次 RAG 问答
 * 负责: 节流(同一 key 至少间隔 MIN_MS), 失败静默, 不阻塞主线程。
 * 目标: https://<your-domain>/v1/hit  (Cloudflare Worker + KV)
 */
(function () {
  var ENDPOINT = 'https://<your-domain>/v1/hit';
  var MIN_MS = 3000;      // 同一 key 最小间隔, 防抖
  var last = {};          // key -> 上次发送时间戳
  var disabled = false;

  // 若页面同时是 HTTPS 且 edge 不可达, 静默关掉, 不报错
  function fire(k) {
    if (disabled || !k) return;
    var now = Date.now();
    if (last[k] && now - last[k] < MIN_MS) return; // 节流
    last[k] = now;
    try {
      fetch(ENDPOINT + '?k=' + encodeURIComponent(k), {
        method: 'GET',
        mode: 'cors',
        cache: 'no-store',
        keepalive: true,               // 页面跳转时也能发出
      }).then(function (r) {
        if (r && r.status === 400) disabled = true; // 非法 key, 停掉
      }).catch(function () { disabled = true; });   // 失败静默并停
    } catch (e) { disabled = true; }
  }

  window.pj = fire;

  // 服务端允许的 key 白名单: home ask search graph doc node
})();
# Cloudflare 隧道(cloudflared)远程访问方案

目标：用你在 Cloudflare 绑定的域名(主域 <your-domain>)，通过 Cloudflare Tunnel 让
这台 7x24 服务器(local RAG 等) 在公网可用，同时保住安全(不把内部服务裸奔到公网)。

## 0. 现状盘点(本机实测)

- cloudflared **2026.8.2 已装**于 /usr/local/bin/cloudflared。
- **隧道已部署完成并实测通过（浏览器访问 https://<your-domain>/ 直接返回本机后端内容）**
  - 隧道名 **home**，id 7b5e5b91-dc88-4c96-988c-9df48179a6c1
  - cert.pem 已生成(账号已授权) + 凭据 json + config.yml 齐全
  - CNAME <your-domain> → 隧道 已建；DNS 解析到 CF 边缘(104/172.67.199.x)
  - systemd 服务 cloudflared.service 常驻+开机自启，走 mihomo 代理出海
  - cloudflared 自带 precheck 全 PASS: DNS/UDP(QUIC)/TCP(H2)/Cloudflare API
  - 公网浏览器实测返回本机 8123 内容 → 端到端闭环成功
  - 注：经数据中心代理 IP 的 curl 会触发 CF Managed Challenge(403)，真浏览器无碍
- **主域名：<your-domain>（CF 托管）**
- **入口子域：<your-domain>（通用入口，路径区分多服务）**
  - `<your-domain>/` → RAG 前端/后端（当前 config 指向 127.0.0.1:8123）
  - 后续新服务按路径 or 新增子域扩展
- 现状在 0.0.0.0 监听(安全隐患)：8101(MimirLink)、22(SSH)。待阶段 4 收紧。
- GPU 空闲。

## 1. 目标架构

```
 Internet
    │ 你的域名 *.example.com (CF nameservers, 代理/CDN 已开)
    ▼
Cloudflare 边缘 ──cloudflared 出站长连接──▶ 本机 cloudflared
                                          │  (只监听 127.0.0.1)
                     ingress 映射(按主机名)▼
   rag.example.com ──────────▶ http://127.0.0.1:8123  (RAG 后端/前端)
   graph.example.com ────────▶ http://127.0.0.1:8090  (图谱前端, 或合一)
   (可选) llm.example.com ───▶ http://127.0.0.1:<llama-server> (仅自用+CF Access 保护)
```

要点：
- cloudflared 主动出站连 CF 边缘，**不需要开公网入站端口/公网 IP**，适合 NAT 机。
- 所有内部服务绑 **127.0.0.1**，不对外网/LAN 暴露，由 cloudflared 回环访问。
- TLS 由 Cloudflare 边缘终结，本机无需证书。
- 域名在 CF，DNS 指向由 `cloudflared tunnel route dns` 自动建 CNAME。

## 2. 前置条件(需要你)

1. 你的 CF 账号能登录该域名所在账户(可浏览器操作即可，box 可 headless)。
2. Cloudflare 免费版即可(隧道免费，Cloudflare Access 前 50 用户免费)。
3. 告诉我你的主域名(比如 rag.example.com / *.example.com)。

## 3. 分阶段执行

### 阶段 1：装 cloudflared + 真实连通性验证(最关键门槛)
1. 从 github releases 装 cloudflared(apt 无包，直接下二进制,放 /usr/local/bin)。
2. 冒烟测试：
   - `cloudflared tunnel ping` 或 `cloudflared tunnel --url http://127.0.0.1:8123`
     试连边缘。
   - 给它配代理出海:`HTTPS_PROXY=http://127.0.0.1:7890 NO_PROXY=localhost,127.0.0.1`
     (cloudflared 支持走 HTTP 上游代理)。
   - 不行就试 QUIC(默认) vs HTTP/2(--protocol http2)、换 edge host。
   退出条件：cloudflared 稳定连上边缘并注册登录成功，否则进入【风险 C】。

### 阶段 2：隧道认证与建隧道
- 认证：`cloudflared tunnel login` → 打印一个 URL，你在**自己浏览器**(任意设备)
  打开并授权，把返回的 token 粘回终端，生成 `~/.cloudflared/cert.pem`
  (headless 友好，不需要本机图形)。
- 建具名隧道：`cloudflared tunnel create rag` → 得到 tunnel id + 凭据 json。
- 全程 headless，做成 systemd 常驻。

### 阶段 3：ingress 配置 + DNS 路由
- 写 `~/.cloudflared/config.yml`：
  ```
  tunnel: rag
  credentials-file: <your-project-path>/.cloudflared/<tunnel-id>.json
  ingress:
    - hostname: rag.example.com
      service: http://127.0.0.1:8123
    - service: http_status:404
  ```
- `cloudflared tunnel route dns rag rag.example.com` → CF 自动建 CNAME。
- `cloudflared tunnel run rag` 验证本机 127.0.0.1:8123 可达。

### 阶段 4：安全加固(必做)
1. 服务只绑 127.0.0.1：调整 RAG backend/frontend、llama-server 的监听
   （llama-server 默认 0.0.0.0，务必 --host 127.0.0.1）。
2. 收紧 8101(MimirLink) 和 22(SSH) 的暴露面——即便不强求，也建议只留
   本机/内网白名单。
3. 上 Cloudflare Zero Trust → Access，给 rag.example.com 套一层
   Email OTP / 一次性密码登录墙，避免知识库网页完全公开。
4. (可选) CF 防火墙规则按国家/IP 限制。

### 阶段 5：接入 RAG 服务(与 RAG 项目阶段 E 衔接)
- RAG 后端/前端绑 127.0.0.1，写对应 ingress。
- 验证浏览器实际能打开 rag.example.com，图谱可视化正常。

### 阶段 6：系统化与验收
- cloudflared systemd 服务(Restart=on-failure)，开机自启。
- 写 README：隧道 ID、凭据位置、config、Access 后台配置步骤、回滚命令。
- 验收清单：公网 HTTPS 访问成功 / 内部服务不回环不可达 / 服务重启后隧道自动恢复。

## 4. 风险与备选(诚实标注)

- A. *.argotunnel.com 出站被针对性干扰(实测已见 TLS 失败)。
  - 缓解：让 cloudflared 走本机 mihomo 代理(如上)。
  - 备选：cloudflared 换边缘/H2；仍未果 → 换用**反向 FRP / Prowler /
    ZeroTier/Tailscale** 组网方案远程访问(FRP 需一台公网跳板，你有域名可搭)。
- B. 免费版 CF 隧道单隧道带宽/并发达标：对个人 RAG 足够；图片/大并发再看。
- C. headless 认证：login 走 URL+token 流程即可，无需本机图形界面。
- D. 安全：任何对外暴露的服务都必须过 CF Access 或至少改默认无口令状态；
  尤其 llama-server / SillyTavern 无鉴权，绝不能直接对外。

## 5. 交付物
- `/usr/local/bin/cloudflared` + `/etc/systemd/system/cloudflared.service`
- `~/.cloudflared/`(cert.pem, 隧道凭据, config.yml)
- CF 后台：DNS CNAME + Zero Trust Access 应用
- README(部署/回滚/运维)

## 6. 需要你提供/操作的东西
1. 主域名(如 rag.example.com 用哪个子域)。
2. 阶段 2 时你在浏览器完成 cloudflared login 授权(给你 URL 后点一下)。
3. CF 后台建 Zero Trust Access 应用时可告知邮箱或选择 OTP 方式。
# YOUR_APP 实时监控仪表盘

地址: https://<your-domain> (经 Cloudflare under_attack 保护, 仅真实浏览器可访问)

## 作用
服务器 7×24 实时状态看板, 自动刷新(每5秒)。返回主页按钮 ↔ 主页"实时监控"入口卡片 双向跳转。

## 代码位置
`<your-project-path>/dashboard/`
- `collect.py`    指标采集脚本(系统/GPU/服务/端口/代理出口/OKX/PG行数)
- `dash.py`       FastAPI 后端 `:8125`, `/api/metrics` + 静态仪表盘页
- `dashboard.html` 前端单页(深色卡片, 零外部依赖)
- `dashboard.service` systemd unit

依赖: 复用 `<your-project-path>/ragkg/.venv` 的 fastapi+uvicorn, 无需单独装。

## 启动
```bash
sudo cp <your-project-path>/dashboard/dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now dashboard.service
```
复用 rag 服务的代理 env(HYPTTPS_PROXY=127.0.0.1:7890)采集出海出口 IP。

## 云通道
- cloudflared config `<your-project-path>/.cloudflared/config.yml` 加:
  `- hostname: <your-domain> / service: http://127.0.0.1:8125`
- DNS CNAME: `cloudflared tunnel route dns home <your-domain>` 已建

## 指标内容
- 系统: CPU型号+负载 / 内存型号+用量 / 磁盘(SSD/机械判定+型号, / /sda1 /sdb1) / uptime / 健康
- 硬件: /proc/cpuinfo CPU型号 · dmidecode 内存(DDR4/速度/part) · lsblk ROTA 判定 SSD/机械 + model
- GPU: GPU 显存/利用率/温度/功耗(NVIDIA进程 9B+2B+嵌入)
- 功耗: GPU 即时功耗 + Intel RAPL CPU包功耗(需sudo读energy_uj) + 外围≈25W → 整机估算
- 服务: llama-qa/embed/slice, mihomo, cloudflared, okx-a2a, mimirlink, filebrowser, rag, hermes-gateway
- 端口: 8080/8998/8999/7890/8124/8123/5432 探活
- 网络: mihomo 出口 IP
- OKX收益: 链上钱包余额(totalValueUsd) + 三服务 soldCount×fee 估算累计
- 知识库: PG ragkg 表行数(documents/chunks/nodes/edges)

## 注意
- collect.py 里 onchainos 命令需 `onchainos` 在 PATH(~/local/bin), dashboard.service 已设
  `Environment=PATH=<your-project-path>/.local/bin:/usr/local/bin:/usr/bin:/bin`; 否则收益采集返回 None。
- rapl 需 sudo 无密码(本机已配 NOPASSWD), 采集每次约2s采样。
- 收益为真实链上数据: wallet balance + service-list soldCount。

## 后续可选
- 超标告警推送 Telegram(gateway 已连): llama 掉线/显存满/mihomo 断/okx daemon 掉/A2A 审核变状态
- OKX ASP#11866 审核状态实时拉取(get-agents)替换占位
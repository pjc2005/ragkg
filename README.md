# ragkg — 自托管 RAG + 知识图谱问答系统

> 仓库内的 `*.service` / `edge-worker/` / 各部署文档为**个人部署参考**——
> 其中的域名、路径、用户名均以占位符或示例给出，部署时替换为你自己的环境。

纯本地部署的知识库检索问答（RAG）+ 知识图谱（KG）系统：文档导入 → 语义切片 →
实体/关系三元组抽取 → 向量化 → PostgreSQL/pgvector 存储 → 混合检索
（向量 + 关键词 + 图谱扩展）→ 本地 LLM 生成带引用的回答 → 浏览器图谱可视化。

全部组件自托管在一台 7×24 服务器（Debian 13 + Tesla P100 16G），可经
Cloudflare Tunnel 从公网访问。

## 架构

```
文档(TXT/PDF/MD/图片)
      │
      ▼
Qwen3-VL-2B (llama.cpp llama-server :8999)   ← 语义切片 + (实体,关系,实体) 抽取
      │
      ▼
[chunks] [nodes/实体] [edges/关系]  ◀── PostgreSQL 17 + pgvector (hnsw)
      │              │
      ▼              ▼
 bge-m3 embedding (:8998) ──▶ pgvector 向量索引 (1024 维)
      │
      ▼
FastAPI 后端 (:8123)
   混合检索: 向量 top-k + BM25/关键词 + 实体→邻居三元组扩展
      │
      ▼
Qwen3.5-9B (:8080) ──▶ 生成带引用来源的回答
      │
      ▼
浏览器前端 (vis-network): 搜索 / 问答 / 图谱节点图（按实体类型着色）
```

## 技术栈

| 组件 | 选型 | 端口 |
|------|------|------|
| 数据库 | PostgreSQL 17 + pgvector 0.8（hnsw 索引） | 5432 |
| 切片/抽取模型 | Qwen3-VL-2B Q8 + mmproj（llama.cpp） | 8999 |
| 向量模型 | bge-m3 Q8（1024 维，`--ubatch-size >= 2048`） | 8998 |
| 回答模型 | Qwen3.5-9B Q8（`--reasoning off`） | 8080 |
| 后端 | FastAPI + uvicorn + psycopg + httpx | 8123 |
| 前端 | 单页 HTML + vis-network（无构建依赖） | 8123 静态挂载 |
| 公网 | Cloudflare Tunnel + Worker（edge） | - |

## 目录结构

```
app.py                  FastAPI 后端（API + 静态前端挂载）
db.py                   PG 数据访问层（pgvector，表结构）
llm.py                  llama-server OpenAI 兼容客户端（embed/chat/slice/extract/answer）
ingest.py               文档导入管线：切片 → 抽取 → embedding → 写 PG
retrieve.py             检索编排：向量检索 + 图谱子串匹配扩展
task_progress.py        长任务进度模块（供仪表盘轮询）
scripts/
  deepseek_export.py    DeepSeek 对话导出 → 知识文档（再 /upload 导入）
  rebuild_graph.py      图谱重建
  refine_domain.py      领域/主题提炼
  restore_doc_files.py  从 chunks 重组缺失的原始文档
  task_bridge.py        后台任务实时桥接
edge-worker/            Cloudflare Worker（<your-domain> 路由 / KV）
web/                    前端页面（index / ui / graph / doc …）
*.service               各 systemd 单元示例
```

## 快速启动

前置：PostgreSQL 17 + pgvector、llama.cpp 的 llama-server、Python 3.12+ venv。

```bash
# 1. 数据库
sudo apt install postgresql-17 postgresql-17-pgvector
sudo -u postgres createdb ragkg
psql -d ragkg -c 'CREATE EXTENSION pgvector;'
#   按 db.py 中的 DSN 建库 / 表（documents/chunks/nodes/edges/chunk_entities）

# 2. 模型（三个 llama-server）
llama-server -m bge-m3-Q8.gguf  --embeddings --port 8998   # 向量
llama-server -m Qwen3-VL-2B-Q8.gguf --mmproj <mmproj> --port 8999   # 切片/抽取
llama-server -m Qwen3.5-9B-Q8.gguf --reasoning off --port 8080      # 回答

# 3. 后端
python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn psycopg pgvector httpx
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8123
```

生产环境按本仓库 `*.service` 用 systemd 托管（开机自启 + 崩溃自拉）。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/ingest` | 直接导入文本 `{"title","text"}` |
| POST | `/upload` | 上传文件（pdf/txt/md），自动导入 |
| GET | `/documents` | 文档列表 |
| GET | `/search?q=` | 混合检索 |
| GET | `/ask?q=` | RAG 问答（带引用来源） |
| GET | `/graph?seed=` | 图谱子图查询 |
| GET | `/graph/node/{id}` | 节点邻居下钻 |
| GET | `/node_detail/{id}` | 节点详情 |
| GET | `/search_nodes?q=` | 实体搜索 |
| GET | `/doc/{id}` · `/doc/{id}/raw` | 文档元信息 / 原始文件 |
| GET | `/stats` | 库统计 |

## 数据模型

- `documents` — 文档元信息（标题/路径/状态）
- `chunks` — 语义切片（text + embedding vector(1024)，hnsw 索引）
- `nodes` — 实体（name, type, description + embedding）
- `edges` — (src, dst, relation) 三元组
- `chunk_entities` — chunk ↔ 实体 关联

## 项目状态

已在生产运行：DeepSeek 全量会话导入（112 会话）、115 文档 / 3,784 节点 /
1,921 边 / 3,258 chunks；图谱经精炼重建为 123 节点 / 122 边的领域图谱；
已接入仪表盘长任务进度、移动端 UI、来源文档渲染。

## 备注

- 三个 LLM 服务共存约占显存 13.4G/16G；9B 长回复时注意 KV 缓存 OOM
  （已用 `--cache-type-k/v q8_0` 缓解），可降 `--ctx-size`。
- 备份按约定手动 rsync 到机械盘，不在仓库内。
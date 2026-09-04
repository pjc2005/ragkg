# 本地 RAG + 知识图谱可视化方案

目标：本地知识库 → 语义切片 → 向量检索 + 知识图谱检索 → 问答；图谱在浏览器可视化。
全部自托管在 `<your-project-path>`（Debian13 + P100 16G 常驻机）。

## 0. 架构总览

```
文档(导入文件夹)
   │
   ▼
QWEN3-VL-2B (llama.cpp llama-server)   ← 切片模型：语义分块 + 实体/关系抽取
   │  语义分块 → chunks
   │  每块抽取 (实体,关系,实体) 三元组
   ▼
[chunks表]  [nodes表 实体]  [edges表 关系]
   │            │
   ▼            ▼
embedding模型  ──▶ pgvector 索引          ← PG 17
   │
   ▼
┌─────────────────────────────┐
│ FastAPI 后端 (venv)          │
│  混合检索: vector + keyword  │
│  + 图谱扩展(实体→邻居三元组)  │
└──────────┬──────────────────┘
           ▼
浏览器前端: vis-network / Cytoscape.js
  搜索 + 问答 + 图谱节点图(按实体类型着色/聚类)
```

## 1. 组件清单（本地）

| 组件 | 选择 | 说明 |
|------|------|------|
| 数据库 | PostgreSQL 17 + pgvector | apt: `postgresql-17` `postgresql-17-pgvector` |
| 切片/抽取模型 | Qwen3-VL-2B (GGUF + mmproj) | llama-server 899 端口；2B 在 P100 毫无压力 |
| 向量模型 | bge-m3 (小 GGUF) | 专用于相似度（不要用聊天模型做 embedding）|
| 后端 | FastAPI (uvicorn) | venv，ConnectorX/psycopg + pgvector |
| 前端 | 单页 + vis-network | 本体里自带，无额外依赖 |
| 回答模型 | 本机 Qwen3.5-9B-Q8（已下载，9.8G）| QA 生成，质量优于 2B —— **已确认沿用** |

## 2. 分阶段执行

### 阶段 A：基础设施
1. `apt install postgresql-17 postgresql-17-pgvector`
2. 起 PG，建库 `ragkg`，开 `pgsql`/`pgvector` extension
3. 建表：`documents` / `chunks(id, doc_id, text, embedding vec)`
   / `nodes(id, name, type, description, embedding vec)`
   / `edges(src_id, dst_id, relation)`
   / chunk→entity 关联表 `chunk_entities`
   凡相似度字段加 `vector(1024/768)` + `ivfflat` 或 `hnsw` 索引
4. 装 python venv：fastapi uvicorn psycopg pgvector 等

### 阶段 B：模型准备
1. 下载 Qwen3-VL-2B GGUF + mmproj（ModelScope 直连 ~5.6MB/s；确认 llama.cpp
   对该模型的 QTensors 支持与 llama-server 启动命令）
   - 若 llama.cpp 尚未支持 Qwen3-VL 架构 → 回退备选：
     仍用 Qwen3-VL-2B 但按其官方 llama-server 命令，或换同为 2B 的 Qwen2.5-VL-3B 替代
2. 下载一个小型 embedding GGUF（bge-m3 / qwen3-embedding）
3. 两个 llama-server：
   - `:8999` Qwen3-VL-2B（chat + 结构化 JSON 生成、图抽取、可兼顾图片）
   - `:8998` embedding 模型（`--embeddings`）
4. 用 curl 验证 /v1/chat/completions 与 /v1/embeddings

### 阶段 C：切片与图谱抽取 pipeline
1. 支持导入格式：PDF / TXT / MD（先文本，图片文档后续）
2. 切块 prompt：模型按语义返回若干 chunks（JSON）
3. 图谱抽取 prompt：对每块输出 `[{head, relation, tail, head_type, tail_type}]`
4. 写入 PG：chunks、nodes（upsert 去重）、edges、chunk_entities
5. 对所有 chunk & node 打 embedding，建索引

### 阶段 D：检索 + 问答
1. 用户查询 → 语义分块/关键词 → 向量 top-k chunk 召回
   → 提取其中实体 → 图谱扩展出邻居三元组
   → 融合为上下文 → 交给回答模型(Qwen 9B)生成答案
2. 返回引用来源（文档/块定位）
3. FastAPI 接口：`/search` `/ask` `/graph`

### 阶段 E：图谱可视化
1. 前端单页：输入 → 结果面板 + 图谱面板
2. vis-network 渲染：按实体类型着色，按度放大，社区布局/聚类
3. `/graph?query=` 返回相关子图 JSON，前端连边

### 阶段 F：验收与文档
- 骑车测：导入 1~2 篇真实长文档，验证切块质量、图谱三元组质量、问答准确率
- 诚实评估：Qwen3-VL-2B 作切片/抽取模型的表现上限；是否需要升到 3B/7B
- 写好 README + systemd 服务串行启停脚本

## 3. 端口规划
- 5432 PostgreSQL
- 8999 Qwen3-VL-2B llama-server
- 8998 embedding llama-server
- 8123 FastAPI 后端
- 8090 前端静态页

## 4. 备注 / 风险
- 本机 P100 仅 16G，Qwen3.5-9B-Q8(9.8G)+embedding(R567MB) 同驻没问题；
  若要 Qwen3-VL-2B + 9B 回答模型同时跑需留意显存合计。
- llama.cpp 对 Qwen3-VL 的 GGUF 支持当前是否稳定是主要不确定点，阶段 B 首批验证。
- 图谱规模大时（成千节点）前端渲染与 pg 查询需加限制/分页。
- 先做"文本库+单机"最小闭环，图片/视觉输入和超大规模再迭代。

## 5. 交付物
- `<your-project-path>/ragkg/`：后端代码 + pipeline + 前端 + .service 文件
- PG `ragkg` 库及其中的知识库/图谱数据
- 浏览器可视化页面（局域网可访问）
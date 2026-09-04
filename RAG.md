# RAG + 知识图谱 项目文档 (<your-domain>)

## 项目定位
本地知识库检索问答 + 知识图谱可视化，全自托管于一台常驻 Linux 服务器。
文档 -> 语义切片 -> 实体/关系图谱抽取 -> bge-m3 向量化 -> PG(带 pgvector) 存储
-> 混合检索(向量+图谱扩展) -> Qwen9B 生成带引用的回答 -> 浏览器图谱可视化。

## 技术栈
| 组件 | 模型/工具 | 端口 | 说明 |
|------|-----------|------|------|
| 数据库 | PostgreSQL 17 + pgvector 0.8 | 5432 | ragkg 库, hnsw 向量索引 |
| 切片+图谱抽取 | Qwen3-VL-2B Q8 + mmproj | 8999 | 语义切片 / 三元组抽取 |
| 向量 | bge-m3 Q8 (1024 维) | 8998 | embedding |
| 回答 | Qwen3.5-9B Q8 (--reasoning off) | 8080 | RAG 生成回答 |
| 后端 | FastAPI (venv) | 8123 | /ask /search /graph /upload /ingest |
| 前端 | vis-network (ui.html) | 8123 | 问答+图谱可视化 |
| 公网 | Cloudflare Tunnel | - | <your-domain>(/ui.html, /files) |

## 目录结构 (<your-project-path>/ragkg/)
- app.py         FastAPI 后端 (API + 静态前端挂载)
- ingest.py      文档导入管线: 切片->抽取->embedding->写PG
- retrieve.py    检索编排: 向量检索 + 图谱子串匹配扩展
- llm.py         llama-server OpenAI 兼容客户端 (embed/chat/slice/extract/answer)
- db.py          PG 数据访问层 (pgvector)
- web/index.html 主页, web/ui.html RAG可视化前端
- files/         filebrowser 文件收件箱 + 知识导入池
- fb/            filebrowser 配置与数据库
- *.md, *.service 本文档/各系统服务单元

## systemd 服务 (全部开机自启, 崩溃自拉)
| 服务 | 作用 |
|------|------|
| postgresql | 数据库 |
| llama-slice | Qwen3-VL-2B :8999 |
| llama-embed | bge-m3 :8998 |
| llama-qa | Qwen3.5-9B :8080 (--reasoning off) |
| rag | FastAPI :8123 |
| cloudflared | CF 隧道 <your-domain> |
| filebrowser | 文件服务 :8124 |

## 常用操作
导入文本(API):  curl -X POST :8123/ingest -d '{"title":"..","text":".."}'
上传文件(API):  curl -X POST :8123/upload -F 'file=@x.pdf'
提问:          GET :8123/ask?q=问题   (浏览器 /ui.html)
检索:          GET :8123/search?q=..
图谱:          GET :8123/graph?seed=实体名
图谱下钻:       GET :8123/graph/node/{id}
节点详情:       GET :8123/node_detail/{id}
节点搜索:       GET :8123/search_nodes?q=..
文档查看:       GET :8123/doc/{id}   (元信息+重组全文)
文档原文件:     GET :8123/doc/{id}/raw  (返回 pdf/md 字节, 浏览器渲染)
查文档:         GET :8123/documents
数据库:        psql -d ragkg
重启全部:      sudo systemctl restart llama-slice llama-embed llama-qa rag cloudflared filebrowser
导入DeepSeek导出: python3 scripts/deepseek_export.py conversations.json "<标题子串,逗号分隔>" <outdir> 再逐个 /upload

## 风险 / 备注
- 显存: 三个模型共存占 ~13.4G/16G, 余 2.8G。9B 长回复时 KV 有 OOM 风险;
  若出现, 降 --ctx-size 或对 9B 用 --cache-type-k/v q8_0(已用)。
- Qwen3-VL-2B 用于切片/抽取(非视觉), 表现良好(实测中文切片/三元组正确)。
- bge-m3 1024 维, 与表结构一致; 若换模型改 columns 维度。
- 知识库目录 files/knowledge 可放 pdf/txt/md, 前端/API 上传即自动导入。
- 备份: 项目文档按约定手动 rsync 到 /media/sdb1/ragkg-backup/。

## 状态
- [x] 阶段A 数据库+表
- [x] 阶段B 模型下载+服务器
- [x] 阶段C 切片/抽取/embedding管线
- [x] 阶段D 检索+问答(RAG)
- [x] 阶段E 图谱可视化前端 + systemd 全套 + <your-domain> 接入
- [x] 移动端竖屏UI优化 + 各页回主页入口 (Playwright 390x844 实测无重叠/无溢出)
- [x] 详情来源文档可点击渲染 (/doc/{id}, /doc/{id}/raw)
- [x] DeepSeek 导出导入 (scripts/deepseek_export.py, 全量112会话已入库)
- [x] 知识库现状: 115 文档/3784 节点/1921 边/3258 chunks (DeepSeek 112会话全部入库, 全量+试点去重后)
- [x] OCR领域知识提炼试点: 11篇对话 -> 9B提炼成《OCR领域知识简介》(doc129, 16完整chunk, 可检索)
- [x] 修复embedding 512ubatch: llama-embed --ubatch-size 2048 (输入>=513token不再500, 全库导入受益)
- [x] ingest切片净化+规则切分降级 (ingest.py _clean_chunks/_rule_split, 防标题碎片)
- [x] 图谱彻底重建(A方案)完成: 清空4000噪音节点, 用2篇综述重建, 再清理孤立碎片 -> 最终 123节点/122边 精炼领域图谱
- [x] 修复doc.html md渲染: looksMarkdown检测替代isPlain, 无扩展名但含md特征的文档正确渲染
- [x] 修复doc129物理文件缺失: restore_doc_files.py 从chunks重组重建.md并关联path
- [x] 图谱顶层筛选优化: 优先知识主题类(method/tech/concept), 排除org/location实例品牌(华为云/腾讯云不再当顶层球)
- [x] 仪表盘长任务进度条(dash.html): 后端collect读task_progress.json, 前端只读轮询5s渲染, 不依赖前端状态
- [x] task_progress.py 进度模块 + task_bridge.py 实时桥接 + rebuild_graph 接入进度
- [ ] 可再提炼 RAG/量化/Docker 等领域综述并同样入库重建图谱
- [ ] 浏览器公网验收 <your-domain>/ui.html + /files
## 待办/资料记录
- 优酷私有视频《零基础学量化》(WorldQuant BRAIN 资料)：链接与密码仅本地留存，不入库。

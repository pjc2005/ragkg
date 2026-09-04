# -*- coding: utf-8 -*-
"""RAG + 知识图谱 FastAPI 后端.
API:
  GET  /health
  GET  /documents         列出已导入文档
  POST /ingest          body:{title,text} 导入文本
  POST /upload            上传文件(pdf/txt/md) 并导入
  GET  /search?q=&top_k=  检索(返回chunks+图谱)
  GET  /ask?q=            RAG问答(返回答案+引用+图谱)
  GET  /graph?seed=       图谱子图(seed可选实体名)
"""
import io
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import (connect, graph_expand, get_node_by_name, node_neighborhood,
                node_detail, get_document, document_text)
from retrieve import retrieve
from llm import answer_with_rag, QA_CHAT_URL
from ingest import ingest_text

app = FastAPI(title="Self-hosted RAG", version="0.1")

FILES_ROOT = Path("<your-project-path>/ragkg/files")
UPLOAD_DIR = FILES_ROOT / "knowledge"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

EXT_TEXT = {".txt", ".md", ".markdown"}
EXT_PDF = {".pdf"}


class IngestReq(BaseModel):
    title: str
    text: str


def _read_text_file(path: Path) -> str:
    if path.suffix.lower() in EXT_PDF:
        from pypdf import PdfReader
        r = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in r.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/documents")
def documents():
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT d.title, COUNT(c.id) AS chunks "
        "FROM documents d LEFT JOIN chunks c ON c.doc_id=d.id "
        "GROUP BY d.id ORDER BY d.id")
    rows = cur.fetchall()
    conn.close()
    return {"documents": rows}


@app.post("/ingest")
def ingest(req: IngestReq):
    try:
        r = ingest_text(req.title, req.text)
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True, **r}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename or "doc.txt").suffix.lower()
    if ext not in EXT_TEXT | EXT_PDF:
        raise HTTPException(400, f"不支持类型 {ext}, 支持: {sorted(EXT_TEXT|EXT_PDF)}")
    fname = f"{uuid.uuid4().hex[:8]}{ext}"
    dest = UPLOAD_DIR / fname
    dest.write_bytes(await file.read())
    try:
        text = _read_text_file(dest)
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"解析失败: {e}")
    if not text.strip():
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "无法从文件提取文本(可能是扫描件)")
    title = Path(file.filename or "doc").stem
    r = ingest_text(title, text, path=str(dest))
    return {"ok": True, "filename": file.filename, "saved": str(dest), **r}


@app.get("/search")
def search(q: str = "", top_k: int = 4):
    if not q:
        raise HTTPException(400, "需要 q")
    r = retrieve(q, top_k=top_k)
    return {
        "query": q,
        "chunks": [{"doc": c["title"], "seq": c["seq"], "text": c["text"]}
                   for c in r["chunks"]],
        "graph": {"nodes": [{"id": n["id"], "name": n["name"], "kind": n["kind"]}
                            for n in r["graph"]["seed_nodes"]],
                  "edges": [{"src": e["src_id"], "dst": e["dst_id"],
                             "relation": e["relation"],
                             "src_name": e["src_name"], "dst_name": e["dst_name"]}
                            for e in r["graph"]["edges"]]},
    }


@app.get("/ask")
def ask(q: str = ""):
    if not q:
        raise HTTPException(400, "需要 q")
    r = retrieve(q, top_k=4)
    try:
        answer, sources = answer_with_rag(QA_CHAT_URL, q, r["chunks"], r["graph"])
    except Exception as e:
        raise HTTPException(502, f"回答失败: {e}")
    return {
        "query": q,
        "answer": answer,
        "sources": sources,
        "graph": {"nodes": [{"id": n["id"], "name": n["name"], "kind": n["kind"]}
                            for n in r["graph"]["seed_nodes"]],
                  "edges": [{"src": e["src_id"], "dst": e["dst_id"],
                             "relation": e["relation"],
                             "src_name": e["src_name"], "dst_name": e["dst_name"]}
                            for e in r["graph"]["edges"]]},
    }


@app.get("/graph")
def graph(seed: str = "", limit: int = 250):
    conn = connect()
    if seed:
        n = get_node_by_name(conn, seed)
        if not n:
            conn.close()
            raise HTTPException(404, f"实体 {seed} 不存在")
        g = graph_expand(conn, [n["id"]], depth=1, limit=limit)
        seed_ids = [x["id"] for x in g["seed_nodes"]]
        # 聚合 nodes(含度数)
        limit_ids = list({e["src_id"] for e in g["edges"]} | {e["dst_id"] for e in g["edges"]} | set(seed_ids))
        cur = conn.cursor()
        cur.execute("""SELECT n.id, n.name, n.kind,
                              (SELECT count(*) FROM edges e WHERE e.src_id=n.id OR e.dst_id=n.id) AS degree
                       FROM nodes n WHERE n.id = ANY(%s)""", (limit_ids,))
        nodes = cur.fetchall()
        edges_all = g["edges"]
        conn.close()
        return {"nodes": nodes, "edges": edges_all, "seed_nodes": nodes}
    # 全部(带度数)
    cur = conn.cursor()
    cur.execute("""SELECT n.id, n.name, n.kind,
                          (SELECT count(*) FROM edges e WHERE e.src_id=n.id OR e.dst_id=n.id) AS degree
                   FROM nodes n ORDER BY degree DESC, n.id LIMIT %s""", (limit,))
    nodes = cur.fetchall()
    cur.execute(
        """SELECT e.id, e.src_id, e.dst_id, e.relation,
                  sn.name AS src_name, dn.name AS dst_name
           FROM edges e JOIN nodes sn ON sn.id=e.src_id
                        JOIN nodes dn ON dn.id=e.dst_id LIMIT %s""",
        (limit,))
    edges = cur.fetchall()
    conn.close()
    return {"nodes": nodes, "edges": edges, "seed_nodes": nodes[:20]}


@app.get("/graph/node/{node_id}")
def graph_node(node_id: int):
    """以指定节点为中心, 返回直系父球 + 子球 (下钻视图数据)."""
    conn = connect()
    try:
        nb = node_neighborhood(conn, node_id)
    finally:
        conn.close()
    if nb is None:
        raise HTTPException(404, f"实体 {node_id} 不存在")
    return nb


@app.get("/node_detail/{node_id}")
def node_detail_api(node_id: int):
    """节点详情: 基本信息 + 关联原文片段 + 来源文档."""
    conn = connect()
    try:
        d = node_detail(conn, node_id)
    finally:
        conn.close()
    if d is None:
        raise HTTPException(404, f"实体 {node_id} 不存在")
    return d


@app.get("/search_nodes")
def search_nodes(q: str = "", limit: int = 12):
    """模糊搜索节点名 (ILIKE %q%), 返回带类型与度数的候选."""
    if not q or not q.strip():
        return {"query": q, "results": []}
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """SELECT n.id, n.name, n.kind,
                  (SELECT count(*) FROM edges e WHERE e.src_id=n.id OR e.dst_id=n.id) AS degree
           FROM nodes n
           WHERE n.name ILIKE %s
           ORDER BY degree DESC, length(n.name) LIMIT %s""",
        (f"%{q.strip()}%", limit))
    rows = cur.fetchall()
    conn.close()
    return {"query": q, "results": rows}


MIME = {
    ".pdf": "application/pdf",
    ".md": "text/markdown; charset=utf-8",
    ".markdown": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


@app.get("/doc/{doc_id}")
def doc_meta(doc_id: int):
    """返回文档元信息 + 重组全文(供前端渲染), 及是否存在可下载的原始文件."""
    conn = connect()
    try:
        row, full = document_text(conn, doc_id)
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, f"文档 {doc_id} 不存在")
    path = row["path"]
    return {
        "id": row["id"], "title": row["title"], "src_type": row["src_type"],
        "has_file": bool(path and os.path.exists(path)),
        "path": path,
        "ext": (Path(path).suffix.lower() if path else ""),
        "text": full,
    }


@app.get("/doc/{doc_id}/raw")
def doc_raw(doc_id: int):
    """返回文档原始文件字节(浏览器原生渲染 pdf/md), 无物理文件时 404."""
    conn = connect()
    try:
        row = get_document(conn, doc_id)
    finally:
        conn.close()
    if not row or not row["path"] or not os.path.exists(row["path"]):
        raise HTTPException(404, f"文档 {doc_id} 无原始文件")
    p = Path(row["path"])
    media = MIME.get(p.suffix.lower(), "application/octet-stream")
    return FileResponse(p, media_type=media, filename=Path(row["title"] or f"doc{doc_id}").name + p.suffix)


# ---- 用量统计反代: /stats -> edge worker (同源, 避免浏览器跨源+CORS+UnderAttack) ----
# 8123 服务端转发到 workers.dev 域(不归 <your-domain> zone 管, 不受 Under Attack,
# 且本机出海走 mihomo 代理可达). 浏览器只需请求同源 /stats, 无跨源 CORS 问题.
# 注意: 此路由必须定义在 app.mount("/", StaticFiles) 之前, 否则被 fallback mount 吞掉。
import urllib.request

EDGE_STATS_BASE = os.environ.get("EDGE_STATS_BASE", "https://<your-worker>.workers.dev")


@app.get("/stats")
def stats_proxy(scope: str = "", date: str = ""):
    q = ""
    if scope:
        q += f"scope={scope}"
    if date:
        q += ("&" if q else "") + f"date={date}"
    url = EDGE_STATS_BASE + "/v1/stats" + (("?" + q) if q else "")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "rag-stats"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
        return Response(content=body, media_type="application/json")
    except Exception as e:
        raise HTTPException(502, f"统计服务暂不可达: {e}")


# 静态前端 (放在所有 API 路由之后, 作为 fallback)
WEB_DIR = Path(__file__).parent / "web"
app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8123)
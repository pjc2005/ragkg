# -*- coding: utf-8 -*-
"""RAG 导入管线: 文档 -> 语义切片 -> 图谱抽取 -> embedding -> 写 PostgreSQL."""
import sys
from db import connect, add_document, add_chunk, vector_search, keyword_search
from db import upsert_node, add_edge, link_chunk_node
from llm import embed_texts, slice_text, extract_graph, VL_CHAT_URL


def _rule_split(text, min_chunk=200, max_chunk=6000):
    """规则切分: 按 Markdown 标题章节 + 段落切块, 适配表格/标题密集文档.
    模型切片失败(全是碎片标题)时的降级方案."""
    text = text.strip()
    if not text:
        return []
    lines = text.split("\n")
    chunks, cur = [], ""
    in_code = False
    for ln in lines:
        s = ln.rstrip()
        # 代码块处理
        if s.strip().startswith("```"):
            in_code = not in_code
            cur += ln + "\n"
            continue
        # 章节标题 -> 切新块
        if not in_code and (s.startswith("# ") or s.startswith("## ")
                            or s.startswith("### ")):
            if len(cur.strip()) >= min_chunk:
                chunks.append(cur.strip())
                cur = ln + "\n"
            elif cur.strip():
                cur += ln + "\n"
            else:
                cur = ln + "\n"
            continue
        cur += ln + "\n"
        # 超长切分
        if len(cur) >= max_chunk:
            chunks.append(cur.strip())
            cur = ""
    if cur.strip():
        chunks.append(cur.strip())
    # 合并过小的尾部
    out = []
    for c in chunks:
        if out and len(c) < min_chunk:
            out[-1] = out[-1] + "\n" + c
        else:
            out.append(c)
    return [c for c in out if c]


def ingest_text(title, text, path=None, chunk_size=6000, progress=True):
    """导入一段文本到 RAG.
    返回 {"doc_id":.., "chunks":N, "nodes":N, "edges":N}
    """

    def _clean_chunks(blocks, min_len=60):
        """净化切片: 丢弃纯垃圾碎片; 短块(<min_len)并入前一块, 保证语义完整."""
        cleaned = []
        for b in blocks:
            b = (b or "").strip()
            if not b:
                continue
            # 纯标题/单一标记碎片(纯ASCII符号、极短) -> 尝试并入上一块
            if len(b) < min_len:
                if cleaned and len(cleaned[-1]) + len(b) < 6000:
                    cleaned[-1] = cleaned[-1] + "\n" + b
                elif len(b) >= 4:  # 至少有点内容才保留
                    cleaned.append(b)
                continue
            cleaned.append(b)
        return cleaned

    conn = connect()
    doc_id = add_document(conn, title, path=path, src_type="text")
    n_chunks = n_nodes = n_edges = 0

    # --- 切片 ---
    raw_chunks = slice_text(VL_CHAT_URL, text)
    if isinstance(raw_chunks, dict):  # 模型可能包一层
        for v in raw_chunks.values():
            if isinstance(v, list) and v and isinstance(v[0], str):
                raw_chunks = v
                break
    if not isinstance(raw_chunks, list):
        # 兜底: 简单按段落分
        raw_chunks = [t.strip() for t in text.split("\n\n") if t.strip()]

    # --- 切片净化: 丢弃/合并碎片, 保证每块是完整语义单元 ---
    raw_chunks = _clean_chunks(raw_chunks)

    # --- 若净化后仍无完整语义块(全是碎片标题), 判定模型切片失败, 改用规则切分 ---
    if not raw_chunks or max((len(b) for b in raw_chunks), default=0) < 100:
        raw_chunks = _rule_split(text)

    # 把超大块再切小 (保证单块不会超模型上下文)
    def _squeeze(blocks, maxc=chunk_size):
        out = []
        for b in blocks:
            while len(b) > maxc:
                out.append(b[:maxc])
                b = b[maxc:]
            if b:
                out.append(b)
        return out
    seq_chunks = _squeeze(raw_chunks)

    # 逐块: 抽取 + embedding + 写库
    all_texts_for_embed = []
    for seq, c in enumerate(seq_chunks):
        all_texts_for_embed.append(c)
        add_chunk(conn, doc_id, seq, c)
    n_chunks = len(seq_chunks)

    # 批量 embedding (按批调用 bge-m3)
    embs = embed_texts(all_texts_for_embed)
    cur = conn.cursor()
    for seq, (c, emb) in enumerate(zip(seq_chunks, embs)):
        cur.execute("UPDATE chunks SET embedding=%s WHERE doc_id=%s AND seq=%s",
                    (emb, doc_id, seq))
    conn.commit()

    # --- 每块抽取图谱三元组 ---
    for seq, c in enumerate(seq_chunks):
        try:
            g = extract_graph(VL_CHAT_URL, c)
        except Exception as e:
            if progress:
                print(f"  [warn] chunk{seq} 抽取失败: {e}", file=sys.stderr)
            continue
        ents = g.get("entities", []) or []
        rels = g.get("relations", []) or []
        chunk_row = cur.execute(
            "SELECT id FROM chunks WHERE doc_id=%s AND seq=%s",
            (doc_id, seq)).fetchone()
        chunk_id = chunk_row["id"] if chunk_row else None

        # 实体 -> nodes (含 embedding), 建 chunk_entities 关联
        name2id = {}
        ent_names = [e.get("head", "").strip() for e in ents if e.get("head")]
        if ent_names:
            ent_embs = embed_texts(ent_names)
            for e, e_emb in zip(ents, ent_embs):
                name = e.get("head", "").strip()
                if not name:
                    continue
                nid = upsert_node(conn, name, kind=e.get("type", "entity"),
                                  description=None, embedding=e_emb)
                name2id[name] = nid
                if chunk_id:
                    link_chunk_node(conn, chunk_id, nid)
        # 关系 -> edges
        for r in rels:
            h = (r.get("head") or "").strip()
            t = (r.get("tail") or "").strip()
            if h in name2id and t in name2id:
                add_edge(conn, name2id[h], name2id[t], r.get("relation", ""),
                         doc_id, weight=1.0)
                n_edges += 1
    # 修正节点计数
    cur.execute("SELECT COUNT(*) AS c FROM nodes")
    n_nodes = cur.fetchone()["c"]
    conn.commit()
    conn.close()
    if progress:
        print(f"[OK] doc={title} chunks={n_chunks} nodes_total={n_nodes} edges={n_edges}")
    return {"doc_id": doc_id, "chunks": n_chunks, "nodes": n_nodes, "edges": n_edges}


if __name__ == "__main__":
    sample = sys.argv[1] if len(sys.argv) > 1 else "神经网络是机器学习的一个子领域。卷积神经网络(CNN)擅长图像。Transformer引入注意力机制，是大语言模型的基础。OpenAI的GPT使用Transformer。"
    r = ingest_text("测试文档", sample)
    print("result:", r)
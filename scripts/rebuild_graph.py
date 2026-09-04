#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图谱重建: 清空现有 nodes/edges/chunk_entities, 只用"领域综述"文档重建干净图谱.
用法: python3 scripts/rebuild_graph.py <综述doc_id,...>   (空则用所有含"知识简介"的文档)
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "<your-project-path>/ragkg")

from db import connect, add_chunk, vector_search, keyword_search
from db import upsert_node, add_edge, link_chunk_node
from llm import embed_texts, extract_graph, VL_CHAT_URL
from task_progress import Progress, clear

def main():
    ids = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else None
    conn = connect()
    cur = conn.cursor()

    # 选定综述文档
    if ids:
        cur.execute("SELECT id,title FROM documents WHERE id = ANY(%s)", (ids,))
    else:
        cur.execute("SELECT id,title FROM documents WHERE title LIKE '%知识简介%' OR title LIKE '%综述%'")
    docs = cur.fetchall()
    doc_ids = [d["id"] for d in docs]
    print(f"将用 {len(docs)} 篇综述重建图谱:", [d["title"] for d in docs])

    # 备份旧图谱数据到独立表
    for t in ("nodes_backup", "edges_backup", "chunk_entities_backup"):
        cur.execute(f"DROP TABLE IF EXISTS {t}")
    cur.execute("CREATE TABLE nodes_backup AS SELECT * FROM nodes")
    cur.execute("CREATE TABLE edges_backup AS SELECT * FROM edges")
    cur.execute("CREATE TABLE chunk_entities_backup AS SELECT * FROM chunk_entities")
    conn.commit()
    print("旧图谱已备份到 *_backup 表")

    # 清空图谱(保留 documents/chunks/embedding)
    cur.execute("DELETE FROM chunk_entities")
    cur.execute("DELETE FROM edges")
    cur.execute("DELETE FROM nodes")
    cur.execute("SELECT setval('nodes_id_seq', 1, false)")
    conn.commit()
    print("已清空 nodes/edges/chunk_entities")

    # 对每篇综述的每个 chunk 重新抽取
    tot_nodes = tot_edges = 0
    all_chunks = []
    for d in docs:
        cur.execute("SELECT c.id, c.text FROM chunks c WHERE c.doc_id=%s ORDER BY c.seq", (d["id"],))
        all_chunks.extend((d["id"], c["id"], c["text"]) for c in cur.fetchall())
    total_chunks = len(all_chunks)
    prog = Progress("图谱重建", total=total_chunks, id="graph_rebuild")
    try:
        for idx, (doc_id, chunk_id, ctext) in enumerate(all_chunks):
            try:
                g = extract_graph(VL_CHAT_URL, ctext[:8000])
            except Exception as e:
                print(f"  [warn] chunk{chunk_id}: {e}")
                prog.tick(f"[{idx+1}/{total_chunks}] 抽取失败")
                continue
            ents, rels = g.get("entities", []), g.get("relations", [])
            if not ents:
                prog.tick(f"[{idx+1}/{total_chunks}] 无实体")
                continue
            name2id = {}
            ent_names = [e.get("head","").strip() for e in ents if e.get("head")]
            if not ent_names:
                prog.tick(f"[{idx+1}/{total_chunks}] 无实体名")
                continue
            try:
                embs = embed_texts(ent_names)
            except Exception as e:
                embs = [None]*len(ent_names)
            for e, emb in zip(ents, embs):
                name = (e.get("head") or "").strip()
                if not name: continue
                nid = upsert_node(conn, name, kind=e.get("type","concept"), embedding=emb)
                name2id[name] = nid
                link_chunk_node(conn, chunk_id, nid)
            for r in rels:
                h, t = (r.get("head") or "").strip(), (r.get("tail") or "").strip()
                if h in name2id and t in name2id:
                    add_edge(conn, name2id[h], name2id[t], r.get("relation",""), doc_id)
                    tot_edges += 1
            tot_nodes += len(ent_names)
            conn.commit()
            prog.tick(f"[{idx+1}/{total_chunks}] {len(ents)}实体/{len(rels)}关系")
    except Exception as e:
        prog.error(f"重建出错: {e}")
        raise
    finally:
        prog.done(f"完成: {tot_nodes}节点/{tot_edges}边（来自 {total_chunks} chunks）")
    conn.close()
    print(f"\n完成: 共 {tot_nodes} 节点录入, {tot_edges} 边录建")

if __name__ == "__main__":
    main()
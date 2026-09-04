# -*- coding: utf-8 -*-
"""检索编排: 向量检索 + 关键词兜底 + 实体识别 + 图谱扩展."""
import re
from db import connect, vector_search, keyword_search, get_node_by_name, graph_expand
from llm import embed_texts


def _load_node_names(conn, limit=20000):
    cur = conn.cursor()
    cur.execute("SELECT name FROM nodes LIMIT %s", (limit,))
    return [r["name"] for r in cur.fetchall()]


def _find_matching_nodes(conn, question):
    """子串匹配: 找出 问题文本里出现的图谱节点名 (倒序, 长名优先)."""
    names = _load_node_names(conn)
    matched = []
    for n in sorted(names, key=len, reverse=True):
        if n and n in question and n not in matched:
            matched.append(n)
    return matched


def retrieve(question, top_k=4, expand=True, conn=None):
    """混合检索: 返回 {"chunks":[...], "nodes":[...], "graph":{...}}"""
    close = conn is None
    if conn is None:
        conn = connect()
    # 1. 向量检索
    emb = embed_texts(question)[0]
    chunks = vector_search(conn, emb, top_k=top_k)
    # 2. 图谱: 用问题里出现的节点名做子串匹配, 扩展子图
    graph = {"seed_nodes": [], "edges": []}
    if expand:
        matched = _find_matching_nodes(conn, question)
        for name in matched:
            n = get_node_by_name(conn, name)
            if n:
                g = graph_expand(conn, [n["id"]], depth=1, limit=60)
                graph["seed_nodes"].extend(g["seed_nodes"])
                graph["edges"].extend(g["edges"])
    # 去重 edge
    seen = set(); dedup_edges = []
    for e in graph["edges"]:
        k = (e["id"])
        if k not in seen:
            seen.add(k); dedup_edges.append(e)
    graph["edges"] = dedup_edges
    if close:
        conn.close()
    return {"chunks": chunks, "graph": graph, "n_chunks": len(chunks),
            "matched_nodes": graph.get("seed_nodes", []),
            "n_edges": len(graph["edges"])}
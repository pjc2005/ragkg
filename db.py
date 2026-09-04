# -*- coding: utf-8 -*-
"""RAG 知识图谱 — 数据库访问层 (PostgreSQL + pgvector)."""
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector

DSN = "dbname=ragkg user=anaya host=/var/run/postgresql"


def connect():
    conn = psycopg.connect(DSN, row_factory=dict_row)
    register_vector(conn)
    return conn


def ensure_schema(conn):
    """幂等建表 (与本机 /tmp/ragkg_schema.sql 一致, 供独立运行确保)."""
    cur = conn.cursor()
    cur.execute("""CREATE EXTENSION IF NOT EXISTS vector""")
    conn.commit()


# ---------------- documents ----------------
def add_document(conn, title, path=None, src_type="text"):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO documents (title, path, src_type) VALUES (%s,%s,%s) RETURNING id",
        (title, path, src_type))
    return cur.fetchone()["id"]


# ---------------- chunks ----------------
def add_chunk(conn, doc_id, seq, text, embedding=None):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chunks (doc_id, seq, text, embedding) VALUES (%s,%s,%s, %s) RETURNING id",
        (doc_id, seq, text, embedding))
    return cur.fetchone()["id"]


def vector_search(conn, embedding, top_k=5, distance="<=>"):
    """向量相似检索. distance: <=> L2, <#> ip, <-> cosine."""
    cur = conn.cursor()
    # pgvector 运算符需要 vector 类型; 用 text 字面量 + ::vector 强转
    if not isinstance(embedding, str):
        vec_lit = "[" + ",".join(repr(float(x)) for x in embedding) + "]"
    else:
        vec_lit = embedding
    cur.execute(
        f"SELECT c.id, c.doc_id, c.seq, c.text, d.title, "
        f"(c.embedding {distance} %s::vector) AS dist "
        f"FROM chunks c JOIN documents d ON d.id=c.doc_id "
        f"WHERE c.embedding IS NOT NULL "
        f"ORDER BY c.embedding {distance} %s::vector "
        f"LIMIT %s",
        (vec_lit, vec_lit, top_k))
    return cur.fetchall()


def keyword_search(conn, q, top_k=5):
    cur = conn.cursor()
    cur.execute(
        "SELECT c.id, c.doc_id, c.seq, c.text, d.title "
        "FROM chunks c JOIN documents d ON d.id=c.doc_id "
        "WHERE c.text ILIKE %s ORDER BY length(c.text) LIMIT %s",
        (f"%{q}%", top_k))
    return cur.fetchall()


# ---------------- nodes / edges ----------------
def upsert_node(conn, name, kind="entity", description=None, embedding=None):
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO nodes (name, kind, description, embedding)
           VALUES (%s,%s,%s,%s)
           ON CONFLICT (name) DO UPDATE SET kind=EXCLUDED.kind
           RETURNING id, (xmax=0) AS inserted""",
        (name, kind, description, embedding))
    row = cur.fetchone()
    return row["id"]


def add_edge(conn, src_id, dst_id, relation, doc_id, weight=1.0):
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO edges (src_id, dst_id, relation, doc_id, weight)
           VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (src_id, dst_id, relation, doc_id) DO NOTHING""",
        (src_id, dst_id, relation, doc_id, weight))


def link_chunk_node(conn, chunk_id, node_id):
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chunk_entities (chunk_id, node_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (chunk_id, node_id))


def graph_expand(conn, node_ids, depth=1, limit=200):
    """给定实体id集合, 返回其邻接子图 (节点+边)."""
    cur = conn.cursor()
    cur.execute(
        """SELECT DISTINCT n.id, n.name, n.kind, n.description
           FROM nodes n
           WHERE n.id = ANY(%s)""", (list(node_ids),))
    seeds = cur.fetchall()
    cur.execute(
        """SELECT e.id, e.src_id, e.dst_id, e.relation, e.weight,
                  sn.name AS src_name, dn.name AS dst_name
           FROM edges e
           JOIN nodes sn ON sn.id=e.src_id
           JOIN nodes dn ON dn.id=e.dst_id
           WHERE e.src_id = ANY(%s) OR e.dst_id = ANY(%s)
           ORDER BY e.weight DESC LIMIT %s""",
        (list(node_ids), list(node_ids), limit))
    edges = cur.fetchall()
    return {"seed_nodes": seeds, "edges": edges}


def get_node_by_name(conn, name):
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM nodes WHERE name=%s", (name,))
    return cur.fetchone()


# ---------- 关系方向表 (父/子语义) ----------
# head=父 的关系词(正常方向): 提出/创建/开发/拥有/推动/主导/成立/发明/推出/发布/研究/发展...
HEAD_IS_PARENT = (
    "提出", "创建", "开发", "发明", "推出", "发布", "拥有", "包含",
    "推动", "主导", "成立", "研究", "发展", "建立", "发起", "领导",
    "制定", "采用",
)
# head=子 的关系词(方向反转: 实际 tail 才是父/上层)
HEAD_IS_CHILD = (
    "属于", "使用", "位于", "依赖", "基于", "采用", "受益", "得益于",
    "由", "是", "成为", "隶属于", "设立于",
)
# 注意 "采用" 同时出现在两表, 按先查主表处理; 实现时 HEAD_IS_PARENT 优先即可


def edge_direction(relation):
    """给定关系词, 返回该边里 ‘head 相对 tail 的语义身份’:
    返回 'parent' 表示 head 是父(tail 是子), 'child' 表示 head 是子(tail 是父)。
    用于修正: 有些关系里 head 虽在前, 但语义上是子(如 ‘X使用Y’ 里 X 才是使用者/父;
              ‘X被Y推动’ 里 X 是被动的子, Y 才是父)。
    """
    if not relation:
        return "parent"
    # 被动态: "被..""、含"被" 多半 center=被动作(子)
    if "被" in relation or relation.startswith("由"):
        return "child"
    if relation in HEAD_IS_CHILD and relation not in HEAD_IS_PARENT:
        return "child"   # head 是子, tail 是父
    return "parent"      # head 是父, tail 是子 (默认含 HEAD_IS_PARENT)


def node_neighborhood(conn, center_id, limit=200):
    """以 center 为中心, 返回其直系邻域并按关系词方向修正父子.
    对每条边(head -rel-> tail): edge 里的 'parent' 身份节点 由其关系词方向决定;
    'child' 身份即相对的另一端。 然后以 center 为准, 把另一端归为 center 的父或子。
    返回 {center, parents:[{id,name,kind,relation}], children:[{...}]}
    """
    cur = conn.cursor()
    cur.execute("SELECT id, name, kind FROM nodes WHERE id=%s", (center_id,))
    center = cur.fetchone()
    if not center:
        return None
    cur.execute(
        """SELECT e.id, e.relation, e.src_id AS hid, sn.name AS hname, sn.kind AS hkind,
                  e.dst_id AS tid, dn.name AS tname, dn.kind AS tkind
           FROM edges e
           JOIN nodes sn ON sn.id=e.src_id
           JOIN nodes dn ON dn.id=e.dst_id
           WHERE e.src_id=%s OR e.dst_id=%s LIMIT %s""",
        (center_id, center_id, limit))
    edges = cur.fetchall()
    parents, children = [], []
    seen = set()
    for e in edges:
        rel = e["relation"]
        # head 是否父
        head_is_parent = (edge_direction(rel) == "parent")
        # head 是父 -> head=parent, tail=child; 否则 head=child, tail=parent
        parent_id, parent_name, parent_kind = (
            (e["hid"], e["hname"], e["hkind"]) if head_is_parent else (e["tid"], e["tname"], e["tkind"]))
        child_id, child_name, child_kind = (
            (e["tid"], e["tname"], e["tkind"]) if head_is_parent else (e["hid"], e["hname"], e["hkind"]))
        # center 是 parent 侧还是 child 侧
        if center_id == parent_id:
            if child_id == center_id:
                continue
            key = ("child", child_id, rel)
            if key not in seen:
                seen.add(key)
                children.append({"id": child_id, "name": child_name, "kind": child_kind,
                                 "relation": rel, "edge_id": e["id"]})
        elif center_id == child_id:
            if parent_id == center_id:
                continue
            key = ("parent", parent_id, rel)
            if key not in seen:
                seen.add(key)
                parents.append({"id": parent_id, "name": parent_name, "kind": parent_kind,
                                "relation": rel, "edge_id": e["id"]})
    return {"center": center, "parents": parents, "children": children}


def get_document(conn, doc_id):
    """返回单个文档行(元信息)."""
    cur = conn.cursor()
    cur.execute("SELECT id, title, path, src_type, created_at FROM documents WHERE id=%s",
                (doc_id,))
    return cur.fetchone()


def document_text(conn, doc_id):
    """重组文档全文: 优先读物理文件, 否则从 chunks 按 seq 拼接."""
    row = get_document(conn, doc_id)
    if not row:
        return None, None
    path = row["path"]
    full = None
    if path and os.path.exists(path):
        p = Path(path)
        if p.suffix.lower() in (".pdf",):
            try:
                from pypdf import PdfReader
                r = PdfReader(str(p))
                full = "\n".join((pg.extract_text() or "") for pg in r.pages)
            except Exception:
                full = None
        else:
            full = p.read_text(encoding="utf-8", errors="ignore")
    if full is None:
        cur = conn.cursor()
        cur.execute("SELECT text FROM chunks WHERE doc_id=%s ORDER BY seq", (doc_id,))
        full = "\n\n".join(r["text"] for r in cur.fetchall())
    return row, full


def node_detail(conn, node_id, limit=20):
    """节点详情: 基本信息 + 关联原文片段 + 来源文档."""
    cur = conn.cursor()
    cur.execute("""SELECT n.id, n.name, n.kind, n.description,
                          (SELECT count(*) FROM edges e WHERE e.src_id=n.id OR e.dst_id=n.id) AS degree
                   FROM nodes n WHERE n.id=%s""", (node_id,))
    base = cur.fetchone()
    if not base:
        return None
    # 关联片段(chunk_entities -> chunks -> documents)
    cur.execute("""SELECT c.id AS chunk_id, c.doc_id, c.seq, c.text, d.title AS doc_title
                   FROM chunk_entities ce
                   JOIN chunks c ON c.id=ce.chunk_id
                   JOIN documents d ON d.id=c.doc_id
                   WHERE ce.node_id=%s
                   ORDER BY c.doc_id, c.seq LIMIT %s""", (node_id, limit))
    snippets = cur.fetchall()
    # 来源文档去重
    cur.execute("""SELECT DISTINCT d.id, d.title, d.path
                   FROM chunk_entities ce
                   JOIN chunks c ON c.id=ce.chunk_id
                   JOIN documents d ON d.id=c.doc_id
                   WHERE ce.node_id=%s""", (node_id,))
    docs = cur.fetchall()
    return {"node": base, "snippets": snippets, "documents": docs}
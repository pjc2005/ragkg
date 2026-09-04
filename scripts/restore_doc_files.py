#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 doc129 重建物理 .md 文件(从chunks重组)并关联 path, 使其与其他综述一致.
也顺便给任何 path 为空但有完整 chunks 的文档重建. 用法: python3 scripts/restore_doc_files.py <doc_id...>
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "<your-project-path>/ragkg")
from db import connect

KNOW = "<your-project-path>/ragkg/files/knowledge"

def main():
    ids = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 else []
    conn = connect()
    cur = conn.cursor()
    query = "SELECT id,title,path FROM documents WHERE id=ANY(%s)" if ids else \
            "SELECT id,title,path FROM documents WHERE (path IS NULL OR path='')"
    cur.execute(query, (ids,))
    docs = cur.fetchall()
    made = 0
    for d in docs:
        cur.execute("SELECT text FROM chunks WHERE doc_id=%s ORDER BY seq", (d["id"],))
        parts = [r["text"] for r in cur.fetchall()]
        if not parts:
            continue
        full = "\n\n".join(parts)
        if len(full) < 50:
            continue
        fname = f"doc_{d['id']}.md" if not (d.get("title") or "").strip() else d["title"]+".md"
        # 安全文件名
        import re
        fname = re.sub(r'[\\/:*?"<>|]', "_", fname)[:80]
        path = os.path.join(KNOW, fname)
        open(path, "w", encoding="utf-8").write(full)
        cur.execute("UPDATE documents SET path=%s, src_type='markdown' WHERE id=%s", (path, d["id"]))
        made += 1
        print(f"重建: doc{d['id']} {d['title']} -> {fname} ({len(full)}字符)")
    conn.commit()
    conn.close()
    print(f"共重建 {made} 个文档的物理文件")

if __name__ == "__main__":
    main()
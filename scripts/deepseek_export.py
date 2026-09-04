#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 DeepSeek 导出 conversations.json → 按会话整块渲染问答对 md。
只保留 REQUEST(用户提问) + RESPONSE(DeepSeek回答), 过滤 THINK/SEARCH/FILE。
输出: <outdir>/<序号>_<会话标题>.md
用法: python3 deepseek_export.py conversations.json <会话ID们...(用标题子串匹配, 缺省全部)> <outdir>
"""
import json, re, sys, os
from pathlib import Path

KEEP = {"REQUEST", "RESPONSE"}


def cname(f):
    return f.get("name") or f.get("meta", {}).get("name") if isinstance(f.get("meta"), dict) else f.get("name")


def clean_citation(text):
    """去除 DeepSeek 回答保留的引用标记 [citation:N] / [!citation:N]."""
    return re.sub(r'\[\s*!?\s*citation\s*:\s*\d+\s*\]', '', ' ' + text + ' ').strip()


def render_conversation(conv):
    """按 mapping 树前序遍历, 将 REQUEST/RESPONSE 渲染为问答对文本."""
    m = conv.get("mapping", {})
    title = (conv.get("title") or "untitled").strip()
    lines = [f"# {title}", ""]

    def walk(nid):
        if not nid or not isinstance(nid, str):
            return
        node = m.get(nid)
        if not node:
            return
        msg = node.get("message")
        if msg:
            frags = msg.get("fragments") or []
            # 合并同一消息的 REQUEST/RESPONSE 片段
            blob, role = [], None
            for f in frags:
                ft = f.get("type")
                if ft in KEEP:
                    c = clean_citation(f.get("content") or "").strip()
                    if c:
                        blob.append(c)
                    if ft == "REQUEST":
                        role = "用户"
                    elif ft == "RESPONSE":
                        role = "助手" if role is None else role
            if blob and role:
                lines.append(f"**{role}**:\n" + "\n".join(blob))
                lines.append("")
        for ch in node.get("children", []):
            walk(ch)

    walk("root")
    text = "\n".join(lines).strip()
    if len(text) < 50:  # 空会话(全是推理/搜索)跳过
        return None
    return text


def safe_name(title):
    name = re.sub(r'[\\/:*?"<>|]', "_", title).strip()
    return name[:60] or "untitled"


def main():
    src, outdir = sys.argv[1], sys.argv[3] if len(sys.argv) > 3 else "deepseek_md"
    filters = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2].strip() else []
    convs = json.load(open(src, encoding="utf-8"))
    os.makedirs(outdir, exist_ok=True)

    chosen, skipped = [], 0
    for conv in convs:
        title = conv.get("title", "")
        if filters and not any(f.strip() in title for f in filters):
            continue
        out = render_conversation(conv)
        if not out:
            skipped += 1
            continue
        p = Path(outdir) / (safe_name(title) + ".md")
        p.write_text(out, encoding="utf-8")
        chosen.append((title, len(out)))

    print(f"导出 {len(chosen)} 篇, 跳过 {skipped} 空会话")
    for t, n in sorted(chosen, key=lambda x: -x[1]):
        print(f"  {n:>7}字符  {t}")
    print("输出目录:", os.path.abspath(outdir))


if __name__ == "__main__":
    main()
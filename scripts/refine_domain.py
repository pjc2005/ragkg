#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""领域知识提炼管线: 把 DeepSeek 废弃问答对 -> 结构化领域综述.

用法:
  python3 scripts/refine_domain.py "<领域名>" "会话标题1,会话标题2,..."
流程:
  1) 从 conversations.json 提取指定会话的问答对(reduce reduced)
  2) 每篇用 9B 提炼成知识卡片
  3) 卡片分批(group)合并成小节(适配16K ctx)
  4) 汇总成一篇完整领域综述 -> <outdir>/<领域名>知识简介.md
需: 本地Qwen9B(:8080) 正常; conversations.json 在 /tmp/deepseek_probe/
"""
import glob, httpx, os, sys, json

QA_URL = "http://127.0.0.1:8080/v1/chat/completions"
SRC = "/tmp/deepseek_probe/conversations.json"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deepseek_export import clean_citation

KEEP = {"REQUEST", "RESPONSE"}

def chat(prompt, max_tokens=4000, system=None):
    msgs = []
    if system: msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    r = httpx.post(QA_URL, json={"messages": msgs, "max_tokens": max_tokens, "temperature": 0.25},
                   timeout=900, trust_env=False)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def render_conv(conv, max_len=60000):
    title = conv.get("title", "").strip()
    m = conv.get("mapping", {})
    lines, total = [f"# {title}", ""], 0
    def walk(nid):
        nonlocal total
        node = m.get(nid)
        if not node: return
        msg = node.get("message")
        if msg:
            blob, role = [], None
            for f in (msg.get("fragments") or []):
                ft = f.get("type")
                if ft in KEEP:
                    c = clean_citation(f.get("content") or "").strip()
                    if c: blob.append(c)
                    if ft == "REQUEST": role = "用户"
                    elif ft == "RESPONSE" and role is None: role = "助手"
            if blob and role:
                block = f"**{role}**:\n" + "\n".join(blob) + "\n"
                if total + len(block) > max_len: return
                lines.append(block); total += len(block)
        for ch in node.get("children", []):
            walk(ch)
    walk("root")
    return "\n".join(lines).strip()

GROUP_SYS = ("你是资深技术编辑。给定若干份关于同一领域的知识卡片，"
             "整合成一段结构清晰的小节 Markdown。合并重叠、保留关键数据/工具/参数/对比，中文。")
SUB_SYS = ("你是资深技术编辑，负责把若干段关于同一领域的章节笔记，"
           "汇编成一篇完整、有序、可作知识库权威资料的领域综述。"
           "合并重复、按逻辑组织章节，中文 Markdown，详实不冗余。")
CARD_SYS = ("你是领域知识提炼助手。给定用户与AI关于某主题的深度对话记录，"
            "提炼最有价值、可复用的知识要点，输出清晰 Markdown。"
            "只保留有检索价值的技术事实/方法论/工具对比/参数/避坑；丢弃临时交互。中文。")

def main():
    domain, titles = sys.argv[1], [t.strip() for t in sys.argv[2].split(",") if t.strip()]
    base = f"/tmp/refine_{domain}"
    src_dir, card_dir = os.path.join(base, "src"), os.path.join(base, "cards")
    os.makedirs(src_dir, exist_ok=True); os.makedirs(card_dir, exist_ok=True)
    convs = json.load(open(SRC, encoding="utf-8"))

    # 1. 提取会话
    sel = [c for c in convs if c.get("title") in titles]
    print(f"选取 {len(sel)}/{len(titles)} 个会话")
    for c in sel:
        txt = render_conv(c)
        if len(txt) > 500:
            open(os.path.join(src_dir, c["title"][:60] + ".md"), "w", encoding="utf-8").write(txt)

    # 2. 逐篇提炼卡片
    for f in sorted(os.listdir(src_dir)):
        card = os.path.join(card_dir, f)
        if os.path.exists(card): continue
        txt = open(os.path.join(src_dir, f), encoding="utf-8").read()
        try:
            out = chat(txt[:20000], system=CARD_SYS)
            open(card, "w", encoding="utf-8").write(out)
            print(f"  [卡片] {f} ({len(out)}字)")
        except Exception as e:
            print(f"  [ERR] {f}: {e}")

    # 3. 分组合并小节
    cards = sorted(glob.glob(os.path.join(card_dir, "*.md")))
    print(f"共 {len(cards)} 张卡片, 分组整合...")
    batch = max(1, (len(cards) + 2) // 3)
    sections = []
    for i in range(0, len(cards), batch):
        group = cards[i:i+batch]
        body = "\n\n".join("===== "+os.path.basename(c)+" =====\n"+open(c, encoding="utf-8").read() for c in group)
        sec = chat(body[:12000], max_tokens=3500, system=GROUP_SYS)
        sections.append(sec)

    # 4. 汇总
    allparts = "\n\n".join(sections)
    final = chat("整合以下章节为最终领域综述(优化顺序补引言,勿遗漏核心):\n\n"+allparts[:15000],
                 max_tokens=4500, system=SUB_SYS)
    outp = os.path.join(base, f"{domain}领域知识简介.md")
    open(outp, "w", encoding="utf-8").write(final)
    print(f"完成: {outp} ({len(final)}字符)")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    main()
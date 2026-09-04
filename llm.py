# -*- coding: utf-8 -*-
"""llama-server (OpenAI 兼容) 客户端: embedding + chat."""
import json
import httpx

# 端配置
EMBED_URL = "http://127.0.0.1:8998/v1/embeddings"   # bge-m3
VL_CHAT_URL = "http://127.0.0.1:8999/v1/chat/completions"  # Qwen3-VL-2B 切片/抽取
QA_CHAT_URL = "http://127.0.0.1:8080/v1/chat/completions"  # Qwen3.5-9B 问答

TIMEOUT = 300


def embed_texts(texts, model="bge-m3"):
    """bge-m3 embedding, 返回 list[list[float]] (1024 维)."""
    if isinstance(texts, str):
        texts = [texts]
    r = httpx.post(EMBED_URL, json={"input": texts, "model": model},
                   timeout=TIMEOUT, trust_env=False)
    r.raise_for_status()
    data = r.json()["data"]
    # data 顺序可能乱, 按 index 排
    data.sort(key=lambda x: x["index"])
    return [d["embedding"] for d in data]


def chat(url, messages, max_tokens=4096, temperature=0.3, json_mode=None,
         timeout=TIMEOUT):
    """通用 chat. json_mode=其 schema(json) 让后端输出结构化."""
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    r = httpx.post(url, json=payload, timeout=timeout, trust_env=False)
    r.raise_for_status()
    out = r.json()
    content = out["choices"][0]["message"].get("content") or ""
    return content


def chat_json(url, messages, max_tokens=4096, temperature=0.3):
    """chat 并解析 JSON 输出 (要求模型只吐 JSON)."""
    content = chat(url, messages, max_tokens=max_tokens,
                   temperature=temperature, json_mode=True)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # 提取首个平衡的 {..} 或 [..] 块, 容忍前后噪音
        import re
        for openc, closec in (("{", "}"), ("[", "]")):
            s = content.find(openc)
            if s < 0:
                continue
            depth = 0
            for i in range(s, len(content)):
                ch = content[i]
                if ch in "\"'":
                    quote = ch
                    i += 1
                    while i < len(content) and content[i] != quote:
                        if content[i] == "\\":
                            i += 1
                        i += 1
                    continue
                if ch == openc:
                    depth += 1
                elif ch == closec:
                    depth -= 1
                    if depth == 0:
                        # 跳过成对引号边界, 取平衡块
                        block = content[s:i + 1]
                        try:
                            return json.loads(block)
                        except json.JSONDecodeError:
                            break
        # 最终兜底: 从损坏的数组/对象中尽力提取所有双引号字符串
        import re as _re
        ss = _re.findall(r'"((?:[^"\\]|\\.)*)"', content, re.S)
        # 过滤掉明显是 json 键的短token
        vals = [s for s in ss if len(s) >= 2 and not s.startswith("head") and
                s not in ("entities", "relations", "type", "relation", "tail")]
        cleaned = vals[:100]
        # 若提取到足够多字符串, 视为数组
        if len(cleaned) >= 1:
            return cleaned
        raise ValueError(f"模型未返回有效 JSON: {content[:200]}")


# ---- 业务调用 ----

def slice_text(vl_url, text, max_chars=6000):
    """语义切片: 让 Qwen3-VL-2B 把长文本切成语义块, 返回 list[str]."""
    sysp = ("你是一个文档语义切片器。把用户提供的文档切分成若干语义自洽的文本块，"
            "每个块表达一个完整主题。块与块不重叠、不遗漏内容。"
            "只输出 JSON 数组，如 [\"块1\",\"块2\",...]，不要任何解释。")
    usr = text[:max_chars]
    try:
        out = chat_json(vl_url, [{"role": "system", "content": sysp},
                                 {"role": "user", "content": usr}])
    except ValueError:
        # 降级: 按段落切分, 保证文档能导入
        blocks = [t.strip() for t in text.split("\n\n") if t.strip()]
        return blocks if blocks else [text.strip() or " "]
    if isinstance(out, list):
        return [x for x in out if isinstance(x, str) and x.strip()]
    return [text.strip()]


def extract_graph(vl_url, chunk_text):
    """从单个切片抽取实体与关系三元组. 返回 {"entities":[{head,type}], "relations":[{head,relation,tail}]}."""
    sysp = ("你是知识图谱抽取器。从文本中抽取关键实体(人/组织/地点/概念/技术/产品等)"
            "以及它们之间的关系，构建知识图谱三元组(head, relation, tail)。"
            "只输出 JSON，格式:\n"
            '{"entities":[{"head":"实体名","type":"person|org|location|concept|tech|..."}],\n'
            ' "relations":[{"head":"实体A","relation":"关系","tail":"实体B"}]}\n'
            "实体名保持一致(去重/标准化)，不要胡编。只输出 JSON。")
    usr = chunk_text[:8000]
    try:
        g = chat_json(vl_url, [{"role": "system", "content": sysp},
                               {"role": "user", "content": usr}])
    except ValueError:
        return {"entities": [], "relations": []}
    # 容忍模型输出裸数组(实体列表), 规范化为标准结构
    if isinstance(g, list):
        g = {"entities": g, "relations": []}
    if not isinstance(g, dict):
        return {"entities": [], "relations": []}
    g.setdefault("entities", [])
    g.setdefault("relations", [])
    # 规范化 entities 元素: 裸字符串 -> {head, type:concept}
    norm_ents = []
    for e in g["entities"]:
        if isinstance(e, dict):
            norm_ents.append(e)
        elif isinstance(e, str) and e.strip():
            norm_ents.append({"head": e.strip(), "type": "concept"})
    g["entities"] = norm_ents
    return g


def answer_with_rag(qa_url, question, context_chunks, context_graph=None):
    """用检索到的 chunk 文本 + 图谱上下文, 让 Qwen9B 作答. 返回 (answer, sources)."""
    ctx = "\n\n".join(f"[片段{i+1}] {c['text']}" for i, c in enumerate(context_chunks))
    graph_txt = ""
    if context_graph and context_graph.get("edges"):
        lines = []
        for e in context_graph["edges"]:
            lines.append(f"{e['src_name']} --({e['relation']})--> {e['dst_name']}")
        graph_txt = "知识图谱关系:\n" + "\n".join(lines[:30])
    sysp = ("你是一个严谨的知识库问答助手。仅依据提供的资料回答；资料中没有的，"
            "明确说不知道，不要编造。回答用简洁中文，可给出推理。")
    usr = (f"参考资料:\n{ctx}\n\n"
           + (graph_txt + "\n\n" if graph_txt else "")
           + f"问题: {question}\n请依据以上资料回答。")
    answer = chat(qa_url, [{"role": "system", "content": sysp},
                           {"role": "user", "content": usr}],
                  max_tokens=1024, temperature=0.3)
    sources = [{"doc": c["title"], "seq": c["seq"], "text": c["text"]}
               for c in context_chunks]
    return answer, sources
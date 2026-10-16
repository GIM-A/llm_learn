"""
RAG 核心：向量检索 → Rerank → LLM 生成（支持流式、支持多轮历史）
"""
import requests
import time
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI

from . import config


# ========== 全局单例 ==========
_vectorstore = None
_llm = None


# ========== 系统提示词 ==========
# 抽成常量，generate_answer / stream_answer 共用，避免两处文案漂移
SYSTEM_PROMPT = "你是校园信息问答助手。根据提供的资料，用一句话直接回答问题。不要解释、不要分析、不要推理。"


# ========== 多轮对话：历史窗口（CARD-3.6）==========
# 最多保留最近几轮历史。一轮 = 一问一答。
# 先按轮数截断（而不是按 token）：够用、结果可解释、方便验收。
MAX_HISTORY_TURNS = 5


def init_vectorstore():
    global _vectorstore
    embeddings = DashScopeEmbeddings(model=config.EMBEDDING_MODEL)
    _vectorstore = Chroma(
        persist_directory=str(config.VECTOR_DIR),
        embedding_function=embeddings,
        collection_name=config.COLLECTION_NAME,
    )
    return _vectorstore


def get_vectorstore():
    if _vectorstore is None:
        raise RuntimeError("vectorstore 未初始化")
    return _vectorstore


def init_llm():
    global _llm
    _llm = ChatOpenAI(
        model=config.LLM_MODEL,
        api_key=config.require_api_key(),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0.1,
        extra_body={
            "enable_thinking": False,   # 关闭思考模式
        },
    )
    return _llm


def get_llm():
    if _llm is None:
        raise RuntimeError("LLM 未初始化")
    return _llm


# ========== 历史截断：成对截断，不拆 user/assistant ==========
def _truncate_history(history) -> list:
    """把历史消息成对截断到最近 MAX_HISTORY_TURNS 轮。

    规则（对应 CARD-3.6）：
      - 一轮 = 一问一答（最多 2 条 message）
      - 从最近往前取最近 MAX_HISTORY_TURNS 轮
      - 绝不把 user 和它对应的 assistant 拆开
      - "不完整尾"（只有 user、没有 assistant）也单独算一组

    history 为 None / 空时直接返回 []，从而让调用方的 messages
    与"没有多轮功能"时完全一致（向后兼容）。
    """
    if not history:
        return []

    # 1) 清洗：只接受 user / assistant 两种角色。
    #    这是防御性的一步 —— 接口是公开的（CORS 全开），客户端理论上能塞
    #    role="system" 的消息做提示词注入；这里直接过滤掉。
    cleaned = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        cleaned.append({"role": role, "content": content})

    if not cleaned:
        return []

    # 2) 按"以 user 开头"分组，每组即一轮
    turns = []
    for msg in cleaned:
        if msg["role"] == "user" or not turns:
            # 遇到新的 user → 开一轮新组；
            # turns 为空却先来了 assistant → 也先起一组兜底，避免越界
            turns.append([msg])
        else:
            turns[-1].append(msg)

    # 3) 只保留最近 MAX_HISTORY_TURNS 轮
    recent_turns = turns[-MAX_HISTORY_TURNS:]

    # 4) 摊平回一维 message 列表
    flattened = []
    for turn in recent_turns:
        flattened.extend(turn)
    return flattened


def _build_messages(question: str, context: str, history) -> list:
    """拼装发给 LLM 的 messages。

    顺序固定为： [system] + [截断后的历史...] + [当前问题(带资料)]
    历史为空时，结果与"单轮"完全一致。
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_truncate_history(history))
    messages.append(
        {"role": "user", "content": f"资料：\n{context}\n\n问题：{question}"}
    )
    return messages


# ========== 检索 + rerank ==========
def search_docs(question: str) -> str:
    """检索 + rerank，返回拼好的 context"""
    t0 = time.time()
    vectorstore = get_vectorstore()
    retriever = vectorstore.as_retriever(search_kwargs={"k": config.VECTOR_TOP_K})
    candidates = retriever.invoke(question)
    t1 = time.time()
    print(f"[timing] 向量检索：{t1 - t0:.2f}s，命中 {len(candidates)} 条")

    if not candidates:
        return ""

    headers = {
        "Authorization": f"Bearer {config.require_api_key()}",
        "Content-Type": "application/json",
    }
    data = {
        "model": config.RERANK_MODEL,
        "input": {
            "query": question,
            "documents": [c.page_content for c in candidates],
        },
        "parameters": {"top_n": config.RERANK_TOP_N, "return_documents": True},
    }
    resp = requests.post(config.RERANK_URL, headers=headers, json=data, timeout=30)
    resp.raise_for_status()
    reranked = resp.json()["output"]["results"]
    t2 = time.time()
    print(f"[timing] Rerank：{t2 - t1:.2f}s")

    context = "\n\n".join([item["document"]["text"] for item in reranked])
    return context


def build_prompt(question: str, context: str) -> str:
    # 被 scripts/debug_prompt.py 使用，保留原样（单轮拼接）
    return f"""根据以下资料回答问题。

【资料】
{context}

【问题】
{question}

请直接给出答案（一句话）："""


# ========== 生成答案（非流式）==========
def generate_answer(question: str, history=None) -> str:
    """history 为可选参数；不传时行为与旧版逐字节一致。"""
    context = search_docs(question)
    if not context:
        return "资料中未提到"

    messages = _build_messages(question, context, history)

    llm = get_llm()
    response = llm.invoke(messages)
    return response.content


# ========== 生成答案（流式）==========
def stream_answer(question: str, history=None):
    """history 为可选参数；不传时行为与旧版逐字节一致。"""
    context = search_docs(question)
    if not context:
        yield "资料中未提到"
        return

    messages = _build_messages(question, context, history)

    llm = get_llm()
    for chunk in llm.stream(messages):
        if chunk.content:
            yield chunk.content

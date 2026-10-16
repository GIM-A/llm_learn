"""
RAG 核心：向量检索 → Rerank → LLM 生成（支持流式）
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
    return f"""根据以下资料回答问题。

【资料】
{context}

【问题】
{question}

请直接给出答案（一句话）："""

def generate_answer(question: str) -> str:
    context = search_docs(question)
    if not context:
        return "资料中未提到"

    messages = [
        {"role": "system", "content": "你是校园信息问答助手。根据提供的资料，用一句话直接回答问题。不要解释、不要分析、不要推理。"},
        {"role": "user", "content": f"资料：\n{context}\n\n问题：{question}"},
    ]

    llm = get_llm()
    response = llm.invoke(messages)   # ⭐ 传 messages 而不是 prompt
    return response.content


def stream_answer(question: str):
    context = search_docs(question)
    if not context:
        yield "资料中未提到"
        return

    messages = [
        {"role": "system", "content": "你是校园信息问答助手。根据提供的资料，用一句话直接回答问题。不要解释、不要分析、不要推理。"},
        {"role": "user", "content": f"资料：\n{context}\n\n问题：{question}"},
    ]

    llm = get_llm()
    for chunk in llm.stream(messages):
        if chunk.content:
            yield chunk.content
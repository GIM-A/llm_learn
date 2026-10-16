"""
RAG 核心：向量检索 → Rerank → LLM 生成
"""
import requests
import time
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI

from . import config


# ========== 全局单例（由 main.py 的 lifespan 初始化）==========
_vectorstore = None
_llm = None


def init_vectorstore():
    """初始化向量库（应用启动时调一次）"""
    global _vectorstore
    embeddings = DashScopeEmbeddings(model=config.EMBEDDING_MODEL)
    _vectorstore = Chroma(
        persist_directory=str(config.VECTOR_DIR),
        embedding_function=embeddings,
        collection_name=config.COLLECTION_NAME,
    )
    return _vectorstore


def get_vectorstore():
    """获取向量库单例"""
    if _vectorstore is None:
        raise RuntimeError("vectorstore 未初始化，请先调 init_vectorstore()")
    return _vectorstore


def init_llm():
    """初始化 LLM（OpenAI 兼容接口，与项目1 一致）"""
    global _llm
    _llm = ChatOpenAI(
        model=config.LLM_MODEL,
        api_key=config.DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0.3,
    )
    return _llm


def get_llm():
    """获取 LLM 单例"""
    if _llm is None:
        raise RuntimeError("LLM 未初始化，请先调 init_llm()")
    return _llm


def search_docs(question: str) -> str:
    """检索 + rerank，返回拼好的 context 字符串"""
    t0 = time.time()

    # 1. 向量检索
    vectorstore = get_vectorstore()
    retriever = vectorstore.as_retriever(search_kwargs={"k": config.VECTOR_TOP_K})
    candidates = retriever.invoke(question)
    t1 = time.time()
    print(f"[timing] 向量检索：{t1 - t0:.2f}s，命中 {len(candidates)} 条")

    if not candidates:
        return ""

    # 2. Rerank
    headers = {
        "Authorization": f"Bearer {config.DASHSCOPE_API_KEY}",
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

    # 3. 拼 context
    context = "\n\n".join([item["document"]["text"] for item in reranked])
    return context


def generate_answer(question: str) -> str:
    """完整 RAG 流程：检索 → 拼 prompt → 调 LLM"""
    t0 = time.time()
    context = search_docs(question)
    t1 = time.time()
    print(f"[timing] 检索总耗时：{t1 - t0:.2f}s")

    if not context:
        return "资料中未提到"

    prompt = f"""请严格根据以下资料回答问题。如果资料里没有答案，就回答"资料中未提到"。不要编造任何信息。

资料：
{context}

问题：{question}"""

    llm = get_llm()
    response = llm.invoke(prompt)
    t2 = time.time()
    print(f"[timing] LLM 生成：{t2 - t1:.2f}s")
    print(f"[timing] 总耗时：{t2 - t0:.2f}s")

    return response.content
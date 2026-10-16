import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(dotenv_path=r"D:\llm_learn\.env")

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_chroma import Chroma
import requests
import dashscope

app = FastAPI()

# ========== 初始化：连接 vectorstore（启动时做一次）==========
embeddings = DashScopeEmbeddings(model="text-embedding-v3")
vectorstore = Chroma(
    persist_directory="./chroma_db_langchain",
    embedding_function=embeddings,
    collection_name="langchain"
)

# ========== 定义请求体 ==========
class ChatRequest(BaseModel):
    question: str

# ========== 根路径 ==========
@app.get("/")
def read_root():
    return {"message": "RAG API is running"}

# ========== RAG 接口 ==========
@app.post("/chat")
def chat(request: ChatRequest):
    question = request.question

    # 1. 向量检索
    retriever = vectorstore.as_retriever(search_kwargs={"k": 20})
    candidates = retriever.invoke(question)

    # 2. Rerank
    url = "https://ws-u2shhcjc8lz52mor.cn-beijing.maas.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    headers = {
        "Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "qwen3-rerank",
        "input": {
            "query": question,
            "documents": [c.page_content for c in candidates]
        },
        "parameters": {"top_n": 3, "return_documents": True}
    }
    resp = requests.post(url, headers=headers, json=data)
    reranked = resp.json()["output"]["results"]

    # 3. 拼 context
    context = "\n\n".join([item["document"]["text"] for item in reranked])

    # 4. 拼 prompt
    prompt = f"""请根据以下资料回答问题。如果资料里没有答案，就说"资料中未提到"。

资料：
{context}

问题：{question}"""

    # 5. 调 LLM
    dashscope.api_key = os.environ["DASHSCOPE_API_KEY"]
    llm_resp = dashscope.Generation.call(model="qwen-turbo", prompt=prompt)

    # 6. 返回
    return {"answer": llm_resp.output["text"]}
"""
FastAPI 入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config  # noqa: F401 触发 .env 加载
from .schemas import ChatRequest, ChatResponse, HealthResponse
from . import rag


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化向量库 + LLM"""
    print("[startup] 初始化向量库...")
    rag.init_vectorstore()
    print("[startup] 初始化 LLM...")
    rag.init_llm()
    print("[startup] 完成")
    yield
    print("[shutdown] 关闭")


app = FastAPI(title="校园知识库问答 API", lifespan=lifespan)

# ========== CORS（允许前端跨域）==========
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # 生产环境要改成具体域名
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=HealthResponse)
def root():
    return HealthResponse(status="ok", message="RAG API is running")


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    answer = rag.generate_answer(request.question)
    return ChatResponse(answer=answer)
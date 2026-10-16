"""
FastAPI 入口
"""
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from . import config  # noqa: F401
from .schemas import ChatRequest, ChatResponse, HealthResponse
from . import rag


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] 初始化向量库...")
    rag.init_vectorstore()
    print("[startup] 初始化 LLM...")
    rag.init_llm()
    print("[startup] 完成")
    yield
    print("[shutdown] 关闭")


app = FastAPI(title="校园知识库问答 API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== 挂载前端静态文件 ==========
FRONTEND_DIR = config.ROOT_DIR / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    """访问根路径 → 返回前端页面"""
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", message="RAG API is running")


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """非流式接口（保留，用于测试）"""
    # 双保险：即便客户端显式传了 history: null，也用 or [] 兜成空列表
    answer = rag.generate_answer(request.question, request.history or [])
    return ChatResponse(answer=answer)


@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    """流式接口：SSE 逐字返回（支持多轮历史）"""
    # 双保险：schemas 已默认空列表，这里再兜一层 None
    history = request.history or []

    def event_generator():
        try:
            for chunk in rag.stream_answer(request.question, history):
                # SSE 格式：data: xxx\n\n
                # 把换行符转义，避免破坏 SSE 格式
                safe = chunk.replace("\n", "\\n")
                yield f"data: {safe}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {e}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # 部署到 nginx 时防止缓冲
        },
    )

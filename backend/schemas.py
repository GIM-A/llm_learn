"""
Pydantic 请求/响应模型
"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求体"""

    question: str = Field(..., min_length=1, max_length=500, description="用户问题")

    # ========== 多轮对话历史（CARD-3.6）==========
    # 形如 [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
    # 说明：
    #   - 可选字段，不传时默认空列表（default_factory=list 保证每个实例拿到独立的新列表，
    #     避免用可变默认值 [] 导致多个请求共享同一个 list 的经典坑）
    #   - 只放"当前问题之前"的历史，当前问题由 question 字段单独承载
    history: list[dict] = Field(
        default_factory=list,
        description="历史对话消息列表（role/content），可选；不传则退化为单轮",
    )


class ChatResponse(BaseModel):
    """对话响应体"""

    answer: str = Field(..., description="模型回答")


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str
    message: str

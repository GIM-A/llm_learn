"""
Pydantic 请求/响应模型
"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求体"""
    question: str = Field(..., min_length=1, max_length=500, description="用户问题")


class ChatResponse(BaseModel):
    """对话响应体"""
    answer: str = Field(..., description="模型回答")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    message: str
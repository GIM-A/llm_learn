"""诊断 LLM 调用（独立测试）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config
from langchain_openai import ChatOpenAI

print(f"模型：{config.LLM_MODEL}")
print(f"API Key 前 10 位：{config.DASHSCOPE_API_KEY[:10]}...")
print(f"API Key 长度：{len(config.DASHSCOPE_API_KEY)}")
print()

llm = ChatOpenAI(
    model=config.LLM_MODEL,
    api_key=config.DASHSCOPE_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    temperature=0.1,
)

# ========== 测试1：最简单 ==========
print("=" * 60)
print("测试1：llm.invoke('你好')")
try:
    response = llm.invoke("你好")
    print(f"content 类型：{type(response.content)}")
    print(f"content 值：{response.content!r}")
    print(f"完整 response 对象：{response}")
    print(f"response_metadata：{response.response_metadata}")
    print(f"additional_kwargs：{response.additional_kwargs}")
except Exception as e:
    import traceback
    traceback.print_exc()

# ========== 测试2：messages 格式 ==========
print("\n" + "=" * 60)
print("测试2：messages 格式")
try:
    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "学校在哪个城市？资料：学校地处重庆市。"},
    ]
    response = llm.invoke(messages)
    print(f"content 类型：{type(response.content)}")
    print(f"content 值：{response.content!r}")
except Exception as e:
    import traceback
    traceback.print_exc()

# ========== 测试3：流式 ==========
print("\n" + "=" * 60)
print("测试3：流式")
try:
    chunks = []
    for chunk in llm.stream("一句话：中国的首都是"):
        chunks.append(chunk.content)
        print(f"  chunk: {chunk.content!r}")
    print(f"拼接：{''.join(chunks)!r}")
except Exception as e:
    import traceback
    traceback.print_exc()
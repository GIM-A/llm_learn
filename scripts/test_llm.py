"""单独测试 LLM 调用，定位问题"""
import sys
from pathlib import Path
# 把项目根加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config
import dashscope

print("=" * 50)
print(f"dashscope 版本：{dashscope.__version__}")
print(f"API Key 前 10 位：{config.DASHSCOPE_API_KEY[:10]}...")
print(f"API Key 长度：{len(config.DASHSCOPE_API_KEY)}")
print("=" * 50)

dashscope.api_key = config.DASHSCOPE_API_KEY

# 逐个测模型
for model in ["qwen-turbo-latest", "qwen-turbo", "qwen-plus", "qwen-flash"]:
    print(f"\n=== 测 {model} ===")
    try:
        resp = dashscope.Generation.call(model=model, prompt="你好")
        print(f"  status_code: {resp.status_code}")
        print(f"  message: {getattr(resp, 'message', 'N/A')}")
        print(f"  code: {getattr(resp, 'code', 'N/A')}")
        print(f"  request_id: {getattr(resp, 'request_id', 'N/A')}")
        if resp.status_code == 200:
            print(f"  ✅ output: {resp.output.get('text', 'N/A')}")
    except Exception as e:
        print(f"  ❌ 异常：{type(e).__name__}: {e}")

print("\n" + "=" * 50)
print("诊断完毕")
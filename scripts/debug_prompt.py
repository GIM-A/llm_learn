"""诊断 LLM 收到的 prompt"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import rag

question = "学校在哪个城市？"
context = rag.search_docs(question)
prompt = rag.build_prompt(question, context)

print("=" * 60)
print("LLM 收到的完整 prompt：")
print("=" * 60)
print(prompt)
print("=" * 60)
print(f"prompt 总长：{len(prompt)} 字")
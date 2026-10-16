"""诊断 RAG 检索链路"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, rag

print("=" * 60)
print("初始化...")
rag.init_vectorstore()
print("向量库 OK")

print("\n" + "=" * 60)
print("测试1：向量检索（不做 rerank）")
question = "学校在哪个城市？"
vectorstore = rag.get_vectorstore()
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
candidates = retriever.invoke(question)
print(f"检索到 {len(candidates)} 条")
for i, c in enumerate(candidates[:3]):
    print(f"\n--- 第 {i+1} 条 ---")
    print(c.page_content[:200])

print("\n" + "=" * 60)
print("测试2：search_docs（含 rerank）")
context = rag.search_docs(question)
print(f"context 长度：{len(context)}")
print(f"context 前 500 字：\n{context[:500]}")

print("\n" + "=" * 60)
print("测试3：完整 RAG")
rag.init_llm()
answer = rag.generate_answer(question)
print(f"答案：{answer}")

import os
import sys
import argparse
import requests
from pathlib import Path
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_chroma import Chroma

# 让脚本既能 `python -m scripts.evaluate` 运行，也能 `python scripts/evaluate.py` 运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, rag

# 连接向量库（路径由 config 从项目根推导，不再依赖当前工作目录）
embeddings = DashScopeEmbeddings(model="text-embedding-v3")
vectorstore = Chroma(
    persist_directory=str(config.VECTOR_DIR),
    embedding_function=embeddings,
    collection_name="langchain"
)

# 调 LLM 用的客户端：直接复用 backend/rag.py 的 ChatOpenAI（qwen3.7-flash + OpenAI 兼容端点）
llm = rag.init_llm()

# 测试集
test_cases = [
    # ========== 基础题（5 道）==========
    {"question": "学校在哪个城市？", "expected_keywords": ["重庆"]},
    {"question": "学校有几个校区？", "expected_keywords": ["两个", "合川", "綦江"]},
    {"question": "学校叫什么名字？", "expected_keywords": ["重庆移通学院"]},
    {"question": "学校有多少学生？", "expected_keywords": ["4500"]},
    {"question": "学校的校训是什么？", "expected_keywords": ["乐教", "乐学"]},

    # ========== 中等题（10 道）==========
    {"question": "綦江校区有哪些书院？", "expected_keywords": ["玉棠", "古剑", "观云"]},
    {"question": "学校有哪些学院？", "expected_keywords": ["通信", "计算机", "大数据"]},
    {"question": "学校的体育教育怎么样？", "expected_keywords": ["竞技", "健康"]},
    {"question": "学校有哪些国际交流项目？", "expected_keywords": ["德国", "国际"]},
    {"question": "学校获得过哪些荣誉？", "expected_keywords": ["教育部", "奖"]},
    {"question": "学校的就业情况怎么样？", "expected_keywords": ["就业", "留渝"]},
    {"question": "学校有哪些公共服务？", "expected_keywords": ["图书馆", "后勤"]},
    {"question": "学校的招标采购信息在哪看？", "expected_keywords": ["招标"]},
    {"question": "学校有哪些党群系统？", "expected_keywords": ["党委"]},
    {"question": "学校有哪些教学科研机构？", "expected_keywords": ["学院"]},

    # ========== 难题（5 道）==========
    {"question": "学校和哪些国家有合作？", "expected_keywords": ["德国", "美国"]},
    {"question": "学校有哪些特色育人模式？", "expected_keywords": ["四位一体", "双院制"]},
    {"question": "学校最近有什么新闻？", "expected_keywords": ["2025"]},
    {"question": "学校的现任领导有哪些？", "expected_keywords": ["校长"]},
    {"question": "学校的学生在哪些竞赛中获奖？", "expected_keywords": ["篮球", "武术"]},
]

# ========== 命令行参数 ==========
parser = argparse.ArgumentParser(description="RAG 检索链路评测")
parser.add_argument(
    "--dry-run",
    action="store_true",
    help="只跑第 1 题，验证链路是否打通（不跑完整 20 题评测）；若下游 LLM 不可用会 exit 1，属预期行为",
)
args = parser.parse_args()

if args.dry_run:
    test_cases = test_cases[:1]
    print(f"[dry-run] 只跑 {len(test_cases)} 题，用于验证链路\n")

correct = 0
for i, case in enumerate(test_cases):
    question = case["question"]
    expected = case["expected_keywords"]

    import requests

    # 向量检索 top 20
    retriever = vectorstore.as_retriever(search_kwargs={"k": 20})
    candidates = retriever.invoke(question)
    context = "\n\n".join([c.page_content for c in candidates])

    # Rerank 精排 top 3
    url = config.RERANK_URL
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
        "parameters": {"top_n": 10, "return_documents": True}
    }
    resp = requests.post(url, headers=headers, json=data)
    if args.dry_run:
        print(f"[dry-run] Rerank HTTP 状态码 = {resp.status_code}")
    reranked = resp.json()["output"]["results"]
    context = "\n\n".join([item["document"]["text"] for item in reranked])
    # 调 LLM（复用 backend/rag.py 的 ChatOpenAI + qwen3.7-flash + OpenAI 兼容端点）
    prompt = f"""请根据以下资料回答问题。

资料：
{context}

问题：{question}"""
    response = llm.invoke([{"role": "user", "content": prompt}])
    answer = response.content
    if args.dry_run:
        print(f"[dry-run] LLM 模型 = {response.response_metadata.get('model_name')}")
        print(f"[dry-run] 回答 = {answer}")

    hit = all(kw in answer for kw in expected)
    if hit:
        correct += 1
        print(f"✅ [{i + 1}] {question}")
    else:
        print(f"❌ [{i + 1}] {question}")
        print(f"   期望：{expected}")
        print(f"   实际：{answer[:100]}")
    print()

print(f"\n=== 准确率：{correct}/{len(test_cases)} = {correct / len(test_cases) * 100:.1f}% ===")

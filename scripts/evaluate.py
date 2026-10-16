
import os
import requests
import dashscope
from dotenv import load_dotenv
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_chroma import Chroma

load_dotenv(dotenv_path=r"D:\llm_learn\.env")
dashscope.api_key = os.environ["DASHSCOPE_API_KEY"]

# 连接向量库
embeddings = DashScopeEmbeddings(model="text-embedding-v3")
vectorstore = Chroma(
    persist_directory="./chroma_db_langchain",
    embedding_function=embeddings,
    collection_name="langchain"
)

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
        "parameters": {"top_n": 10, "return_documents": True}
    }
    resp = requests.post(url, headers=headers, json=data)
    reranked = resp.json()["output"]["results"]
    context = "\n\n".join([item["document"]["text"] for item in reranked])
    # 调 LLM
    prompt = f"""请根据以下资料回答问题。

资料：
{context}

问题：{question}"""
    resp = dashscope.Generation.call(model="qwen-turbo", prompt=prompt)
    answer = resp.output["text"]

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
# RAG 评测结果

## 测试集
- 20 道题，覆盖基础、中等、难题

## 三种策略对比
| 策略 | 准确率 |
|---|---|
| 纯向量检索 | 75% |
| 向量检索 + rerank（top 3） | 85% |
| 向量检索 + rerank（top 10） | 80% |

## 结论
- rerank 提升 10%
- top_n 太大反而降准
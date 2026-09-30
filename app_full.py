import os
import streamlit as st
import requests
import dashscope
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_community.chat_models.tongyi import ChatTongyi
from tavily import TavilyClient

# ========== 加载环境 ==========
try:
    if "DASHSCOPE_API_KEY" in st.secrets:
        os.environ["DASHSCOPE_API_KEY"] = st.secrets["DASHSCOPE_API_KEY"]
    else:
        raise KeyError("No key in secrets")
except Exception:
    if os.path.exists(r"D:\llm_learn\.env"):
        load_dotenv(dotenv_path=r"D:\llm_learn\.env")
    else:
        load_dotenv()

dashscope.api_key = os.environ["DASHSCOPE_API_KEY"]

# ========== 初始化向量库 ==========
@st.cache_resource
def init_rag():
    embeddings = DashScopeEmbeddings(model="text-embedding-v3")

    if not os.path.exists("./chroma_db_langchain"):
        print("向量库不存在，重新生成...")
        loader = TextLoader("crawled_data.txt", encoding="utf-8")
        docs = loader.load()
        splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)
        chunks = splitter.split_documents(docs)
        vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory="./chroma_db_langchain",
            collection_name="langchain"
        )
    else:
        vectorstore = Chroma(
            persist_directory="./chroma_db_langchain",
            embedding_function=embeddings,
            collection_name="langchain"
        )
    return vectorstore

vectorstore = init_rag()

# ========== 工具1：查学校资料 ==========
@tool
def search_school_docs(query: str) -> str:
    """查询重庆移通学院的相关信息。当用户问学校相关问题时调用此工具。"""
    retriever = vectorstore.as_retriever(search_kwargs={"k": 50})
    candidates = retriever.invoke(query)

    # 如果问的是"书院"，只保留含"书院"的 chunk
    if "书院" in query:
        candidates = [c for c in candidates if "书院" in c.page_content]

    # Rerank
    url = "https://ws-u2shhcjc8lz52mor.cn-beijing.maas.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    headers = {
        "Authorization": f"Bearer {os.environ['DASHSCOPE_API_KEY']}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "qwen3-rerank",
        "input": {
            "query": query,
            "documents": [c.page_content for c in candidates]
        },
        "parameters": {"top_n": 10, "return_documents": True}
    }
    resp = requests.post(url, headers=headers, json=data)
    reranked = resp.json()["output"]["results"]

    context = "\n\n".join([item["document"]["text"] for item in reranked])
    return context
# ========== 工具2：计算器 ==========
@tool
def calculator(expression: str) -> str:
    """执行数学计算。当用户需要算数时调用。参数是数学表达式，如 '(128+45)*3'。"""
    try:
        result = eval(expression)
        return f"计算结果：{expression} = {result}"
    except Exception as e:
        return f"计算失败：{e}"

# ========== 工具3：获取当前时间 ==========
from datetime import datetime, timezone, timedelta

@tool
def get_current_time() -> str:
    """获取当前时间。当用户问时间时调用此工具。"""
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    return f"当前时间：{now.strftime('%Y年%m月%d日 %H:%M')}"
# ========== 工具4：联网搜索 ==========
@tool
def search_web(query: str) -> str:
    """联网搜索最新信息。当学校资料里没有答案，或需要实时信息时调用此工具。
    参数是搜索关键词，如 '重庆移通学院 2026 招生计划'。"""
    try:
        client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
        results = client.search(query, max_results=3)

        text = ""
        for r in results["results"]:
            text += f"标题：{r['title']}\n内容：{r['content']}\n\n"
        return text
    except Exception as e:
        return f"搜索失败：{e}"

# ========== 创建 Agent ==========
@st.cache_resource
def init_agent():
    llm = ChatTongyi(model="qwen-turbo")
    tools = [search_school_docs, calculator, get_current_time, search_web]

    system_prompt = """你是一个校园助手，有 4 个工具：
    1. search_school_docs：查学校资料。遇到学校相关问题优先用它。
    2. calculator：数学计算。
    3. get_current_time：获取当前时间。
    4. search_web：联网搜索。当学校资料里没有答案时用它。

    规则：
    - 优先查学校资料（search_school_docs）
    - 如果资料里没有答案，再用 search_web
    - **只回答资料里明确提到的内容，不要猜测、不要编造**
    - **不确定的信息，直接说"资料中未明确"**
    - **不要自己拼接名称（如"子师湖书院"是错的）**
    - **不要编造细节（如"凤鸣书院设有风雨操场"）**"""

    memory = MemorySaver()   # ← 加这一行
    agent = create_react_agent(llm, tools, prompt=system_prompt, checkpointer=memory)   # ← 加 checkpointer
    return agent

agent = init_agent()

# ========== Streamlit 界面 ==========
st.title("学校信息问答助手")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# 初始化 thread_id（每个用户一个会话）
if "thread_id" not in st.session_state:
    st.session_state.thread_id = "user_session_1"

if prompt := st.chat_input("问点什么..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    with st.spinner("思考中..."):
        result = agent.invoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config={"configurable": {"thread_id": st.session_state.thread_id}}   # ← 传 thread_id
        )
        answer = result["messages"][-1].content

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.chat_message("assistant").write(answer)
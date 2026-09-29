import os
import streamlit as st
import requests
import dashscope
from dotenv import load_dotenv
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ========== 加载环境 ==========
try:
    if "DASHSCOPE_API_KEY" in st.secrets:
        os.environ["DASHSCOPE_API_KEY"] = st.secrets["DASHSCOPE_API_KEY"]
    else:
        raise KeyError("No key in secrets")
except Exception:
    # 本地：从 .env 读
    if os.path.exists(r"D:\llm_learn\.env"):
        load_dotenv(dotenv_path=r"D:\llm_learn\.env")
    else:
        load_dotenv()

dashscope.api_key = os.environ["DASHSCOPE_API_KEY"]
# ========== 初始化向量库（缓存，只加载一次）==========
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

# ========== RAG 函数 ==========
def rag_chat(question):
    retriever = vectorstore.as_retriever(search_kwargs={"k": 50})   # 20 → 50
    candidates = retriever.invoke(question)

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
        "parameters": {"top_n": 10, "return_documents": True}  # 3 → 10
    }
    resp = requests.post(url, headers=headers, json=data)
    reranked = resp.json()["output"]["results"]

    context = "\n\n".join([item["document"]["text"] for item in reranked])

    prompt = f"""请根据以下资料回答问题。如果资料里没有答案，就说"资料中未提到"。

    资料：
    {context}

    问题：{question}

    要求：如果问题涉及"有哪些"、"列出"等，请尽量列全资料中提到的所有项。"""

    llm_resp = dashscope.Generation.call(model="qwen-turbo", prompt=prompt)
    return llm_resp.output["text"]

# ========== Streamlit 界面 ==========
st.title("学校信息问答助手")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("问点什么..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    with st.spinner("思考中..."):
        answer = rag_chat(prompt)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.chat_message("assistant").write(answer)
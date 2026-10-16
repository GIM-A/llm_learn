import streamlit as st
import requests

st.title("学校信息问答助手")

# 初始化聊天记录
if "messages" not in st.session_state:
    st.session_state.messages = []

# 显示历史消息
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

# 输入框
if prompt := st.chat_input("问点什么..."):
    # 显示用户消息
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # 调后端 API
    with st.spinner("思考中..."):
        resp = requests.post(
            "http://localhost:8000/chat",
            json={"question": prompt}
        )
        answer = resp.json()["answer"]

    # 显示 AI 回复
    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.chat_message("assistant").write(answer)
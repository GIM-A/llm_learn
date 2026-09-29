# 学校信息问答助手（RAG）

基于 RAG（检索增强生成）的学校信息问答系统。用户提问学校相关的问题，系统从文档中检索相关内容，经 rerank 精排后，由大模型生成回答。

**🔗 在线演示**：https://school-question.streamlit.app

<img width="635" height="728" alt="image" src="https://github.com/user-attachments/assets/85eb7430-f646-4f0e-af13-7790c86423c7" />



## ✨ 功能

- 📄 **文档问答**：基于 `my_doc.txt` 中的内容回答
- 🔍 **向量检索 + Rerank**：先用向量检索召回 top 20，再用 `qwen3-rerank` 精排 top 3
- 🤖 **LLM 生成**：调用通义千问 `qwen-turbo` 生成回答
- 🛡️ **防幻觉**：资料中没有的内容，模型回答"资料中未提到"
- 💬 **多轮对话**：支持聊天式交互

## 🏗️ 架构
用户提问
↓
Streamlit 前端（chat_input）
↓
向量检索（Chroma + text-embedding-v3，召回 top 20）
↓
Rerank 精排（qwen3-rerank，返回 top 3）
↓
拼 context + prompt
↓
LLM 生成（qwen-turbo）
↓
返回回答

## 🛠️ 技术栈

| 类别 | 技术 |
|---|---|
| 大模型 | 通义千问（qwen-turbo、text-embedding-v3、qwen3-rerank） |
| RAG 框架 | LangChain |
| 向量数据库 | Chroma |
| 前端 | Streamlit |
| 部署 | Streamlit Cloud |
| 语言 | Python 3.11 |

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/GIM-A/llm_learn.git
cd llm_learn

2. 安装依赖
bash
pip install -r requirements.txt
3. 配置 API Key
在项目根目录创建 .env 文件：

text
DASHSCOPE_API_KEY=sk-你的key
API Key 从 阿里云百炼 获取。

4. 启动应用
bash
streamlit run app_full.py
浏览器访问 http://localhost:8501。
📁 项目结构
text
llm_learn/
├── app_full.py          # 主程序（Streamlit + RAG）
├── my_doc.txt           # 知识库文档
├── requirements.txt     # 依赖清单
├── .gitignore           # Git 忽略配置
└── README.md            # 本文档
🔑 关键实现
1. RAG 流程
文档切分：按 400 字切 chunk，重叠 50 字（防止切断语义）

向量嵌入：用 text-embedding-v3 把 chunk 转成 1024 维向量

向量检索：用 Chroma 召回 top 20（多召回，避免遗漏）

Rerank：用 qwen3-rerank 对 20 条精排出 top 3（提升相关性）

生成：把 top 3 chunk 拼成 context，让 qwen-turbo 基于 context 回答

2. 为什么用 Rerank
纯向量检索算的是"整体语义相似度"，会返回"整体相关但细节不相关"的 chunk。

实测：问"学校的就业情况"，向量检索 top 5 里只有 1 条真的相关。

加 rerank 后：相关 chunk 分数 0.836，不相关降到 0.4 以下。

3. 防幻觉
prompt 里写："如果资料里没有答案，就说'资料中未提到'。"

效果：问"它怎么样"（无上下文），模型回答"资料中未提到"，不编造。
📝 踩坑记录
HF 镜像配置：国内下载 HuggingFace 模型需要 HF_ENDPOINT=https://hf-mirror.com

禁用 Xet 协议：新版 HuggingFace 用 Xet 协议，镜像站不支持，需 HF_HUB_DISABLE_XET=1

API Key 管理：用 .env + python-dotenv，避免硬编码；load_dotenv() 默认不覆盖环境变量，需 override=True

Streamlit Secrets：部署到 Cloud 时，用 st.secrets 读 key，而非 .env

模型下线：gte-rerank 已下线，改用 qwen3-rerank

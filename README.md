# 校园知识库问答（RAG）

基于 **RAG（检索增强生成）** 的校园信息问答系统。用户提问，系统先从知识库检索相关片段、
经 rerank 精排后交给大模型，流式（打字机）返回一句话答案。

前端是原生 HTML/CSS/JS，后端是 FastAPI；**不依赖任何前端框架**（没有 React/Vue，也没有 Streamlit）。

---

## ✨ 功能

| 功能 | 说明 |
|---|---|
| 📄 **知识库问答** | 基于 `data/my_doc.txt`（全自动生成，977 条向量）回答校园问题 |
| 🔍 **向量检索 + Rerank** | 向量召回 top 20 → `qwen3-rerank` 精排 top 3 |
| 🤖 **LLM 生成** | 通义千问 `qwen3.7-flash`（走 OpenAI 兼容端点） |
| ⌨️ **流式输出** | SSE 逐字返回，前端实时显示"打字机"效果 |
| 💬 **多轮对话** | 后端接收 `history`，最多保留最近 5 轮 |
| 🛡️ **防幻觉** | 提示词约束"根据资料一句话回答"；未检索到资料时明确回答"资料中未提到" |
| 🧯 **前端容错** | 断网/断流时就地显示错误气泡 + 「重试」按钮，不弹 alert、不白屏 |

---

## 🏗️ 架构

```
用户提问（浏览器）
      │  POST /chat/stream  { question, history? }
      ▼
FastAPI 后端（backend/main.py）
      │
      ▼
向量检索（backend/rag.py: search_docs）
      │  Chroma + text-embedding-v3，召回 top 20
      ▼
Rerank 精排（qwen3-rerank，返回 top 3）
      │
      ▼
拼装 messages：[system] + [最近 5 轮历史] + [当前问题 + 资料]
      │
      ▼
LLM 生成（qwen3.7-flash，ChatOpenAI / OpenAI 兼容端点）
      │  SSE 逐字下发： data: xxx\n\n ... data: [DONE]
      ▼
前端逐片渲染（frontend/app.js）
```

---

## 🛠️ 技术栈

| 类别 | 技术 |
|---|---|
| 后端框架 | FastAPI + Uvicorn |
| 前端 | 原生 HTML / CSS / JavaScript（无框架、无构建步骤） |
| RAG 框架 | LangChain（`langchain-community` / `langchain-chroma` / `langchain-openai`） |
| 向量数据库 | Chroma（本地持久化到 `chroma_db_langchain/`） |
| 大模型服务 | 阿里云百炼 DashScope：`text-embedding-v3` / `qwen3-rerank` / `qwen3.7-flash` |
| 配置管理 | `python-dotenv` + `backend/config.py`（**唯一配置源**） |
| 语言 | Python 3.11 |
| 部署 | Nginx 反代 + systemd（子路径 `/school-qa/`） |

---

## 📁 项目结构

```
llm_learn/
├── backend/                  # FastAPI 后端
│   ├── config.py             # ⭐ 唯一配置源：路径/模型名/参数/API Key
│   ├── main.py               # FastAPI 入口 + 路由 + 静态文件挂载
│   ├── rag.py                # RAG 核心：检索 → rerank → 生成（含多轮截断）
│   └── schemas.py            # Pydantic 请求/响应模型
├── frontend/                 # 原生前端（静态文件，由 /static 挂载）
│   ├── index.html
│   ├── style.css
│   └── app.js                # 多轮对话 / 错误重试 / 清空 / 打字机
├── scripts/                  # 工具脚本（都不是服务运行必需的）
│   ├── build_index.py        # 重建向量库（读 my_doc.txt → 切分 → 嵌入）
│   ├── crawler.py            # 爬取原始语料 → data/crawled_data_full.txt（CI 定时任务用）
│   ├── clean_corpus.py       # 清洗语料 → data/my_doc.txt（去模板/去重，覆盖写）
│   ├── evaluate.py           # 20 题评测（支持 --dry-run）
│   ├── test_api.py           # 接口冒烟测试
│   ├── test_rag.py           # 检索链路诊断
│   ├── test_llm.py           # LLM 调用诊断
│   └── debug_prompt.py       # 打印拼好的 prompt
├── data/                     # 语料（**整体不进 git**，部署时需单独 scp）
│   ├── crawled_data_full.txt # 爬虫原始输出（约 2.2MB / 500 页）
│   └── my_doc.txt            # ⭐ 唯一进向量库的文档（约 1.8MB / 442 页，由 clean_corpus.py 生成）
├── chroma_db_langchain/      # 向量库持久化目录（被 .gitignore 忽略，需另行传；当前 977 条）
├── docs/
│   ├── eval_report.md        # 评测报告
│   └── deploy/               # 部署文档（01 环境 → 02 systemd → 03 nginx → 04 验证）
├── _deprecated/              # 已废弃的旧 Streamlit 版本（仅作存档）
├── .github/workflows/        # GitHub Actions（定时爬取语料，只跑 crawler + clean，不提交）
├── requirements.txt
└── README.md
```

---

## 🚀 运行方式

### 本地开发

```bash
# 1. 建虚拟环境（Python 3.11）
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/macOS:  source .venv/bin/activate

# 2. 装依赖
pip install -r requirements.txt

# 3. 配置 API Key（见下方"环境变量"）
#    在项目根目录建 .env，写入 DASHSCOPE_API_KEY=sk-xxxx

# 4. 准备向量库（完整数据链路见「🔁 数据链路与重建知识库」一节）
#    - 如果 chroma_db_langchain/ 已经有内容，跳过这步
#    - 否则先确保 data/my_doc.txt 存在，再重建（会调 embedding 接口，977 条时会慢一些）
python -m scripts.build_index

# 5. 启动服务
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

浏览器打开 **http://127.0.0.1:8001/** 即可提问。

> **端口说明**：Uvicorn 自己的默认端口是 `8000`，但本项目约定用 **`8001`**
> （`backend/config.py` 的 `DEFAULT_PORT`，也用于 `scripts/test_api.py`）。
> 想换端口：`--port 9000` 并同时设环境变量 `DEFAULT_PORT=9000`。

**验证服务起来了**：

```bash
curl http://127.0.0.1:8001/health
# {"status":"ok","message":"RAG API is running"}
```

### 部署到服务器

完整步骤见 [`docs/deploy/`](./docs/deploy/)：

| 文档 | 内容 |
|---|---|
| [01-server-setup.md](./docs/deploy/01-server-setup.md) | 服务器环境（Python、swap、系统用户、目录、依赖） |
| [02-systemd.md](./docs/deploy/02-systemd.md) | systemd 常驻服务（开机自启、内存限制） |
| [03-nginx.md](./docs/deploy/03-nginx.md) | Nginx 子路径反代 `/school-qa/`（含 SSE 配置） |
| [04-verify.md](./docs/deploy/04-verify.md) | 验证清单（含 SSE 流式判定方法） |

> ⚠️ **子路径部署有个前置条件**：前端所有资源路径必须是**相对路径**
> （`static/app.js` 而不是 `/static/app.js`）。本项目已经改成相对路径，
> 因此既能挂子路径，也能直接跑在根路径。

---

## 🔁 数据链路与重建知识库

知识库是**全自动生成**的，四个环节串成一条链路（`data/` 里的文件**都不进 git**）：

```
官网（www.cqytxy.edu.cn）
      │  python -m scripts.crawler          # BFS 爬取 + URL/内容去重 + 过滤短页
      ▼
data/crawled_data_full.txt                    # 爬虫原始输出（约 2.2MB / 500 页）
      │  python -m scripts.clean_corpus      # 去导航/版权模板 + 页内重复压缩 + 去重
      ▼
data/my_doc.txt                               # ⭐ 唯一进向量库（约 1.8MB / 442 页，带 `=== url ===` 标记）
      │  python -m scripts.build_index       # 切分（chunk 1000 / overlap 150）→ embedding → Chroma
      ▼
chroma_db_langchain/                          # 向量库（当前 977 条，collection = langchain）
```

**重建知识库（完整流程）**：

```bash
# 0) 若服务正在运行，先停掉（重建会删掉旧库，避免边删边读）
#    本地没起服务可跳过；服务器上必须停 —— 见 docs/deploy/01-server-setup.md 附录 B

# 1) 爬取官网全量静态页 → data/crawled_data_full.txt（覆盖写）
python -m scripts.crawler          # 可选：--max-pages / --depth / --min-chars / --delay

# 2) 清洗 → data/my_doc.txt（覆盖写）
python -m scripts.clean_corpus     # 可选：--min-chars / --freq-threshold / --repeat-times

# 3) 重建向量库（先删旧库 → 切分 → 调 embedding 接口 → 写 Chroma）
python -m scripts.build_index      # 可选：--chunk-size / --chunk-overlap
```

> ⚠️ **重建向量库前必须先停服务**：`build_index` 会先 `rmtree` 掉 `chroma_db_langchain/`。
> 服务还在跑时 Chroma 持有 SQLite 连接，删目录会失败或留下半坏的库。

> 💡 **只更新向量库、语料不变**：跳过第 1、2 步，直接跑第 3 步即可。
> `data/` 不进 git，服务器上若缺 `my_doc.txt`，用 `scp` 单独补传（见部署文档 01 篇）。

---

## 🔑 环境变量

在项目根目录创建 `.env`（**已在 `.gitignore` 中，不会进仓库**）：

```dotenv
# 必填：阿里云百炼（DashScope）API Key
DASHSCOPE_API_KEY=sk-你的key

# 可选：默认端口，默认 8001（scripts/test_api.py 用它拼请求地址）
# DEFAULT_PORT=8001
```

- Key 从 [阿里云百炼控制台](https://bailian.console.aliyun.com/) 获取。
- `backend/config.py` 是**唯一配置来源**，它按 `ROOT_DIR` 自动定位 `.env`，**因此无论从哪个目录启动都能读到**。
- Key 的校验是**惰性**的：`import backend.config` 不会因为缺 Key 而报错
  （这样只需要路径常量的脚本/crawler 在 CI 里也能跑）；真正要用 Key 时才由
  `config.require_api_key()` 抛出明确的 `ValueError`。

---

## 🌐 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 返回前端页面 `frontend/index.html` |
| GET | `/health` | 健康检查 |
| POST | `/chat` | 非流式问答（保留用于测试） |
| POST | `/chat/stream` | **流式问答（SSE）**，前端实际使用 |
| GET | `/static/*` | 前端静态资源 |

**请求体**（`/chat` 与 `/chat/stream` 相同）：

```json
{
  "question": "学校在哪个城市？",
  "history": [
    { "role": "user", "content": "重庆移通学院在哪个城市？" },
    { "role": "assistant", "content": "重庆移通学院位于重庆市。" }
  ]
}
```

- `history` **可选**：不传时行为与单轮问答完全一致（向后兼容）。
- `history` 里**只放"当前问题之前"的对话**；当前问题由 `question` 单独承载。
- 只接受 `role` 为 `user` / `assistant` 的消息（`system` 会被过滤，防提示词注入）。
- 服务端只保留**最近 5 轮**（`rag.MAX_HISTORY_TURNS`），按"一问一答"成对截断，不会拆散一对。

**流式响应格式**：

```
data: 学校
data: 地处
data: 重庆市
data: 。
data: [DONE]
```

出错时下发 `data: [ERROR] 具体错误`。

---

## 🔬 关键实现

### 1. RAG 流程

1. **切分**：`RecursiveCharacterTextSplitter`，`chunk_size=1000` / `chunk_overlap=150`
   （语料扩到几百页后，1000 字更接近"一段完整信息"；由 `scripts/build_index.py` 执行）
2. **嵌入**：`text-embedding-v3`（云端接口，**本地不跑模型，不占内存**）
3. **召回**：Chroma 向量检索 top **20**（`config.VECTOR_TOP_K`）
4. **精排**：`qwen3-rerank` 精排后保留 top **3**（`config.RERANK_TOP_N`）
5. **生成**：把 top 3 拼成 context，连同一句话约束的 system 提示词交给 `qwen3.7-flash`

### 2. 为什么要有 Rerank

纯向量检索算的是"整体语义相似度"，会返回**整体相关但细节不相关**的片段。
Rerank 用交叉编码器逐条打分，把真正相关的挑到最前面，相关性区分度明显更高。

### 3. 多轮对话怎么截断

`rag._truncate_history()`：先把历史清洗成只剩 `user`/`assistant`，
再按"以 user 开头"分组（一组 = 一轮），取**末尾 5 组**再摊平。
只有 `user` 没有 `assistant` 的"不完整尾"也算一组，不会被丢掉。

### 4. 前端容错

- **断流检测**：流读完却没收到 `[DONE]` → 判为「连接中断」，就地变红色气泡 + 重试按钮。
- **重试不重复**：重试时先把上一条失败的 `user` 从历史里弹出再重新压入，
  保证历史里不会出现两条一模一样的提问。
- **会话作废**：点「清空对话」会让 `sessionId` 自增，还在飞行中的旧请求会因编号不匹配而停止写入页面。

---

## 📝 踩坑记录

> 按"下次一定还会遇到"的顺序排列。

1. **DashScope 原生 SDK 调不了 `qwen3.7-flash`**
   用 `dashscope.Generation.call` 会报 `400 InvalidParameter: url error`；
   必须走 **OpenAI 兼容端点** `https://dashscope.aliyuncs.com/compatible-mode/v1`
   （即 `ChatOpenAI` + `base_url`）。项目里统一由 `rag.init_llm()` 构造。

2. **`qwen-turbo` 会持续 429**
   该模型在本账号下持续 `Throttling.RateQuota`（隔 8 秒重试仍然 429，不是偶发）。
   所以项目统一用 `qwen3.7-flash`，不要再退回 `qwen-turbo`。

3. **私有 rerank 端点可能被拒**
   曾经用过的私有地址会返回 `403 Endpoint.AccessDenied`；
   统一用 `config.RERANK_URL`（官方地址）。

4. **`data/` 整体不进 git，部署时别漏传**
   `crawled_data_full.txt`（爬虫原始输出，约 2.2MB）→ `my_doc.txt`（清洗后，**唯一进向量库的**，
   约 1.8MB）是流水线关系，内容互不相同，且都在 `.gitignore` 里。
   因此 `git clone` 拿不到它们 —— 部署时必须**单独 `scp`**（见部署文档 01 篇）。

5. **项目根目录由 `config.py` 推导，不要写死绝对路径**
   `ROOT_DIR = Path(__file__).resolve().parent.parent`，所有路径常量从它派生。
   这样从任何工作目录启动、换机器部署都不会跑偏。

6. **子路径部署必须用相对路径**
   前端只要有一处 `/static/...` 这种**以 `/` 开头**的写法，
   挂到 `/school-qa/` 下就会去请求站点根 → 打到别的应用上 → 白屏。
   现在 `index.html` / `app.js` 全部改成相对路径，两种部署方式都正确。

7. **`.gitignore` 会阻止 `git add`**
   被忽略的文件用 `git add` 会直接失败（需要 `-f`）。
   改 `.gitignore` 时要注意有没有 CI 流程依赖那个文件。

8. **Windows 上 Git Bash 垫片不可用 + PowerShell 管道会毁掉中文编码**
   本机环境里 `bash` 垫片报 `dirname: command not found`，只能用 PowerShell；
   而 Python 输出经 PowerShell 管道会变成乱码（`PYTHONIOENCODING=utf-8` 也救不回来），
   需要干净中文输出时，**让 Python 自己以 UTF-8 写文件**。

9. **不再需要 HuggingFace 镜像**
   旧版本在本地跑 embedding 模型，需要 `HF_ENDPOINT` / `HF_HUB_DISABLE_XET`；
   现在 embedding 走 DashScope 云端接口，这些配置**已经不需要了**。

---

## 🧰 常用脚本

```bash
# 爬取官网语料 → data/crawled_data_full.txt
python -m scripts.crawler

# 清洗语料 → data/my_doc.txt
python -m scripts.clean_corpus

# 重建向量库（会先删掉旧的，再调 embedding 接口）★ 重建前先停服务
python -m scripts.build_index

# 接口冒烟测试（端口取 config.DEFAULT_PORT，默认 8001）
python -m scripts.test_api

# 检索链路诊断（向量检索 / 含 rerank / 完整 RAG）
python -m scripts.test_rag

# LLM 调用诊断（非流式 / messages / 流式）
python -m scripts.test_llm

# 打印最终拼好的 prompt
python -m scripts.debug_prompt

# 评测：只跑 1 题验证链路
python -m scripts.evaluate --dry-run
# 评测：跑完整 20 题
python -m scripts.evaluate
```

> `evaluate.py --dry-run` 在下游 LLM 不可用时**会 exit 1** —— 这是**故意的"看门狗"行为**，
> 用来暴露链路故障，**不要**把它改成静默成功。

---

## 📌 已知限制

- 检索只用**当前问题**做查询，不参与历史。所以像"它呢？"这种**纯代词提问**，
  即使多轮历史生效了，检索到的资料也可能不准（答案里代词能被正确解析，但依据可能不足）。
- 评测脚本（`scripts/evaluate.py`）与线上链路仍未完全对齐（它的 prompt 没有 system 消息、
  rerank `top_n=10` 而线上是 3），因此评测准确率不能直接等同于线上表现。
- 会话历史保存在**浏览器内存**里，刷新页面即丢失；服务端**不持久化**会话。

---

## 📚 相关文档

- 评测报告：[`docs/eval_report.md`](./docs/eval_report.md)
- 部署文档：[`docs/deploy/`](./docs/deploy/)

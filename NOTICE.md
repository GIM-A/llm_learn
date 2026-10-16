# 项目交接通知（NOTICE）

> 面向**接手的同学**与**新对话的 AI**。读完这一份就能上手。
> 术语：RAG = 检索增强生成（Retrieval-Augmented Generation）—— 先检索资料，再让大模型照着资料回答。
>
> 最后更新：2026-10-16 ｜ 分支 `refactor/fastapi` ｜ 最新提交：见 `git log --oneline -1`

---

## 1. 项目是什么

**一句话**：基于**重庆移通学院官网语料**的校园信息问答系统 —— 用户提问，系统先从本地知识库检索相关片段、经 rerank 精排后交给大模型，**流式（打字机）返回一句话答案**。

**RAG 说明**：

| 环节 | 做法 |
|---|---|
| 知识来源 | 官网全站静态页（BFS 爬取 → 清洗 → 442 页语料） |
| 检索 | Chroma 向量库（`text-embedding-v3` 嵌入），召回 top **20** |
| 精排 | `qwen3-rerank` 交叉编码器逐条打分，保留 top **3** |
| 生成 | `qwen3.7-flash`，system 提示词约束「**根据资料用一句话直接回答**」；检索不到就明确回答「资料中未提到」 |
| 输出 | SSE 逐字下发，前端实时渲染 |

**技术栈**：FastAPI + 原生 HTML/CSS/JS（**无前端框架、无构建步骤**）+ LangChain + Chroma。

---

## 2. 两条链路

### 2.1 离线建库（爬取 → 清洗 → 入库）

```text
官网 www.cqytxy.edu.cn
      │  python -m scripts.crawler        # BFS + URL/内容去重 + 过滤短页
      ▼
data/crawled_data_full.txt                # 爬虫原始输出（约 2.2MB / 500 页）
      │  python -m scripts.clean_corpus   # 去导航/版权模板 + 页内重复压缩 + 去重
      ▼
data/my_doc.txt                           # ⭐ 唯一进向量库（1.8MB / 442 页，带 "=== url ===" 标记）
      │  python -m scripts.build_index    # 切分(chunk 1000 / overlap 150) → 嵌入 → 写 Chroma
      ▼
chroma_db_langchain/                      # 向量库（977 chunk，collection = langchain）
```

### 2.2 在线问答（请求 → 检索 → 生成）

```text
浏览器（frontend/）
      │  POST /chat/stream   { question, history? }
      ▼
FastAPI 后端（backend/main.py）
      ▼
向量检索（backend/rag.py: search_docs）
      │  Chroma，召回 top 20
      ▼
Rerank 精排（qwen3-rerank）→ 保留 top 3
      ▼
拼装 messages：[system] + [最近 5 轮历史] + [当前问题 + 资料]
      ▼
LLM 生成（qwen3.7-flash，走 OpenAI 兼容端点）
      │  SSE：data: xxx\n\n ... data: [DONE]
      ▼
前端逐片渲染（frontend/app.js）
```

---

## 3. 快速信息表

| 项 | 值 |
|---|---|
| 项目根（本地） | `D:\llm_learn` |
| 安装目录（服务器） | `/opt/llm_learn` |
| 远端仓库 | `https://github.com/GIM-A/llm_learn.git` |
| 当前分支 | `refactor/fastapi` |
| 最新提交 | 见 `git log --oneline -1`（**不写死 hash**，避免随提交过期） |
| 服务端口 | **8001**（只监听 `127.0.0.1`；端口 **8000** 被「项目1」占用） |
| 公网地址 | **http://8.149.236.20/school-qa/** |
| 生成模型 | `qwen3.7-flash`（**OpenAI 兼容端点** `https://dashscope.aliyuncs.com/compatible-mode/v1`） |
| Embedding | `text-embedding-v3`（云端接口，本地不跑模型） |
| Rerank | `qwen3-rerank`（`config.RERANK_URL`） |
| 召回 / 精排 | top **20** / top **3**（`VECTOR_TOP_K=20`、`RERANK_TOP_N=3`） |
| 切分参数 | `chunk_size=1000`、`chunk_overlap=150` |
| 向量库 | **977 chunk**，collection `langchain`，来源 442 页 |
| 知识库 | `data/my_doc.txt`，**442 页 / 1.8 MB** |
| Python | 3.11.9（本地 venv：`.venv\Scripts\python.exe`） |
| 服务器 | `8.149.236.20`，Ubuntu 22.04，**2 核 2 GiB**，华东1（杭州） |
| 配置唯一来源 | `backend/config.py` |

> `.env` 里只有 `DASHSCOPE_API_KEY=sk-xxxx`（**真实 Key 绝不进仓库、绝不写进任何文档**）。

---

## 4. 目录结构

```text
llm_learn/
├── backend/                  # FastAPI 后端
│   ├── config.py             # ⭐ 唯一配置源：路径 / 模型名 / 检索参数 / Key
│   ├── main.py               # 入口 + 路由 + 静态文件挂载
│   ├── rag.py                # RAG 核心：检索 → rerank → 生成（含多轮截断）
│   └── schemas.py            # Pydantic 请求/响应模型
├── frontend/                 # 原生前端（由 /static 挂载）
│   ├── index.html
│   ├── style.css
│   └── app.js                # 多轮对话 / 错误重试 / 清空 / 打字机
├── scripts/                  # 工具脚本（都不是服务运行必需的）
│   ├── crawler.py            # 爬取语料 → data/crawled_data_full.txt
│   ├── clean_corpus.py       # 清洗语料 → data/my_doc.txt
│   ├── build_index.py        # 重建向量库
│   ├── evaluate.py           # 20 题评测（支持 --dry-run）
│   ├── test_api.py           # 接口冒烟测试
│   ├── test_rag.py           # 检索链路诊断
│   ├── test_llm.py           # LLM 调用诊断
│   └── debug_prompt.py       # 打印拼好的 prompt
├── data/                     # 语料（**整体不进 git**，部署时单独 scp）
│   ├── crawled_data_full.txt # 爬虫原始输出（约 2.2MB / 500 页）
│   └── my_doc.txt            # ⭐ 唯一进向量库（1.8MB / 442 页）
├── chroma_db_langchain/      # 向量库持久化目录（不进 git，977 chunk）
├── docs/
│   ├── eval_report.md        # 评测报告
│   └── deploy/               # 部署文档（01 环境 → 02 systemd → 03 nginx → 04 验证）
├── _deprecated/              # 已废弃的旧 Streamlit 版本（仅存档）
├── .github/workflows/        # GitHub Actions（定时爬取语料，只跑 crawler + clean，不提交）
├── NOTICE.md                 # 本文档（交接通知）
├── README.md
└── requirements.txt
```

---

## 5. 已完成的工作

| 阶段 | 内容 | 代表提交 |
|---|---|---|
| 阶段 1 | 从 Streamlit 迁移到 FastAPI + 原生前端；RAG 核心 + 流式输出；目录分层（`backend/ frontend/ data/ scripts/ _deprecated/`） | `6041151`→`df4dba9` |
| 阶段 1.6 | 修 `evaluate.py` 语法错误、评测链路与线上对齐、修 `crawl.yml` 三处断裂、`config.py` Key 校验**惰性化**、`crawler.py` 写出路径改 `config.DATA_DIR` | `d36afcd`→`ffd43ee` |
| 阶段 3 | 前端完善（多轮 UI / 断流检测与重试 / 清空 / 三点加载动画）；**真·多轮**后端接收 `history`（最多 5 轮） | `ffb5c49`、`7803351` |
| 阶段 4 | 部署：服务器环境（swap / 专用用户 / venv）、systemd 常驻、nginx 子路径 `/school-qa/`、验证清单；前端 3 处绝对路径改**相对路径** | `56bb5db`→`bb619d8` |
| 阶段 5 | README 重写、合并 `test_llm/debug_llm`（并去掉打印 Key）、`data/` 进 `.gitignore`、`test_api` 端口取自 config | `37d968d` |
| **扩语料** | `crawler.py` 改 BFS（深度 3 / 页数上限 500 / 双去重 / 短页过滤）；新建 `clean_corpus.py`；`build_index.py` 支持多文件 + 记来源 URL；`.gitignore` 加 `.gitignore` 编码修复 | `da9ea8c`→`a5a8e41` |
| 文档对齐 | README / 部署文档与「data/ 不进 git、977 chunk、`VECTOR_TOP_K=20`」对齐 | `abca45a` |

**扩语料前后对比（本阶段最大变化）**：

| 指标 | 之前 | 现在 |
|---|---|---|
| 向量库 chunk | 8 | **977** |
| 知识库页数 | 1（手工整理） | **442（自动生成）** |
| 爬取页数 | 89（深度 1） | **500（BFS 深度 3）** |
| 召回 top_k | 5（只有 8 条时形同无效） | **20** |

---

## 6. 已决策不做

> 以下都是**经过讨论后主动拍板的决策**，**不是**被遗忘的待办。

| 项 | 决策 | 理由 |
|---|---|---|
| **MySQL 持久化会话** | **不做**（原 CARD-2.x）<br>**用户明确表态**："只存在前端记忆里一轮就够了" | ① 服务器只有 **2 GiB 内存**，再挂一个 MySQL 实例风险高；② 当前是**单实例**，**无多用户 / 无审计 / 无跨设备历史**需求；③ 会话历史留在浏览器内存（刷新即丢）已够用；引入后还会新增安装、备份、连接池、迁移等运维面，收益不匹配。若将来真要多用户 + 历史持久化，再单开卡片。 |
| CI 自动更新知识库 | 不做 | `crawl.yml` 只做「爬取 + 清洗」校验，**不提交**任何文件（全量语料会造成巨大 diff，且易撑爆仓库）。 |
| JS 渲染爬取 | 不做 | 官网主体是静态页；图书馆子站 `lib.cqytxy.edu.cn` 是纯 JS SPA，需上浏览器渲染，成本高，暂不覆盖（见踩坑 8.3）。 |
| 全量语料进 git | 不做 | `data/` 整体 gitignore，部署时单独 `scp`。 |

---

## 7. 部署架构

```text
公网 http://8.149.236.20/school-qa/
      │
      ▼
nginx（80 端口，复用项目1 的 server 块）
      │  include /etc/nginx/snippets/school-qa.conf
      │  proxy_pass http://127.0.0.1:8001/;    ← 结尾斜杠必须有
      ▼
systemd 单元 school-qa.service
      │  ExecStart: uvicorn backend.main:app --host 127.0.0.1 --port 8001 --workers 1
      ▼
uvicorn（只监听回环 127.0.0.1:8001，**不开安全组**）
```

| 要点 | 说明 |
|---|---|
| 部署方案 | **方案 B**：子路径 `/school-qa/`，复用现有 nginx，**不动项目1 的 `/`**，不加安全组、不买域名 |
| 安全组 | 只开 **80 / 8000 / 22 / 3389 / ICMP**；**未开 8001** → 所以服务必须只监听回环 |
| SSE 三件套 | `proxy_buffering off;` + `gzip off;` + `proxy_request_buffering off;`（否则答案会「一次性出现」） |
| 内存限制 | systemd `MemoryHigh=700M` / `MemoryMax=1000M`；2 GiB 机器必加 **2G swap**（`vm.swappiness=10`） |
| 启动参数 | `--workers 1`（绝不加多 worker）+ `OMP/MKL/...=1`、`MALLOC_ARENA_MAX=2` |
| 部署文档 | `docs/deploy/01-server-setup.md` → `02-systemd.md` → `03-nginx.md` → `04-verify.md` |

---

## 8. 关键踩坑记录

### 8.1 环境（本机 Windows）

- **PowerShell 写文件必须指定编码**：`Out-File` / `Add-Content` 默认是 **UTF-16LE**，会把 UTF-8 文件写坏（本项目 `.gitignore` 就被这么毁过一次）。写文本用 `Write` 工具、`Set-Content -Encoding UTF8`，或用 Python 以 `open(..., "w", encoding="utf-8")` 写。
- **Git Bash 的 coreutils 不可用**：`ls` / `head` / `tail` / `sleep` / `dirname` 全是 `command not found`（PATH 坏了）。列文件用 Glob 工具，跑脚本用绝对路径 `.venv\Scripts\python.exe`。
- **PowerShell 工具的 stdout 不回传** → 把输出重定向到临时文件再读。
- **`HTTP_PROXY` 会劫持 localhost**：本机设了 `HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:53312` 且无 `NO_PROXY`，`requests` 会把发往 `127.0.0.1` 的请求也塞给代理 → 回 **502**，看着像「服务没起」。本地自测要 `session.trust_env = False`。
- **中文输出走 Python 写文件**：经 PowerShell 管道会变乱码（`PYTHONIOENCODING=utf-8` 也救不回来）。
- `cmd /c` 被安全策略禁用。

### 8.2 代码

- **DashScope 原生 SDK 调不了 `qwen3.7-flash`**：`dashscope.Generation.call` 报 `400 InvalidParameter: url error`；**必须走 OpenAI 兼容端点**（即 `ChatOpenAI` + `base_url`）。统一由 `rag.init_llm()` 构造。
- 本账号 `qwen-turbo` **持续 429 `Throttling.RateQuota`**（隔 8 秒重试仍 429，非偶发）；`qwen-turbo-latest` 是 403。→ 不要退回 `qwen-turbo`。
- **`config.py` 的 Key 校验必须惰性化**：不能在 `import` 阶段 `raise`，否则 CI 里只取路径常量的 `scripts/crawler.py` 一 import 就崩。现由 `config.require_api_key()` 在真正调用时 fail-fast。
- 私有 rerank 端点会 403 `Endpoint.AccessDenied` → 统一用官方 `config.RERANK_URL`。
- `evaluate.py` 曾把一段 Markdown 误粘进 `.py`，导致 `SyntaxError`（已剪到 `docs/eval_report.md`）。
- `evaluate.py --dry-run` 在下游 LLM 不可用时**故意 `exit 1`**（看门狗），**不要**改成静默成功。

### 8.3 数据

- **`data/` 里的文件不是重复文件**：`crawled_data_full.txt`（爬虫原始）→ `my_doc.txt`（清洗后，唯一进向量库）是流水线关系，内容互不相同。
- 内容去重指纹 = **剔除空白后 SHA256**（能抓住「同内容不同空白」的重复页）。
- 短页过滤：正文 **< 200 字符**丢弃。
- **`clean_corpus.py` 的 `--freq-threshold` 默认 0.25**：实测本站导航块出现在 **175/500 = 35%** 的页面里，用 0.6（=300 页）**一条都抓不到** → 导航文字会漏进向量库污染检索。
- **`lib.cqytxy.edu.cn` 是纯 JS SPA**：对任何路径（含 `/robots.txt`）都返回同一个 **2450 字节空壳**，`trafilatura` 提取 **0 字符** → 图书馆开放时间这类问题，静态爬虫**永远拿不到**。
- `robots.txt` / `sitemap.xml` 都是 404 → 只能靠链接发现。

### 8.4 前端

- **子路径部署必须用相对路径**：任何 `/static/...`、`/chat/stream` 这种以 `/` 开头的写法，挂到 `/school-qa/` 下都会打到站点根 → 白屏。现已全部改为相对路径（`static/app.js`、`chat/stream`）。
- 前端已做：多轮渲染、**断流检测**（读完流没收到 `[DONE]` → 判「连接中断」）、错误气泡 + 重试（**不 alert、不白屏**）、`sessionId` 自增作废飞行中的旧请求、三点加载动画。

### 8.5 nginx

- `proxy_pass` 结尾**必须有 `/`**，否则 `/school-qa/static/app.js` 会 404。
- 项目1 的 server 块里若有 `gzip on` / `proxy_buffering on`，会被子 location 继承 → 必须显式关掉（SSE 才不会被缓冲）。
- `location = /school-qa { return 301 /school-qa/; }`（相对路径依赖地址以 `/` 结尾）。

### 8.6 git

- **`git check-ignore` 对已追踪文件不报**（返回空 + exit 1）→ 判断忽略规则是否命中**必须加 `--no-index`**。
- **一个侧含 NUL 的 blob 会让 diff 退化成二进制**：只要 HEAD 侧的文件被 git 判为 binary，`git diff` 就只输出 `Bin 819 -> 787 bytes`，无法逐行 review（提交后就正常了）。
- 仓库 `.gitattributes` 是 `* text=auto`（LF 归一化）；工作区文件是 CRLF，`git add` 时的 `CRLF will be replaced by LF` 提示属正常。

### 8.7 部署

- **2 GiB 内存必加 swap**，否则迟早被 OOM Killer 杀掉。
- **向量库与语料都不在 git，必须单独 `scp`**：`chroma_db_langchain/`（977 条 / 约 22MB）与 `data/`（含 `my_doc.txt` 1.8MB）；只传代码的话服务器上是**空库** → 所有提问都返回「资料中未提到」。
- **重建向量库前必须先停服务**：`build_index.py` 会先 `rmtree` 掉 `chroma_db_langchain/`；服务在跑时 Chroma 持有 SQLite 连接，删目录会失败或留下半坏的库。
- `/opt/llm_learn` 必须**对 `schoolqa` 可写**（Chroma 要写 WAL）。

---

## 9. 常用命令

### 本地开发

```bash
# 建虚拟环境（Python 3.11）并装依赖
python -m venv .venv
# Windows: .venv\Scripts\activate   |  Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 启动服务（约定端口 8001）
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001

# 健康检查
curl http://127.0.0.1:8001/health
```

### 重建知识库（**顺序不能错**）

```bash
# 0) 若服务在跑，先停掉（重建会删旧库）
# 1) 爬取官网 → data/crawled_data_full.txt
python -m scripts.crawler            # 可选 --max-pages / --depth / --min-chars / --delay
# 2) 清洗 → data/my_doc.txt
python -m scripts.clean_corpus       # 可选 --min-chars / --freq-threshold / --repeat-times
# 3) 重建向量库（会调 embedding 接口）
python -m scripts.build_index        # 可选 --chunk-size / --chunk-overlap
```

> 只更新向量库、语料不变 → 跳过第 1、2 步，直接跑第 3 步。

### 测试 / 诊断

```bash
python -m scripts.test_api           # 接口冒烟测试（端口取 config.DEFAULT_PORT）
python -m scripts.test_rag           # 检索链路诊断
python -m scripts.test_llm           # LLM 调用诊断
python -m scripts.debug_prompt       # 打印最终拼好的 prompt
python -m scripts.evaluate --dry-run # 评测：只跑 1 题验链路
python -m scripts.evaluate           # 评测：跑完整 20 题
```

### git

```bash
git status --short
git log --oneline -20
git diff --stat
git check-ignore -v --no-index <path>   # 查某个文件是否被忽略（必须带 --no-index）
```

### 服务器

```bash
sudo systemctl status school-qa --no-pager
sudo systemctl restart school-qa
sudo journalctl -u school-qa -n 100 --no-pager
curl -s http://127.0.0.1:8001/health
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/school-qa/health
```

---

## 10. 约束（不变）

1. **卡片驱动开发**：每张卡有明确的输入 / 输出 / 验收 / 注意。**严格守范围** —— 卡片没写的改动一律先问，不要顺手改。
2. **提交由人来做**：AI 只交付改动 + 验收证据，**不代为 commit / push**。
3. **证据优先**：要求硬证据（`git diff` / 实测 HTTP 状态码 / 实测退出码），不接受口头断言；遇到报错先停下来讲清楚。
4. **`data/` 整体不进 git**：部署时单独 `scp`。
5. **不要擅自动** `.env`、`chroma_db_langchain/`（需明确要求才改）。
6. **绝不写入真实 API Key**：文档里只能用占位符 `sk-xxxx`；`.env` 内容不进仓库、不进文档。
7. **`backend/config.py` 是唯一配置源**：路径 / 模型名 / 检索参数都从它读，不要在各处写死绝对路径。

---

## 11. 新对话开场建议

把下面这段直接发给新对话的 AI：

```text
项目：D:\llm_learn，校园知识库问答（RAG），分支 refactor/fastapi。
请先读 D:\llm_learn\NOTICE.md（交接通知）和 D:\llm_learn\.workbuddy\memory\MEMORY.md（项目长期约定），
再按需读 README.md、backend/config.py。

当前状态：向量库 977 chunk，知识库 data/my_doc.txt 442 页 / 1.8MB，
召回 20 / 精排 3，chunk_size=1000 / overlap=150，
模型 qwen3.7-flash（OpenAI 兼容端点），本地端口 8001，最新提交见 `git log --oneline -1`。

工作方式：卡片驱动、严格守范围；改动由我自己 commit；要求实测证据。
```

---

## 12. 给 AI 的提示

- **动手前先读**：`NOTICE.md`（本文）、`.workbuddy/memory/MEMORY.md`、必要时当天的 `.workbuddy/memory/YYYY-MM-DD.md` 日记；代码相关再读 `backend/config.py`。
- **先侦察、再动手**：涉及数据 / 参数 / 目录的改动，先给出实测现状（条数、路径、状态码），确认后再改。
- **写文件注意编码**：只用 `Write` 工具或 `Set-Content -Encoding UTF8` / Python UTF-8；**绝不要**用 PowerShell 的 `Add-Content` / `Out-File` 默认编码（会写坏 UTF-8 文件）。
- **本机环境是"半残"的**：Git Bash 的 `ls/head/tail/sleep` 不可用、PowerShell 工具不回传 stdout、`cmd /c` 被禁。请用 Glob / 绝对路径 Python / 重定向到文件再读。
- **判断命令成败看 exit code**，不要被 `langchain-community` 的 DeprecationWarning（走 stderr，PowerShell 会渲染成 `NativeCommandError`）误导。
- **不要做的事**：不要改 `.env` / `chroma_db_langchain/`；不要把 `data/` 加回 git；不要在文档里写真实 Key；不要为了让 `evaluate.py --dry-run` 变绿而改成静默成功。
- **改动交付格式**：整文件覆盖（不追加）、给出 diff、附实测验收证据，然后交给用户自己提交。

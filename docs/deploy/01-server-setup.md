# CARD-4.3 服务器环境准备（Ubuntu 22.04）

> **目标**：把 `D:\llm_learn` 这套 RAG 代码在服务器上跑起来（**先不接 systemd、先不接 nginx**），
> 做到「手动敲一条命令能启动、`curl /health` 有响应」。
>
> **服务器**：`8.149.236.20`（Ubuntu 22.04，2 核 **2 GiB**，华东1 杭州）
> **部署方式**：方案 B —— 子路径 `http://8.149.236.20/school-qa/`，**复用现有 nginx**，不动项目1 的 `/`，不加安全组，不买域名。
> **安装目录**：`/opt/llm_learn`　**监听**：`127.0.0.1:8001`（**只监听回环**，不走安全组）

---

## ⚠️ 开始之前：两件必须先知道的事

### 1. 前端有 3 行绝对路径，不改会导致 `/school-qa/` 白屏

当前前端用的是**以 `/` 开头**的绝对路径：

| 文件 | 行 | 现在 | 问题 |
|---|---|---|---|
| `frontend/index.html` | 9 | `<link rel="stylesheet" href="/static/style.css">` | 浏览器会去请求 `http://8.149.236.20/static/style.css`（打到项目1 去了） |
| `frontend/index.html` | 45 | `<script src="/static/app.js"></script>` | 同上 |
| `frontend/app.js` | 164 | `const resp = await fetch("/chat/stream", {` | 打到 `http://8.149.236.20/chat/stream`，同上 |

**必须改成相对路径**（去掉开头的 `/`）。补丁与原理见 **[03-nginx.md](./03-nginx.md) 第 0 节**，**建议在第 1 步之前就先改掉并提交**。

### 2. `chroma_db_langchain/` 和 `.env` 被 gitignore，`git clone` 拿不到

`.gitignore` 里明确忽略了这两项：

```
.env
chroma_db_langchain/
```

- **`.env`**：含 `DASHSCOPE_API_KEY`，**绝不能进仓库**，必须单独 `scp` 上传。
- **`chroma_db_langchain/`**：向量库（本地 756 KB / 5 个文件）。**必须一起上传**，否则服务器上是空库 → 所有提问都返回「资料中未提到」。
  - 兜底方案（不推荐，会消耗 embedding 额度）：上传后在服务器上执行 `python -m scripts.build_index` 重建。

---

## 第 1 步：前置检查（先看清现状，别急着装东西）

```bash
# 1.1 系统与资源
uname -a
lsb_release -a
nproc                     # 期望 2
free -h                   # 期望总量 ~1.9Gi，先记下 used / available
df -h /                   # 看根分区剩余（要留出 ≥2G 给 swap）
swapon --show             # 现在有没有 swap（大概率没有）

# 1.2 已有服务与端口占用（重点：确认项目1 在跑什么）
sudo ss -lntp | grep -E ':(80|8000|8001|8080)\b' || true
systemctl is-active nginx 2>/dev/null || echo "nginx 未运行"

# 1.3 nginx 现状（后面要用）
nginx -v
ls -l /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null
sudo grep -rn "listen\|root\|proxy_pass" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null

# 1.4 Python 现状（Ubuntu 22.04 自带 3.10）
python3 --version
which python3
```

**记下这三样，后面要用**：

1. `free -h` 里 `available` 有多少；
2. 哪个 `server` 块监听了 **80 端口**（它的文件路径）；
3. 项目1 到底是**静态文件**还是**反代到 8000**。

```bash
# 1.5 顺手给项目1 存一个"改动前基线"，第 4 篇验证时要对比
curl -s -o /dev/null -w '项目1 状态码=%{http_code}\n' http://127.0.0.1/
curl -s http://127.0.0.1/ | md5sum | tee /tmp/project1_baseline.md5
```

> `md5sum` 后面会变（动态页面），**能存就存**；存不了就至少记下状态码和标题。

---

## 第 2 步：加 2 GiB swap（**2G 内存必做**）

2 GiB 物理内存要同时跑项目1 + nginx + 这套 Python 应用，**不加 swap 迟早被 OOM Killer 杀掉**。

```bash
# 2.1 创建 2G swap 文件
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 2.2 开机自动挂载
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 2.3 降低换出倾向（默认 60 太激进，对交互式服务不友好；10 表示"能不换就不换"）
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
sudo sysctl -p /etc/sysctl.d/99-swappiness.conf

# 2.4 验证
free -h
swapon --show
```

**期望**：`free -h` 的 `Swap` 一行总量 ≈ `2.0Gi`。

> 如果 `fallocate` 报错（某些老文件系统不支持），改用：
> `sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress`

**顺手限制系统日志占用**（2G 小盘必备，避免 journal 把磁盘吃满）：

```bash
sudo mkdir -p /etc/systemd/journald.conf.d
sudo tee /etc/systemd/journald.conf.d/99-size.conf >/dev/null <<'EOF'
[Journal]
SystemMaxUse=200M
SystemMaxFileSize=50M
EOF
sudo systemctl restart systemd-journald
journalctl --disk-usage
```

---

## 第 3 步：装 Python 3.11

**为什么不用系统自带的 3.10**：本地开发环境是 **Python 3.11.9**，而 `requirements.txt` 大部分包**没钉版本**，
换 Python 版本会解析出不同的包版本组合 —— 本地能跑、服务器跑不起来是最难查的一类问题。**版本对齐成本最低**。

```bash
# 3.1 装 add-apt-repository 工具
sudo apt update
sudo apt install -y software-properties-common

# 3.2 加 deadsnakes PPA 并装 3.11
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# 3.3 验证
python3.11 --version          # 期望 Python 3.11.x
```

> **如果 PPA 加不上**（网络/镜像问题）：退而用系统 `python3.10`，
> 但请务必按本文**附录 A** 生成锁定文件后再安装，把版本漂移的风险掐死。
> 命令：`sudo apt install -y python3.10-venv python3.10-dev`

**不建议装 `python3` 全局软链**，用 `python3.11` 显式调用更安全，不会影响系统工具。

---

## 第 4 步：建专用系统用户 + 目录

**为什么不用 root 跑**：应用以最小权限运行，即使被攻破也拿不到整机；进程崩了也不会影响系统。顺便也让文件归属清晰。

```bash
# 4.1 建一个不能登录的系统用户
sudo useradd --system --create-home --home-dir /home/schoolqa --shell /usr/sbin/nologin schoolqa
id schoolqa

# 4.2 建应用目录
sudo mkdir -p /opt/llm_learn
sudo chown -R schoolqa:schoolqa /opt/llm_learn
sudo chmod 755 /opt/llm_learn
ls -ld /opt/llm_learn
```

> **注意**：`/opt/llm_learn` 必须**对 `schoolqa` 可写** ——
> Chroma 会在 `chroma_db_langchain/` 里写 SQLite 的 WAL/临时文件，只读权限会让应用启动就报错。

---

## 第 5 步：上传代码

本项目远端仓库：`https://github.com/GIM-A/llm_learn.git`，分支 `refactor/fastapi`。
但如前所述，**仓库里没有 `.env` 和 `chroma_db_langchain/`**，所以有两条路。

### 路线 A（推荐）：全部从本地 `scp` 上去

一次性把代码 + 向量库 + `.env` 都传齐，不用在服务器上配 git 凭据。

**在本地 Windows PowerShell 里执行**（Windows 10+ 自带 `scp`）：

```powershell
# 5A.1 先确保本地已应用前端相对路径补丁（见 03-nginx.md 第 0 节）并提交

# 5A.2 用 tar 打包（排除虚拟环境和缓存，别把 Windows 的 .venv 传上去！）
cd D:\llm_learn
tar --exclude=.venv --exclude=__pycache__ --exclude=.git --exclude=.idea --exclude=.workbuddy --exclude=.agents -czf $env:TEMP\llm_learn_deploy.tar.gz .
Get-Item $env:TEMP\llm_learn_deploy.tar.gz | Select-Object Length

# 5A.3 上传（会提示输入 root 或 schoolqa 的密码）
scp $env:TEMP\llm_learn_deploy.tar.gz root@8.149.236.20:/tmp/
```

**回到服务器上解包**：

```bash
# 5A.4 解包到 /opt/llm_learn
cd /opt/llm_learn
sudo tar -xzf /tmp/llm_learn_deploy.tar.gz
sudo chown -R schoolqa:schoolqa /opt/llm_learn

# 5A.5 确认关键文件都在
ls -l /opt/llm_learn
ls -l /opt/llm_learn/chroma_db_langchain/     # 必须有 chroma.sqlite3 / data_level0.bin 等 5 个文件
ls -l /opt/llm_learn/.env                     # 必须存在，下一步改权限
ls -l /opt/llm_learn/data/my_doc.txt
```

### 路线 B：服务器 `git clone` + 单独传两个文件

```bash
# 5B.1 拉代码（公开仓库直接 clone；私有仓库需配 token / deploy key）
sudo -u schoolqa git clone -b refactor/fastapi https://github.com/GIM-A/llm_learn.git /opt/llm_learn

# 5B.2 再补传被 gitignore 的两样
#   在本地 PowerShell：
#   scp -r D:\llm_learn\chroma_db_langchain root@8.149.236.20:/opt/llm_learn/
#   scp    D:\llm_learn\.env                 root@8.149.236.20:/opt/llm_learn/
sudo chown -R schoolqa:schoolqa /opt/llm_learn
```

---

## 第 6 步：建 venv + 装依赖

```bash
cd /opt/llm_learn

# 6.1 建虚拟环境（用 3.11 对齐本地）
sudo -u schoolqa python3.11 -m venv .venv
sudo -u schoolqa .venv/bin/python -m pip install --upgrade pip

# 6.2 装依赖（--no-cache-dir：不占额外磁盘、不占额外内存）
sudo -u schoolqa env PIP_NO_CACHE_DIR=1 .venv/bin/pip install -r requirements.txt

# 6.3 验证关键导入（这一步能暴露 90% 的装包问题）
sudo -u schoolqa .venv/bin/python -c "
import fastapi, uvicorn, chromadb, langchain_openai, langchain_chroma
from langchain_community.embeddings import DashScopeEmbeddings
print('imports OK')
"

# 6.4 跑通配置加载（不联网，只验证路径推导）
sudo -u schoolqa .venv/bin/python -c "
from backend import config
print('ROOT_DIR   =', config.ROOT_DIR)
print('VECTOR_DIR =', config.VECTOR_DIR, config.VECTOR_DIR.exists())
print('DOC_PATH   =', config.DOC_PATH, config.DOC_PATH.exists())
print('KEY 已设置 =', bool(config.DASHSCOPE_API_KEY))
"
```

**期望输出**：三个路径都指向 `/opt/llm_learn/...` 且 `exists()` 为 `True`，`KEY 已设置 = True`。

> **2G 内存下的装包提示**：上面这些包在 Ubuntu 22.04 x86_64 上**都有预编译 wheel**，正常不会触发源码编译，
> 内存占用可控。如果 `pip install` 中途被 `Killed`，说明内存不够 —— 先确认第 2 步的 swap 已生效（`free -h`），再重试。

---

## 第 7 步：.env 权限收紧

```bash
sudo chown schoolqa:schoolqa /opt/llm_learn/.env
sudo chmod 600 /opt/llm_learn/.env
ls -l /opt/llm_learn/.env        # 期望 -rw------- 1 schoolqa schoolqa

# 只看变量名，不打印密钥内容
sudo -u schoolqa grep -o '^[A-Z_]*=' /opt/llm_learn/.env   # 期望看到 DASHSCOPE_API_KEY=
```

`.env` 至少要有这一行（`backend/config.py` 读的就是它）：

```
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx
```

---

## 第 8 步：前台冒烟测试（**先不加 systemd**）

目的：验证「代码 + 依赖 + 向量库 + Key」这条链路本身是通的。**这一步不需要 nginx。**

```bash
cd /opt/llm_learn
sudo -u schoolqa env OMP_NUM_THREADS=1 MALLOC_ARENA_MAX=2 \
  .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --workers 1
```

启动日志期望看到：

```
[startup] 初始化向量库...
[startup] 初始化 LLM...
[startup] 完成
INFO:     Uvicorn running on http://127.0.0.1:8001 (Press CTRL+C to quit)
```

**另开一个 SSH 窗口**验证：

```bash
curl -s http://127.0.0.1:8001/health
# 期望：{"status":"ok","message":"RAG API is running"}

curl -s -o /dev/null -w 'index=%{http_code}\n' http://127.0.0.1:8001/
# 期望：index=200

# 最关键的：验证"能检索 + 能调 LLM"（会真的花钱/耗额度，一条就够）
curl -N -s -X POST http://127.0.0.1:8001/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"question":"学校在哪个城市？"}'
# 期望：逐块输出 data: xxx，最后一行 data: [DONE]
```

**验证完按 `Ctrl+C` 停掉**（第 9 步交给 systemd 常驻）。

> **如果 `/chat/stream` 返回空或「资料中未提到」**：八成是向量库没传上来。
> 检查 `ls /opt/llm_learn/chroma_db_langchain/`；空的话用附录 B 重建。

---

## 第 9 步：确认内存水位（装 systemd 前先摸个底）

```bash
# 看当前整体
free -h

# 看项目1 占多少（找出它到底哪个进程）
sudo ss -lntp | grep ':80\|:8000'
ps -eo pid,ppid,rss,comm --sort=-rss | head -10
```

**记下数字**，第 2 篇（systemd）里的 `MemoryHigh` / `MemoryMax` 要按这个来定。
粗算：应用本体约 **300–450 MiB**；如果项目1 也占 400 MiB 左右，那么这套服务上限设 **1000 MiB** 是安全的。

---

## 附录 A：锁定依赖版本（**强烈建议**）

`requirements.txt` 里 `fastapi / uvicorn / langchain* / chromadb` 都**没写版本号**，
意味着服务器上装到的版本可能和本地不同 → 出现"本地好好的、服务器起不来"。

**在本地 `D:\llm_learn` 生成锁定文件**：

```powershell
D:\llm_learn\.venv\Scripts\python.exe -m pip freeze > D:\llm_learn\docs\deploy\requirements.lock.txt
```

**在服务器上用锁定文件安装**（替换第 6 步的 6.2）：

```bash
# 先把 lock 文件传上去
#   scp D:\llm_learn\docs\deploy\requirements.lock.txt root@8.149.236.20:/opt/llm_learn/
cd /opt/llm_learn
sudo -u schoolqa env PIP_NO_CACHE_DIR=1 .venv/bin/pip install -r requirements.lock.txt
```

> `pip freeze` 会导出**包括间接依赖**在内的完整清单（通常上百行），这正是我们要的"可复现"。
> 注意它会把 `pip`、`setuptools` 等也写进去，属正常现象。

---

## 附录 B：重建向量库（兜底，会消耗 embedding 额度）

```bash
cd /opt/llm_learn
sudo -u schoolqa .venv/bin/python -m scripts.build_index
# 期望：最后一行 "✅ 完成！向量库条数：N"（N > 0）
```

该脚本会**先删掉** `chroma_db_langchain/` 再重建，所以只在向量库确实缺失/损坏时用。

---

## ✅ 本阶段完成标志

- [ ] `free -h` 显示 swap ≈ 2.0Gi
- [ ] `python3.11 --version` 正常
- [ ] `id schoolqa` 存在，`/opt/llm_learn` 属主为 `schoolqa`
- [ ] `/opt/llm_learn/chroma_db_langchain/chroma.sqlite3` 存在
- [ ] `/opt/llm_learn/.env` 权限为 `600`
- [ ] 依赖安装无错，`imports OK`
- [ ] 前台启动能看到 `[startup] 完成`
- [ ] `curl http://127.0.0.1:8001/health` 返回 `{"status":"ok",...}`
- [ ] `curl -N -X POST .../chat/stream` 能逐块返回并以 `[DONE]` 结束

**下一步** → [02-systemd.md](./02-systemd.md)（让它开机自启、崩了自动重启）

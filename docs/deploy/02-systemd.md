# CARD-4.4 systemd 常驻服务

> **目标**：让这套应用**开机自启**、**崩了自动重启**，而且**只监听 `127.0.0.1:8001`**
> （不暴露到公网，所以**不用动安全组**，方案 B 成立的关键就在这）。
>
> **服务名**：`school-qa.service`
> **工作目录**：`/opt/llm_learn`
> **运行用户**：`schoolqa`（第 1 篇建的，不给 shell）

---

## 第 1 步：创建单元文件

```bash
sudo tee /etc/systemd/system/school-qa.service >/dev/null <<'EOF'
[Unit]
Description=Campus QA (RAG) FastAPI service
Documentation=file:/opt/llm_learn/docs/deploy/02-systemd.md
After=network-online.target
Wants=network-online.target
# 防止"起来就崩、崩了立刻重启"把 CPU 打满：60 秒内最多重启 5 次
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=schoolqa
Group=schoolqa
WorkingDirectory=/opt/llm_learn

# ---- 环境：2 核 2G 机器的省内存设置 ----
# PYTHONUNBUFFERED：日志实时进 journal，排查问题时不会"卡着不输出"
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
# 下面四个把 数学库/OpenBLAS 的线程数钉成 1：2 核机器上多线程只会抢 CPU 和内存
Environment=OMP_NUM_THREADS=1
Environment=OPENBLAS_NUM_THREADS=1
Environment=MKL_NUM_THREADS=1
Environment=NUMEXPR_NUM_THREADS=1
# glibc 默认给每个线程开 64MB 内存池，多线程场景下会成倍浪费；压到 2 个
Environment=MALLOC_ARENA_MAX=2
# 收紧 HOME（配合下面的 ProtectHome），避免库去 /home 找缓存
Environment=HOME=/opt/llm_learn

# ---- 启动命令 ----
# 必须用 .venv 里的 python；-m uvicorn 走模块方式，配合 WorkingDirectory 才能 import backend
# workers 固定 1：每个 worker 都是一份完整内存占用，2G 机器开不起第二个
# 生产环境绝不要加 --reload
ExecStart=/opt/llm_learn/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001 --workers 1 --timeout-keep-alive 30

Restart=always
RestartSec=3
TimeoutStopSec=20
KillSignal=SIGINT

# ---- 内存红线（2 GiB 总内存，必须给项目1 留余量）----
# MemoryHigh：软上限，超过后内核开始"收紧"该 cgroup（回收页缓存、优先换出），服务不会死
MemoryHigh=700M
MemoryMax=1000M
# 允许最多用 1G swap；上限=1000M 内存 + 1000M swap，足以扛住峰值
MemorySwapMax=1G

# ---- 安全加固（可选；若服务起不来，整段删掉重来时优先删这里）----
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=yes
ReadWritePaths=/opt/llm_learn
LimitNOFILE=4096

# ---- 日志 ----
StandardOutput=journal
StandardError=journal
SyslogIdentifier=school-qa

[Install]
WantedBy=multi-user.target
EOF
```

**检查语法/内容**：

```bash
systemctl cat school-qa
```

> **为什么没写 `EnvironmentFile=/opt/llm_learn/.env`**：
> 应用是**自己**用 `backend/config.py` 里的 `load_dotenv()` 读 `.env` 的（且 `override=True`）。
> 保持"配置只有一个来源"更不容易出错，所以这里不重复注入。

> **关于 `MemorySwapMax`**：它需要 cgroup v2（Ubuntu 22.04 默认就是 v2，`stat -fc %T /sys/fs/cgroup` 应显示 `cgroup2fs`）。
> 万一你的机器是 cgroup v1，systemd 会启动失败并抱怨 `MemorySwapMax`。
> 那就**把这一行删掉**，`daemon-reload` 后重启 —— 其余配置照旧有效。

---

## 第 2 步：启动并设开机自启

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now school-qa
```

`enable --now` = 设开机自启 + 立即启动。

---

## 第 3 步：验证

```bash
# 3.1 状态：期望 active (running)，且 User=schoolqa
systemctl status school-qa --no-pager

# 3.2 看启动日志：期望出现 [startup] 完成
sudo journalctl -u school-qa -n 50 --no-pager

# 3.3 关键：确认只监听回环地址（0.0.0.0 是错的！）
sudo ss -lntp | grep 8001
# 期望形如： LISTEN 0 2048 127.0.0.1:8001 0.0.0.0:* users:(("python",pid=...,fd=...))
#   看到 127.0.0.1:8001 → 正确（外网打不到）
#   看到 0.0.0.0:8001   → 不对，说明 --host 写错了

# 3.4 接口自测
curl -s http://127.0.0.1:8001/health
# 期望：{"status":"ok","message":"RAG API is running"}

# 3.5 看内存实际占用（拿这个数去校准第 1 步的 MemoryHigh/Max）
systemctl show school-qa -p MemoryCurrent -p MemoryHigh -p MemoryMax
# MemoryCurrent 单位是字节，除以 1048576 得 MiB
```

---

## 第 4 步：把内存数字校准一下

```bash
# 看这套服务真实吃多少
systemctl show school-qa -p MemoryCurrent \
  | awk -F= '{printf "MemoryCurrent = %.1f MiB\n", $2/1048576}'

# 看全机水位
free -h
# 看 cgroup 水位排名（谁最吃内存一目了然）
systemd-cgtop -1 --order=memory 2>/dev/null | head
```

**判断标准**（2 GiB 机器）：

| 现象 | 处置 |
|---|---|
| 服务其实只吃 250–450 MiB | 保持 `700M/1000M` 不动，安全 |
| `MemoryCurrent` 已接近或顶到 `MemoryMax` | 把 `MemoryMax` 提到 `1300M`，并回头确认项目1 的占用 |
| `journalctl` 里出现 `oom-kill` | 见下方"排障"：要么放宽上限，要么查是不是循环在泄漏 |

改完限制后：

```bash
sudo systemctl daemon-reload
sudo systemctl restart school-qa
```

---

## 第 5 步：常用运维命令（存下来）

```bash
# 重启 / 停止 / 启动
sudo systemctl restart school-qa
sudo systemctl stop school-qa
sudo systemctl start school-qa

# 实时看日志（相当于 tail -f，最常用）
sudo journalctl -u school-qa -f

# 看最近 200 行、带时间戳
sudo journalctl -u school-qa -n 200 --no-pager

# 只看某段时间
sudo journalctl -u school-qa --since "10 min ago" --no-pager

# 关掉开机自启 / 彻底停用
sudo systemctl disable --now school-qa

# 改了代码后重启生效
cd /opt/llm_learn && sudo git pull     # 或重新 scp
sudo systemctl restart school-qa
```

---

## 第 6 步：排障速查表

| 现象 | 原因 | 处置 |
|---|---|---|
| `status` 显示 `activating (auto-restart)` 反复重启 | 启动即崩 | `sudo journalctl -u school-qa -n 80 --no-pager` 看第一段 traceback |
| 日志里 `ValueError: DASHSCOPE_API_KEY 未设置` | `.env` 没传上来 / 权限读不到 / 变量名拼错 | 检查 `/opt/llm_learn/.env` 存在、`chmod 600`、属主 `schoolqa`、里面有 `DASHSCOPE_API_KEY=` |
| 日志里 `RuntimeError: vectorstore 未初始化` | 向量库目录缺失 | 见 01 篇附录 B 重建 |
| 启动报 `PermissionError` 指向 `chroma_db_langchain/` | 目录属主不是 `schoolqa`（Chroma 要写 WAL） | `sudo chown -R schoolqa:schoolqa /opt/llm_learn` |
| `status` 出现 `code=killed, signal=KILL` + journal 有 `oom-kill` | 内存顶到 `MemoryMax` | 提到 `1300M`；或检查是不是漏了 `--workers 1` |
| `ss -lntp` 显示 `0.0.0.0:8001` | `--host` 写成了 `0.0.0.0` | 改回 `127.0.0.1`，`daemon-reload` + `restart` |
| `ModuleNotFoundError: No module named 'backend'` | `WorkingDirectory` 不对 | 确认 `WorkingDirectory=/opt/llm_learn`，且该目录下有 `backend/__init__.py` |
| 服务起不来但看不出原因 | 加固项与运行环境冲突 | 把 `NoNewPrivileges`~`LimitNOFILE` 整段注释掉，`daemon-reload` 后重启再试 |

**前台手动跑一遍（把 systemd 摘出去，直接看报错）**：

```bash
sudo -u schoolqa -H bash -c 'cd /opt/llm_learn && .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001'
```

这条能跑通、systemd 跑不通 → 基本就是环境变量差异（`HOME` / 线程数）或加固项的问题。

---

## ✅ 本阶段完成标志

- [ ] `systemctl status school-qa` = `active (running)`
- [ ] 已 `enable`（`systemctl is-enabled school-qa` → `enabled`）
- [ ] `ss -lntp | grep 8001` 显示 **`127.0.0.1:8001`**（不是 `0.0.0.0`）
- [ ] `curl -s http://127.0.0.1:8001/health` 返回 ok
- [ ] `sudo reboot` 后服务能自动起来（**可选但建议验一次**）
- [ ] `MemoryCurrent` 小于 `MemoryMax`，且 `free -h` 还有余量

**下一步** → [03-nginx.md](./03-nginx.md)（挂到 `http://8.149.236.20/school-qa/`）

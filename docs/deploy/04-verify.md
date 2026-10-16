# CARD-4.6 部署验证清单

> 逐项跑、逐项打勾。**每一项都给了「命令」和「期望结果」**，不对就查最后一节的排障表。
>
> 三大验收目标（卡片原文）：
> 1. `http://8.149.236.20/school-qa/` 可访问
> 2. 项目1 的 `/` **未受影响**
> 3. 前端 **SSE 流式**正常（不是"一次性吐完"）

---

## 一键验收脚本（省事版）

存成 `/root/verify-school-qa.sh`，`chmod +x` 后直接跑，会打印一张结果表：

```bash
sudo tee /root/verify-school-qa.sh >/dev/null <<'EOF'
#!/usr/bin/env bash
# 校园问答 部署验收（在服务器上跑）
BASE_LOCAL="http://127.0.0.1"
PROJ1="http://127.0.0.1/"
SQ="${BASE_LOCAL}/school-qa/"
PASS=0; FAIL=0
ck() { # ck 名称 期望 实际
  if [ "$2" = "$3" ]; then printf '  ✅ %-42s %s\n' "$1" "$3"; PASS=$((PASS+1));
  else printf '  ❌ %-42s 期望=%s 实际=%s\n' "$1" "$2" "$3"; FAIL=$((FAIL+1)); fi
}
code() { curl -s -o /dev/null -w '%{http_code}' -m 15 "$1"; }

echo "===== A. systemd 服务 ====="
printf '  %-44s %s\n' "systemctl is-active" "$(systemctl is-active school-qa)"
printf '  %-44s %s\n' "systemctl is-enabled" "$(systemctl is-enabled school-qa)"
echo "  监听情况:"; ss -lntp 2>/dev/null | grep 8001 | sed 's/^/    /'
printf '  %-44s %s\n' "MemoryCurrent(MiB)" \
  "$(systemctl show school-qa -p MemoryCurrent | awk -F= '{printf "%.1f", $2/1048576}')"

echo "===== B. 直连后端（绕过 nginx）====="
ck "后端 /health" "200" "$(code http://127.0.0.1:8001/health)"
ck "后端 /" "200" "$(code http://127.0.0.1:8001/)"

echo "===== C. 经 nginx ====="
ck "项目1 /" "200" "$(code $PROJ1)"
ck "school-qa 首页 /school-qa/" "200" "$(code $SQ)"
ck "静态 app.js" "200" "$(code ${SQ}static/app.js)"
ck "静态 style.css" "200" "$(code ${SQ}static/style.css)"
ck "无斜杠 301" "301" "$(code http://127.0.0.1/school-qa)"
ck "health 经 nginx" "200" "$(code ${SQ}health)"

echo "===== D. SSE 流式（HTTP 头）====="
HDR=$(curl -s -D - -o /dev/null -m 60 -N -X POST "${SQ}chat/stream" \
      -H 'Content-Type: application/json' -d '{"question":"你好"}')
echo "$HDR" | grep -iE 'HTTP/|content-type|transfer-encoding|x-accel-buffering' | sed 's/^/    /'

echo
echo "===== 汇总：PASS=$PASS  FAIL=$FAIL ====="
EOF
sudo chmod +x /root/verify-school-qa.sh
sudo /root/verify-school-qa.sh
```

下面分节说明每一项**为什么这么验**。

---

## A. 服务层（systemd）

```bash
systemctl status school-qa --no-pager | head -12
```

| 检查点 | 期望 |
|---|---|
| `Active` | `active (running)` |
| `Loaded` | `enabled`（开机自启） |
| `Main PID` | 有具体 pid（不是 `0`） |
| 最近日志 | 有 `[startup] 完成`，**没有** traceback |

```bash
sudo journalctl -u school-qa -n 30 --no-pager
sudo journalctl -u school-qa --since "30 min ago" --no-pager | grep -iE 'error|traceback|exception' || echo "近 30 分钟无 error ✓"
```

- [ ] 状态 `active (running)`
- [ ] 日志出现 `[startup] 初始化向量库...` → `[startup] 完成`
- [ ] 无 traceback

---

## B. 直连后端（先证明应用本身没问题）

**先绕过 nginx** —— 这样出问题时能立刻分清是"应用的锅"还是"nginx 的锅"。

```bash
curl -s http://127.0.0.1:8001/health
# 期望：{"status":"ok","message":"RAG API is running"}

curl -s -o /dev/null -w 'index=%{http_code} type=%{content_type}\n' http://127.0.0.1:8001/
# 期望：index=200 type=text/html; charset=utf-8

curl -s -o /dev/null -w 'app.js=%{http_code}\n' http://127.0.0.1:8001/static/app.js
# 期望：app.js=200
```

- [ ] `/health` 返回 `{"status":"ok",...}`
- [ ] `/` = 200 且 `content_type` 是 `text/html`
- [ ] `/static/app.js` = 200

**再确认监听地址正确**（安全组没开 8001，所以必须只监听回环）：

```bash
sudo ss -lntp | grep 8001
# 期望：127.0.0.1:8001
# 若出现 0.0.0.0:8001 → --host 写错了，改回 127.0.0.1
```

- [ ] 显示 `127.0.0.1:8001`

---

## C. `/school-qa/` 可访问（验收目标 1）

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/school-qa/          # 期望 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/school-qa/health     # 期望 200

# 首页内容里"引用的资源路径"必须是相对的（不能出现 /static/ 这种绝对路径）
curl -s http://127.0.0.1/school-qa/ | grep -nE 'href=|src='
# ✅ 期望看到：href="static/style.css"  /  src="static/app.js"
# ❌ 若看到：   href="/static/style.css"  /  src="/static/app.js" → 前端第 0 步没做，必然白屏

# 静态资源
curl -s -o /dev/null -w 'app.js = %{http_code}\n'   http://127.0.0.1/school-qa/static/app.js
curl -s -o /dev/null -w 'style.css = %{http_code}\n' http://127.0.0.1/school-qa/static/style.css
# 期望都是 200

# 无斜杠跳转（保证相对路径解析正确）
curl -s -o /dev/null -w 'code=%{http_code} → %{redirect_url}\n' http://127.0.0.1/school-qa
# 期望：code=301 → http://127.0.0.1/school-qa/
```

- [ ] `/school-qa/` = 200
- [ ] `/school-qa/health` = 200
- [ ] 首页里的 `href/src` 都是**相对路径**
- [ ] `/school-qa/static/app.js` = 200、`/school-qa/static/style.css` = 200
- [ ] `/school-qa`（无斜杠）= 301 → `/school-qa/`

---

## D. 项目1 未受影响（验收目标 2）

```bash
# 1) 状态码
curl -s -o /dev/null -w '项目1 状态码 = %{http_code}\n' http://127.0.0.1/
# 期望 200

# 2) 和改 nginx 之前存的基线对比（01/03 篇让你存过）
cat /tmp/project1_baseline.md5
curl -s http://127.0.0.1/ | md5sum
# 动态页面 md5 可能变化；重点是"能正常返回、内容结构不变"

# 3) 确认项目1 的 location 一个字没动
sudo nginx -T 2>/dev/null | sed -n '/server {/,/^}/p' | head -40
# 目视确认项目1 原有的 location / { ... } 还是原样

# 4) 确认没有把 /static/ 或 /chat/ 这种"站点根"路径劫持走
curl -s -o /dev/null -w '根 /static/app.js = %{http_code}\n' http://127.0.0.1/static/app.js
# 这应该是项目1 自己的结果（200 或 404 都行），但**不能**变成我们后端的 app.js。
# 快速核对：比对长度，若与 http://127.0.0.1/school-qa/static/app.js 一模一样 → 说明劫持了，要回滚
echo "根:        $(curl -s http://127.0.0.1/static/app.js | wc -c) bytes"
echo "school-qa: $(curl -s http://127.0.0.1/school-qa/static/app.js | wc -c) bytes"
```

- [ ] 项目1 `/` = 200
- [ ] 页面内容/结构正常（可打开浏览器肉眼确认一次）
- [ ] 项目1 原有 `location` 未被修改
- [ ] 站点根的 `/static/...` **没有**被路由到我们后端

---

## E. SSE 流式正常（验收目标 3）—— **最关键的一项**

### E1. 先用 HTTP 头排除"被缓冲"

```bash
curl -s -D - -o /dev/null -m 60 -N -X POST http://127.0.0.1/school-qa/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"question":"学校在哪个城市？"}'
```

**期望看到**：

```
HTTP/1.1 200 OK
content-type: text/event-stream; charset=utf-8
transfer-encoding: chunked          ← 有这条 = 分块传输，好事
x-accel-buffering: no               ← 后端主动告诉 nginx 别缓冲
```

**不该看到** `content-length: ...`（有它说明整个响应被攒起来了）。

- [ ] `content-type: text/event-stream`
- [ ] 有 `transfer-encoding: chunked`
- [ ] 有 `x-accel-buffering: no`
- [ ] **没有** `content-length`

### E2. 用时间戳证明"真的一点点在吐"

**这是判断流式是否真的生效的硬证据** —— 每一行前面打到达时刻：

```bash
curl -N -s -m 60 -X POST http://127.0.0.1/school-qa/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"question":"学校在哪个城市？"}' \
| while IFS= read -r line; do
    printf '%s | %s\n' "$(date +%H:%M:%S.%3N)" "$line"
  done
```

**期望**（时间戳是**递增且分散**的，说明是流式）：

```
09:12:31.204 | data: 学校
09:12:31.487 | data: 地处
09:12:31.790 | data: 重庆市
09:12:32.115 | data: 。
09:12:32.118 | data: [DONE]
09:12:32.120 | 
```

**失败的样子**（所有行时间戳几乎同一个毫秒 → 被缓冲了）：

```
09:12:35.001 | data: 学校地处重庆市。
09:12:35.002 | data: [DONE]
```

- [ ] 时间戳**递增且分散**（首尾相差 ≥ 0.3 秒更好）
- [ ] 最后一行是 `data: [DONE]`

> **如果是"被缓冲"的样子**：确认 `location` 里 `proxy_buffering off;` **和** `gzip off;` 都在
> （`sudo nginx -T | grep -A 25 'location /school-qa/'`）。
> 项目1 的 server 块里如果有 `gzip on;` 或 `proxy_buffering on;`，会被子 location 继承 —— 所以我们必须显式关掉。

### E3. 多轮历史也顺带验一下

```bash
curl -N -s -m 60 -X POST http://127.0.0.1/school-qa/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"question":"那它是什么类型的学校？","history":[{"role":"user","content":"重庆移通学院在哪个城市？"},{"role":"assistant","content":"重庆移通学院位于重庆市。"}]}'
```

**期望**：回答里出现「重庆移通学院」，也就是代词「它」被正确解析。

- [ ] 带 `history` 的请求能正常返回，且答案复用了上文

---

## F. 前端功能手测（浏览器）

打开 **`http://8.149.236.20/school-qa/`**（在你的本机浏览器里，不是服务器上）：

| 操作 | 期望 |
|---|---|
| 打开页面 | 有标题、有输入框、**有样式**（不是裸 HTML） |
| 输入「学校在哪个城市？」回车 | 先出现「思考中」三点 → 再逐字出现答案（**打字机效果**） |
| 连续问第 2、3 题 | **历史留在屏幕上**，没有清空 |
| 第 3 问用代词（「那它有几个校区？」） | 能联系上文，答出校区信息 |
| 拔网线/断网后提问 | 出现红色错误气泡 + **重试**按钮，**不弹 alert、不白屏** |
| 恢复网络后点「重试」 | 正常出答案，且**不会重复出现同一条问题** |
| 点右上角「清空对话」 | 回到欢迎语；再问第一题时历史为空 |

- [ ] 页面有样式
- [ ] 打字机效果（不是等很久后一次性出现）
- [ ] 连续 3 题历史保留
- [ ] 代词问题能联系上文
- [ ] 断网 → 红色气泡 + 重试，不白屏
- [ ] 重试不重复问题
- [ ] 清空按钮回到初始状态

**浏览器里再看一眼开发者工具的 Network**（可选但很有用）：
打开 F12 → Network → 提问 → 找到 `chat/stream` 请求 →
**Response 面板应该"一行一行往外冒"**，而不是等几秒后整段出现。

---

## G. 外网访问 + 安全面

**在你自己的 Windows 上**（PowerShell，用 `curl.exe` 避免和 `Invoke-WebRequest` 的别名打架）：

```powershell
# G1 外网能访问子路径
curl.exe -s -o NUL -w "school-qa 外网 = %{http_code}\n" http://8.149.236.20/school-qa/
# 期望 200

# G2 项目1 外网正常
curl.exe -s -o NUL -w "项目1 外网 = %{http_code}\n" http://8.149.236.20/
# 期望 200

# G3 8001 不应该能从外网访问（安全组没开 + 只监听回环）
curl.exe -m 8 -s -o NUL -w "8001 = %{http_code}\n" http://8.149.236.20:8001/health
# 期望：超时失败（退出码 28）。若返回 200 → 监听地址或安全组有问题，赶紧收敛
```

- [ ] `http://8.149.236.20/school-qa/` = 200
- [ ] `http://8.149.236.20/` = 200
- [ ] `http://8.149.236.20:8001/health` **访问不到**（超时）

---

## H. 资源与稳定性（2 GiB 机器专项）

```bash
# H1 内存水位
free -h
systemctl show school-qa -p MemoryCurrent -p MemoryHigh -p MemoryMax
systemctl show school-qa -p MemoryCurrent | awk -F= '{printf "服务占用 = %.1f MiB\n", $2/1048576}'
# 期望：available 还有余量；服务占用 < MemoryMax

# H2 有没有被 OOM 杀过
sudo journalctl -u school-qa --since "1 day ago" --no-pager | grep -iE 'oom|killed|out of memory' || echo "无 OOM 记录 ✓"
sudo dmesg -T 2>/dev/null | grep -i 'oom' | tail -5 || true

# H3 swap 生效
swapon --show

# H4 磁盘
df -h /
journalctl --disk-usage
```

- [ ] `free -h` 仍有可用内存，`Swap` 约 2.0Gi
- [ ] 服务占用 < `MemoryMax`
- [ ] 无 OOM 记录

**重启自启验证（建议做一次）**：

```bash
sudo reboot
# 等 1~2 分钟重新 SSH 上来
systemctl is-active school-qa nginx
curl -s -o /dev/null -w '重启后 school-qa = %{http_code}\n' http://127.0.0.1/school-qa/
curl -s -o /dev/null -w '重启后 项目1    = %{http_code}\n' http://127.0.0.1/
```

- [ ] 重启后两个服务都自动起来，两个入口都 200

---

## 失败排查速查表

| 症状 | 最可能的原因 | 一句话处置 |
|---|---|---|
| 页面**白屏 / 无样式 / 点了没反应** | 前端还是绝对路径 | 查 `curl -s .../school-qa/ \| grep src=`，应为 `static/app.js` |
| 首页 200 但 `/school-qa/static/app.js` **404** | `proxy_pass` 结尾漏 `/` | 改成 `proxy_pass http://127.0.0.1:8001/;` 再 `nginx -t && reload` |
| **502** | 后端没起来 / 不在 8001 | `systemctl status school-qa`；`ss -lntp \| grep 8001` |
| **504** | 上游慢 / 超时短 | 加 `proxy_read_timeout 300s;`；看后端日志 |
| 答案**一次性出现**（不是打字机） | SSE 被缓冲 | 确认 `proxy_buffering off;` + `gzip off;`；`nginx -T` 复核 |
| `/school-qa/` 跳到项目1 | 请求落在别的 server 块 | `grep -rn 'listen 80\|server_name' /etc/nginx/sites-enabled/` |
| 项目1 也坏了 | `include` 放错位置 | 回滚：`sudo tar -xzf /root/nginx-backup-<STAMP>.tar.gz -C /etc && nginx -t && systemctl reload nginx` |
| 提问返回「资料中未提到」 | 向量库没传上去 | `ls /opt/llm_learn/chroma_db_langchain/`；缺就按 01 篇附录 B 重建 |
| 服务反复重启 | 启动即崩 | `journalctl -u school-qa -n 80 --no-pager` 看第一段 traceback |
| 改完 nginx 后**两个入口都 404** | `nginx -t` 过了但 include 位置不对 | `sudo nginx -T \| grep -n school-qa` 看它落在哪个 server 块 |

**通用排查顺序**（从里到外，别跳步）：

```
systemctl status school-qa      →  应用活没活
  ↓ 活
curl 127.0.0.1:8001/health      →  应用层通不通
  ↓ 通
curl 127.0.0.1/school-qa/health →  nginx 转发通不通
  ↓ 通
curl 8.149.236.20/school-qa/    →  外网通不通
```

---

## ✅ 最终打勾表

- [ ] A 服务 `active` + `enabled`，日志有 `[startup] 完成`
- [ ] B `127.0.0.1:8001/health` 返回 ok，监听地址是 `127.0.0.1`
- [ ] C `http://127.0.0.1/school-qa/` = 200，静态资源 = 200，无斜杠 301
- [ ] D 项目1 `/` = 200 且未被劫持
- [ ] E SSE：`chunked` + `x-accel-buffering: no` + 时间戳递增分散 + 结尾 `[DONE]`；带 history 生效
- [ ] F 浏览器手测 7 项全过
- [ ] G 外网 200，8001 从外网打不到
- [ ] H 内存有余量、无 OOM、重启自启正常

全部打勾 → **阶段 4 部署完成**，可以开始写 CARD-2.x（MySQL 接入）。

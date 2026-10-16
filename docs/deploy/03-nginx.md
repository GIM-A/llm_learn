# CARD-4.5 nginx 子路径反代（/school-qa/）

> **目标**：让 `http://8.149.236.20/school-qa/` 能访问这套服务，**复用现有 nginx**，
> **绝不影响项目1 的 `/`**，不加安全组、不买域名。
>
> **原理**：nginx 把 `/school-qa/xxx` 去掉前缀后转发到本机 `127.0.0.1:8001/xxx`。
> 后端代码**一个字都不用改**（`main.py` 的 `/`、`/static`、`/chat/stream` 全部保持原样）。

---

## 第 0 步（**必做，否则白屏**）：把前端 3 处绝对路径改成相对路径

### 为什么必须改

前端现在是**以 `/` 开头**的绝对路径，浏览器会拼成**站点根**：

| 文件 | 现在 | 在 `/school-qa/` 下浏览器实际请求 | 结果 |
|---|---|---|---|
| `frontend/index.html` | `href="/static/style.css"` | `http://8.149.236.20/static/style.css` | ❌ 打到项目1，404 或拿到别人的文件 → **页面没样式** |
| `frontend/index.html` | `src="/static/app.js"` | `http://8.149.236.20/static/app.js` | ❌ **JS 不加载 → 输入框点了没反应** |
| `frontend/app.js` | `fetch("/chat/stream", …)` | `http://8.149.236.20/chat/stream` | ❌ 打到项目1 → 提问无响应 |

改成**相对路径**后，浏览器基于"当前文档地址"拼接：文档是 `…/school-qa/`，
`static/style.css` → `…/school-qa/static/style.css` ✅，`chat/stream` → `…/school-qa/chat/stream` ✅。
**而且本地 `http://127.0.0.1:8000/` 直接访问同样正常**（这种写法两边都对）。

### 具体改什么（共 3 行）

**`frontend/index.html`（第 9 行）**

```diff
-    <link rel="stylesheet" href="/static/style.css">
+    <link rel="stylesheet" href="static/style.css">
```

**`frontend/index.html`（第 45 行）**

```diff
-    <script src="/static/app.js"></script>
+    <script src="static/app.js"></script>
```

**`frontend/app.js`（第 164 行，`sendQuestion()` 里发起请求那行）**

```diff
-        const resp = await fetch("/chat/stream", {
+        const resp = await fetch("chat/stream", {
```

> 顺便把文件开头注释里"通过 FastAPI 的 /static 挂载点访问"这类描述一并更新也可以，非必须。

### 怎么改

**推荐：本地改 + 提交 + 重新上传**，这样仓库和服务器不会漂移。

```powershell
# 本地 D:\llm_learn
git add frontend/index.html frontend/app.js
git commit -m "fix(frontend): 改用相对路径，支持部署到子路径 /school-qa/"
git push
```

改完**务必本地起一次服务肉眼确认页面正常**（`http://127.0.0.1:8000/`），再走 01 篇第 5 步上传。

> **为什么不用 nginx 的 `sub_filter` 去重写 HTML/JS**：
> 那需要额外模块、要对 HTML 和 JS 分别做字符串替换，任何一次前端改动都可能失配，
> 反而更难维护。改 3 行路径是成本最低、最稳的做法。

---

## 第 1 步：改动前先备份 nginx 配置

**任何 `nginx` 改动之前都先备份**，出问题能 1 分钟回滚。

```bash
# 1.1 先看清现状：哪个文件在监听 80 端口
sudo grep -rn "listen" /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ 2>/dev/null
# 记下监听 80 的那个文件名（Ubuntu 默认是 /etc/nginx/sites-enabled/default）

# 1.2 整体打包备份（最省事、最完整）
STAMP=$(date +%F-%H%M%S)
sudo tar -czf /root/nginx-backup-$STAMP.tar.gz -C /etc nginx
ls -lh /root/nginx-backup-$STAMP.tar.gz
echo ">>> 备份文件：/root/nginx-backup-$STAMP.tar.gz"
```

**把这个文件名抄到小本本上**（回滚要用）。

```bash
# 1.3 顺手存一份项目1 的响应基线，第 4 篇验证时要对比
curl -s -o /dev/null -w '项目1 状态码 = %{http_code}\n' http://127.0.0.1/
curl -s http://127.0.0.1/ | md5sum | tee /tmp/project1_baseline.md5
```

---

## 第 2 步：把 location 写成独立片段文件

**好处**：只需要在现有 `server` 块里插**一行** `include`，改动面最小、最容易回滚；
配置本体放在独立文件里，将来调 SSE 参数也不用碰项目1 的文件。

```bash
sudo mkdir -p /etc/nginx/snippets

sudo tee /etc/nginx/snippets/school-qa.conf >/dev/null <<'EOF'
# ============================================================
# /school-qa/  →  http://127.0.0.1:8001/   (school-qa.service)
# 由 CARD-4.5 添加；回滚方式见 docs/deploy/03-nginx.md
# ============================================================

location /school-qa/ {
    # ⭐ 结尾这个 "/" 是关键，不能省：
    #   location /school-qa/ 匹配前缀 /school-qa/
    #   proxy_pass 结尾带 / → 把匹配到的 /school-qa/ 替换成 /
    #   例：/school-qa/static/app.js  →  转发成  /static/app.js  ✅
    # 少了结尾的 /，就会原样转发成 /school-qa/static/app.js → 后端 404
    proxy_pass http://127.0.0.1:8001/;

    proxy_http_version 1.1;
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    # 清掉默认的 Connection: close，与上游保持长连接
    proxy_set_header Connection        "";

    # ===== SSE 流式必需的几条（缺一条，"打字机"就会变成"一次性吐完"）=====
    proxy_buffering off;          # 关响应缓冲：上游吐一个字节就立刻下发
    proxy_cache off;              # 不缓存
    gzip off;                     # gzip 会攒缓冲再压缩，同样会破坏流式
    proxy_request_buffering off;  # 请求体也不缓冲
    chunked_transfer_encoding on;

    # LLM 首字可能要等几秒，别用默认的 60s 把连接掐断
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
}

# 少写结尾斜杠时补一个 301：
# 因为页面里的"相对路径"依赖文档地址以 "/" 结尾，
# 如果用户访问 /school-qa（无斜杠），相对路径会被解析到站点根，静态资源就 404 了。
location = /school-qa {
    return 301 /school-qa/;
}
EOF

# 看一眼写进去的内容对不对
cat /etc/nginx/snippets/school-qa.conf
```

---

## 第 3 步：在 80 端口的 `server` 块里挂上它

```bash
# 3.1 打开第 1 步查到的那份配置（以 Ubuntu 默认站点为例）
sudo nano /etc/nginx/sites-available/default
```

在 `server { ... }` **内部**（`listen 80;` 那个块里），**任意空行处**加一行：

```nginx
    include /etc/nginx/snippets/school-qa.conf;
```

改完形如：

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    root /var/www/html;
    index index.html;

    # ⭐ 只加这一行，不碰项目1 的任何现有 location
    include /etc/nginx/snippets/school-qa.conf;

    location / {
        try_files $uri $uri/ =404;      # ← 项目1 原本的配置，保持不动
    }
}
```

`nano` 保存：`Ctrl+O` → 回车 → `Ctrl+X`。

> **小技巧**：用 `/` 搜索定位更快 —— 在 nano 里按 `Ctrl+W`，输入 `server_name`，回车跳过去。
>
> **要改的是 `sites-available/` 下的真实文件**（`sites-enabled/` 里通常是符号链接，改它等于改真身，但容易迷路）。

---

## 第 4 步：测试通过再 reload（**顺序不能反**）

```bash
# 4.1 语法检查 —— 必须先过这一关
sudo nginx -t
# 期望：
#   nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
#   nginx: configuration file /etc/nginx/nginx.conf test is successful

# 4.2 确认 include 真的生效了（nginx -T 会打印"合并后"的完整配置）
sudo nginx -T 2>/dev/null | grep -n "school-qa" 
# 期望能看到： include /etc/nginx/snippets/school-qa.conf;
#             location /school-qa/ {
#             location = /school-qa {

# 4.3 平滑重载（不中断现有连接，项目1 完全无感）
sudo systemctl reload nginx
# 若这条报错，用： sudo nginx -s reload

# 4.4 立刻确认 nginx 没挂
systemctl is-active nginx        # 期望 active
```

> **`nginx -t` 失败就停在这里，千万别 reload**。把报错贴出来对照修；
> 急着恢复就先执行第 6 步的回滚。

---

## 第 5 步：快速自测

```bash
# 5.1 首页（经 nginx）
curl -s -o /dev/null -w 'school-qa 首页 = %{http_code}\n' http://127.0.0.1/school-qa/
# 期望 200

# 5.2 静态资源（最容易 404 的地方）
curl -s -o /dev/null -w 'app.js  = %{http_code}\n' http://127.0.0.1/school-qa/static/app.js
curl -s -o /dev/null -w 'style.css = %{http_code}\n' http://127.0.0.1/school-qa/static/style.css
# 期望都是 200；如果是 404 → proxy_pass 结尾的 "/" 漏了

# 5.3 无斜杠跳转
curl -s -o /dev/null -w 'no-slash = %{http_code} → %{redirect_url}\n' http://127.0.0.1/school-qa
# 期望 301 → http://127.0.0.1/school-qa/

# 5.4 项目1 没被动
curl -s -o /dev/null -w '项目1 = %{http_code}\n' http://127.0.0.1/
# 期望 200（且和第 1 步记的基线一致）
```

完整的验收清单见 **[04-verify.md](./04-verify.md)**。

---

## 第 6 步：回滚（出问题就照这个来）

```bash
# 6.1 用第 1 步的备份恢复整个 /etc/nginx
sudo tar -xzf /root/nginx-backup-<把第1步的STAMP填这里>.tar.gz -C /etc

# 6.2 确认恢复后的配置没问题
sudo nginx -t

# 6.3 重新加载
sudo systemctl reload nginx

# 6.4 （可选）把新增的片段文件也删掉
sudo rm -f /etc/nginx/snippets/school-qa.conf
```

**只想临时关掉这一个入口**（保留其它改动，最小动作）：

```bash
# ⚠️ 把最后的文件名换成"你实际加 include 的那个文件"（第 1 步 grep 出来的那个）
sudo sed -i 's|^\([[:space:]]*include /etc/nginx/snippets/school-qa.conf;\)|#\1|' /etc/nginx/sites-available/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## 第 7 步：排障速查表

| 现象 | 原因 | 处置 |
|---|---|---|
| `/school-qa/` 返回 **404** | `proxy_pass` 结尾漏了 `/`；或后端没起 | `curl -s http://127.0.0.1:8001/health` 先确认后端活着；再检查 `proxy_pass http://127.0.0.1:8001/;` 的斜杠 |
| 页面能开但**没样式/点了没反应** | 前端还是绝对路径（第 0 步没做） | `curl -s http://127.0.0.1/school-qa/ \| grep -E 'href\|src'`，看到 `/static/` 就说明没改 |
| `curl …/school-qa/static/app.js` → **404** | 同第 1 条 | 同上 |
| 页面**一直转圈**，但答案最后一次性出现 | SSE 被缓冲 | 确认 `proxy_buffering off;` + `gzip off;` 都在 `location` 里；用 `sudo nginx -T` 确认生效 |
| **502 Bad Gateway** | 后端没在 8001 上监听 | `sudo ss -lntp \| grep 8001`、`systemctl status school-qa` |
| **504 Gateway Timeout** | 上游太慢 / 超时太短 | 确认 `proxy_read_timeout 300s;` 已加；同时看后端日志有无报错 |
| **403** | `location` 块里混进了 `deny`；或目录权限 | 检查 `nginx -T` 里该 location 的完整内容 |
| 项目1 **也 404 了** | `include` 放到了错误的 `server` 块（或放到了最外层） | `sudo nginx -T` 检查位置；按第 6 步回滚 |
| 访问 `/school-qa/` 却跳到项目1 | 存在多个 80 端口 server 块，请求落到了 `default_server` | `sudo grep -rn "listen 80\|server_name" /etc/nginx/sites-enabled/`；把 `include` 加进**真正生效**的那个块 |

**看 nginx 自己的报错**：

```bash
sudo tail -n 50 /var/log/nginx/error.log
```

---

## ✅ 本阶段完成标志

- [ ] 前端 3 处已改为相对路径（`grep -rn '"/static\|"/chat' frontend/` **无输出**）
- [ ] nginx 配置已备份（`/root/nginx-backup-*.tar.gz` 存在）
- [ ] `/etc/nginx/snippets/school-qa.conf` 已创建
- [ ] 80 端口 `server` 块里已 `include` 该片段
- [ ] `sudo nginx -t` **successful**
- [ ] `sudo nginx -T | grep school-qa` 能看到 location
- [ ] `sudo systemctl reload nginx` 无报错，nginx 仍 `active`
- [ ] `http://127.0.0.1/school-qa/` = 200
- [ ] `http://127.0.0.1/school-qa/static/app.js` = 200
- [ ] `http://127.0.0.1/`（项目1）仍 = 200

**下一步** → [04-verify.md](./04-verify.md)（逐项验收，含 SSE 流式的硬证据）

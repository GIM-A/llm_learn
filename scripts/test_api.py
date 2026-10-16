"""用 Python 测本地 /chat 接口（绕开 PowerShell 的编码 / 引号问题）

端口来源（CARD-5.5）：
    端口从 backend.config.DEFAULT_PORT 读取，不再把 8001 写死在脚本里。
    DEFAULT_PORT 默认 8001，可用同名环境变量覆盖。
    注意：真正决定服务监听端口的是启动命令（uvicorn --port XXXX / systemd ExecStart），
    改端口时要同时改启动命令与这里（或直接用环境变量），两边保持一致。

代理（实测踩坑）：
    本机若设置了 HTTP_PROXY / HTTPS_PROXY（例如 http://127.0.0.1:53312），requests 默认
    会把发往 127.0.0.1 的请求也塞进代理；代理连不上上游就回 502，看着像"服务没起"。
    本地自测不该走代理，所以用 trust_env=False 关掉「读环境变量里的代理」。

用法：
    .venv\\Scripts\\python.exe -m scripts.test_api
    退出码：0 = 接口返回 200；1 = 连不上或非 200。
"""
import sys
from pathlib import Path

import requests

# 允许从任意工作目录执行：把项目根加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config

# ---------- 端口从配置读取，不写死 ----------
PORT = config.DEFAULT_PORT
URL = f"http://127.0.0.1:{PORT}/chat"

print(f"请求地址：{URL}")

# trust_env=False：忽略 HTTP_PROXY / HTTPS_PROXY 等环境变量，本地请求直连。
session = requests.Session()
session.trust_env = False

# 请求体不带 history：顺便验证后端对「单轮（无历史）」请求依然向后兼容。
try:
    resp = session.post(URL, json={"question": "学校在哪个城市？"}, timeout=60)
except requests.exceptions.ConnectionError:
    print(f"[FAIL] 连不上 {URL} —— 服务没起？还是端口不对？")
    print(f"       启动示例：uvicorn backend.main:app --port {PORT}")
    sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"[FAIL] 请求异常：{e}")
    sys.exit(1)

print("状态码:", resp.status_code)
if resp.status_code != 200:
    # 非 200 时把响应正文前 500 字打出来，方便看后端报错
    print("返回:", resp.text[:500])
    sys.exit(1)

print("返回:", resp.json())

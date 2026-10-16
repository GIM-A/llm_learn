"""用 Python 测接口，绕开 PowerShell 编码问题"""
import requests

resp = requests.post(
    "http://127.0.0.1:8001/chat",
    json={"question": "学校在哪个城市？"},
)
print("状态码:", resp.status_code)
print("返回:", resp.json())
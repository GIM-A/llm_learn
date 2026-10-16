"""LLM 调用诊断脚本（CARD-5.3：由原 test_llm.py 与 debug_llm.py 合并而来）

用途：
    单独验证 DashScope 的「OpenAI 兼容端点」能否正常调用 qwen3.7-flash。
    不碰向量库、不碰 rerank，只测 LLM 这一条链路，方便排障时逐层定位。

安全：
    只报告「API Key 是否已配置」和长度，绝不回显 Key 内容。
    （原 test_llm.py / debug_llm.py 会打印 Key 前 10 位，属于信息泄露，已移除。）

用法：
    .venv\\Scripts\\python.exe -m scripts.test_llm
    退出码：0 = 三条用例全部通过；1 = 有任一用例失败（便于 CI / 脚本判断）。
"""
import sys
import traceback
from pathlib import Path

# 允许从项目根或任意工作目录执行：把项目根加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, rag


def main() -> int:
    # ---------- 1. 环境信息（不回显 Key）----------
    print("=" * 60)
    print("环境信息")
    print(f"  模型：{config.LLM_MODEL}")
    print("  端点：https://dashscope.aliyuncs.com/compatible-mode/v1")
    # 只判断「能不能拿到 Key」，不读取、不回显 Key 本身。
    # 统一走 config.require_api_key()，避免直接触摸原始常量。
    try:
        config.require_api_key()
        print("  API Key：已配置（内容不回显）")
    except ValueError:
        print("  API Key：未配置（请检查项目根目录 .env 里的 DASHSCOPE_API_KEY）")
    print("=" * 60)

    # ---------- 2. 复用 rag.init_llm()，保证与线上同一套参数 ----------
    # init_llm() 内部会调用 config.require_api_key()：缺 Key 时 fail-fast 抛 ValueError。
    try:
        llm = rag.init_llm()
    except ValueError as e:
        print(f"[FAIL] 初始化 LLM 失败：{e}")
        return 1

    failed = 0

    # ---------- 用例 1：纯字符串输入 ----------
    print("\n[用例 1] llm.invoke('你好')")
    try:
        resp = llm.invoke("你好")
        print(f"  content 类型：{type(resp.content)}")
        print(f"  content 值：{resp.content!r}")
    except Exception:
        failed += 1
        print("  [FAIL] 调用异常：")
        traceback.print_exc()

    # ---------- 用例 2：messages 格式（system + user，贴近线上拼法）----------
    print("\n[用例 2] llm.invoke(messages) —— system + user")
    try:
        messages = [
            {"role": "system", "content": "你是助手，回答要简短。"},
            {"role": "user", "content": "学校在哪个城市？资料：学校地处重庆市。"},
        ]
        resp = llm.invoke(messages)
        print(f"  content 值：{resp.content!r}")
    except Exception:
        failed += 1
        print("  [FAIL] 调用异常：")
        traceback.print_exc()

    # ---------- 用例 3：流式（线上 /chat/stream 走的就是这个）----------
    print("\n[用例 3] llm.stream('一句话：中国的首都是')")
    try:
        chunks = []
        for chunk in llm.stream("一句话：中国的首都是"):
            chunks.append(chunk.content)
        text = "".join(chunks)
        print(f"  分片数：{len(chunks)}")
        print(f"  拼接结果：{text!r}")
    except Exception:
        failed += 1
        print("  [FAIL] 流式异常：")
        traceback.print_exc()

    # ---------- 汇总 ----------
    print("\n" + "=" * 60)
    if failed:
        print(f"结果：{failed} 个用例失败")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

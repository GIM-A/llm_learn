"""爬取重庆移通学院官网 → data/crawled_data_full.txt（BFS，只抓静态页）

本版改动（扩语料 + 去重卡片）：
  1. 从"只抓首页链接（深度 1）"改成 **BFS 队列 + 深度上限**（默认 3），能进到列表页里的详情页
  2. **seen 集合** 做 URL 级去重（同一 URL 只抓一次）
  3. **页数上限**（默认 500，可用 --max-pages 配）—— 防站群新闻页无限膨胀
  4. **内容去重**：正文按 SHA256（先剔除空白）比对，同一内容只保留第一次出现的 URL
     （实测发现 cdh/zh2/{xs,ty,jq}.htm 三页字节完全相同，占旧语料 26.5%）
  5. **过滤短页**：正文 < 200 字符直接丢弃（多半是 JS 渲染页/空壳页）
  6. 输出覆盖 data/crawled_data_full.txt

不做（本卡范围外）：
  - **JS 渲染**。本机和 2G 服务器都跑不动 Playwright。正文由 JS 注入的页面
    （实测：4.7 万字符 HTML 只能提出 127 字符正文）抓不到，会被"短页过滤"丢掉。

用法：
  python -m scripts.crawler                                  # 深度 3 / 500 页 / 最小 200 字符
  python -m scripts.crawler --depth 2 --max-pages 30         # 小规模试跑
  python -m scripts.crawler --delay 1.5 --min-chars 300      # 放慢/提高门槛
"""
import argparse
import hashlib
import re
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

import requests
import trafilatura
import urllib3
from bs4 import BeautifulSoup

# 允许从项目根或任意工作目录执行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ========== 站点常量 ==========
BASE_URL = "https://www.cqytxy.edu.cn/"
HOST = "www.cqytxy.edu.cn"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 非网页资源，直接跳过（否则会把图片/安装包当页面抓）
SKIP_EXT = (
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".ico", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".gz", ".tar",
    ".mp3", ".mp4", ".avi", ".mov", ".flv", ".wmv",
    ".css", ".js", ".json", ".xml", ".txt", ".apk", ".exe",
)

# 只保留"分页类" query，其余（统计/搜索参数）一律丢掉，避免 URL 爆炸
KEEP_QUERY = re.compile(r"^(page|p|pageno|pagenum|pageindex|pageid)=\d+$", re.I)


# ========== 1. URL 归一化 ==========
def normalize_url(url: str, base: str | None = None) -> str | None:
    """把链接整理成可比较的规范形式；不属于本站/不是网页则返回 None。

    规则：
      - 相对路径 → 用 base 拼成绝对路径
      - 去掉 #fragment
      - 只保留本站域名
      - 丢掉 非网页后缀
      - query 只保留分页参数
      - 统一成 https://host/path 形态（便于 seen 去重）
    """
    if not url:
        return None
    try:
        if base:
            url = urljoin(base, url)
        url, _ = urldefrag(url)                      # 去掉锚点
        p = urlparse(url)
    except Exception:
        return None

    if p.scheme not in ("http", "https"):
        return None
    if p.netloc != HOST:                              # 外站一律不要
        return None

    path = p.path or "/"
    if path.lower().endswith(SKIP_EXT):               # 非网页资源
        return None

    q = ""
    if p.query:
        kept = [kv for kv in p.query.split("&") if KEEP_QUERY.match(kv)]
        q = "&".join(kept)

    return f"https://{HOST}{path}" + (f"?{q}" if q else "")


# ========== 2. 抓取（带重试） ==========
def fetch_html(session: requests.Session, url: str, retries: int = 2) -> str | None:
    """GET 一个页面，返回 HTML 文本；失败返回 None。"""
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=15, verify=False)
            if resp.status_code == 200:
                resp.encoding = resp.apparent_encoding
                return resp.text
            if resp.status_code in (403, 404, 500, 502, 503):
                return None                          # 明确的失败，不重试
        except Exception:
            if attempt >= retries:
                return None
            time.sleep(1.5)                          # 网络抖动，退避重试
    return None


# ========== 3. 正文提取 ==========
def extract_text(html: str, url: str) -> str:
    """trafilatura 提取正文。

    这里显式传参（旧版是裸默认值，实测会多丢 30% 正文）：
      - url=            → 启用站点专用规则，并让相对链接可解析
      - include_tables= → 保留表格（招生计划/收费标准这类页面靠表格承载信息）
      - favor_recall=   → 偏向"多留"，少漏正文
    """
    try:
        return trafilatura.extract(
            html, url=url, include_tables=True, favor_recall=True
        ) or ""
    except Exception:
        return ""


def iter_links(html: str, base_url: str) -> list[str]:
    """从页面里取出所有本站、可抓的链接（已归一化）。"""
    out = []
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return out
    for a in soup.find_all("a", href=True):
        u = normalize_url(a["href"], base=base_url)
        if u:
            out.append(u)
    return out


# ========== 4. 内容指纹（去重用） ==========
def content_hash(text: str) -> str:
    """正文指纹：先剔除所有空白，再 SHA256。

    剔除空白是有意的 —— 同一份内容在不同页面里换行/缩进可能不同，
    去掉空白后能抓住"排版不同但内容相同"的重复页。
    """
    norm = re.sub(r"\s+", "", text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


# ========== 5. BFS 主循环 ==========
def crawl(depth_limit: int, max_pages: int, min_chars: int, delay: float) -> None:
    session = requests.Session()
    session.trust_env = False          # 本地直连，绕开 HTTP_PROXY 劫持（见备忘）

    queue = deque([(BASE_URL, 0)])     # (url, depth)
    seen: set[str] = set()             # URL 级去重
    seen_hash: dict[str, str] = {}     # 内容指纹 → 首次出现的 URL
    kept: list[tuple[str, str]] = []   # [(url, text)]

    # 统计
    fetched = tried = failed = too_short = dup_content = 0
    max_fetch = max_pages * 3          # 请求数硬上限，防止空转太久
    t0 = time.time()

    print(f"[start] 深度上限={depth_limit} 页数上限={max_pages} "
          f"最小正文={min_chars}字符 间隔={delay}s 请求上限={max_fetch}")

    while queue and len(kept) < max_pages and tried < max_fetch:
        url, depth = queue.popleft()
        if url in seen:
            continue
        seen.add(url)

        tried += 1
        html = fetch_html(session, url)
        if html is None:
            failed += 1
            continue

        fetched += 1
        text = extract_text(html, url)

        # 5.1 短页过滤：正文太短 = 空壳页 / JS 渲染页
        if len(text) < min_chars:
            too_short += 1
            time.sleep(delay)
            continue

        # 5.2 内容去重：同一份正文只保留第一次出现的 URL
        h = content_hash(text)
        if h in seen_hash:
            dup_content += 1
            time.sleep(delay)
            continue
        seen_hash[h] = url

        kept.append((url, text))
        print(f"[{len(kept):>3}/{max_pages}] d{depth} {len(text):>5}字 {url}")

        # 5.3 把本页的新链接按 depth+1 入队（只在还有深度预算时）
        if depth < depth_limit:
            for link in iter_links(html, url):
                if link not in seen:
                    queue.append((link, depth + 1))

        time.sleep(delay)              # 礼貌抓取：单线程 + 固定间隔

    # ========== 6. 写文件（覆盖） ==========
    output_path = config.DATA_DIR / "crawled_data_full.txt"
    body = "\n\n".join(f"=== {u} ===\n{t}" for u, t in kept)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(body)

    # ========== 7. 报告 ==========
    elapsed = time.time() - t0
    total_chars = sum(len(t) for _, t in kept)
    print("\n" + "=" * 60)
    print("爬取完成")
    print(f"  实际请求        : {tried}（含失败 {failed}）")
    print(f"  成功取回 HTML   : {fetched}")
    print(f"  短页丢弃(<{min_chars}) : {too_short}")
    print(f"  内容重复丢弃    : {dup_content}")
    print(f"  保留页面        : {len(kept)}")
    print(f"  总字符          : {total_chars}")
    print(f"  平均每页        : {total_chars // len(kept) if kept else 0} 字符")
    print(f"  耗时            : {elapsed:.0f}s")
    print(f"  输出            : {output_path}")
    print("=" * 60)


# ========== 8. 入口 ==========
def main() -> int:
    parser = argparse.ArgumentParser(description="爬取重庆移通学院官网（BFS，静态页）")
    parser.add_argument("--depth", type=int, default=3, help="BFS 深度上限（默认 3）")
    parser.add_argument("--max-pages", type=int, default=500, help="保留页数上限（默认 500）")
    parser.add_argument("--min-chars", type=int, default=200, help="正文短于此值则丢弃（默认 200）")
    parser.add_argument("--delay", type=float, default=1.0, help="每次请求后的间隔秒数（默认 1.0，别调太小）")
    args = parser.parse_args()

    crawl(args.depth, args.max_pages, args.min_chars, args.delay)
    return 0


if __name__ == "__main__":
    sys.exit(main())

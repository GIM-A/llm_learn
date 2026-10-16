"""清洗语料：data/crawled_data_full.txt → data/my_doc.txt（覆盖）

位置：爬虫与向量库之间的"中间工序"。爬虫只管抓，清洗只管去噪，入库只管切片。

做三件事：
  1. **过滤导航/版权模板行** —— 三层过滤：
     a) 固定样板：友情链接 / 版权所有 / ICP备 / 地址： 这类"每页都有的壳"
     b) 前缀样板：Copyright / 当前位置： / 邮编： / 技术支持： 等
     c) **数据驱动的高频短行**：在 ≥ 一定比例的页面里都出现、且长度 ≤40 字 的行
        （站群导航的栏目名千奇百怪，写死列表必然漏；用频率抓更稳）
  2. **页内重复行压缩**：同一页里重复出现 ≥3 次的短行（如 `<p>温馨书院</p>` ×8）只留一条
  3. **去重 + 保留来源 URL**：正文指纹（剔除空白后 SHA256）防御性兜底；
     输出仍是 `=== url ===` 分节格式，下游 build_index.py 解析它写进 chunk metadata

阈值为什么是 0.25：实测本站导航块出现在 175/500 页（35%），
早先用 0.6（=300 页）完全抓不到，导航文字会漏进向量库污染检索。

用法：
  python -m scripts.clean_corpus
  python -m scripts.clean_corpus --freq-threshold 0.15 --min-chars 150
"""
import argparse
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

# 允许从项目根或任意工作目录执行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config

# ========== 1. 固定样板行（整行等于这些词的，一定是导航/按钮）==========
BOILERPLATE_EXACT = {
    # 通用页脚/按钮
    "友情链接", "常用链接", "相关链接", "快速链接", "常用服务", "常用网站",
    "学校首页", "返回首页", "返回顶部", "返回列表", "关闭", "打印", "分享", "分享到",
    "更多", "更多>>", "查看更多", "上一页", "下一页", "上一篇", "下一篇",
    "首页", "尾页", "搜索", "登录", "注册", "English", "网站地图",
    # 本站导航栏（实测高频栏目名）
    "联系我们", "智慧门户", "领导信箱", "网上缴费", "招贤纳士", "后勤保障",
    "公共服务", "招生就业", "移通概况", "机构设置", "学校校历", "掌上迎新",
    "迎评促建", "招标采购", "文化移通", "移通资讯", "就业网", "校园风光",
    "校友天地", "教育理念", "特色育人模式", "行政教辅管理机构", "教学科研机构",
}

# 以这些前缀开头的行，也是模板壳（页脚备案、面包屑、联系方式等）
BOILERPLATE_RE = re.compile(
    r"^\s*(Copyright|版权所有|ICP备|渝ICP|渝公网安备|地址[:：]|邮编[:：]|"
    r"电话[:：]|传真[:：]|邮箱[:：]|E-?mail[:：]|技术支持[:：]|设计制作[:：]|"
    r"主办[:：]|承办[:：]|网站地图|当前位置|扫码关注|微博|微信)"
)

# 整行只有标点/符号的行（分割线、面包屑箭头之类）
PUNCT_ONLY_RE = re.compile(
    r"^[\s\-—_=*·。，,、;；:：|/\\~`^><＞＜««»»　]*$"
)


# ========== 2. 解析 / 组装 ==========
def parse_sections(text: str) -> list[tuple[str, str]]:
    """把 `=== url ===` 分节文本拆成 [(url, body)]。"""
    parts = re.split(r"^=== (.*?) ===$", text, flags=re.M)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def render_sections(sections: list[tuple[str, str]]) -> str:
    """反向组装成 `=== url ===` 分节文本。"""
    return "\n\n".join(f"=== {u} ===\n{t}" for u, t in sections)


def content_hash(text: str) -> str:
    """与 crawler.py 同款指纹：剔除空白后 SHA256。"""
    return hashlib.sha256(re.sub(r"\s+", "", text).encode("utf-8")).hexdigest()


# ========== 3. 高频短行检测（数据驱动找模板） ==========
def detect_frequent_lines(bodies: list[str], threshold: float) -> set[str]:
    """找出"在 ≥threshold 比例的页面里都出现、且 ≤40 字"的行，视为模板行。"""
    if len(bodies) < 3:
        return set()                       # 页面太少，频率统计不可靠
    counter: Counter = Counter()
    for body in bodies:
        for line in {ln.strip() for ln in body.splitlines() if ln.strip()}:
            counter[line] += 1
    min_pages = max(3, int(len(bodies) * threshold))
    return {ln for ln, c in counter.items() if c >= min_pages and len(ln) <= 40}


# ========== 4. 主流程 ==========
def clean(min_chars: int, freq_threshold: float, repeat_times: int) -> None:
    src = config.DATA_DIR / "crawled_data_full.txt"
    dst = config.DOC_PATH                        # data/my_doc.txt

    if not src.exists():
        print(f"[FAIL] 找不到输入：{src}")
        raise SystemExit(1)

    raw = src.read_text(encoding="utf-8")
    sections = parse_sections(raw)
    print(f"[input] {src.name}：{len(sections)} 页")

    # 4.1 数据驱动的高频模板行
    frequent = detect_frequent_lines([b for _, b in sections], freq_threshold)
    if frequent:
        print(f"\n[高频模板行] {len(frequent)} 条（≥{freq_threshold:.0%} 页面且 ≤40 字），示例：")
        for ln in sorted(frequent, key=len, reverse=True)[:12]:
            print(f"    {ln}")
    else:
        print("\n[高频模板行] 未检测到")

    # 4.2 逐页清洗
    dropped_line = dropped_template = dropped_repeat = dropped_short = 0
    cleaned: list[tuple[str, str]] = []

    for url, body in sections:
        # (1) 页内重复行统计：同一页里出现 ≥repeat_times 次的短行 → 只留一次
        per_page: Counter = Counter(
            ln.strip() for ln in body.splitlines() if ln.strip()
        )
        repeated = {ln for ln, c in per_page.items() if c >= repeat_times and len(ln) <= 40}

        kept_lines: list[str] = []
        emitted_repeat: set[str] = set()

        for line in body.splitlines():
            s = line.strip()
            if not s:
                kept_lines.append("")            # 空行先留，最后统一压缩
                continue

            # 固定样板 / 前缀样板 / 高频模板行
            if s in BOILERPLATE_EXACT or BOILERPLATE_RE.match(s) or s in frequent:
                dropped_template += 1
                continue
            # 纯标点行
            if PUNCT_ONLY_RE.match(s):
                dropped_line += 1
                continue
            # 页内重复行：第一次保留，之后丢弃
            if s in repeated:
                if s in emitted_repeat:
                    dropped_repeat += 1
                    continue
                emitted_repeat.add(s)

            kept_lines.append(s)

        # 压缩连续空行：最多保留 1 个空行，首尾去空
        text = re.sub(r"\n{2,}", "\n", "\n".join(kept_lines)).strip()
        if len(text) >= min_chars:
            cleaned.append((url, text))
        else:
            dropped_short += 1

    # 4.3 防御性去重（爬虫已经去过一次，这里再兜一次）
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for url, text in cleaned:
        h = content_hash(text)
        if h in seen:
            continue
        seen.add(h)
        deduped.append((url, text))

    # 4.4 写出（覆盖）
    dst.write_text(render_sections(deduped), encoding="utf-8")

    total_chars = sum(len(t) for _, t in deduped)
    print("\n" + "=" * 60)
    print("清洗完成")
    print(f"  输入页面            : {len(sections)}")
    print(f"  删除·模板/导航行    : {dropped_template} 行")
    print(f"  删除·纯符号行       : {dropped_line} 行")
    print(f"  删除·页内重复行     : {dropped_repeat} 行")
    print(f"  整页丢弃(<{min_chars}字)  : {dropped_short}")
    print(f"  去重丢弃            : {len(cleaned) - len(deduped)}")
    print(f"  输出页面            : {len(deduped)}")
    print(f"  总字符              : {total_chars}")
    print(f"  输出                : {dst}")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="清洗语料 → data/my_doc.txt")
    parser.add_argument("--min-chars", type=int, default=100,
                        help="清洗后短于此值则丢弃整页（默认 100）")
    parser.add_argument("--freq-threshold", type=float, default=0.25,
                        help="高频模板行判定：出现在 ≥该比例的页面里（默认 0.25）")
    parser.add_argument("--repeat-times", type=int, default=3,
                        help="页内重复行判定：同一页重复 ≥N 次即只留一条（默认 3）")
    args = parser.parse_args()

    clean(args.min_chars, args.freq_threshold, args.repeat_times)
    return 0


if __name__ == "__main__":
    sys.exit(main())

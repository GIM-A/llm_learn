import requests
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

base_url = "https://www.cqytxy.edu.cn/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def fetch(url):
    """抓一个页面，只返回正文区域"""
    try:
        resp = requests.get(url, headers=headers, timeout=10, verify=False)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, "html.parser")

        content = soup.find("section", class_="inner-page")
        if content:
            text = content.get_text(separator="\n", strip=True)
            # 过滤侧边导航
            noise = ["移通资讯", "特色育人模式", "专业教育", "通识教育", "商科教育",
                     "完满教育", "双院制", "国际化", "体育", "艺术", "学术", "进取"]
            lines = text.split("\n")
            while lines and lines[0].strip() in noise:
                lines.pop(0)
            return "\n".join(lines)
        else:
            return ""
    except Exception as e:
        print(f"抓 {url} 失败: {e}")
        return ""

# 1. 抓首页，找链接
resp = requests.get(base_url, headers=headers, timeout=10, verify=False)
resp.encoding = resp.apparent_encoding
soup = BeautifulSoup(resp.text, "html.parser")

links = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    full_url = urljoin(base_url, href)
    if full_url.startswith("https://www.cqytxy.edu.cn") and full_url != base_url:
        links.append(full_url)

links = list(set(links))
print(f"找到 {len(links)} 个链接")

# 2. 抓前 30 个，保存到文件
all_content = []
success = 0
for i, link in enumerate(links[:30]):
    print(f"[{i+1}/30] 抓取: {link}")
    text = fetch(link)
    if len(text) < 100:
        print(f"  跳过（内容太短）")
        continue
    all_content.append(f"=== {link} ===\n{text}\n")
    success += 1
    print(f"  成功，{len(text)} 字符")
    time.sleep(1)

# 3. 保存到文件
with open("crawled_data.txt", "w", encoding="utf-8") as f:
    f.write("\n\n".join(all_content))

print(f"\n✅ 完成！成功抓取 {success} 个页面，保存到 crawled_data.txt")
print(f"   总字符数: {sum(len(c) for c in all_content)}")
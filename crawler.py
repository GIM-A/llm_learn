import requests
import urllib3
import trafilatura
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

base_url = "https://www.cqytxy.edu.cn/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def fetch(url):
    """用 trafilatura 提取正文"""
    try:
        resp = requests.get(url, headers=headers, timeout=10, verify=False)
        resp.encoding = resp.apparent_encoding
        text = trafilatura.extract(resp.text)
        return text if text else ""
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

# 2. 爬全部链接
all_content = []
success = 0
for i, link in enumerate(links):
    print(f"[{i+1}/{len(links)}] 抓取: {link}")
    text = fetch(link)
    if len(text) < 100:
        print(f"  跳过（内容太短）")
        continue
    all_content.append(f"=== {link} ===\n{text}\n")
    success += 1
    print(f"  成功，{len(text)} 字符")
    time.sleep(1)

# 3. 保存到文件
with open("crawled_data_full.txt", "w", encoding="utf-8") as f:
    f.write("\n\n".join(all_content))

print(f"\n✅ 完成！成功抓取 {success} 个页面，保存到 crawled_data_full.txt")
print(f"   总字符数: {sum(len(c) for c in all_content)}")
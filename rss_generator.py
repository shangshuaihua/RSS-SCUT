# rss_generator.py (V8 - 最终完整、高兼容性、UTC标准时间版)
import requests
import time
from datetime import datetime, timezone, timedelta
from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- 1. 配置区 ---
GITHUB_PAGES_URL = "https://shangshuaihua.github.io/RSS-SCUT/rss.xml"
BASE_SITE_URL = "https://jw.scut.edu.cn"
API_URL = f"{BASE_SITE_URL}/zhinan/cms/article/v2/findInformNotice.do"
ITEMS_TO_FETCH = 30
OUTPUT_FILE = "rss.xml"

# --- 2. 辅助数据 ---
TAG_MAP = {
    6: "信息", 1: "选课", 2: "考试", 3: "实践", 4: "交流", 5: "教师"
}


# --- 3. 核心功能函数 ---

def fetch_latest_notices():
    """从教务处API获取最新的通知列表。"""
    print(f"正在从 API 获取最新的 {ITEMS_TO_FETCH} 条通知...")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
            'Referer': f'{BASE_SITE_URL}/zhinan/cms/toPosts.do'
        }
        payload = {
            'category': '0', 'tag': '0', 'pageNum': '1',
            'pageSize': str(ITEMS_TO_FETCH), 'keyword': ''
        }
        response = requests.post(API_URL, headers=headers, data=payload, timeout=20)
        response.raise_for_status()
        data = response.json()

        if data.get("success") and "list" in data and data["list"]:
            notice_list = data["list"]
            print(f"✅ 成功获取到 {len(notice_list)} 条通知。")
            return notice_list
        else:
            print(f"❌ API返回数据格式不正确或列表为空: {data}")
            return []

    except Exception as e:
        print(f"❌ 获取通知列表失败: {e}")
        return []


def scrape_article_content(url):
    """
    访问文章URL，只尝试提取使用 <div class="content"> 模板的正文。
    如果失败，则优雅地返回提示信息，确保主程序稳定。
    """
    print(f"  -> 正在尝试抓取正文: {url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        # ★★★ 修正点：确保 soup 变量被完整定义 ★★★
        soup = BeautifulSoup(response.text, 'lxml')

        content_div = soup.find('div', class_='content')

        if content_div:
            # 清理和链接修复
            if content_div.find('h3', class_='content-title'): content_div.find('h3',
                                                                                class_='content-title').decompose()
            if content_div.find('h5', class_='content-date'): content_div.find('h5', class_='content-date').decompose()
            if content_div.find('hr'): content_div.find('hr').decompose()
            for tag in content_div.find_all(['a', 'img'], href=True):
                if tag.get('href') and (tag['href'].startswith('/') or tag['href'].startswith('../')):
                    tag['href'] = urljoin(BASE_SITE_URL, tag['href'])
            for tag in content_div.find_all(['a', 'img'], src=True):
                if tag.get('src') and (tag['src'].startswith('/') or tag['src'].startswith('../')):
                    tag['src'] = urljoin(BASE_SITE_URL, tag['src'])
            return str(content_div)
        else:
            print(f"  -> 提示: 页面未使用标准模板, 跳过正文抓取。")
            return "<p><i>(该通知使用特殊布局, 无法自动提取正文, 请点击链接查看原文)</i></p>"

    except Exception as e:
        print(f"  -> 警告: 抓取或解析页面失败: {e}")
        return f"<p><i>(抓取正文失败, 请点击链接查看原文。错误: {e})</i></p>"


def generate_rss_feed(notice_list):
    """根据通知列表生成RSS Feed，使用UTC标准时间以获得最佳兼容性。"""
    print("开始生成 RSS Feed 文件...")
    fg = FeedGenerator()
    fg.title('华南理工大学教务处通知')
    fg.link(href='https://jw.scut.edu.cn/zhinan/cms/index.do', rel='alternate')
    fg.description('自动更新的华南理工大学主校区教务处最新通知')
    fg.language('zh-CN')
    fg.link(href=GITHUB_PAGES_URL, rel='self', type='application/rss+xml')

    beijing_tz = timezone(timedelta(hours=8))

    for item in sorted(notice_list, key=lambda x: x.get('createTime', ''), reverse=True):
        fe = fg.add_entry()
        article_id = item.get('id', '')
        article_url = f"https://jw.scut.edu.cn/zhinan/cms/article/view.do?type=posts&id={article_id}"
        news_type = TAG_MAP.get(item.get('tag'), "通知")
        fe.title(f"【{news_type}】{item.get('title', '无标题')}")
        fe.link(href=article_url)
        fe.guid(article_url, permalink=True)

        try:
            pub_date_naive = datetime.strptime(item.get('createTime'), '%Y.%m.%d')
            pub_date_aware_beijing = pub_date_naive.replace(tzinfo=beijing_tz)
            pub_date_utc = pub_date_aware_beijing.astimezone(timezone.utc)
            fe.pubDate(pub_date_utc)
        except (ValueError, TypeError):
            pass

        description_summary = f"类型: {news_type}<br>日期: {item.get('createTime', 'N/A')}"
        fe.description(description_summary)

        content_html = scrape_article_content(article_url)
        fe.content(content_html, type='html')

        time.sleep(0.5)

    fg.rss_file(OUTPUT_FILE, pretty=True)
    print(f"✅ 成功生成 {OUTPUT_FILE} 文件，包含 {len(notice_list)} 条通知。")


def main():
    if "YourUsername" in GITHUB_PAGES_URL or "shangshuaihua" not in GITHUB_PAGES_URL:
        print("❌ 错误: 请先确认脚本顶部的 GITHUB_PAGES_URL 变量已正确修改！")
        return
    print("--- 开始执行华工教务处RSS生成任务 ---")
    latest_notices = fetch_latest_notices()
    if latest_notices:
        generate_rss_feed(latest_notices)
    else:
        print("未获取到任何通知，本次任务不生成新文件。")
    print("--- 任务完成 ---")


if __name__ == "__main__":
    main()
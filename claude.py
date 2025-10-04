# rss_generator.py (V9 - 修复重复显示 + 增强HTML兼容性)
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
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
    智能提取正文内容,支持多种HTML模板:
    1. <div class="content"> (标准模板)
    2. <div class="news_con"> (备用模板)
    3. 其他常见容器
    """
    print(f"  -> 正在抓取正文: {url}")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        # 尝试多种选择器策略
        content_div = None
        selectors = [
            ('div', 'content'),  # 模板1
            ('div', 'news_con'),  # 模板2
            ('div', 'article-content'),  # 常见模板3
            ('div', 'post-content'),  # 常见模板4
        ]

        for tag, class_name in selectors:
            content_div = soup.find(tag, class_=class_name)
            if content_div:
                print(f"  -> ✓ 使用选择器: {tag}.{class_name}")
                break

        if content_div:
            # 清理冗余元素
            for unwanted in content_div.find_all(['h3', 'h5'], class_=['content-title', 'content-date']):
                unwanted.decompose()
            for hr in content_div.find_all('hr'):
                hr.decompose()

            # 修复相对链接
            for tag in content_div.find_all(['a', 'img']):
                for attr in ['href', 'src']:
                    if tag.get(attr) and (tag[attr].startswith('/') or tag[attr].startswith('../')):
                        tag[attr] = urljoin(BASE_SITE_URL, tag[attr])

            return str(content_div)
        else:
            print(f"  -> ⚠ 未匹配到已知模板")
            return "<p><i>⚠️ 该通知使用特殊布局,无法自动提取正文,请点击下方链接查看原文。</i></p>"

    except Exception as e:
        print(f"  -> ❌ 抓取失败: {e}")
        return f"<p><i>❌ 抓取正文时出错,请访问原文链接。</i></p>"


def generate_rss_feed(notice_list):
    """生成RSS Feed,每条通知只显示一次完整内容。"""
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
        title = item.get('title', '无标题')
        pub_date_str = item.get('createTime', 'N/A')

        # 设置基本信息
        fe.title(f"【{news_type}】{title}")
        fe.link(href=article_url)
        fe.guid(article_url, permalink=True)

        # 设置发布时间
        try:
            pub_date_naive = datetime.strptime(pub_date_str, '%Y.%m.%d')
            pub_date_aware = pub_date_naive.replace(tzinfo=beijing_tz)
            pub_date_utc = pub_date_aware.astimezone(timezone.utc)
            fe.pubDate(pub_date_utc)
        except (ValueError, TypeError):
            pass

        # ★★★ 关键修复: 将元信息和正文合并为一个完整内容 ★★★
        content_body = scrape_article_content(article_url)

        # 构建完整HTML内容(元信息 + 正文)
        full_content = f"""
<div style="border-left: 4px solid #0066cc; padding-left: 15px; margin-bottom: 20px; background: #f5f5f5; padding: 10px;">
    <p style="margin: 5px 0;"><strong>📌 类型:</strong> {news_type}</p>
    <p style="margin: 5px 0;"><strong>📅 日期:</strong> {pub_date_str}</p>
    <p style="margin: 5px 0;"><strong>🔗 原文:</strong> <a href="{article_url}" target="_blank">点击查看</a></p>
</div>
<hr style="border: none; border-top: 1px solid #ddd; margin: 15px 0;">
<div style="line-height: 1.8;">
{content_body}
</div>
"""

        # 只设置一次内容 - 使用 content() 而不是 description()
        fe.content(full_content, type='html')

        # 为兼容性添加简短描述(某些阅读器需要)
        fe.description(f"{news_type} | {pub_date_str}")

        time.sleep(0.5)

    fg.rss_file(OUTPUT_FILE, pretty=True)
    print(f"✅ 成功生成 {OUTPUT_FILE},包含 {len(notice_list)} 条通知。")


def main():
    if "YourUsername" in GITHUB_PAGES_URL:
        print("❌ 错误: 请先修改 GITHUB_PAGES_URL 变量！")
        return

    print("=" * 60)
    print("华工教务处 RSS 自动生成工具 V9")
    print("=" * 60)

    latest_notices = fetch_latest_notices()
    if latest_notices:
        generate_rss_feed(latest_notices)
        print("\n✅ 任务完成！可以推送到 GitHub 了。")
    else:
        print("\n⚠️ 未获取到通知,请检查网络或API状态。")


if __name__ == "__main__":
    main()
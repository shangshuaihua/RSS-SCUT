# rss_generator.py (V18 - 完全遵循三花AI标准)
import requests
import time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urljoin

GITHUB_PAGES_URL = "https://shangshuaihua.github.io/RSS-SCUT/rss.xml"
BASE_SITE_URL = "https://jw.scut.edu.cn"
API_URL = f"{BASE_SITE_URL}/zhinan/cms/article/v2/findInformNotice.do"
ITEMS_TO_FETCH = 30
OUTPUT_FILE = "rss.xml"
TAG_MAP = {6: "信息", 1: "选课", 2: "考试", 3: "实践", 4: "交流", 5: "教师"}


def fetch_latest_notices():
    print("获取通知...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': f'{BASE_SITE_URL}/zhinan/cms/toPosts.do'}
        payload = {'category': '0', 'tag': '0', 'pageNum': '1', 'pageSize': str(ITEMS_TO_FETCH), 'keyword': ''}
        response = requests.post(API_URL, headers=headers, data=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        if data.get("success") and data.get("list"):
            print(f"成功获取 {len(data['list'])} 条")
            return data["list"]
        return []
    except Exception as e:
        print(f"失败: {e}")
        return []


def scrape_article_content(url):
    print(f"  抓取: {url}")
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        for tag, cls in [('div', 'content'), ('div', 'news_con'), ('div', 'article-content'), ('div', 'post-content')]:
            content = soup.find(tag, class_=cls)
            if content:
                print(f"  匹配模板: {cls}")
                for unwanted in content.find_all(['h3', 'h5', 'hr']):
                    if 'title' in str(unwanted.get('class', [])) or 'date' in str(unwanted.get('class', [])):
                        unwanted.decompose()
                for elem in content.find_all(['a', 'img']):
                    for attr in ['href', 'src']:
                        if elem.get(attr, '').startswith(('/', '../')):
                            elem[attr] = urljoin(BASE_SITE_URL, elem[attr])
                return True, str(content)
        print("  无法匹配模板")
        return False, ""
    except Exception as e:
        print(f"  错误: {e}")
        return False, ""


def generate_rss_feed(notice_list):
    """完全模仿三花AI的RSS标准结构"""
    print("\n生成RSS...")

    # 完全参照三花AI的XML头部
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:content="http://purl.org/rss/1.0/modules/content/">',
        '    <channel>',
        '        <title>华南理工大学教务处通知</title>',
        '        <link>https://jw.scut.edu.cn/zhinan/cms/index.do</link>',
        '        <description>华工教务处最新通知自动订阅</description>',
        f'        <lastBuildDate>{datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")}</lastBuildDate>',
        '        <docs>https://validator.w3.org/feed/docs/rss2.html</docs>',
        '        <generator>RSS Generator for SCUT</generator>',
        '        <language>zh-cn</language>',
    ]

    beijing_tz = timezone(timedelta(hours=8))
    success = 0
    item_id = 1

    for item in sorted(notice_list, key=lambda x: x.get('createTime', ''), reverse=True):
        article_id = item.get('id', '')
        url = f"{BASE_SITE_URL}/zhinan/cms/article/view.do?type=posts&id={article_id}"
        news_type = TAG_MAP.get(item.get('tag'), "通知")
        title = item.get('title', '无标题')
        pub_date = item.get('createTime', 'N/A')

        pub_date_str = ''
        try:
            dt = datetime.strptime(pub_date, '%Y.%m.%d').replace(tzinfo=beijing_tz)
            pub_date_str = dt.astimezone(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        except:
            pass

        has_content, body = scrape_article_content(url)

        # 参照三花AI: 简洁的HTML结构,无emoji,无复杂样式
        if has_content:
            # 添加简洁的元信息段落
            meta_html = f'<p><strong>类型:</strong> {news_type} | <strong>日期:</strong> {pub_date} | <a href="{url}" title="查看原文">查看原文</a></p>'
            full_html = f'{meta_html}\n{body}'
            success += 1
        else:
            full_html = f'<p><strong>类型:</strong> {news_type} | <strong>日期:</strong> {pub_date}</p>\n<p>该通知无法自动提取正文内容，请<a href="{url}" title="查看原文">点击此处</a>访问原文。</p>'

        # 转义CDATA内容
        full_html_escaped = full_html.replace(']]>', ']]]]><![CDATA[>')
        description_text = f"{news_type} - {pub_date}"
        title_text = f"【{news_type}】{title}"

        # 完全参照三花AI的item结构
        lines.extend([
            '        <item>',
            f'            <title><![CDATA[{title_text}]]></title>',
            f'            <link>{url}</link>',
            f'            <guid>{item_id}</guid>',
            f'            <pubDate>{pub_date_str}</pubDate>' if pub_date_str else '',
            f'            <description><![CDATA[{description_text}]]></description>',
            f'            <content:encoded><![CDATA[{full_html_escaped}]]></content:encoded>',
            '        </item>',
        ])

        item_id += 1
        time.sleep(0.5)

    lines.extend(['    </channel>', '</rss>'])

    # 写入文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join([line for line in lines if line]))

    print(f"完成! 总数:{len(notice_list)} | 有正文:{success}")


def main():
    print("=" * 50)
    print("华工教务处RSS生成器 V18")
    print("=" * 50)

    notices = fetch_latest_notices()
    if notices:
        generate_rss_feed(notices)
        print("\n可以推送到GitHub了!")
    else:
        print("\n未获取到通知")


if __name__ == "__main__":
    main()
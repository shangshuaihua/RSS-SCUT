# rss_generator.py (V14 - 手动生成RSS,彻底解决)
import requests
import time
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
from xml.dom import minidom

# --- 配置 ---
GITHUB_PAGES_URL = "https://shangshuaihua.github.io/RSS-SCUT/rss.xml"
BASE_SITE_URL = "https://jw.scut.edu.cn"
API_URL = f"{BASE_SITE_URL}/zhinan/cms/article/v2/findInformNotice.do"
ITEMS_TO_FETCH = 30
OUTPUT_FILE = "rss.xml"
TAG_MAP = {6: "信息", 1: "选课", 2: "考试", 3: "实践", 4: "交流", 5: "教师"}


def fetch_latest_notices():
    print(f"📡 获取通知...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': f'{BASE_SITE_URL}/zhinan/cms/toPosts.do'}
        payload = {'category': '0', 'tag': '0', 'pageNum': '1', 'pageSize': str(ITEMS_TO_FETCH), 'keyword': ''}
        response = requests.post(API_URL, headers=headers, data=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        if data.get("success") and data.get("list"):
            print(f"✅ 获取 {len(data['list'])} 条")
            return data["list"]
        return []
    except Exception as e:
        print(f"❌ 失败: {e}")
        return []


def scrape_article_content(url):
    print(f"  🔍 {url}")
    try:
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        for tag, cls in [('div', 'content'), ('div', 'news_con'), ('div', 'article-content'), ('div', 'post-content')]:
            content = soup.find(tag, class_=cls)
            if content:
                print(f"  ✓ {cls}")
                for unwanted in content.find_all(['h3', 'h5', 'hr']):
                    if 'title' in str(unwanted.get('class', [])) or 'date' in str(unwanted.get('class', [])):
                        unwanted.decompose()
                for elem in content.find_all(['a', 'img']):
                    for attr in ['href', 'src']:
                        if elem.get(attr, '').startswith(('/', '../')):
                            elem[attr] = urljoin(BASE_SITE_URL, elem[attr])
                return True, str(content)
        print(f"  ⚠ 无模板")
        return False, ""
    except Exception as e:
        print(f"  ❌ {e}")
        return False, ""


def generate_rss_feed(notice_list):
    """手动生成RSS XML,确保使用 content:encoded"""
    print("\n📝 生成RSS...")

    # 创建RSS根元素
    rss = ET.Element('rss', {
        'version': '2.0',
        'xmlns:content': 'http://purl.org/rss/1.0/modules/content/',
        'xmlns:atom': 'http://www.w3.org/2005/Atom'
    })

    channel = ET.SubElement(rss, 'channel')

    # 频道信息
    ET.SubElement(channel, 'title').text = '华南理工大学教务处通知'
    ET.SubElement(channel, 'link').text = 'https://jw.scut.edu.cn/zhinan/cms/index.do'
    ET.SubElement(channel, 'description').text = '华工教务处通知订阅'
    ET.SubElement(channel, 'language').text = 'zh-CN'
    ET.SubElement(channel, 'lastBuildDate').text = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')
    ET.SubElement(channel, '{http://www.w3.org/2005/Atom}link', {
        'href': GITHUB_PAGES_URL,
        'rel': 'self',
        'type': 'application/rss+xml'
    })

    beijing_tz = timezone(timedelta(hours=8))
    success = 0

    for item in sorted(notice_list, key=lambda x: x.get('createTime', ''), reverse=True):
        article_id = item.get('id', '')
        url = f"{BASE_SITE_URL}/zhinan/cms/article/view.do?type=posts&id={article_id}"
        news_type = TAG_MAP.get(item.get('tag'), "通知")
        title = item.get('title', '无标题')
        pub_date = item.get('createTime', 'N/A')

        # 创建条目
        entry = ET.SubElement(channel, 'item')
        ET.SubElement(entry, 'title').text = f"【{news_type}】{title}"
        ET.SubElement(entry, 'link').text = url
        ET.SubElement(entry, 'guid', {'isPermaLink': 'true'}).text = url

        # 发布时间
        try:
            dt = datetime.strptime(pub_date, '%Y.%m.%d').replace(tzinfo=beijing_tz)
            pub_date_utc = dt.astimezone(timezone.utc)
            ET.SubElement(entry, 'pubDate').text = pub_date_utc.strftime('%a, %d %b %Y %H:%M:%S +0000')
        except:
            pass

        # 简短描述(纯文本)
        ET.SubElement(entry, 'description').text = f"{news_type} | {pub_date}"

        # 抓取正文
        has_content, body = scrape_article_content(url)

        # 构建完整HTML
        meta = f'''<div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:15px;border-radius:8px;margin-bottom:20px">
<p style="margin:5px 0">📌 {news_type} | 📅 {pub_date} | 🔗 <a href="{url}" style="color:#ffd700">原文</a></p></div>'''

        if has_content:
            html = f"{meta}<div>{body}</div>"
            success += 1
        else:
            html = f'''{meta}<div style="text-align:center;padding:40px;background:#f9f9f9;border-radius:8px">
<p>⚠️ 无法提取正文</p><p><a href="{url}" style="background:#667eea;color:white;padding:10px 20px;text-decoration:none;border-radius:5px">查看原文</a></p></div>'''

        # ★★★ 关键: 使用 content:encoded 标签 ★★★
        content_elem = ET.SubElement(entry, '{http://purl.org/rss/1.0/modules/content/}encoded')
        content_elem.text = html

        time.sleep(0.5)

    # 格式化输出
    xml_str = ET.tostring(rss, encoding='utf-8', method='xml')
    dom = minidom.parseString(xml_str)
    pretty_xml = dom.toprettyxml(indent='  ', encoding='UTF-8')

    # 移除多余空行
    lines = [line for line in pretty_xml.decode('utf-8').split('\n') if line.strip()]
    final_xml = '\n'.join(lines)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(final_xml)

    print(f"✅ 完成! 总数:{len(notice_list)} | 有正文:{success}")


def main():
    print("=" * 50)
    print("华工教务处RSS V14")
    print("=" * 50)

    notices = fetch_latest_notices()
    if notices:
        generate_rss_feed(notices)
        print("\n🎉 可以推送了!")
    else:
        print("\n⚠️ 无通知")


if __name__ == "__main__":
    main()
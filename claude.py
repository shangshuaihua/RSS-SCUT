# rss_generator.py (V10 - 简洁高效版)
import requests
import time
from datetime import datetime, timezone, timedelta
from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- 配置区 ---
GITHUB_PAGES_URL = "https://shangshuaihua.github.io/RSS-SCUT/rss.xml"
BASE_SITE_URL = "https://jw.scut.edu.cn"
API_URL = f"{BASE_SITE_URL}/zhinan/cms/article/v2/findInformNotice.do"
ITEMS_TO_FETCH = 30
OUTPUT_FILE = "rss.xml"

TAG_MAP = {6: "信息", 1: "选课", 2: "考试", 3: "实践", 4: "交流", 5: "教师"}


def fetch_latest_notices():
    """从教务处API获取最新通知列表"""
    print(f"📡 正在获取最新 {ITEMS_TO_FETCH} 条通知...")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': f'{BASE_SITE_URL}/zhinan/cms/toPosts.do'
        }
        payload = {
            'category': '0', 'tag': '0', 'pageNum': '1',
            'pageSize': str(ITEMS_TO_FETCH), 'keyword': ''
        }
        response = requests.post(API_URL, headers=headers, data=payload, timeout=20)
        response.raise_for_status()
        data = response.json()

        if data.get("success") and data.get("list"):
            print(f"✅ 成功获取 {len(data['list'])} 条通知")
            return data["list"]
        else:
            print(f"❌ API返回异常: {data}")
            return []
    except Exception as e:
        print(f"❌ 获取失败: {e}")
        return []


def scrape_article_content(url):
    """
    智能提取正文,支持多种模板。
    返回: (成功?, HTML内容)
    """
    print(f"  🔍 抓取: {url}")
    try:
        response = requests.get(
            url,
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=15
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')

        # 按优先级尝试4种选择器(找到就停止)
        selectors = [
            ('div', 'content'),
            ('div', 'news_con'),
            ('div', 'article-content'),
            ('div', 'post-content')
        ]

        for tag, cls in selectors:
            content = soup.find(tag, class_=cls)
            if content:
                print(f"  ✓ 使用模板: {cls}")

                # 清理冗余元素
                for unwanted in content.find_all(['h3', 'h5', 'hr']):
                    if 'title' in str(unwanted.get('class', [])) or \
                            'date' in str(unwanted.get('class', [])):
                        unwanted.decompose()

                # 修复相对链接
                for elem in content.find_all(['a', 'img']):
                    for attr in ['href', 'src']:
                        if elem.get(attr, '').startswith(('/', '../')):
                            elem[attr] = urljoin(BASE_SITE_URL, elem[attr])

                return True, str(content)

        print(f"  ⚠ 未匹配到已知模板")
        return False, ""

    except Exception as e:
        print(f"  ❌ 抓取失败: {e}")
        return False, ""


def generate_rss_feed(notice_list):
    """生成RSS订阅源"""
    print("\n📝 开始生成RSS文件...")

    fg = FeedGenerator()
    fg.title('华南理工大学教务处通知')
    fg.link(href='https://jw.scut.edu.cn/zhinan/cms/index.do', rel='alternate')
    fg.link(href=GITHUB_PAGES_URL, rel='self', type='application/rss+xml')
    fg.description('华工教务处最新通知自动订阅')
    fg.language('zh-CN')

    beijing_tz = timezone(timedelta(hours=8))
    success_count = 0

    for item in sorted(notice_list, key=lambda x: x.get('createTime', ''), reverse=True):
        article_id = item.get('id', '')
        article_url = f"{BASE_SITE_URL}/zhinan/cms/article/view.do?type=posts&id={article_id}"
        news_type = TAG_MAP.get(item.get('tag'), "通知")
        title = item.get('title', '无标题')
        pub_date = item.get('createTime', 'N/A')

        # 创建RSS条目
        fe = fg.add_entry()
        fe.title(f"【{news_type}】{title}")
        fe.link(href=article_url)
        fe.guid(article_url, permalink=True)

        # 设置发布时间
        try:
            dt = datetime.strptime(pub_date, '%Y.%m.%d').replace(tzinfo=beijing_tz)
            fe.pubDate(dt.astimezone(timezone.utc))
        except:
            pass

        # ★★★ 核心逻辑: 构建统一的完整内容 ★★★
        has_content, body_html = scrape_article_content(article_url)

        # 元信息卡片(始终显示)
        meta_card = f"""
<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
            color: white; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
    <p style="margin: 5px 0; font-size: 14px;">📌 <strong>类型:</strong> {news_type}</p>
    <p style="margin: 5px 0; font-size: 14px;">📅 <strong>日期:</strong> {pub_date}</p>
    <p style="margin: 5px 0; font-size: 14px;">🔗 <strong>原文:</strong> 
       <a href="{article_url}" style="color: #ffd700;">点击访问</a>
    </p>
</div>
"""

        if has_content:
            # 情况1: 成功提取正文
            full_html = f"{meta_card}<div style='line-height: 1.8;'>{body_html}</div>"
            success_count += 1
        else:
            # 情况2: 无法提取正文,仅显示元信息
            full_html = f"""
{meta_card}
<div style="text-align: center; padding: 40px; background: #f9f9f9; 
            border-radius: 8px; color: #666;">
    <p style="font-size: 16px;">⚠️ 该通知使用特殊页面布局</p>
    <p>无法自动提取正文内容</p>
    <p style="margin-top: 15px;">
        <a href="{article_url}" 
           style="background: #667eea; color: white; padding: 10px 20px; 
                  text-decoration: none; border-radius: 5px;">
            📄 查看完整通知
        </a>
    </p>
</div>
"""

        # ★★★ 关键: 只设置content,不设置description,避免重复显示 ★★★
        fe.content(full_html, type='html')

        # 注意: 故意不调用 fe.description(),因为某些阅读器会将其当作独立条目

        time.sleep(0.5)  # 礼貌延迟

    fg.rss_file(OUTPUT_FILE, pretty=True)
    print(f"\n✅ RSS生成完成!")
    print(f"   - 总通知数: {len(notice_list)}")
    print(f"   - 成功提取正文: {success_count}")
    print(f"   - 仅元信息: {len(notice_list) - success_count}")


def main():
    if "YourUsername" in GITHUB_PAGES_URL:
        print("❌ 请先修改 GITHUB_PAGES_URL")
        return

    print("=" * 60)
    print("  🎓 华工教务处RSS生成工具 V10")
    print("=" * 60)

    notices = fetch_latest_notices()
    if notices:
        generate_rss_feed(notices)
        print("\n🎉 任务完成! 可以推送到GitHub了")
    else:
        print("\n⚠️ 未获取到通知")


if __name__ == "__main__":
    main()
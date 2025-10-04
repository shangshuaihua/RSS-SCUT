# rss_generator.py (V9 - 修复功能问题+稳定性优化版)
import requests
import time
from datetime import datetime, timezone, timedelta
from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# 可选：添加重试机制（需先安装 tenacity：pip install tenacity）
# from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# --- 1. 配置区（请根据自己的需求修改）---
# 替换为你自己的GitHub Pages RSS链接（如 "https://your-username.github.io/your-repo/rss.xml"）
GITHUB_PAGES_URL = "https://shangshuaihua.github.io/RSS-SCUT/rss.xml"
BASE_SITE_URL = "https://jw.scut.edu.cn"
API_URL = f"{BASE_SITE_URL}/zhinan/cms/article/v2/findInformNotice.do"
ITEMS_TO_FETCH = 30  # 每次获取的通知数量
OUTPUT_FILE = "rss.xml"  # 输出的RSS文件名
REQUEST_DELAY = 0.5  # 爬取正文的间隔（防反爬，可调整）

# --- 2. 辅助数据（修复标签映射的类型匹配问题）---
# 若API返回的tag是字符串（如"6"），则键改为字符串；若返回整数，保持整数（需根据API实际返回调整）
TAG_MAP = {
    "6": "信息", "1": "选课", "2": "考试", "3": "实践", "4": "交流", "5": "教师"
    # 若测试发现标签匹配失败，替换为整数键：
    # 6: "信息", 1: "选课", 2: "考试", 3: "实践", 4: "交流", 5: "教师"
}


# --- 3. 核心功能函数（修复+优化）---

def fetch_latest_notices():
    """从教务处API获取最新的通知列表（修复编码+防反爬）。"""
    print(f"正在从 API 获取最新的 {ITEMS_TO_FETCH} 条通知...")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
            'Referer': f'{BASE_SITE_URL}/zhinan/cms/toPosts.do',
            'Content-Type': 'application/x-www-form-urlencoded'  # 补充POST请求的Content-Type
        }
        payload = {
            'category': '0', 'tag': '0', 'pageNum': '1',
            'pageSize': str(ITEMS_TO_FETCH), 'keyword': ''
        }
        response = requests.post(API_URL, headers=headers, data=payload, timeout=20)
        response.encoding = 'utf-8'  # 显式指定编码，避免中文乱码
        response.raise_for_status()  # 触发HTTP错误（如404、500）
        data = response.json()

        if data.get("success") is True and "list" in data and len(data["list"]) > 0:
            notice_list = data["list"]
            print(f"✅ 成功获取到 {len(notice_list)} 条通知。")
            return notice_list
        else:
            print(f"❌ API返回数据异常: success={data.get('success')}, list长度={len(data.get('list', []))}")
            print(f"API原始返回: {data}")
            return []

    except requests.exceptions.RequestException as e:
        print(f"❌ API请求失败（网络/超时/HTTP错误）: {e}")
        return []
    except ValueError as e:
        print(f"❌ API返回非JSON格式: {e}")
        return []
    except Exception as e:
        print(f"❌ 获取通知列表未知错误: {e}")
        return []


# 可选：添加重试机制（需安装tenacity库）
# @retry(
#     stop=stop_after_attempt(3),  # 最多重试3次
#     wait=wait_exponential(multiplier=1, min=1, max=5),  # 重试间隔：1s→2s→4s（不超过5s）
#     retry=retry_if_exception_type((requests.exceptions.RequestException, ValueError))
# )
def scrape_article_content(url):
    """
    访问文章URL提取正文（修复图片链接+补充Referer+优化错误提示）。
    分别处理<a>（href）和<img>（src），确保所有相对路径转为绝对路径。
    """
    print(f"  -> 正在抓取正文: {url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
            'Referer': f'{BASE_SITE_URL}/zhinan/cms/toPosts.do'  # 补充Referer，防反爬
        }
        response = requests.get(url, headers=headers, timeout=20)
        response.encoding = 'utf-8'  # 显式指定编码
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')  # 依赖lxml库，需安装：pip install lxml

        content_div = soup.find('div', class_='content')
        if not content_div:
            print(f"  -> 提示: 页面无标准content容器，跳过正文抓取。")
            return "<p><i>(该通知使用特殊布局，无法自动提取正文，请点击链接查看原文)</i></p>"

        # 1. 清理无关元素（标题、日期、分隔线）
        for selector in ['h3.content-title', 'h5.content-date', 'hr']:
            elem = content_div.find(selector)
            if elem:
                elem.decompose()

        # 2. 修复<a>标签的href（相对路径→绝对路径）
        for a_tag in content_div.find_all('a', href=True):
            href = a_tag.get('href', '')
            if href.startswith(('/')) or href.startswith(('../')):
                a_tag['href'] = urljoin(BASE_SITE_URL, href)

        # 3. 修复<img>标签的src（核心修复：单独处理img的src属性）
        for img_tag in content_div.find_all('img', src=True):
            src = img_tag.get('src', '')
            if src.startswith(('/')) or src.startswith(('../')):
                img_tag['src'] = urljoin(BASE_SITE_URL, src)
                # 可选：添加图片alt属性，提升可访问性
                if not img_tag.get('alt'):
                    img_tag['alt'] = "通知中的图片"

        return str(content_div)

    except requests.exceptions.RequestException as e:
        err_msg = f"网络/超时错误: {str(e)[:50]}..."  # 截断长错误信息
    except Exception as e:
        err_msg = f"解析错误: {str(e)[:50]}..."
    print(f"  -> 警告: 抓取正文失败: {err_msg}")
    return f"<p><i>(抓取正文失败，请点击链接查看原文。错误：{err_msg})</i></p>"


def generate_rss_feed(notice_list):
    """生成RSS Feed（修复pubDate缺失+优化排序）。"""
    print("开始生成 RSS Feed 文件...")
    fg = FeedGenerator()
    # RSS源基础信息（根据需求修改）
    fg.title('华南理工大学教务处通知 - 自动更新')
    fg.link(href=f'{BASE_SITE_URL}/zhinan/cms/index.do', rel='alternate', type='text/html')
    fg.description('华南理工大学主校区教务处最新通知（含正文预览，每小时更新）')
    fg.language('zh-CN')
    fg.copyright('版权归华南理工大学教务处所有，本RSS仅用于信息同步')
    # RSS自链接（必须是可公开访问的URL，否则客户端无法刷新）
    fg.link(href=GITHUB_PAGES_URL, rel='self', type='application/rss+xml')
    # RSS更新时间（当前UTC时间）
    fg.lastBuildDate(datetime.now(timezone.utc))

    beijing_tz = timezone(timedelta(hours=8))  # 北京时间时区

    # 按创建时间降序排序（确保最新通知在最前，处理空createTime的情况）
    sorted_notices = sorted(
        notice_list,
        key=lambda x: x.get('createTime', '1970.01.01'),  # 空时间排最前（实际是最旧）
        reverse=True
    )

    for item in sorted_notices:
        fe = fg.add_entry()
        article_id = item.get('id', str(time.time_ns()))  # 用时间戳避免ID重复
        article_url = f"{BASE_SITE_URL}/zhinan/cms/article/view.do?type=posts&id={article_id}"

        # 修复标签映射（处理tag的类型匹配）
        tag_str = str(item.get('tag', '0'))  # 转为字符串，匹配TAG_MAP的键
        news_type = TAG_MAP.get(tag_str, "通知")  # 无法匹配时默认"通知"

        # 1. RSS条目标题（含标签，便于快速识别类型）
        fe.title(f"【{news_type}】{item.get('title', '无标题通知')}")
        # 2. 条目链接（唯一标识，必须可访问）
        fe.link(href=article_url, rel='alternate', type='text/html')
        # 3. 唯一标识（用URL+ID确保不重复，permalink=True表示是永久链接）
        fe.guid(f"{article_url}#id={article_id}", permalink=False)

        # 4. 发布时间（修复缺失问题，优先用API的createTime，失败则用当前UTC时间）
        create_time = item.get('createTime', '')
        try:
            # 解析北京时间（如"2024.05.20"）
            pub_date_naive = datetime.strptime(create_time, '%Y.%m.%d')
            pub_date_beijing = pub_date_naive.replace(tzinfo=beijing_tz)
            pub_date_utc = pub_date_beijing.astimezone(timezone.utc)  # 转为UTC时间（RSS标准）
            fe.pubDate(pub_date_utc)
        except (ValueError, TypeError):
            # 解析失败时，用当前UTC时间作为默认（避免缺失pubDate）
            default_pub_date = datetime.now(timezone.utc)
            fe.pubDate(default_pub_date)
            print(f"  -> 警告: 通知[{item.get('title')}]的时间[{create_time}]解析失败，用默认时间{default_pub_date}")

        # 5. 条目摘要（含类型、发布时间、来源）
        summary = f"""
        <p>类型：{news_type}</p>
        <p>发布时间：{create_time if create_time else '未知'}</p>
        <p>来源：<a href="{article_url}">华南理工大学教务处官网</a></p>
        <hr>
        """
        fe.description(summary)  # description是摘要，content是完整正文

        # 6. 条目完整正文（调用抓取函数）
        content_html = scrape_article_content(article_url)
        fe.content(f"{summary}{content_html}", type='html')  # 正文包含摘要，便于阅读

        # 7. 控制爬取频率（防反爬）
        time.sleep(REQUEST_DELAY)

    # 生成RSS文件（pretty=True格式化输出，便于调试）
    fg.rss_file(OUTPUT_FILE, pretty=True, encoding='utf-8')
    print(f"✅ 成功生成 RSS 文件: {OUTPUT_FILE}（包含 {len(sorted_notices)} 条通知）")


def main():
    # 优化GitHub Pages链接检查（提醒用户替换为自己的链接，而非硬检查）
    if "your-username" in GITHUB_PAGES_URL or "shangshuaihua" in GITHUB_PAGES_URL:
        print("⚠️  警告: 请先修改脚本顶部的 GITHUB_PAGES_URL 为你自己的GitHub Pages RSS链接！")
        print("   示例: GITHUB_PAGES_URL = 'https://your-github-username.github.io/your-repo/rss.xml'")
        # 可选：若未修改，是否继续执行？这里设为继续（避免阻断测试）
        confirm = input("是否继续使用当前链接生成RSS？(y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ 任务终止，请先修改GITHUB_PAGES_URL。")
            return

    print("\n--- 华南理工大学教务处RSS生成任务启动 ---")
    # 1. 获取通知列表
    latest_notices = fetch_latest_notices()
    if not latest_notices:
        print("❌ 未获取到任何通知，本次任务不生成RSS文件。")
        print("--- 任务失败 ---")
        return

    # 2. 生成RSS Feed
    generate_rss_feed(latest_notices)
    print("\n--- 任务完成！RSS文件已保存为: ./rss.xml ---")
    print(f"   可将 {OUTPUT_FILE} 上传到GitHub Pages，或本地用RSS客户端打开测试。")


if __name__ == "__main__":
    # 检查依赖库（提醒用户安装缺失的库）
    try:
        import feedgen.feed
        import bs4
        import requests
    except ImportError as e:
        missing_lib = str(e).split("No module named ")[-1].strip('"\'')
        print(f"❌ 缺失依赖库: {missing_lib}，请先安装：")
        print(f"   pip install {missing_lib}")
        print("   完整依赖安装命令: pip install feedgen beautifulsoup4 requests lxml")
        exit(1)
    # 启动主函数
    main()
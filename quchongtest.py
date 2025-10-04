# rss_generator.py (V10 - 彻底解决重复条目+完整功能版)
import requests
import time
from datetime import datetime, timezone, timedelta
from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# --- 1. 配置区（请根据自身需求修改）---
# 替换为你的GitHub Pages RSS链接（必须唯一，避免客户端误判）
GITHUB_PAGES_URL = "https://shangshuaihua.github.io/RSS-SCUT/rss.xml"
BASE_SITE_URL = "https://jw.scut.edu.cn"  # 教务处官网根地址（勿改）
API_URL = f"{BASE_SITE_URL}/zhinan/cms/article/v2/findInformNotice.do"  # 通知API（勿改）
ITEMS_TO_FETCH = 30  # 每次获取的最大通知数量（建议≤50，防反爬）
OUTPUT_FILE = "rss.xml"  # 输出的RSS文件名
REQUEST_DELAY = 0.8  # 抓取正文的间隔（秒，建议0.5-1，防反爬）

# --- 2. 辅助数据（标签映射，根据API返回类型调整键的格式）---
# 若API返回tag为整数（如6），则键改为整数（6: "信息"）；若为字符串（如"6"），保持当前格式
TAG_MAP = {
    "6": "信息", "1": "选课", "2": "考试", "3": "实践", "4": "交流", "5": "教师"
}


# --- 3. 核心功能函数（关键修改：去重+GUID唯一+稳定抓取）---

def fetch_latest_notices():
    """从教务处API获取通知列表（防反爬+编码修复+异常捕获）"""
    print(f"🔍 正在从API获取最新{ITEMS_TO_FETCH}条通知...")
    try:
        # 模拟浏览器请求头，降低被拦截概率
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Referer': f'{BASE_SITE_URL}/zhinan/cms/toPosts.do',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'X-Requested-With': 'XMLHttpRequest'  # 模拟AJAX请求（API常见要求）
        }
        # API请求参数（category=0表示全部分类，tag=0表示全部标签）
        payload = {
            'category': '0', 'tag': '0', 'pageNum': '1',
            'pageSize': str(ITEMS_TO_FETCH), 'keyword': ''
        }
        response = requests.post(
            API_URL, headers=headers, data=payload, timeout=25,
            verify=True  # 启用SSL验证（安全，避免证书问题）
        )
        response.encoding = 'utf-8'  # 强制UTF-8编码，解决中文乱码
        response.raise_for_status()  # 触发HTTP错误（如403、500）
        data = response.json()

        # 验证API返回格式（必须包含success=True和非空list）
        if data.get("success") is True and isinstance(data.get("list"), list) and len(data["list"]) > 0:
            notice_list = data["list"]
            print(f"✅ 成功获取{len(notice_list)}条通知（去重前）")
            return notice_list
        else:
            print(f"❌ API返回无效数据：success={data.get('success')}，list长度={len(data.get('list', []))}")
            print(f"📝 API原始返回：{str(data)[:200]}...")  # 截断长数据，避免日志冗余
            return []

    except requests.exceptions.HTTPError as e:
        print(f"❌ API请求失败（HTTP错误）：{e}（可能被反爬拦截，建议调整请求头）")
        return []
    except requests.exceptions.ConnectionError:
        print(f"❌ 网络连接失败：无法访问{API_URL}（检查网络或官网是否可用）")
        return []
    except requests.exceptions.Timeout:
        print(f"❌ 请求超时：超过25秒未收到API响应（建议增大timeout值）")
        return []
    except ValueError:
        print(f"❌ API返回非JSON格式（可能是HTML错误页，被反爬拦截）")
        return []
    except Exception as e:
        print(f"❌ 获取通知未知错误：{str(e)[:100]}...")
        return []


def scrape_article_content(url):
    """抓取文章正文（修复图片链接+防反爬+优雅失败）"""
    print(f"  📄 正在抓取正文：{url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Referer': f'{BASE_SITE_URL}/zhinan/cms/toPosts.do',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        }
        response = requests.get(
            url, headers=headers, timeout=20, verify=True
        )
        response.encoding = 'utf-8'
        response.raise_for_status()

        # 解析HTML（依赖lxml，需安装：pip install lxml）
        soup = BeautifulSoup(response.text, 'lxml')
        # 关键：正文容器（若后续官网改结构，需用F12检查新容器class/id）
        content_div = soup.find('div', class_='content')

        if not content_div:
            print(f"  ⚠️ 页面无标准正文容器（class='content'），跳过抓取")
            return "<p><i>（该通知使用特殊布局，无法自动提取正文，请点击链接查看原文）</i></p>"

        # 清理无关元素（标题、日期、分隔线，避免重复显示）
        for elem_selector in ['h3.content-title', 'h5.content-date', 'hr', 'div.content-footer']:
            elem = content_div.find(elem_selector)
            if elem:
                elem.decompose()  # 移除元素

        # 修复<a>标签相对路径→绝对路径
        for a_tag in content_div.find_all('a', href=True):
            href = a_tag.get('href', '').strip()
            if href and (href.startswith('/') or href.startswith('../')):
                a_tag['href'] = urljoin(BASE_SITE_URL, href)
                a_tag['target'] = '_blank'  # 新窗口打开链接，提升体验

        # 修复<img>标签相对路径→绝对路径（核心修复：单独处理src）
        for img_tag in content_div.find_all('img', src=True):
            src = img_tag.get('src', '').strip()
            if src and (src.startswith('/') or src.startswith('../')):
                img_tag['src'] = urljoin(BASE_SITE_URL, src)
            # 补充alt属性，提升可访问性（无alt时显示默认文本）
            if not img_tag.get('alt'):
                img_tag['alt'] = "通知正文图片"
                img_tag['loading'] = 'lazy'  # 懒加载图片，优化RSS加载速度

        # 返回清理后的正文HTML
        return str(content_div)

    except requests.exceptions.RequestException as e:
        err_msg = f"网络错误：{str(e)[:60]}..."
    except Exception as e:
        err_msg = f"解析错误：{str(e)[:60]}..."
    print(f"  ⚠️ 抓取正文失败：{err_msg}")
    return f"<p><i>（抓取正文失败：{err_msg}，请点击链接查看原文）</i></p>"


def generate_rss_feed(notice_list):
    """生成RSS Feed（关键修改：去重+GUID唯一+避免重复条目）"""
    print("📊 开始生成RSS Feed...")
    fg = FeedGenerator()

    # RSS源基础信息（符合RSS 2.0规范，提升客户端兼容性）
    fg.title('华南理工大学教务处通知 - 自动更新')
    fg.link(
        href=f'{BASE_SITE_URL}/zhinan/cms/index.do',
        rel='alternate',
        type='text/html',
        title='教务处官网首页'
    )
    fg.description('华南理工大学主校区教务处最新通知（含完整正文预览，每小时自动更新）')
    fg.language('zh-CN')
    fg.copyright('版权归华南理工大学教务处所有，本RSS仅用于信息同步，不用于商业用途')
    fg.managingEditor('your-email@example.com')  # 替换为你的邮箱（可选，RSS规范字段）
    fg.webMaster('your-email@example.com')       # 替换为你的邮箱（可选）
    # RSS自链接（必须是可公开访问的URL，客户端通过此链接刷新）
    fg.link(
        href=GITHUB_PAGES_URL,
        rel='self',
        type='application/rss+xml',
        title='华工教务处通知RSS订阅'
    )
    # RSS更新时间（当前UTC时间，符合国际标准）
    fg.lastBuildDate(datetime.now(timezone.utc))

    # 时区设置（北京时间→UTC，RSS标准要求）
    beijing_tz = timezone(timedelta(hours=8))
    # 关键：去重集合（记录已处理的article_id，避免重复条目）
    processed_ids = set()
    # 按创建时间降序排序（最新通知在前）
    sorted_notices = sorted(
        notice_list,
        key=lambda x: x.get('createTime', '1970.01.01'),
        reverse=True
    )

    for item in sorted_notices:
        # 1. 提取核心字段（处理空值，避免KeyError）
        article_id = str(item.get('id', '')).strip()  # 转为字符串，确保唯一性
        title = item.get('title', '无标题通知').strip()
        create_time = item.get('createTime', '').strip()
        tag = str(item.get('tag', '0')).strip()  # 标签转为字符串，匹配TAG_MAP

        # 2. 去重逻辑（核心：跳过已处理的article_id）
        if not article_id:
            print(f"  ⚠️ 跳过无ID的通知：{title}（无唯一标识，可能重复）")
            continue
        if article_id in processed_ids:
            print(f"  ⚠️ 跳过重复通知：{title}（ID={article_id}已处理）")
            continue
        processed_ids.add(article_id)  # 标记为已处理

        # 3. 构建文章链接（确保URL唯一且可访问）
        article_url = f"{BASE_SITE_URL}/zhinan/cms/article/view.do?type=posts&id={article_id}"
        # 验证URL有效性（可选，避免无效链接）
        if not article_url.startswith(('http://', 'https://')):
            print(f"  ⚠️ 无效文章链接：{article_url}，跳过该通知")
            continue

        # 4. 创建RSS条目
        fe = fg.add_entry()

        # 5. 条目核心字段（确保GUID唯一，解决重复条目问题）
        # 标题：添加标签前缀，便于快速识别通知类型
        news_type = TAG_MAP.get(tag, "通知")  # 标签映射，无匹配时默认"通知"
        fe.title(f"【{news_type}】{title}")

        # 链接：文章原始URL
        fe.link(
            href=article_url,
            rel='alternate',
            type='text/html',
            title=title
        )

        # GUID：唯一标识（核心修改！用article_id确保唯一，避免重复）
        # permalink=False：表示这是内部ID（非URL），RSS客户端会优先用此判断重复
        fe.guid(article_id, permalink=False)

        # 发布时间：北京时间→UTC，解决时区问题
        try:
            if create_time:
                # 解析API返回的时间（格式：2024.05.20）
                pub_date_naive = datetime.strptime(create_time, '%Y.%m.%d')
                # 转为北京时间（带时区）
                pub_date_beijing = pub_date_naive.replace(tzinfo=beijing_tz)
                # 转为UTC时间（RSS标准要求）
                pub_date_utc = pub_date_beijing.astimezone(timezone.utc)
                fe.pubDate(pub_date_utc)
            else:
                # 无时间时用当前UTC时间（避免缺失pubDate导致客户端排序异常）
                fe.pubDate(datetime.now(timezone.utc))
                print(f"  ⚠️ 通知[{title}]无发布时间，用当前时间填充")
        except (ValueError, TypeError):
            # 时间格式错误时用当前UTC时间
            fe.pubDate(datetime.now(timezone.utc))
            print(f"  ⚠️ 通知[{title}]时间格式错误（{create_time}），用当前时间填充")

        # 6. 条目摘要（description：仅显示关键信息，避免与content重复）
        summary = f"""
        <div style="margin-bottom: 10px;">
            <span style="background: #f0f0f0; padding: 2px 8px; border-radius: 4px; margin-right: 8px;">{news_type}</span>
            <span style="color: #666;">发布时间：{create_time if create_time else '未知'}</span>
        </div>
        <div style="margin: 10px 0; padding: 8px; background: #fafafa; border-left: 3px solid #ccc;">
            <p>来源：<a href="{article_url}" target="_blank" style="color: #0066cc;">华南理工大学教务处官网</a></p>
            <p>提示：点击标题或链接可访问原文，正文内容已自动同步。</p>
        </div>
        <hr style="border: none; border-top: 1px solid #eee; margin: 15px 0;" />
        """
        fe.description(summary)  # 摘要仅用于列表预览

        # 7. 条目完整正文（content:encoded：包含摘要+正文，客户端点击后显示）
        content_html = scrape_article_content(article_url)
        full_content = f"{summary}{content_html}"
        fe.content(
            content=full_content,
            type='html',  # 明确指定HTML格式，避免客户端解析为纯文本
            xmlBase=BASE_SITE_URL  # 基础URL，确保相对路径 fallback
        )

        # 8. 控制抓取频率（防反爬，避免短时间内大量请求）
        time.sleep(REQUEST_DELAY)

    # 生成RSS文件（UTF-8编码+格式化输出，便于调试和兼容）
    fg.rss_file(
        OUTPUT_FILE,
        pretty=True,  # 格式化XML，可读性强
        encoding='utf-8',  # 强制UTF-8，解决中文乱码
        xml_declaration=True  # 包含XML声明，符合规范
    )

    # 输出结果日志
    total_processed = len(processed_ids)
    print(f"✅ RSS Feed生成完成！")
    print(f"📈 统计：共处理{len(notice_list)}条通知，去重后保留{total_processed}条有效通知")
    print(f"📁 输出文件：{OUTPUT_FILE}（路径：{str(__import__('os').path.abspath(OUTPUT_FILE))}）")
    print(f"🔗 订阅链接：{GITHUB_PAGES_URL}（需上传到GitHub Pages或其他公开服务器）")


def main():
    """主函数（流程控制+依赖检查+用户提示）"""
    # 1. 检查依赖库（避免因缺失库导致崩溃）
    required_libs = {
        'feedgen': 'feedgen.feed',
        'beautifulsoup4': 'bs4',
        'requests': 'requests',
        'lxml': 'lxml'
    }
    missing_libs = []
    for lib_name, import_path in required_libs.items():
        try:
            __import__(import_path)
        except ImportError:
            missing_libs.append(lib_name)
    if missing_libs:
        print(f"❌ 缺失必需依赖库：{', '.join(missing_libs)}")
        print(f"📦 安装命令：pip install {' '.join(missing_libs)}")
        print(f"💡 完整安装命令（含可选重试库）：pip install feedgen beautifulsoup4 requests lxml tenacity")
        return

    # 2. 检查配置（提醒用户修改关键参数）
    if "your-github-username" in GITHUB_PAGES_URL or "shangshuaihua" in GITHUB_PAGES_URL:
        print("⚠️ 警告：未修改GITHUB_PAGES_URL（默认值可能无效）")
        print("   正确格式：GITHUB_PAGES_URL = 'https://你的GitHub用户名.github.io/你的仓库名/rss.xml'")
        confirm = input("是否继续使用当前链接生成RSS？（y/n，默认n）：").strip().lower() or 'n'
        if confirm != 'y':
            print("❌ 任务终止：请先修改GITHUB_PAGES_URL为有效链接")
            return

    # 3. 执行主流程
    print("\n" + "="*50)
    print("🎯 华南理工大学教务处RSS生成工具（V10）")
    print("📅 执行时间：" + datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S（北京时间）"))
    print("="*50 + "\n")

    # 步骤1：获取通知列表
    notice_list = fetch_latest_notices()
    if not notice_list:
        print("\n❌ 任务失败：未获取到有效通知（可能是API问题或网络问题）")
        print("💡 建议：1. 检查教务处官网是否可访问；2. 调整请求头或增加timeout；3. 减少ITEMS_TO_FETCH")
        print("\n" + "="*50)
        return

    # 步骤2：生成RSS Feed
    generate_rss_feed(notice_list)

    # 4. 后续操作提示
    print("\n" + "="*50)
    print("📌 后续操作建议：")
    print("   1. 本地测试：用RSS客户端（如Feedly、Inoreader）打开./rss.xml，检查是否有重复条目")
    print("   2. 上传部署：将rss.xml上传到GitHub Pages仓库的根目录，确保可通过GITHUB_PAGES_URL访问")
    print("   3. 定时更新：在GitHub Actions中设置定时任务（如每小时运行一次脚本），自动更新RSS")
    print("   4. 问题排查：若仍有重复，检查API返回的article_id是否唯一（日志中查看「跳过重复通知」提示）")
    print("="*50)


if __name__ == "__main__":
    main()
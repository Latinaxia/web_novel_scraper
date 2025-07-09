import time
import argparse
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import re


def setup_driver(headless=False):
    # 配置浏览器驱动
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--log-level=3")  # 仅显示错误日志
    chrome_options.add_experimental_option(
        "prefs", {"profile.default_content_setting_values.cookies": 1}
    )
    if headless:
        chrome_options.add_argument("--headless=new")
    return webdriver.Chrome(options=chrome_options)


def clean_text(html_content):
    """清理HTML内容，提取纯文本并过滤广告"""
    soup = BeautifulSoup(html_content, "html.parser")

    # 移除所有脚本、样式和广告标签
    for tag in soup(["script", "style", "ins", "noscript"]):
        tag.decompose()

    # 移除所有链接（通常包含广告）
    for a in soup.find_all("a"):
        a.decompose()

    # 获取文本并处理空格和换行
    text = soup.get_text(strip=True, separator="\n")

    # 过滤广告相关文本行
    lines = text.split("\n")
    cleaned_lines = []
    ad_keywords = [
        "ad:",
        "hgame:",
        "本站发布页",
        "请勿使用非浏览器访问本站",
        "www.",
        "http",
        ".com",
    ]

    for line in lines:
        # 跳过包含广告关键词的行
        if any(keyword in line.lower() for keyword in ad_keywords):
            continue
        # 跳过空行或仅含标点的行
        if line.strip() and not re.match(r"^[^\w\s]+$", line):
            cleaned_lines.append(line.strip())

    # 合并行，处理多余空行
    cleaned_text = "\n\n".join([line for line in cleaned_lines if line])
    return cleaned_text


def detect_content_selector(driver):
    # 自动检测内容选择器（基于常见小说网站结构）
    potential_selectors = [
        "div#content",
        "div#contenta",
        "div.novelcontent",
        "div.read-content",
        "div.article-content",
    ]

    for selector in potential_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements and len(elements[0].text) > 500:  # 内容长度阈值
                print(f"检测到内容选择器: {selector}")
                return selector
        except:
            continue

    print("未检测到合适的内容选择器，使用默认选择器")
    return "body"  # 作为备选，抓取整个页面


def scrape_text(url, selector=None, manual_verify_time=30, headless=False):
    # 抓取单个URL的文本内容
    driver = setup_driver(headless)
    try:
        driver.get(url)
        print(f"正在访问: {url}")

        if not headless:
            print(f"请在 {manual_verify_time} 秒内完成安全验证（如果有）...")
            time.sleep(manual_verify_time)

        # 等待页面加载稳定
        time.sleep(3)

        # 如果未指定选择器，尝试自动检测
        if not selector:
            selector = detect_content_selector(driver)

        try:
            # 等待内容区域加载
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
        except:
            print(f"内容区域未找到，使用选择器: {selector}")

        # 获取内容区域的HTML
        content_element = driver.find_element(By.CSS_SELECTOR, selector)
        content_html = content_element.get_attribute("innerHTML")

        # 清理文本
        cleaned_text = clean_text(content_html)

        if len(cleaned_text) < 200:  # 内容过短，可能抓取失败
            print(f"警告: 从 {url} 抓取的内容可能不完整")

        return {"url": url, "content": cleaned_text, "selector": selector}

    except Exception as e:
        print(f"抓取 {url} 时发生错误: {e}")
        return {"url": url, "content": "", "error": str(e)}
    finally:
        driver.quit()


def batch_scrape(
    urls, output_file, selector=None, verify_time=30, headless=False, append=False
):
    # 批量抓取多个URL的文本内容
    all_content = []

    for i, url in enumerate(urls, 1):
        print(f"\n===== 开始抓取第 {i}/{len(urls)} 个URL =====")
        result = scrape_text(url, selector, verify_time, headless)
        all_content.append(result)

        # 如果是第一个URL且未指定选择器，使用检测到的选择器继续后续抓取
        if i == 1 and not selector and "selector" in result:
            selector = result["selector"]

    # 合并所有文本内容
    combined_text = (
        "\n\n"
        + "=" * 50
        + "\n\n".join(
            [
                f"来源: {result['url']}\n\n{result['content']}"
                for result in all_content
                if result["content"]
            ]
        )
    )

    # 保存到文件（支持追加模式）
    mode = "a" if append else "w"
    with open(output_file, mode, encoding="utf-8") as file:
        file.write(combined_text)

    print(f"\n===== 批量抓取完成 =====")
    print(
        f"已将 {len([r for r in all_content if r['content']])} 个页面的内容保存到: {output_file}"
    )

    # 输出统计信息
    for result in all_content:
        status = (
            "成功" if result["content"] else f"失败: {result.get('error', '未知原因')}"
        )
        print(f"- {result['url']}: {status}")


def main():
    parser = argparse.ArgumentParser(description="批量网页文字抓取工具")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="单个目标URL")
    group.add_argument("--url-file", help="包含多个URL的JSON文件路径")
    parser.add_argument("--selector", help="CSS选择器，用于定位内容区域")
    parser.add_argument("--output", default="scraped_text.txt", help="输出文件名")
    parser.add_argument(
        "--verify-time", type=int, default=30, help="手动验证时间（秒）"
    )
    parser.add_argument("--headless", action="store_true", help="启用无头模式")
    parser.add_argument("--append", action="store_true", help="追加到现有文件而非覆盖")
    args = parser.parse_args()

    # 处理URL输入
    if args.url:
        urls = [args.url]
    else:
        try:
            with open(args.url_file, "r", encoding="utf-8") as f:
                urls = json.load(f)
            print(f"从文件加载了 {len(urls)} 个URL")
        except Exception as e:
            print(f"无法加载URL文件: {e}")
            return

    # 执行批量抓取（添加append参数）
    batch_scrape(
        urls, args.output, args.selector, args.verify_time, args.headless, args.append
    )


if __name__ == "__main__":
    main()

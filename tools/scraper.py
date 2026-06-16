"""
tools/scraper.py
网页内容抓取 + 联系方式提取
从公司网站提取：邮箱、电话、公司简介、关键联系人
"""

import re
import logging
import requests
from typing import Dict, Optional, List
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import config

logger = logging.getLogger(__name__)

# 邮箱正则
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
# 电话正则（国际格式）
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{3,4}[-.\s]?\d{3,4}"
)
# LinkedIn 个人主页
LINKEDIN_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/in/[\w\-]+")

HEADERS = {
    "User-Agent": UserAgent().random,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch_page(url: str, timeout: int = 10) -> Optional[str]:
    """抓取网页内容，带错误处理"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.debug(f"抓取失败 [{url}]: {e}")
        return None


def _extract_emails(text: str) -> List[str]:
    """从文本中提取邮箱地址，过滤垃圾邮箱"""
    emails = EMAIL_RE.findall(text)
    # 过滤常见无效邮箱
    invalid_patterns = ["noreply", "no-reply", "donotreply", "example.com", "test@"]
    filtered = []
    for e in emails:
        if not any(p in e.lower() for p in invalid_patterns):
            filtered.append(e.lower())
    return list(set(filtered))


def _extract_phones(text: str) -> List[str]:
    """提取电话号码"""
    phones = PHONE_RE.findall(text)
    # 简单去重 + 过滤太短的匹配
    cleaned = []
    for p in phones:
        p = re.sub(r"[^\d+]", "", p)
        if len(p) >= 7:
            cleaned.append(p)
    return list(set(cleaned))[:5]  # 最多返回5个


def _extract_company_description(soup: BeautifulSoup) -> str:
    """尝试提取公司简介（从 About 页面或 meta description）"""
    # 先试 meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        return meta["content"].strip()[:300]

    # 试 about 页面链接
    about_link = soup.find("a", string=re.compile(r"about|关于", re.I))
    #  fallback: 取第一段有意义的文字
    for tag in soup.find_all(["p", "div"], limit=20):
        text = tag.get_text(strip=True)
        if len(text) > 50:
            return text[:300]

    return ""


def _extract_social_links(soup: BeautifulSoup, base_url: str) -> Dict[str, str]:
    """提取社交媒体链接"""
    links = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if "linkedin.com/company" in href:
            links["linkedin_company"] = a["href"]
        elif "linkedin.com/in/" in href:
            links["linkedin_person"] = a["href"]
        elif "facebook.com" in href:
            links["facebook"] = a["href"]
        elif "twitter.com" in href or "x.com" in href:
            links["twitter"] = a["href"]
    return links


def scrape_lead(lead: Dict) -> Dict:
    """
    对单个潜在客户进行深度抓取
    输入: {title, url, snippet, source}
    输出: 补充了联系方式的 lead dict
    """
    url = lead.get("url", "")
    if not url.startswith("http"):
        logger.debug(f"跳过无效URL: {url}")
        return lead

    html = _fetch_page(url, config.SCRAPE_TIMEOUT)
    if not html:
        return lead

    try:
        soup = BeautifulSoup(html, "html.parser")

        # 提取联系方式
        emails = _extract_emails(html)
        phones = _extract_phones(html)

        # 提取公司描述
        description = _extract_company_description(soup)

        # 提取社交媒体
        social = _extract_social_links(soup, url)

        # 更新 lead
        lead.update({
            "emails": emails,
            "phones": phones,
            "description": description,
            "social": social,
            "scraped": True,
        })

        # 如果首页没找到邮箱，尝试 About 页面
        if not emails:
            about_links = [a["href"] for a in soup.find_all("a", href=True)
                           if re.search(r"about|contact|联系|关于", a.get_text(strip=True, separator=" "), re.I)]
            for link in about_links[:2]:  # 最多试2个
                full_url = link if link.startswith("http") else url.rstrip("/") + "/" + link.lstrip("/")
                about_html = _fetch_page(full_url, config.SCRAPE_TIMEOUT)
                if about_html:
                    emails = _extract_emails(about_html)
                    if emails:
                        lead["emails"] = emails
                        break

    except Exception as e:
        logger.warning(f"抓取 lead 失败 [{url}]: {e}")

    return lead


def batch_scrape(leads: List[Dict], max_workers: int = 3) -> List[Dict]:
    """
    批量抓取（顺序执行，避免并发被ban）
    每抓取一个 lead 后稍作延迟
    """
    scraped = []
    for i, lead in enumerate(leads):
        logger.info(f"抓取进度: {i+1}/{len(leads)} - {lead.get('url', '')[:50]}")
        scraped_lead = scrape_lead(lead)
        scraped.append(scraped_lead)
        import time
        time.sleep(2)  # 礼貌延迟
    return scraped

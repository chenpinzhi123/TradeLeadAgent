"""
tools/scraper.py
网页内容抓取 + 联系方式提取
从公司网站提取：邮箱、电话、公司简介、关键联系人
改进：更严格的电话/邮箱验证，过滤垃圾联系方式
"""

import re
import time
import logging
import requests
from typing import Dict, Optional, List
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
import config

logger = logging.getLogger(__name__)

# 邮箱正则（标准格式）
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
# 电话正则（更严格：支持国际格式，至少8位有效数字）
PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?"
    r"(?:\(?\d{1,4}\)?[\s.-]?)"
    r"\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{3,4}"
)
# 宽松电话正则（备用，捕捉更多格式）
PHONE_RE_LOOSE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?\d{7,15}"
)

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
        # 只处理 HTML
        if "text/html" not in resp.headers.get("content-type", ""):
            return None
        return resp.text
    except Exception as e:
        logger.debug(f"抓取失败 [{url}]: {e}")
        return None


def _extract_emails(text: str) -> List[str]:
    """
    从文本中提取邮箱地址，严格过滤垃圾邮箱。
    改进：
      1. 过滤常见无效邮箱（noreply, support, admin 等）
      2. 过滤明显格式错误的邮箱
      3. 优先返回联系类邮箱（info, contact, sales, hello）
    """
    emails = EMAIL_RE.findall(text)
    invalid_patterns = [
        "noreply", "no-reply", "donotreply", "example.com", "test@",
        "admin@", "abuse@", "postmaster@", "webmaster@",
        "support@",  # 客服邮箱，非采购联系人
    ]
    # 优先联系类关键词
    priority_patterns = ["info@", "contact@", "sales@", "hello@", "enquiry@", "inquiry@", "buy@", "procure@"]

    filtered = []
    priority = []
    seen = set()
    for e in emails:
        e = e.lower().strip()
        if e in seen:
            continue
        seen.add(e)
        # 过滤无效
        if any(p in e for p in invalid_patterns):
            continue
        # 基本格式检查：@ 前后至少1个字符，域名至少2级
        parts = e.split("@")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            continue
        if "." not in parts[1]:
            continue
        # 优先邮箱放前面
        if any(p in e for p in priority_patterns):
            priority.append(e)
        else:
            filtered.append(e)

    # 去重合并：优先邮箱在前
    result = []
    seen2 = set()
    for e in priority + filtered:
        if e not in seen2:
            seen2.add(e)
            result.append(e)
    return result[:10]  # 最多返回10个


def _extract_phones(text: str) -> List[str]:
    """
    提取电话号码，过滤垃圾号码。
    改进：
      1. 验证号码长度（7-15位有效数字）
      2. 过滤明显无效号码（全同数字、太短的号码）
      3. 格式化输出
    """
    phones = PHONE_RE.findall(text)
    # 备用：宽松正则补抓
    if len(phones) < 2:
        phones_loose = PHONE_RE_LOOSE.findall(text)
        phones.extend(phones_loose)

    cleaned = []
    seen_normalized = set()
    for p in phones:
        # 清理所有非数字和+号
        digits_only = re.sub(r"[^\d+]", "", p)
        # 过滤：至少7位，不超过15位
        if len(digits_only) < 7 or len(digits_only) > 15:
            continue
        # 过滤：不能全是相同数字
        if len(set(digits_only)) <= 2:
            continue
        # 过滤：不能以0-2开头后全0（明显假号）
        if re.match(r"^[0-2]0+$", digits_only):
            continue
        # 标准化：保留 E.164 格式（最多保留 + 和数字）
        normalized = re.sub(r"[^\d+]", "", digits_only)
        if normalized not in seen_normalized:
            seen_normalized.add(normalized)
            # 格式化：尝试加 -
            formatted = _format_phone(p)
            cleaned.append(formatted)

    return cleaned[:8]  # 最多返回8个


def _format_phone(raw: str) -> str:
    """尝试格式化电话号码（不加括号）"""
    digits = re.sub(r"[^\d+]", "", raw)
    # 如果是国际格式（+开头），保留
    if raw.strip().startswith("+"):
        return raw.strip()
    # 否则返回纯数字
    return digits


def _extract_company_description(soup: BeautifulSoup) -> str:
    """尝试提取公司简介（从 About 页面或 meta description）"""
    # 先试 meta description
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        desc = meta["content"].strip()
        if len(desc) > 20:
            return desc[:300]

    # 试 about 页面链接
    about_link = soup.find("a", string=re.compile(r"about|关于", re.I))
    #  fallback: 取第一段有意义的文字
    for tag in soup.find_all(["p", "div"], limit=20):
        text = tag.get_text(strip=True)
        if len(text) > 50 and len(text) < 500:
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
        elif "facebook.com" in href and "profile" not in href and "people" not in href:
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

        # 如果首页没找到邮箱，尝试 About / Contact 页面
        if not emails:
            about_links = []
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text(strip=True, separator=" ")
                if re.search(r"about|contact|联系|关于", text, re.I) and href:
                    full_url = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
                    if full_url not in about_links:
                        about_links.append(full_url)
                elif re.search(r"about|contact", href, re.I) and href:
                    full_url = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
                    if full_url not in about_links:
                        about_links.append(full_url)

            for link in about_links[:3]:  # 最多试3个
                about_html = _fetch_page(link, config.SCRAPE_TIMEOUT)
                if about_html:
                    new_emails = _extract_emails(about_html)
                    if new_emails:
                        lead["emails"] = new_emails
                        # 也从 contact 页面抓电话
                        new_phones = _extract_phones(about_html)
                        if new_phones:
                            lead["phones"] = new_phones
                        break
                    time.sleep(1)

    except Exception as e:
        logger.warning(f"抓取 lead 失败 [{url}]: {e}")

    return lead


def batch_scrape(ads: List[Dict], max_workers: int = 3) -> List[Dict]:
    """
    批量抓取（顺序执行，避免并发被ban）
    每抓取一个 lead 后稍作延迟
    改进：限制抓取数量，避免耗时过长
    """
    scraped = []
    # 最多抓取 max_results 个，避免超时
    max_to_scrape = min(len(ads), config.MAX_PAGES_PER_LEAD * 10)
    for i, lead in enumerate(ads[:max_to_scrape]):
        logger.info(f"抓取进度: {i+1}/{len(ads[:max_to_scrape])} - {lead.get('url', '')[:50]}")
        scraped_lead = scrape_lead(lead)
        scraped.append(scraped_lead)
        time.sleep(2)  # 礼貌延迟
    return scraped

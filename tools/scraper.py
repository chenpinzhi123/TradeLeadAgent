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

# 请求头（必须定义，之前缺失导致 _fetch_page NameError）
try:
    ua = UserAgent()
    _DEFAULT_UA = ua.random
except Exception:
    _DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

HEADERS = {
    "User-Agent": _DEFAULT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8,fr;q=0.7,es;q=0.6",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}

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


# 常见免费邮箱域名（非公司域名）
FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
    "yandex.com", "yandex.ru", "mail.ru", "qq.com", "163.com", "126.com",
    "sina.com", "sohu.com", "foxmail.com", "icloud.com", "me.com",
    "protonmail.com", "zoho.com", "aol.com", "msn.com", "ymail.com",
}

# 目标市场常见电话区号（用于验证电话号码归属）
MARKET_PHONE_PREFIXES = {
    "美国": ["+1", "1"],
    "欧盟": ["+32", "+33", "+34", "+39", "+31", "+49", "+43", "+41", "+44"],
    "德国": ["+49", "49"],
    "英国": ["+44", "44"],
    "法国": ["+33", "33"],
    "意大利": ["+39", "39"],
    "西班牙": ["+34", "34"],
    "加拿大": ["+1", "1"],
    "澳大利亚": ["+61", "61"],
    "日本": ["+81", "81"],
    "韩国": ["+82", "82"],
    "印度": ["+91", "91"],
    "俄罗斯": ["+7", "7"],
    "土耳其": ["+90", "90"],
    "波兰": ["+48", "48"],
    "墨西哥": ["+52", "52"],
    "巴西": ["+55", "55"],
    "东南亚": ["+65", "+66", "+60", "+84", "+62", "+63"],
    "中东": ["+971", "+966", "+965", "+974", "+968"],
    "南非": ["+27", "27"],
}


def _validate_email_quality(email: str, base_domain: str = "") -> Dict[str, any]:
    """
    验证邮箱质量，返回质量评级和类型。
    返回: {"is_valid": bool, "quality": "high"|"medium"|"low", "type": "company"|"free"|"generic"}
    """
    email = email.lower().strip()
    parts = email.split("@")
    if len(parts) != 2:
        return {"is_valid": False, "quality": "low", "type": "invalid"}
    
    domain = parts[1]
    
    # 检查是否免费邮箱
    if domain in FREE_EMAIL_DOMAINS:
        return {"is_valid": True, "quality": "medium", "type": "free"}
    
    # 检查是否公司域名邮箱（与网站域名匹配）
    if base_domain and base_domain in domain:
        return {"is_valid": True, "quality": "high", "type": "company"}
    
    # 其他域名（可能是公司域名）
    if domain.endswith(".com") or domain.endswith(".de") or domain.endswith(".fr") or domain.endswith(".uk") or domain.endswith(".co") or domain.endswith(".net") or domain.endswith(".org"):
        return {"is_valid": True, "quality": "high", "type": "company"}
    
    return {"is_valid": True, "quality": "medium", "type": "generic"}


def _validate_phone_market(phone: str, target_market: str) -> Dict[str, any]:
    """
    验证电话号码是否可能属于目标市场。
    返回: {"is_valid": bool, "likely_market": str, "normalized": str}
    """
    normalized = re.sub(r"[^\d+]", "", phone)
    
    # 基础长度检查
    if len(normalized) < 7 or len(normalized) > 15:
        return {"is_valid": False, "likely_market": "", "normalized": normalized}
    
    # 检查区号匹配
    expected_prefixes = MARKET_PHONE_PREFIXES.get(target_market, [])
    matches = any(normalized.startswith(prefix) or normalized.startswith(prefix.lstrip("+")) for prefix in expected_prefixes)
    
    if matches:
        return {"is_valid": True, "likely_market": target_market, "normalized": normalized}
    
    # 如果没有匹配到目标市场区号，也可能是有效的（比如本地号码不带区号）
    return {"is_valid": True, "likely_market": "", "normalized": normalized}




def _fetch_page(url: str, timeout: int = 15, max_retries: int = 2) -> Optional[str]:
    """抓取网页内容，带重试和宽松的 HTML 检测"""
    for attempt in range(max_retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            # 宽松检查：只要内容看起来像 HTML 就处理
            text = resp.text
            if "<html" in text[:2000].lower() or "<!doctype" in text[:2000].lower():
                return text
            # content-type 明确是 HTML 也处理
            ct = resp.headers.get("content-type", "").lower()
            if "text/html" in ct or "application/xhtml" in ct:
                return text
            logger.debug(f"非HTML内容，跳过 [{url}] content-type={ct}")
            return None
        except Exception as e:
            if attempt < max_retries:
                logger.debug(f"抓取失败，重试 [{url}] attempt={attempt+1}: {e}")
                time.sleep(2 * (attempt + 1))
            else:
                logger.debug(f"抓取失败（已重试）[{url}]: {e}")
                return None
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
    priority_patterns = ["info@", "contact@", "sales@", "hello@", "enquiry@", "inquiry@", "buy@", "procure@", "export@", "business@", "marketing@", "ceo@", "director@", "manager@"]

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


def _extract_company_info(soup: BeautifulSoup, base_url: str) -> Dict:
    """提取公司信息：名称、地址、简介、行业等"""
    info = {
        "company_name": "",
        "address": "",
        "industry": "",
        "description": "",
    }
    
    # 公司名：尝试从 title、logo alt、schema.org 中提取
    title = soup.find("title")
    if title:
        info["company_name"] = title.get_text(strip=True).split("|")[0].split("-")[0].strip()[:100]
    
    # 地址：寻找包含 "address", "location", "headquarters" 的元素
    for tag in soup.find_all(["div", "p", "span"]):
        text = tag.get_text(strip=True, separator=" ")
        if any(kw in text.lower() for kw in ["address", "headquarters", "location", "office"]):
            if len(text) > 20 and len(text) < 200:
                info["address"] = text
                break
    
    # 行业
    for tag in soup.find_all(["div", "p", "span"]):
        text = tag.get_text(strip=True, separator=" ")
        if any(kw in text.lower() for kw in ["industry", "sector", "business type"]):
            if len(text) > 10 and len(text) < 100:
                info["industry"] = text
                break
    
    return info


def _find_priority_pages(soup: BeautifulSoup, base_url: str) -> List[str]:
    """
    从首页HTML中找出优先级高的内页链接。
    优先级：Contact > About > Team > Products > Services > Locations
    返回绝对URL列表。
    """
    links = []
    seen = set()
    
    priority_patterns = [
        # (关键词正则, 权重)
        (r"contact|contact us|get in touch|reach us|inquiry|enquiry|quote", 10),
        (r"about|about us|company|our company|who we are|overview", 8),
        (r"team|our team|management|leadership|directors|executives", 7),
        (r"product|products|our products|catalog|catalogue|range", 6),
        (r"service|services|solutions|offering|what we do", 5),
        (r"location|locations|offices|headquarters|address|find us", 4),
        (r"partner|partners|distributor|distribution|dealer|reseller", 3),
        # 阿拉伯语关键词（中东地区）
        (r"اتصل بنا|معلومات الاتصال|تواصل معنا", 10),   # 联系我们
        (r"من نحن|عن الشركة|نبذة عنا|عن المؤسسة", 8),       # 关于我们
        (r"فريق العمل|الإدارة|القادة|مجلس الإدارة", 7),        # 团队/管理层
        (r"منتجاتنا|المنتجات|كتالوج|منتجات", 6),             # 产品
        (r"العنوان|الموقع|مقر الشركة|فروعنا", 4),             # 地址/位置
    ]
    
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = a.get_text(strip=True, separator=" ")
        if not href or href.startswith("#") or href.startswith("javascript"):
            continue
        
        # 构建绝对URL
        full_url = href if href.startswith("http") else base_url.rstrip("/") + "/" + href.lstrip("/")
        
        # 避免重复和外部链接
        if full_url in seen:
            continue
        domain = base_url.split("/")[2] if "/" in base_url else base_url
        if domain not in full_url:
            continue
        seen.add(full_url)
        
        # 计算权重
        weight = 0
        combined = f"{text} {href}".lower()
        for pattern, w in priority_patterns:
            if re.search(pattern, combined, re.I):
                weight = max(weight, w)
        
        if weight > 0:
            links.append((weight, full_url))
    
    # 按权重排序，高权重在前
    links.sort(key=lambda x: x[0], reverse=True)
    return [url for _, url in links]


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


def _try_common_contact_paths(base_url: str, lead: Dict, timeout: int) -> None:
    """
    主动探测常见联系页面（/contact、/about 等），
    当首页没拿到邮箱时补充抓取。
    直接修改 lead dict（in-place）。
    """
    common_paths = [
        "/contact", "/contact-us", "/get-in-touch", "/reach-us", "/inquiry", "/enquiry",
        "/about", "/about-us", "/company", "/who-we-are",
        "/team", "/our-team", "/leadership",
        "/products", "/catalog", "/catalogue",
    ]
    base = base_url.rstrip("/")
    for path in common_paths:
        test_url = base + path
        page_html = _fetch_page(test_url, timeout)
        if not page_html:
            continue
        new_emails = _extract_emails(page_html)
        # 同时检查 mailto: 链接
        try:
            ps = BeautifulSoup(page_html, "html.parser")
            for a in ps.find_all("a", href=True):
                hr = a["href"]
                if hr.lower().startswith("mailto:"):
                    em = hr[7:].split("?")[0].strip()
                    if em and "@" in em and "." in em.split("@")[-1]:
                        new_emails.append(em)
        except Exception:
            pass

        if new_emails:
            base_domain = base_url.split("/")[2] if "/" in base_url else ""
            validated = []
            for e in set(new_emails):
                v = _validate_email_quality(e, base_domain)
                if v["is_valid"]:
                    validated.append(e)
            if validated:
                lead["emails"] = list(set(lead.get("emails", []) + validated))
                lead["email_quality"] = "high" if any(
                    "@" in e and base_domain in e for e in validated
                ) else lead.get("email_quality", "medium")
                lead["scraped"] = True
                # 顺便抓电话
                new_phones = _extract_phones(page_html)
                if new_phones:
                    lead["phones"] = list(set(lead.get("phones", []) + new_phones))
                logger.debug(f"常见路径命中: {test_url}")
                break
        time.sleep(1)


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

    # 初始失败 → 尝试替代 URL（http/https 互换、www 互换）
    if not html:
        alt_urls = []
        if url.startswith("https://"):
            alt_urls.append(url.replace("https://", "http://"))
        elif url.startswith("http://"):
            alt_urls.append(url.replace("http://", "https://"))
        if "://www." in url:
            alt_urls.append(url.replace("://www.", "://", 1))
        elif "://" in url and "www." not in url:
            alt_urls.append(url.replace("://", "://www.", 1))
        for alt in alt_urls:
            html = _fetch_page(alt, config.SCRAPE_TIMEOUT)
            if html:
                url = alt
                logger.debug(f"替代URL成功: {alt}")
                break

    if not html:
        return lead

    try:
        soup = BeautifulSoup(html, "html.parser")

        # 提取联系方式（正文正则）
        emails = _extract_emails(html)
        phones = _extract_phones(html)

        # 新增：首页没拿到邮箱，主动探测常见联系页面
        if not emails:
            _try_common_contact_paths(url, lead, config.SCRAPE_TIMEOUT)

        # 新增：从 mailto: 链接提取邮箱
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().startswith("mailto:"):
                email = href[7:].split("?")[0].split("<")[0].strip()
                if email and "@" in email and "." in email.split("@")[-1]:
                    emails.append(email)

        # 新增：从 tel: 链接提取电话
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().startswith("tel:"):
                phone = re.sub(r"[^\d\s\-+().extEXT]", "", href[4:]).strip()
                if phone:
                    phones.append(phone)

        # 提取公司信息
        company_info = _extract_company_info(soup, url)

        # 提取社交媒体
        social = _extract_social_links(soup, url)

        # 验证邮箱质量
        base_domain = url.split("/")[2] if "/" in url else ""
        validated_emails = []
        email_quality = ""
        for e in emails:
            v = _validate_email_quality(e, base_domain)
            if v["is_valid"]:
                validated_emails.append(e)
                if v["quality"] == "high":
                    email_quality = "high"
                elif v["quality"] == "medium" and email_quality != "high":
                    email_quality = "medium"
        
        # 验证电话（目标市场匹配）
        validated_phones = []
        phone_match_market = False
        for p in phones:
            pv = _validate_phone_market(p, target_market="")
            if pv["is_valid"]:
                validated_phones.append(p)
        
        # 更新 lead
        lead.update({
            "emails": validated_emails,
            "phones": validated_phones,
            "email_quality": email_quality,
            "description": company_info.get("description", ""),
            "company_name": company_info.get("company_name", ""),
            "address": company_info.get("address", ""),
            "industry": company_info.get("industry", ""),
            "social": social,
            "scraped": True,
        })

        # 如果首页没找到邮箱，尝试更多页面（About/Contact/Team/Products/Partners）
        if not validated_emails:
            priority_links = _find_priority_pages(soup, url)
            for link in priority_links[:5]:  # 最多试5个（扩展）
                page_html = _fetch_page(link, config.SCRAPE_TIMEOUT)
                if page_html:
                    new_emails = _extract_emails(page_html)
                    # 验证新邮箱
                    new_validated = []
                    for e in new_emails:
                        v = _validate_email_quality(e, base_domain)
                        if v["is_valid"]:
                            new_validated.append(e)
                            if v["quality"] == "high":
                                email_quality = "high"
                    if new_validated:
                        lead["emails"] = new_validated
                        lead["email_quality"] = email_quality
                        # 也从 contact 页面抓电话
                        new_phones = _extract_phones(page_html)
                        new_validated_phones = [p for p in new_phones if _validate_phone_market(p, "").get("is_valid")]
                        if new_validated_phones:
                            lead["phones"] = new_validated_phones
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

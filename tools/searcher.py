"""
tools/searcher.py
多源搜索工具 - 寻找潜在进口商/分销商
支持：DuckDuckGo Web搜索、商业目录搜索、海关数据、展会数据
"""

import time
import logging
from typing import List, Dict, Optional
from ddgs import DDGS
import config

logger = logging.getLogger(__name__)

# ============ 域名过滤配置 ============

EXCLUDED_DOMAINS = {
    # B2B平台（我们是供应商，不需要找其他供应商）
    "alibaba.com", "alibaba.ru", "1688.com", "made-in-china.com",
    "globalsources.com", "tradekey.com", "ec21.com", "exportpages.com",
    "diytrade.com", "b2b.baidu.com", "b2b168.com", "dhgate.com",
    "hkc22.com", "szb2b.com", "b2bmate.com",
    # 电商/零售平台（非B2B采购）
    "amazon.com", "amazon.co", "ebay.com", "aliexpress.com",
    "walmart.com", "target.com", "costco.com", "bestbuy.com",
    "tmall.com", "jd.com", "taobao.com",
    # 社媒/视频（非商业采购）
    "youtube.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "reddit.com", "quora.com", "pinterest.com",
    "weibo.com", "douyin.com",
    # 新闻/博客/论坛（非商业采购）
    "wikipedia.org", "news", "blog", "forum", "bbs",
    "wordpress.com", "medium.com", "blogspot.com", "ghost.io",
    # 中文无关站
    "baike.baidu.com", "zhihu.com",
    "sohu.com", "sina.com.cn", "163.com", "ifeng.com",
    "csdn.net", "oschina.net",
    # 政府/教育站点
    "gov.cn", "edu.cn",
    # 招聘/分类信息
    "indeed.com", "glassdoor.com", "monster.com", "51job.com", "zhaopin.com",
    "craigslist.org", "kijiji.ca",
    # LinkedIn 单独搜，Web里排除
    "linkedin.com",
}

# 高价值域名白名单：这些站点的结果直接保留，不做关键词过滤
GOOD_DOMAINS = {
    # 商业目录（高质量B2B）
    "kompass.com", "europages.com", "thomasnet.com",
    "importgenius.com", "tradesns.com", "cnlist.com",
    "fibre2fashion.com", "textileinfomedia.com",
    "go4worldbusiness.com", "tradeindia.com",
    # 展会/协会
    "10times.com", "eventbrite.com", "expopromoter.com",
    # 海关数据相关
    "zauba.com", "seair.co.in", "volgosa.com",
    # 黄页/商业目录
    "yellowpages.com", "yell.com", "paginasamarillas.com",
}

# 标题/Snippet 包含以下关键词的，优先保留（宽松匹配，非强制）
PRIORITY_KEYWORDS = [
    "importer", "import", "distributor", "distribution", "wholesale", "wholesaler",
    "dealer", "reseller", "supplier", "vendor", "buyer", "purchasing", "procurement",
    "trading", "trade", "export", "exports", "b2b", "distribute",
    "distribuidor", "importador", "mayorista",  # 西班牙语
    "进口", "进口商", "分销", "分销商", "经销商", "批发商", "采购", "供应商",
    "importador", "distribuidor", "revendedor",  # 葡萄牙语
    "grossiste", "importateur", "distributeur",  # 法语
    "großhändler", "importeur", "distributor",  # 德语
]

# 仅当标题/Snippet 包含这些"非商业"信号时才排除（比 REQUIRED_KEYWORDS 更宽松）
JUNK_SIGNALS = [
    "job", "career", "hiring", "salary", "resume", "cv",
    "招聘", "简历", "求职", "人才",
    "login", "sign up", "register", "password",
    "news", "article", "blog", "post",
]


# ============ 搜索 Query 构建 ============

def _build_search_queries(
    product: str,
    target_market: str,
    buyer_type: str = "importer",
) -> List[str]:
    """
    构建多维度搜索query，覆盖不同搜索意图。
    新增：海关数据、展会exhibitor、行业协会、B2B目录等来源。
    """
    market_suffix = config.MARKET_KEY_WORDS.get(target_market, target_market)

    queries = [
        # 核心：直接找进口商/分销商
        f'{product} {buyer_type} {market_suffix} "contact" "email"',
        f'{product} distributor {market_suffix} wholesale -alibaba -made-in-china',
        f'{product} import company {market_suffix} "looking for supplier"',
        f'{product} procurement {market_suffix} -retail -amazon',
        # 公司目录类（高意向）
        f'"{product}" {market_suffix} company "import" OR "distribute" "email"',
        f'"{product}" {market_suffix} "buyer" OR "purchasing" -blog -news',
        # 海关数据 / 展会 exhibitor（高价值）
        f'{product} {market_suffix} "customs data" importer OR "bill of lading"',
        f'{product} {market_suffix} trade show exhibitor "contact"',
        f'{product} {market_suffix} "exporter" OR "supplier" directory',
        # 行业目录
        f'site:kompass.com "{product}" {market_suffix}',
        f'site:europages.com "{product}" {market_suffix}',
        f'site:thomasnet.com "{product}" {market_suffix}',
    ]

    # 中文query（针对东南亚/中东/南美/非洲市场）
    if target_market in ["东南亚", "中东", "南美", "非洲"]:
        queries.append(f'{product} 进口商 {market_suffix} "联系方式"')
        queries.append(f'{product} 分销商 {market_suffix} 采购')
        queries.append(f'{product} 批发市场 {market_suffix}')

    # 西班牙语市场
    if target_market in ["墨西哥", "南美", "巴西"]:
        queries.append(f'{product} importador {market_suffix} "contacto"')
        queries.append(f'{product} distribuidor {market_suffix} "email"')

    return queries


def _build_directory_queries(product: str, target_market: str) -> List[str]:
    """构建商业目录搜索 query"""
    market_suffix = config.MARKET_KEY_WORDS.get(target_market, target_market)
    return [
        f'site:kompass.com "{product}" {market_suffix}',
        f'site:europages.com "{product}" {market_suffix}',
        f'site:thomasnet.com "{product}" {market_suffix}',
        f'site:go4worldbusiness.com "{product}" {market_suffix}',
        f'site:tradeindia.com "{product}" {market_suffix}',
    ]


def _build_customs_queries(product: str, target_market: str) -> List[str]:
    """构建海关数据/贸易数据搜索 query"""
    market_suffix = config.MARKET_KEY_WORDS.get(target_market, target_market)
    return [
        f'"{product}" {market_suffix} "bill of lading" "importer"',
        f'"{product}" {market_suffix} customs import data "buyer"',
        f'site:importgenius.com "{product}" {market_suffix}',
        f'site:tradesns.com "{product}"',
        f'{product} {market_suffix} "import records" "buyer"',
    ]


def _build_tradeshow_queries(product: str, target_market: str) -> List[str]:
    """构建展会 exhibitor 搜索 query"""
    market_suffix = config.MARKET_KEY_WORDS.get(target_market, target_market)
    return [
        f'{product} {market_suffix} "trade show" exhibitor "contact"',
        f'{product} {market_suffix} "exhibition" exhibitor list',
        f'{product} {market_suffix} "trade fair" "buyer" OR "visitor"',
        f'site:10times.com "{product}" {market_suffix}',
        f'{product} {market_suffix} "expo" exhibitor directory',
    ]


# ============ 相关性过滤 ============

def _is_relevant(result: Dict, target_market: str = "") -> bool:
    """
    判断一条搜索结果是否与寻找潜在客户相关（宽松策略）。
    返回 True = 保留，False = 排除。
    策略：
      1. 域名黑名单 → 直接排除
      2. 域名白名单 → 直接保留
      3. 垃圾信号（招聘/登录/新闻）→ 排除
      4. 若目标市场是海外，排除明显的中文国内站点
      5. 其余均保留（关键词仅作优先级排序用，不过滤）
    """
    url = result.get("url", "").lower()
    title = result.get("title", "").lower()
    snippet = result.get("snippet", "").lower()
    combined = f"{title} {snippet}"

    # 1. 域名黑名单 → 排除
    for bad in EXCLUDED_DOMAINS:
        if bad in url:
            return False

    # 2. 域名白名单 → 直接保留
    for good in GOOD_DOMAINS:
        if good in url:
            return True

    # 3. 垃圾信号 → 排除（招聘/登录/新闻等无意义页面）
    for junk in JUNK_SIGNALS:
        if junk in combined:
            return False

    # 4. 若目标市场是海外，排除明显的中文国内站点
    overseas_markets = ["美国", "欧盟", "德国", "英国", "法国", "意大利", "加拿大",
                        "澳大利亚", "日本", "韩国", "印度", "俄罗斯", "土耳其", "波兰",
                        "墨西哥", "巴西", "东南亚", "中东", "南美", "非洲"]
    if target_market in overseas_markets:
        if ".cn" in url and not any(m in target_market for m in ["东南亚", "中国"]):
            return False

    # 5. 默认保留（关键词匹配仅影响排序，不过滤）
    return True


# ============ 去重 ============

def deduplicate_leads(leads: List[Dict]) -> List[Dict]:
    """基于URL去重"""
    seen = set()
    unique = []
    for lead in leads:
        url = lead.get("url", "").split("?")[0].rstrip("/")
        if url not in seen:
            seen.add(url)
            unique.append(lead)
    return unique


# ============ 通用搜索辅助 ============

def _search_with_ddgs(
    queries: List[str],
    max_per_query: int,
    source_label: str,
    target_market: str = "",
) -> List[Dict]:
    """通用 DDGS 搜索辅助函数，带相关性过滤"""
    results = []
    seen_urls = set()
    with DDGS() as ddgs:
        for query in queries:
            try:
                logger.info(f"[{source_label}] 搜索: {query}")
                search_results = list(ddgs.text(
                    query,
                    max_results=max_per_query,
                    region="wt-wt",
                ))
                for r in search_results:
                    url = r.get("href", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        item = {
                            "title": r.get("title", ""),
                            "url": url,
                            "snippet": r.get("body", ""),
                            "source": source_label,
                            "query": query,
                        }
                        if _is_relevant(item, target_market):
                            results.append(item)
                time.sleep(1)
            except Exception as e:
                logger.warning(f"[{source_label}] 搜索失败 [{query}]: {e}")
                continue
    logger.info(f"[{source_label}] 完成: 过滤后 {len(results)} 条")
    return results


# ============ 对外搜索接口 ============

def search_web(
    product: str,
    target_market: str,
    max_results: int = 50,
    buyer_type: str = "importer",
) -> List[Dict]:
    """
    执行Web搜索，返回潜在客户列表。
    每个结果: {title, url, snippet, source}
    max_results: 每个 query 最多返回的结果数（minimum 10）
    """
    queries = _build_search_queries(product, target_market, buyer_type)
    all_results = []
    seen_urls = set()

    # 每个 query 至少返回 10 条，或按 max_results 分配
    per_query = max(10, max_results // len(queries) + 5)

    with DDGS() as ddgs:
        for query in queries:
            try:
                logger.info(f"Web搜索: {query}")
                results = list(ddgs.text(
                    query,
                    max_results=per_query,
                    region="wt-wt",
                ))

                for r in results:
                    url = r.get("href", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        item = {
                            "title": r.get("title", ""),
                            "url": url,
                            "snippet": r.get("body", ""),
                            "source": "web_search",
                            "query": query,
                        }
                        if _is_relevant(item, target_market):
                            all_results.append(item)

                time.sleep(1)

            except Exception as e:
                logger.warning(f"Web搜索失败 [{query}]: {e}")
                continue

    logger.info(f"Web搜索完成: 原始 {len(seen_urls)} 条, 过滤后 {len(all_results)} 条")
    return all_results


def search_business_directories(
    product: str,
    target_market: str,
    max_results: int = 30,
) -> List[Dict]:
    """
    搜索商业目录（Kompass、Europages、ThomasNet等）
    这些是B2B目录，质量比普通搜索高。
    """
    queries = _build_directory_queries(product, target_market)
    per_query = max(10, max_results // len(queries) + 3)
    return _search_with_ddgs(queries, per_query, "business_directory", target_market)


def search_customs_and_tradeshow(
    product: str,
    target_market: str,
    max_results: int = 30,
) -> List[Dict]:
    """
    搜索海关数据和展会 exhibitor 名单（高意向来源）。
    包括：
      1. 海关进口记录（bill of lading 数据）
      2. 行业展会 exhibitor list
      3. 贸易数据平台（ImportGenius, TradeSNS等）
    """
    customs_queries = _build_customs_queries(product, target_market)
    tradeshow_queries = _build_tradeshow_queries(product, target_market)
    all_queries = customs_queries + tradeshow_queries

    per_query = max(8, max_results // len(all_queries) + 2)

    results = []
    seen_urls = set()
    with DDGS() as ddgs:
        for query in all_queries:
            try:
                logger.info(f"[customs/tradeshow] 搜索: {query}")
                search_results = list(ddgs.text(
                    query,
                    max_results=per_query,
                    region="wt-wt",
                ))
                for r in search_results:
                    url = r.get("href", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        item = {
                            "title": r.get("title", ""),
                            "url": url,
                            "snippet": r.get("body", ""),
                            "source": "customs_tradeshow",
                            "query": query,
                        }
                        if _is_relevant(item, target_market):
                            results.append(item)
                time.sleep(1)
            except Exception as e:
                logger.warning(f"[customs/tradeshow] 搜索失败 [{query}]: {e}")
                continue
    logger.info(f"[customs/tradeshow] 完成: 过滤后 {len(results)} 条")
    return results


def search_linkedin(
    product: str,
    target_market: str,
    max_results: int = 20,
) -> List[Dict]:
    """
    搜索 LinkedIn 相关的采购经理 / 进口商联系人。
    由于 LinkedIn 屏蔽搜索引擎爬虫，策略改为：
    - 搜索公司官网上标注的 LinkedIn 联系人
    - 搜索 "LinkedIn" + 职位 + 产品 + 市场
    """
    market_suffix = config.MARKET_KEY_WORDS.get(target_market, target_market)
    queries = [
        f'"{product}" {market_suffix} procurement manager linkedin',
        f'"{product}" {market_suffix} importer linkedin "contact"',
        f'"{product}" {market_suffix} purchasing director linkedin',
        f'"{product}" {market_suffix} buyer linkedin "email" OR "contact"',
    ]
    per_query = max(5, max_results // len(queries) + 2)
    return _search_with_ddgs(queries, per_query, "linkedin", target_market)


def search_social_media(
    product: str,
    target_market: str,
    max_results: int = 20,
) -> List[Dict]:
    """
    搜索 Facebook / Instagram 等社交媒体上的商家主页。
    由于社媒平台屏蔽爬虫，策略改为：
    - 搜索 "facebook page" + 产品 + 市场
    - 搜索 "instagram" + 产品 + 市场 + importer/distributor
    """
    market_suffix = config.MARKET_KEY_WORDS.get(target_market, target_market)
    queries = [
        f'"{product}" {market_suffix} "facebook page" importer OR distributor',
        f'"{product}" {market_suffix} instagram importer distributor',
        f'"{product}" {market_suffix} "facebook" wholesaler "contact"',
        f'"{product}" {market_suffix} social media business page importer',
    ]
    per_query = max(5, max_results // len(queries) + 2)
    return _search_with_ddgs(queries, per_query, "social_media", target_market)

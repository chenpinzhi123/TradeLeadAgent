"""
tools/searcher.py
多源搜索工具 - 寻找潜在进口商/分销商
支持：DuckDuckGo Web搜索、商业目录搜索
"""

import time
import logging
from typing import List, Dict, Optional
from ddgs import DDGS
import config

logger = logging.getLogger(__name__)


def _build_search_queries(
    product: str,
    target_market: str,
    buyer_type: str = "importer",
) -> List[str]:
    """
    构建多维度搜索query，覆盖不同搜索意图
    """
    market_suffix = config.MARKET_KEYWORDS.get(target_market, target_market)

    queries = [
        f'{product} {buyer_type} {market_suffix} "contact" "email"',
        f'{product} distributor {market_suffix} wholesale',
        f'{product} import company {market_suffix} "looking for supplier"',
        f'{product} procurement {market_suffix} -alibaba -made-in-china',
        f'site:linkedin.com {product} {market_suffix} procurement manager',
    ]

    # 中文query（针对东南亚/中东市场）
    if target_market in ["东南亚", "中东", "南美"]:
        queries.append(f'{product} 进口商 {market_suffix}')
        queries.append(f'{product} 供应商 寻找 {market_suffix}')

    return queries


def search_web(
    product: str,
    target_market: str,
    max_results: int = 20,
    buyer_type: str = "importer",
) -> List[Dict]:
    """
    执行Web搜索，返回潜在客户列表
    每个结果: {title, url, snippet, source}
    """
    queries = _build_search_queries(product, target_market, buyer_type)
    all_results = []
    seen_urls = set()

    with DDGS() as ddgs:
        for query in queries:
            try:
                logger.info(f"搜索: {query}")
                results = list(ddgs.text(
                    query,
                    max_results=max_results // len(queries) + 2,
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
                        if _is_relevant(item):
                            all_results.append(item)

                time.sleep(1)  # 避免限流

            except Exception as e:
                logger.warning(f"搜索失败 [{query}]: {e}")
                continue

    logger.info(f"Web搜索完成: 原始 {len(seen_urls)} 条, 过滤后 {len(all_results)} 条")
    return all_results

def search_business_directories(
    product: str,
    target_market: str,
    max_results: int = 10,
) -> List[Dict]:
    """
    搜索商业目录（Kompass、Europages等）
    这些是B2B目录，质量比普通搜索高
    """
    directory_queries = [
        f'site:kompass.com {product} {target_market}',
        f'site:europages.com {product} {target_market}',
        f'site:thomasnet.com {product} {target_market}',
    ]

    results = []
    seen_urls = set()

    with DDGS() as ddgs:
        for query in directory_queries:
            try:
                logger.info(f"目录搜索: {query}")
                search_results = list(ddgs.text(
                    query,
                    max_results=max_results // len(directory_queries) + 1,
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
                            "source": "business_directory",
                            "query": query,
                        }
                        if _is_relevant(item):
                            results.append(item)

                time.sleep(1)

            except Exception as e:
                logger.warning(f"目录搜索失败 [{query}]: {e}")
                continue

    logger.info(f"目录搜索完成: 过滤后 {len(results)} 条")
    return results


EXCLUDED_DOMAINS = {
    # B2B平台（我们是供应商，不需要找其他供应商）
    "alibaba.com", "alibaba.ru", "1688.com", "made-in-china.com",
    "globalsources.com", "tradekey.com", "ec21.com", "exportpages.com",
    "diytrade.com", "b2b.baidu.com", "b2b168.com",
    # 通用无关站点
    "youtube.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "reddit.com", "quora.com", "pinterest.com",
    "wikipedia.org", "wiki", "linkedin.com",  # LinkedIn/Social 单独搜，Web里排除
    "amazon.com", "amazon.co", "ebay.com", "aliexpress.com",
    "news", "blog", "forum", "bbs",
    # 中文无关站
    "baike.baidu.com", "zhihu.com", "weibo.com", "douyin.com",
    "sohu.com", "sina.com.cn", "163.com", "ifeng.com",
    "tmall.com", "jd.com", "taobao.com",
}

# 标题/Snippet 必须包含至少一个业务关键词，才算潜在客户
REQUIRED_KEYWORDS = [
    "importer", "import", "distributor", "distribution", "wholesale", "wholesaler",
    "dealer", "reseller", "supplier", "vendor", "buyer", "purchasing", "procurement",
    "trading", "trade", "export", "exports", "b2b", "distribute",
    " distribuidor", "importador", "mayorista",  # 西班牙语
    "进口", "进口商", "分销", "分销商", "经销商", "批发商", "采购", "供应商",
]


def _is_relevant(result: Dict) -> bool:
    """
    判断一条搜索结果是否与寻找潜在客户相关。
    排除已知无关域名，并要求标题或摘要包含业务关键词。
    """
    url = result.get("url", "").lower()
    title = result.get("title", "").lower()
    snippet = result.get("snippet", "").lower()

    # 1. 排除域名黑名单
    for bad in EXCLUDED_DOMAINS:
        if bad in url:
            return False

    # 2. 标题或摘要必须包含业务关键词（至少一个）
    combined = f"{title} {snippet}"
    if not any(kw in combined for kw in REQUIRED_KEYWORDS):
        return False

    return True


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


def _search_with_ddgs(queries: List[str], max_per_query: int, source_label: str) -> List[Dict]:
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
                        if _is_relevant(item):
                            results.append(item)
                time.sleep(1)
            except Exception as e:
                logger.warning(f"[{source_label}] 搜索失败 [{query}]: {e}")
                continue
    logger.info(f"[{source_label}] 完成: 过滤后 {len(results)} 条")
    return results


def search_linkedin(
    product: str,
    target_market: str,
    max_results: int = 10,
) -> List[Dict]:
    """
    搜索 LinkedIn 相关的采购经理 / 进口商联系人。
    由于 LinkedIn 屏蔽搜索引擎爬虫，策略改为：
    - 搜索公司官网上标注的 LinkedIn 联系人
    - 搜索 "LinkedIn" + 职位 + 产品 + 市场
    """
    market_suffix = config.MARKET_KEYWORDS.get(target_market, target_market)
    queries = [
        f'"{product}" {market_suffix} procurement manager linkedin',
        f'"{product}" {market_suffix} importer linkedin "contact"',
        f'"{product}" {market_suffix} purchasing director linkedin',
        f'"{product}" {market_suffix} buyer linkedin "email" OR "contact"',
    ]
    per_query = max(2, max_results // len(queries) + 1)
    return _search_with_ddgs(queries, per_query, "linkedin")


def search_social_media(
    product: str,
    target_market: str,
    max_results: int = 10,
) -> List[Dict]:
    """
    搜索 Facebook / Instagram 等社交媒体上的商家主页。
    由于社媒平台屏蔽爬虫，策略改为：
    - 搜索 "facebook page" + 产品 + 市场
    - 搜索 "instagram" + 产品 + 市场 + importer/distributor
    """
    market_suffix = config.MARKET_KEYWORDS.get(target_market, target_market)
    queries = [
        f'"{product}" {market_suffix} "facebook page" importer OR distributor',
        f'"{product}" {market_suffix} instagram importer distributor',
        f'"{product}" {market_suffix} "facebook" wholesaler "contact"',
        f'"{product}" {market_suffix} social media business page importer',
    ]
    per_query = max(2, max_results // len(queries) + 1)
    return _search_with_ddgs(queries, per_query, "social_media")

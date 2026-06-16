"""
tools/searcher.py
多源搜索工具 - 寻找潜在进口商/分销商
支持：DuckDuckGo Web搜索、商业目录搜索
"""

import time
import logging
from typing import List, Dict, Optional
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS
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
                        all_results.append({
                            "title": r.get("title", ""),
                            "url": url,
                            "snippet": r.get("body", ""),
                            "source": "web_search",
                            "query": query,
                        })

                time.sleep(1)  # 避免限流

            except Exception as e:
                logger.warning(f"搜索失败 [{query}]: {e}")
                continue

    logger.info(f"搜索完成，共找到 {len(all_results)} 条结果")
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
                        results.append({
                            "title": r.get("title", ""),
                            "url": url,
                            "snippet": r.get("body", ""),
                            "source": "business_directory",
                            "query": query,
                        })

                time.sleep(1)

            except Exception as e:
                logger.warning(f"目录搜索失败 [{query}]: {e}")
                continue

    return results


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
    """通用 DDGS 搜索辅助函数"""
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
                        results.append({
                            "title": r.get("title", ""),
                            "url": url,
                            "snippet": r.get("body", ""),
                            "source": source_label,
                            "query": query,
                        })
                time.sleep(1)
            except Exception as e:
                logger.warning(f"[{source_label}] 搜索失败 [{query}]: {e}")
                continue
    return results


def search_linkedin(
    product: str,
    target_market: str,
    max_results: int = 10,
) -> List[Dict]:
    """
    搜索 LinkedIn 上的采购经理 / 进口商联系人
    返回潜在客户列表
    """
    market_suffix = config.MARKET_KEYWORDS.get(target_market, target_market)
    queries = [
        f'site:linkedin.com/in {product} {market_suffix} procurement manager email',
        f'site:linkedin.com/in {product} {market_suffix} importer',
        f'site:linkedin.com/in {product} {market_suffix} purchasing manager',
        f'"{product}" {market_suffix} site:linkedin.com "contact" "email"',
    ]
    per_query = max(2, max_results // len(queries) + 1)
    return _search_with_ddgs(queries, per_query, "linkedin")


def search_social_media(
    product: str,
    target_market: str,
    max_results: int = 10,
) -> List[Dict]:
    """
    搜索 Facebook / Instagram 等社交媒体上的商家主页
    返回潜在客户列表
    """
    market_suffix = config.MARKET_KEYWORDS.get(target_market, target_market)
    queries = [
        f'site:facebook.com {product} {market_suffix} importer "contact us"',
        f'site:instagram.com {product} {market_suffix} distributor',
        f'{product} {market_suffix} facebook page importer distributor',
        f'"{product}" {market_suffix} "facebook.com" "email" OR "contact"',
    ]
    per_query = max(2, max_results // len(queries) + 1)
    return _search_with_ddgs(queries, per_query, "social_media")

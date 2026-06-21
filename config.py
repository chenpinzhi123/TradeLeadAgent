"""
TradeLeadAgent - 配置管理
支持多LLM后端，环境变量配置
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env（本地开发用）
load_dotenv(Path(__file__).parent / ".env")

# 判断是否在 Streamlit Cloud 上运行
try:
    import streamlit as st
    IS_STREAMLIT_CLOUD = True
except ImportError:
    IS_STREAMLIT_CLOUD = False


def get_secret(key: str, default: str = "") -> str:
    """优先从 Streamlit Cloud secrets 读取，否则 fallback 到环境变量"""
    if IS_STREAMLIT_CLOUD:
        try:
            # 先尝试从 st.secrets 读取
            value = st.secrets.get(key, "")
            if value:
                return str(value)
        except Exception:
            pass
    # fallback 到本地环境变量 / .env
    return os.getenv(key, default)


# ============ LLM 配置 ============
LLM_PROVIDER = get_secret("LLM_PROVIDER", "openai")  # openai / anthropic / none
LLM_MODEL = get_secret("LLM_MODEL", "gpt-4o-mini")
LLM_API_KEY = get_secret("LLM_API_KEY", "")
LLM_BASE_URL = get_secret("LLM_BASE_URL", "")  # 支持自定义 endpoint

# ============ 搜索配置 ============
MAX_SEARCH_RESULTS = int(get_secret("MAX_SEARCH_RESULTS", "10"))
SEARCH_TIMEOUT = int(get_secret("SEARCH_TIMEOUT", "15"))

# ============ 爬取配置 ============
SCRAPE_TIMEOUT = int(get_secret("SCRAPE_TIMEOUT", "10"))
MAX_PAGES_PER_LEAD = int(get_secret("MAX_PAGES_PER_LEAD", "3"))

# ============ 输出配置 ============
OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

# ============ 目标市场默认配置 ============
# 常见外贸目标市场搜索关键词后缀
MARKET_KEYWORDS = {
    "美国": "USA United States America",
    "欧盟": "Europe European Union EU",
    "德国": "Germany Deutsche",
    "英国": "UK United Kingdom Britain",
    "法国": "France French",
    "意大利": "Italy Italian Italia",
    "加拿大": "Canada Canadian",
    "澳大利亚": "Australia Australian",
    "日本": "Japan Japanese",
    "韩国": "South Korea Korean",
    "印度": "India Indian",
    "俄罗斯": "Russia Russian",
    "土耳其": "Turkey Turkish",
    "波兰": "Poland Polish",
    "墨西哥": "Mexico Mexican",
    "巴西": "Brazil Brazilian",
    "东南亚": "Southeast Asia ASEAN Thailand Vietnam Malaysia Singapore Indonesia",
    "中东": "Middle East UAE Saudi Arabia Dubai Qatar",
    "南美": "South America Brazil Argentina Chile Colombia",
    "非洲": "Africa Nigeria South Africa Egypt Kenya",
}

# 别名（兼容旧版 searcher.py 中 MARKET_KEY_WORDS 的拼写）
MARKET_KEY_WORDS = MARKET_KEYWORDS

# 进口商类型关键词（用于搜索过滤）
BUYER_KEYWORDS = [
    "importer", "distributor", "wholesaler", "buyer", "procurement",
    "trading company", "supply chain", "retailer", "reseller",
    "进口商", "分销商", "批发商", "采购", "贸易公司",
]

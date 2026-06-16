"""
tools/lead_scorer.py
LLM驱动的客户线索评分 + 优先级排序
评估维度：匹配度、采购能力、联系方式完整性、市场潜力
"""

import json
import logging
from typing import List, Dict, Optional
import config

logger = logging.getLogger(__name__)

# ============ 评分 Prompt 模板 ============
SCORING_PROMPT = """\
你是专业的B2B外贸客户评估专家。请对以下潜在客户进行评分（1-10分）。

【产品描述】
{product}

【目标市场】
{target_market}

【潜在客户信息】
公司名称: {company_name}
网站: {url}
简介: {description}
联系方式: {contact_info}
来源: {source}

请从以下4个维度评分（每项是1-10分），并给出总分和推荐理由：
1. 产品匹配度 - 该客户是否真正需要该产品
2. 采购能力 - 公司规模/网站专业度/是否有进口经验
3. 联系可行性 - 是否有有效联系方式
4. 市场潜力 - 该客户所在市场的潜力

以JSON格式输出：
{{
  "match_score": <1-10>,
  "capability_score": <1-10>,
  "contact_score": <1-10>,
  "market_score": <1-10>,
  "total_score": <加权平均, 1-10>,
  "priority": <"高"|"中"|"低">,
  "reason": "<100字以内的推荐理由>",
  "suggested_approach": "<接触建议，中英文均可>"
}}
"""

# ============ 无LLM时的模板评分 ============
def _template_score(lead: Dict) -> Dict:
    """无LLM时的降级评分（基于规则）"""
    score = 5  # 基础分

    # 有邮箱 +2
    if lead.get("emails"):
        score += 2
    # 有电话 +1
    if lead.get("phones"):
        score += 1
    # 有公司描述 +1
    if lead.get("description"):
        score += 1
    # 来源是商业目录 +1
    if lead.get("source") == "business_directory":
        score += 1
    # snippet里有 "importer"/"distributor" 等关键词 +1
    snippet = lead.get("snippet", "").lower()
    if any(kw in snippet for kw in ["importer", "distributor", "wholesale", "procurement"]):
        score += 1

    score = min(score, 10)
    priority = "高" if score >= 7 else ("中" if score >= 5 else "低")

    return {
        "match_score": score,
        "capability_score": score,
        "contact_score": score,
        "market_score": score,
        "total_score": score,
        "priority": priority,
        "reason": "基于规则自动评分（未使用LLM）",
        "suggested_approach": "发送产品目录和报价单",
    }


def score_lead(
    lead: Dict,
    product: str,
    target_market: str,
    llm_provider: str = "none",
) -> Dict:
    """
    对单个线索评分
    如果 llm_provider=="none"，使用模板评分
    """
    if llm_provider == "none" or not config.LLM_API_KEY:
        scoring = _template_score(lead)
        lead.update(scoring)
        return lead

    # 调用LLM
    prompt = SCORING_PROMPT.format(
        product=product,
        target_market=target_market,
        company_name=lead.get("title", ""),
        url=lead.get("url", ""),
        description=lead.get("description", "")[:500],
        contact_info=str(lead.get("emails", [])) + str(lead.get("phones", [])),
        source=lead.get("source", ""),
    )

    try:
        if llm_provider == "openai":
            result = _call_openai(prompt)
        elif llm_provider == "anthropic":
            result = _call_anthropic(prompt)
        else:
            result = None

        if result:
            scoring = json.loads(result)
        else:
            scoring = _template_score(lead)

    except Exception as e:
        logger.warning(f"LLM评分失败，使用模板评分: {e}")
        scoring = _template_score(lead)

    lead.update(scoring)
    return lead


def _call_openai(prompt: str) -> Optional[str]:
    """调用 OpenAI API"""
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL or None,
        )
        resp = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI调用失败: {e}")
        return None


def _call_anthropic(prompt: str) -> Optional[str]:
    """调用 Anthropic API"""
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=config.LLM_API_KEY)
        resp = client.messages.create(
            model=config.LLM_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text
    except Exception as e:
        logger.error(f"Anthropic调用失败: {e}")
        return None


def batch_score(
    leads: List[Dict],
    product: str,
    target_market: str,
) -> List[Dict]:
    """批量评分并排序"""
    llm_provider = config.LLM_PROVIDER if config.LLM_API_KEY else "none"

    scored = []
    for lead in leads:
        scored_lead = score_lead(lead, product, target_market, llm_provider)
        scored.append(scored_lead)

    # 按总分排序
    scored.sort(key=lambda x: x.get("total_score", 0), reverse=True)
    return scored

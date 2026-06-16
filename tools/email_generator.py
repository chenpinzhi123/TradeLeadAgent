"""
tools/email_generator.py
AI生成个性化开发信（Outreach Email）
支持中英文，根据客户类型调整语气和长度
"""

import logging
from typing import Dict, List, Optional
import config

logger = logging.getLogger(__name__)

# ============ 开发信 Prompt 模板 ============
EMAIL_GEN_PROMPT = """\
你是专业的B2B外贸开发信撰写专家。请根据以下信息，生成一封个性化的开发信。

【我方信息】
产品: {product}
公司优势: {company_strength}
目标市场: {target_market}

【对方信息】
公司名称: {company_name}
公司简介: {description}
评分/优先级: {priority}（高/中/低）
接触建议: {approach}

【要求】
1. 语言: {language}（中文 / English / Español）
2. 长度: 中文150-250字；英文120-180词；西班牙文120-180词
3. 语气: 专业、简洁、不推销感太强
4. 必须包含: 我是谁、为什么联系你、我能提供什么价值、明确的CTA（行动号召）
5. 不要使用"希望能和您合作"这类空话，要有具体价值点
6. 如果是高优先级客户，可以附上具体产品参数/案例；中低优先级则保持简洁

输出格式（JSON）:
{{
  "subject": "<邮件主题，吸引打开>",
  "body": "<邮件正文>",
  "follow_up": "<7天后的跟进邮件正文（可选）>"
}}
"""

# ============ 模板开发信（无LLM时使用）===========
EMAIL_TEMPLATES_ZH = {
    "高": """主题：关于{product}的供应合作机会

尊敬的采购负责人，

您好！我是中国{p Product}的生产供应商。通过{p source}了解到贵司在{p market}市场有相关业务。

我们的核心优势：
- 工厂直供，价格比贸易商低10-15%
- 已通过{standard}认证，出口{market}市场{Years}年
- 最小起订量灵活，支持OEM/ODM

如果您正在寻找新的供应商或需要比价，欢迎回复此邮件，我可以在24小时内提供：
✓ 产品目录和最新报价
✓ 同类客户案例
✓ 样品安排（DHL到付）

期待您的回复。

此致
{person_name}
{company_name_cn}
WhatsApp: {whatsapp}
""",
    "中": """主题：{product}工厂直供 - 中国供应商

您好，

我司专业生产{product}，主要出口{p Market}。

核心参数：
- 产能：{capacity}/月
- 认证：{Certification}
- 交期：{Delivery}

如您有采购需求，可随时联系。免费提供样品和报价单。

此致
{person_name}
""",
    "低": """主题：{product}供应商推介

您好，

我是中国{p Product}制造商，看到贵司网站，特来联系。

附上我们的产品目录供参考。如有需求，欢迎随时联系。

此致
{person_name}
""",
}

EMAIL_TEMPLATES_ES = {
    "高": """Asunto: Oportunidad de suministro de {product} - Fabricante directo en China

Estimado equipo de compras:

Espero que este correo les encuentre bien. Les escribo para presentar nuestras capacidades de fabricación de {product}. Identificamos su empresa a través de {source} y creemos que hay una gran compatibilidad.

Por qué considerarnos:
- Precios directos de fábrica (10-15% por debajo de comercantes)
- Certificados {Standard}, exportando a {market} desde hace {Years} años
- MOQ flexible, OEM/ODM soportado
- Muestras disponibles vía DHL (flete por cobrar)

Puedo proporcionar dentro de las 24 horas:
✓ Catálogo de productos y última cotización
✓ Clientes de referencia en su región
✓ Informe de auditoría de fábrica (si es necesario)

¿Estarían abiertos a una breve llamada de presentación o recibir nuestro catálogo?

Atentamente,
{person_name}
{company_name_en}
WhatsApp: {whatsapp}
""",
    "中": """Asunto: Fabricante de {product} - China Directo

Hola:

Fabricamos {product} y exportamos principalmente a {market}.

Especificaciones rápidas:
- Capacidad: {capacity}/mes
- Certificaciones: {Certification}
- Tiempo de entrega: {Delivery}

Si está buscando diversificar su base de proveedores o necesita una cotización, no dude en responder. Muestras gratuitas disponibles.

Atentamente,
{person_name}
""",
    "低": """Asunto: Introducción de proveedor de {product}

Hola:

Somos un fabricante de {product} con base en China. Llegué a su sitio web y pensé que podría haber una oportunidad de colaborar.

Adjunto está nuestro catálogo de productos para su referencia. Seré feliz de proporcionar una cotización si tiene requisitos específicos.

Atentamente,
{person_name}
""",
}

EMAIL_TEMPLATES_EN = {
    "高": """Subject: {product} Supply Opportunity - Direct from China Manufacturer

Dear Procurement Team,

Hope this email finds you well. I'm writing to introduce our {product} manufacturing capabilities. We identified your company through {source} and believe there's a strong mutual fit.

Why consider us:
- Direct factory pricing (10-15% below trading companies)
- {Standard} certified, exporting to {market} for {Years} years
- Flexible MOQ, OEM/ODM supported
- Sample available via DHL (freight collect)

I can provide within 24 hours:
✓ Product catalog & latest quotation
✓ Reference customers in your region
✓ Factory audit report (if needed)

Would you be open to a brief introduction call or receiving our catalog?

Best regards,
{person_name}
{company_name_en}
WhatsApp: {whatsapp}
""",
    "中": """Subject: {product} Manufacturer - China Direct

Hi,

We manufacture {product} and export primarily to {market}.

Quick specs:
- Capacity: {capacity}/month
- Certifications: {Certification}
- Lead time: {Delivery}

If you're looking to diversify your supplier base or need a quotation, feel free to reply. Free samples available.

Best regards,
{person_name}
""",
    "低": """Subject: {product} Supplier Introduction

Hi,

We're a {product} manufacturer based in China. Came across your website and thought there might be an opportunity to collaborate.

Attached is our product catalog for your reference. Happy to provide a quotation if you have specific requirements.

Best regards,
{person_name}
""",
}


def generate_email(
    lead: Dict,
    product: str,
    target_market: str,
    language: str = "auto",
    company_strength: str = "",
    sender_name: str = "",
    sender_company: str = "",
    whatsapp: str = "",
) -> Dict:
    """
    为单个线索生成开发信
    返回: {subject, body, follow_up}
    """
    # 自动判断语言
    if language == "auto":
        spanish_markets = ["墨西哥", "西班牙", "南美"]
        if target_market in ["中国", "东南亚", "中东"] or target_market in ["日本", "韩国"]:
            language = "zh"
        elif target_market in spanish_markets:
            language = "es"
        else:
            language = "en"

    # 尝试LLM生成
    if config.LLM_PROVIDER != "none" and config.LLM_API_KEY:
        email = _llm_generate(
            lead, product, target_market, language,
            company_strength, sender_name, sender_company, whatsapp,
        )
        if email:
            return email

    # 降级：使用模板
    return _template_generate(
        lead, product, target_market, language,
        sender_name, sender_company, whatsapp,
    )


def _llm_generate(
    lead: Dict, product: str, target_market: str, language: str,
    company_strength: str, sender_name: str, sender_company: str, whatsapp: str,
) -> Optional[Dict]:
    """调用LLM生成开发信"""
    prompt = EMAIL_GEN_PROMPT.format(
        product=product,
        company_strength=company_strength,
        target_market=target_market,
        company_name=lead.get("title", ""),
        description=lead.get("description", "")[:300],
        priority=lead.get("priority", "中"),
        approach=lead.get("suggested_approach", ""),
        language="中文" if language == "zh" else ("Español" if language == "es" else "English"),
    )

    try:
        if config.LLM_PROVIDER == "openai":
            from openai import OpenAI
            client = OpenAI(
                api_key=config.LLM_API_KEY,
                base_url=config.LLM_BASE_URL or None,
            )
            resp = client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            import json
            return json.loads(resp.choices[0].message.content)

        elif config.LLM_PROVIDER == "anthropic":
            from anthropic import Anthropic
            client = Anthropic(api_key=config.LLM_API_KEY)
            resp = client.messages.create(
                model=config.LLM_MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            import json
            return json.loads(resp.content[0].text)

    except Exception as e:
        logger.warning(f"LLM生成开发信失败: {e}")

    return None


def _template_generate(
    lead: Dict, product: str, target_market: str, language: str,
    sender_name: str, sender_company: str, whatsapp: str,
) -> Dict:
    """使用模板生成开发信"""
    priority = lead.get("priority", "中")

    # 简单占位符替换
    placeholders = {
        "{product}": product,
        "{market}": target_market,
        "{Market}": target_market,
        "{person_name}": sender_name,
        "{company_name_cn}": sender_company,
        "{company_name_en}": sender_company,
        "{whatsapp}": whatsapp,
        "{Product}": product,
        "{source}": lead.get("source", "行业目录"),
        "{standard}": "ISO9001",
        "{Standard}": "ISO9001",
        "{Certification}": "ISO9001, CE",
        "{Years}": "5",
        "{years}": "5",
        "{Delivery}": "15-30天",
        "{delivery}": "15-30 days",
        "{capacity}": "50000",
        "{Capacity}": "50,000",
    }

    if language == "zh":
        template = EMAIL_TEMPLATES_ZH.get(priority, EMAIL_TEMPLATES_ZH["中"])
    elif language == "es":
        template = EMAIL_TEMPLATES_ES.get(priority, EMAIL_TEMPLATES_ES["中"])
    else:
        template = EMAIL_TEMPLATES_EN.get(priority, EMAIL_TEMPLATES_EN["中"])

    body = template
    for k, v in placeholders.items():
        body = body.replace(k, str(v))

    # 提取主题行（支持中文/英文/西班牙文）
    first_line = body.split("\n")[0]
    for prefix in ["主题：", "Subject: ", "Asunto: "]:
        first_line = first_line.replace(prefix, "")
    subject_line = first_line.strip()

    return {
        "subject": subject_line,
        "body": body,
        "follow_up": "",
    }


def batch_generate_emails(
    leads: List[Dict],
    product: str,
    target_market: str,
    language: str = "auto",
    **kwargs,
) -> List[Dict]:
    """批量生成开发信"""
    results = []
    for lead in leads:
        email = generate_email(lead, product, target_market, language, **kwargs)
        lead["email_subject"] = email.get("subject", "")
        lead["email_body"] = email.get("body", "")
        lead["email_follow_up"] = email.get("follow_up", "")
        results.append(lead)
    return results

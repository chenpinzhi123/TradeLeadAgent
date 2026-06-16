"""
tools/promote_generator.py
推广内容生成器 —— 将用户信息注入到各渠道的推广文案中
支持渠道：LinkedIn 动态、Facebook 主页、商业目录提交、Twitter/X
"""

import logging
from typing import Dict
import config

logger = logging.getLogger(__name__)


def generate_promote_content(
    product: str,
    company: str,
    website: str,
    markets: list,
    channels: list,
    sender_name: str = "",
    whatsapp: str = "",
    company_strength: str = "",
    language: str = "auto",
) -> Dict[str, str]:
    """
    为每个渠道生成可一键复制的推广文案。

    返回: {channel_name: content_md, ...}
    """
    market_str = "、".join(markets) if markets else "全球"

    # 根据 language 参数决定文案语言
    lang_map = {
        "中文": "中文",
        "English": "English",
        "Español": "Spanish",
        "auto": None,   # 根据 markets 自动判断
    }
    target_lang = lang_map.get(language, None)

    results = {}

    if "LinkedIn动态" in channels:
        results["LinkedIn 动态"] = _gen_linkedin_post(
            product, company, website, market_str,
            sender_name, whatsapp, company_strength, target_lang
        )

    if "Facebook主页" in channels:
        results["Facebook 主页"] = _gen_facebook_post(
            product, company, website, market_str,
            sender_name, whatsapp, company_strength, target_lang
        )

    if "商业目录提交" in channels:
        results["商业目录提交（Kompass / Europages / ThomasNet）"] = _gen_directory_submission(
            product, company, website, market_str,
            sender_name, whatsapp, company_strength, target_lang
        )

    if "Twitter/X" in channels:
        results["Twitter / X"] = _gen_twitter_post(
            product, company, website, market_str,
            target_lang
        )

    return results


def _detect_language(markets: str) -> str:
    """根据目标市场推断语言"""
    if any(k in markets for k in ["中国", "台湾", "新加坡"]):
        return "中文"
    if any(k in markets for k in ["Spain", "西班牙", "拉美", "Mexico", "墨西哥", "Brazil", "巴西"]):
        return "Spanish"
    return "English"


def _gen_linkedin_post(product, company, website, markets,
                        sender_name, whatsapp, strength, lang) -> str:
    actual_lang = lang or _detect_language(markets)

    if actual_lang == "中文":
        return f"""
### 📢 LinkedIn 动态文案（中文）

---
**正文：**

{company or "我司"} 专注于 **{product}**，服务覆盖 {markets}。

✅ {strength or "优质产品，竞争力价格"}
✅ 支持小批量试单 & 快速发货
✅ 可提供 OEM / ODM 服务

如有采购需求，欢迎联系 👇
{"📱 WhatsApp: " + whatsapp if whatsapp else ""}
{"🌐 " + website if website else ""}

#贸易 #进出口 #{product.replace(" ", "")} #供应链

**（复制到 LinkedIn 发布，建议配上产品图片）**
---
"""

    if actual_lang == "Spanish":
        return f"""
### 📢 LinkedIn Post (Español)

---
**Body:**

We at **{company or "our company"}** specialize in **{product}**, serving clients in {markets}.

✅ {strength or "High quality products at competitive prices"}
✅ Small trial orders & fast shipping supported
✅ OEM / ODM services available

Contact us for a quote 👇
{"📱 WhatsApp: " + whatsapp if whatsapp else ""}
{"🌐 " + website if website else ""}

#trading #import #export #{product.replace(" ", "")} #supplychain

**(Copy and post on LinkedIn with product photos)**
---
"""

    # Default: English
    return f"""
### 📢 LinkedIn Post (English)

---
**Body:**

**{company or "Our company"}** is a trusted supplier of **{product}**, serving clients across {markets}.

✅ {strength or "High quality products at competitive prices"}
✅ Small trial orders & fast shipping supported
✅ OEM / ODM services available

Contact us for a quote 👇
{"📱 WhatsApp: " + whatsapp if whatsapp else ""}
{"🌐 " + website if website else ""}

#trading #import #export #{product.replace(" ", "")} #supplychain

**(Copy and post on LinkedIn with product photos)**
---
"""


def _gen_facebook_post(product, company, website, markets,
                        sender_name, whatsapp, strength, lang) -> str:
    actual_lang = lang or _detect_language(markets)

    if actual_lang == "中文":
        return f"""
### 📘 Facebook 主页文案（中文）

---
**帖子正文：**

🔔 {company or "我司"} 新品推广 🔔

我们主营 **{product}**，已服务 {markets} 多家进口商和分销商。

🌟 {strength or "品质保证，价格优势"}
🌟 支持定制包装 & 贴牌
🌟 7-15 天交货

📩 欢迎私信或 WhatsApp 联系：{whatsapp or "（请在后台设置联系方式）"}
{"🌐 官网：" + website if website else ""}

**（建议配图：产品实拍图 或 公司门头照片）**

**Facebook 主页设置建议：**
1. 在「简介」中填写公司名、产品关键词、联系方式
2. 在「行动按钮」设置"发送消息"或"访问网站"
3. 每周发布 2-3 条产品动态
---
"""

    if actual_lang == "Spanish":
        return f"""
### 📘 Facebook Page Post (Español)

---
**Post Body:**

🔔 **New Product Promotion** 🔔

We supply **{product}**, serving importers and distributors in {markets}.

🌟 {strength or "Quality assured, competitive pricing"}
🌟 Custom packaging & private labeling supported
🌟 7-15 days delivery

📩 Contact us on WhatsApp: {whatsapp or "(set contact in settings)"}
{"🌐 Website: " + website if website else ""}

**(Recommended image: product photos or company facade)**

**Facebook Page Setup Tips:**
1. Fill in company name, product keywords, contact info in "About"
2. Set "Send Message" or "Visit Website" as action button
3. Post 2-3 product updates per week
---
"""

    return f"""
### 📘 Facebook Page Post (English)

---
**Post Body:**

🔔 **New Product Promotion** 🔔

We at **{company or "our company"}** supply **{product}**, serving importers and distributors in {markets}.

🌟 {strength or "Quality assured, competitive pricing"}
🌟 Custom packaging & private labeling supported
🌟 7-15 days delivery

📩 Contact us on WhatsApp: {whatsapp or "(set contact in settings)"}
{"🌐 Website: " + website if website else ""}

**(Recommended image: product photos or company facade)**

**Facebook Page Setup Tips:**
1. Fill in company name, product keywords, contact info in "About"
2. Set "Send Message" or "Visit Website" as action button
3. Post 2-3 product updates per week
---
"""


def _gen_directory_submission(product, company, website, markets,
                              sender_name, whatsapp, strength, lang) -> str:
    actual_lang = lang or _detect_language(markets)

    if actual_lang == "中文":
        return f"""
### 📚 商业目录提交文案（可直接复制填写）

---
以下平台可免费提交公司信息，让海外买家主动找到你：

**1. Kompass（全球）**
- 网址：https://www.kompass.com
- 公司简介填写参考：
> {company or "我司"} —— {product} 专业供应商，服务 {markets} 市场。{strength or "提供高品质产品和有竞争力的价格。"}支持小批量试单。

**2. Europages（欧洲）**
- 网址：https://www.europages.co.uk
- 公司简介填写参考：
> We are a trusted supplier of {product}, serving clients in {markets}. {strength or "High quality, competitive price."} MOQ flexible.

**3. ThomasNet（北美）**
- 网址：https://www.thomasnet.com
- 公司简介填写参考（英文）：
> {company or "Our Company"} is a leading supplier of {product} in {markets}. Contact us for a quote.

**4. 中国制造网（Made-in-China.com）**
- 免费注册，上传产品，获取海外询盘

**统一联系方式模板：**
- 📱 WhatsApp: {whatsapp or "（填写你的 WhatsApp）"}
- 🌐 官网: {website or "（填写你的官网）"}
- 👤 联系人: {sender_name or "（填写你的姓名）"}

**（逐条复制到对应平台的公司简介栏，提交后等待审核）**
---
"""

    if actual_lang == "Spanish":
        return f"""
### 📚 Directorio Comercial - Textos para enviar (Español)

---
Plataformas donde puedes registrar tu empresa gratis:

**1. Kompass (Global)**
- URL: https://www.kompass.com
- Descripción sugerida:
> {company or "Nuestra empresa"} — proveedor profesional de {product}, sirviendo a {markets}. {strength or "Productos de alta calidad y precios competitivos."} MOQ flexible.

**2. Europages (Europa)**
- URL: https://www.europages.co.uk
- Descripción sugerida (inglés o español):
> Somos un proveedor confiable de {product} en {markets}.

**3. Directorios locales (según el mercado):**
- Para México: https://www.seccionamarilla.com.mx
- Para España: https://www.paginasamarillas.es

**Plantilla de contacto:**
- 📱 WhatsApp: {whatsapp or "(tu WhatsApp)"}
- 🌐 Sitio web: {website or "(tu sitio web)"}
- 👤 Contacto: {sender_name or "(tu nombre)"}

**(Copia y pega en el formulario de cada plataforma)**
---
"""

    # Default English
    return f"""
### 📚 Business Directory Submission Text (English)

---
Submit your company info to these platforms so overseas buyers can find you:

**1. Kompass (Global)**
- URL: https://www.kompass.com
- Suggested company description:
> {company or "Our Company"} — professional supplier of {product}, serving {markets}. {strength or "High quality products at competitive prices."} Flexible MOQ.

**2. Europages (Europe)**
- URL: https://www.europages.co.uk
- Suggested description:
> We are a trusted supplier of {product}, serving clients in {markets}. {strength or "High quality, competitive price."} MOQ flexible.

**3. ThomasNet (North America)**
- URL: https://www.thomasnet.com
- Suggested description:
> {company or "Our Company"} is a leading supplier of {product} in {markets}. Contact us for a quote.

**4. Made-in-China.com (China export platform)**
- Register for free, upload products, get overseas inquiries

**Unified contact template:**
- 📱 WhatsApp: {whatsapp or "(your WhatsApp)"}
- 🌐 Website: {website or "(your website)"}
- 👤 Contact: {sender_name or "(your name)"}

**(Copy and paste into each platform's company profile form, then wait for review)**
---
"""


def _gen_twitter_post(product, company, website, markets, lang) -> str:
    actual_lang = lang or _detect_language(markets)

    if actual_lang == "中文":
        return f"""
### 🐦 Twitter / X 推文文案（中文，280字符内）

---
**推文 1（产品推广）：**
> 🚢 {company or "我司"} 供应 **{product}**，服务 {markets} 多家分销商。高品质 / 有竞争力的价格 / 小批量可试单。联系我们 👇 {"🌐 " + website if website else ""} #{product.replace(" ", "")} #外贸 #进出口

**推文 2（信任背书）：**
> ✅ 已服务 {markets} 客户超过 X 家，{product} 月出口 XX 集装箱。可提供验厂报告。私信获取目录 📩 #{product.replace(" ", "")} #供应链

**推文 3（限时促销）：**
> 🎉 新客户首单享 __% 折扣！{product} 现货供应，7 天交货。WhatsApp 速联：{whatsapp or "（你的 WhatsApp）"} 🚀 #{product.replace(" ", "")} #促销

**（建议每天发 1 条，配合产品图片）**
---
"""

    if actual_lang == "Spanish":
        return f"""
### 🐦 Twitter / X Tweets (Español, under 280 chars)

---
**Tweet 1 (Product promo):**
> 🚢 We supply **{product}** to {markets}. High quality, competitive pricing, small trial orders welcome. Contact us 👇 {"🌐 " + website if website else ""} #{product.replace(" ", "")} #import #export

**Tweet 2 (Social proof):**
> ✅ Served {markets} clients with {product}. Factory audit reports available. DM for catalog 📩 #{product.replace(" ", "")} #supplychain

**(Post 1 per day with product photos)**
---
"""

    return f"""
### 🐦 Twitter / X Tweets (English, under 280 chars)

---
**Tweet 1 (Product promo):**
> 🚢 **{company or "We"}** supply **{product}** to {markets}. High quality, competitive pricing, small trial orders welcome. Contact us 👇 {"🌐 " + website if website else ""} #{product.replace(" ", "")} #import #export

**Tweet 2 (Social proof):**
> ✅ Served {markets} clients with {product}. Factory audit reports available. DM for catalog 📩 #{product.replace(" ", "")} #supplychain

**Tweet 3 (Limited offer):**
> 🎉 New client discount available! {product} in stock, 7-day delivery. WhatsApp: {whatsapp or "(your WhatsApp)"} 🚀 #{product.replace(" ", "")} #promo

**(Post 1 per day with product photos)**
---
"""

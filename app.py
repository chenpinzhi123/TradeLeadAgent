"""
TradeLeadAgent - 外贸客户线索搜索 Agent
Streamlit Web 界面
"""

import sys
import os
import time
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
from datetime import datetime

import config
from tools.searcher import (
    search_web, search_business_directories,
    search_linkedin, search_social_media,
    deduplicate_leads,
)
from tools.scraper import batch_scrape
from tools.lead_scorer import batch_score
from tools.email_generator import batch_generate_emails
from utils.helpers import setup_logging, export_to_excel, format_lead_card

setup_logging()

# ============ Session State 初始化 ============
if "target_market_key" not in st.session_state:
    # 用索引而非字符串，避免 key 不匹配
    st.session_state.target_market_key = 0   # 0 = 第一个市场
if "promote_myself" not in st.session_state:
    st.session_state.promote_myself = False

# ============ 页面配置 ============
st.set_page_config(
    page_title="TradeLeadAgent - 外贸客户线索搜索",
    page_icon="🌍",
    layout="wide",
)

# ============ 侧边栏 ============
with st.sidebar:
    st.title("🌍 TradeLeadAgent")
    st.caption("外贸客户线索智能搜索")

    st.divider()

    # LLM配置状态
    llm_status = "✅ 已配置" if config.LLM_API_KEY else "⚠️ 未配置（将使用模板模式）"
    st.info(f"LLM状态: {llm_status}")

    st.divider()

    # 关于
    with st.expander("ℹ️ 关于"):
        st.markdown("""
        **TradeLeadAgent** 帮助外贸商户寻找潜在客户。

        **工作流程：**
        1. 输入产品和目标市场
        2. 自动搜索潜在进口商/分销商（Web/目录/LinkedIn/社媒）
        3. 过滤无关结果，抓取联系方式
        4. AI评分 + 生成开发信
        5. 可选：生成推广文案（手动发布到社媒/目录）
        6. 导出Excel

        **数据源：** Web搜索 / 商业目录 / LinkedIn / 社交媒体（可选）
        **推广功能：** 生成可手动发布的文案，不会自动发布
        """)

# ============ 主界面 ============
st.title("🌍 外贸客户线索搜索 Agent")
st.caption("输入你的产品和目标市场，让AI帮你找客户")

# ============ 输入表单（所有控件在同一框架内）============
st.subheader("🔍 搜索条件")

# 第一行：产品 + 目标市场
col1, col2 = st.columns(2)

with col1:
    product = st.text_input(
        "🔧 产品名称 *",
        placeholder="例如：LED显示屏、不锈钢紧固件、光伏组件",
        help="尽量用目标市场的语言描述产品",
        key="product_input",
    )

    # 目标市场选择
    market_options = list(config.MARKET_KEYWORDS.keys()) + ["自定义"]
    target_market_sel = st.selectbox(
        "🎯 目标市场",
        options=market_options,
        index=0,
        key="target_market_key",
    )
    # 始终显示自定义输入框，disabled 状态动态切换
    custom_market = st.text_input(
        "✏️ 自定义目标市场",
        placeholder="例如：Brazil、France、Nigeria",
        disabled=(target_market_sel != "自定义"),
        help="仅当上方选择「自定义」时填写此栏",
    )
    # 最终目标市场
    final_target_market = custom_market.strip() if target_market_sel == "自定义" else target_market_sel

with col2:
    buyer_type = st.selectbox(
        "👥 客户类型",
        options=["importer", "distributor", "wholesaler", "retailer"],
        index=0,
        key="buyer_type",
    )
    max_results = st.slider("📊 搜索结果数量", 10, 50, 20, key="max_results")

    language = st.selectbox(
        "📧 开发信语言",
        options=["auto", "中文", "English", "Español"],
        index=0,
        help="auto：根据目标市场自动选择",
        key="language_sel",
    )

    data_sources = st.multiselect(
        "📡 数据源（可多选）",
        options=["Web搜索", "商业目录", "LinkedIn", "社交媒体"],
        default=["Web搜索", "商业目录", "LinkedIn", "社交媒体"],
        help="LinkedIn/社交媒体需要网络访问，可能增加搜索时间",
        key="data_sources",
    )

# ---- 发件人信息（用于生成开发信）----
st.divider()
st.subheader("✉️ 发件人信息（可选，用于生成开发信）")
col_a, col_b = st.columns(2)
with col_a:
    sender_name = st.text_input("你的姓名/公司联系人", "", key="sender_name")
    sender_company = st.text_input("公司名称", "", key="sender_company")
with col_b:
    whatsapp = st.text_input("WhatsApp（带国际区号）", "", key="whatsapp")
    company_strength = st.text_area("公司优势（一句话）", "", height=80, key="company_strength")

# ---- 推广我自己（表单外部，动态响应）----
st.divider()
promote_myself = st.checkbox(
    "🌟 同时生成推广文案（被动获客）",
    value=False,
    key="promote_myself",
    help="开启后，AI会生成可直接复制到 LinkedIn / Facebook / 商业目录 / Twitter 的文案，让买家主动找到你。不会自动发布。",
)

if promote_myself:
    with st.expander("📢 推广内容设置", expanded=True):
        st.caption("以下内容将用于生成推广文案。你需要手动复制文案到各平台发布，系统不会自动发布。")

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            promote_product = st.text_input(
                "推广产品/服务",
                value=product,
                placeholder="产品名称",
                key="promote_product",
            )
            promote_website = st.text_input(
                "公司网址",
                placeholder="https://www.yourcompany.com",
                key="promote_website",
            )
        with col_p2:
            _default_markets = [final_target_market] if final_target_market else []
            promote_markets = st.multiselect(
                "目标推广市场",
                options=list(config.MARKET_KEYWORDS.keys()) + ["自定义"],
                default=_default_markets,
                key="promote_markets",
            )
            promote_channels = st.multiselect(
                "推广渠道",
                options=["LinkedIn动态", "Facebook主页", "商业目录提交", "Twitter/X"],
                default=["LinkedIn动态", "商业目录提交"],
                key="promote_channels",
            )

# 搜索按钮（不在 form 内，直接触发）
submitted = st.button("🚀 开始搜索", use_container_width=True, type="primary")

# ============ 主逻辑 ============
if submitted:
    if not product:
        st.error("⚠️ 请输入产品名称")
        st.stop()

    if target_market_sel == "自定义" and not custom_market.strip():
        st.error("⚠️ 请在「自定义目标市场」中输入市场名称")
        st.stop()

    target_market = final_target_market

    # 步骤1: 搜索
    st.header("🔍 第1步：搜索潜在客户")
    progress = st.progress(0.0, text="正在搜索...")

    all_leads = []
    step_weight = 0.0
    total_sources = len(data_sources)

    # Web 搜索
    if "Web搜索" in data_sources:
        with st.spinner("正在从Web搜索潜在客户..."):
            web_results = search_web(product, target_market, max_results, buyer_type)
            step_weight += 0.2
            progress.progress(min(step_weight, 0.45), text=f"Web搜索完成，找到 {len(web_results)} 条")
            all_leads.extend(web_results)

    # 商业目录搜索
    if "商业目录" in data_sources:
        with st.spinner("正在搜索商业目录..."):
            dir_results = search_business_directories(product, target_market, max_results // 2)
            step_weight += 0.15
            progress.progress(min(step_weight, 0.45), text=f"目录搜索完成，找到 {len(dir_results)} 条")
            all_leads.extend(dir_results)

    # LinkedIn 搜索
    if "LinkedIn" in data_sources:
        with st.spinner("正在搜索 LinkedIn..."):
            linkedin_results = search_linkedin(product, target_market, max_results // 3)
            step_weight += 0.10
            progress.progress(min(step_weight, 0.45), text=f"LinkedIn搜索完成，找到 {len(linkedin_results)} 条")
            all_leads.extend(linkedin_results)

    # 社交媒体搜索
    if "社交媒体" in data_sources:
        with st.spinner("正在搜索社交媒体（Facebook/Instagram）..."):
            social_results = search_social_media(product, target_market, max_results // 3)
            step_weight += 0.10
            progress.progress(min(step_weight, 0.45), text=f"社交媒体搜索完成，找到 {len(social_results)} 条")
            all_leads.extend(social_results)

    all_leads = deduplicate_leads(all_leads)
    st.success(f"✅ 共找到 **{len(all_leads)}** 条潜在客户（已去重）")

    if not all_leads:
        st.warning("未找到结果，请尝试调整搜索关键词或目标市场")
        st.stop()

    # 预览搜索结果 — 按来源分组展示，全部可见（Streamlit dataframe 自带分页）
    with st.expander("👀 预览搜索结果（全部）", expanded=True):
        source_counts = {}
        for l in all_leads:
            source_counts[l.get("source", "unknown")] = source_counts.get(l.get("source", "unknown"), 0) + 1
        st.caption(f"📊 来源分布: {' | '.join(f'{k}: {v}' for k, v in source_counts.items())}")
        preview_data = [{"公司名称": l["title"], "网址": l["url"], "来源": l["source"], "搜索query": l.get("query", "")} for l in all_leads]
        st.dataframe(pd.DataFrame(preview_data), use_container_width=True, height=400)
        st.caption(f"共 {len(all_leads)} 条结果，可拖动表格右下角调整显示行数")

    progress.progress(0.5, text="开始抓取联系方式...")

    # 步骤2: 抓取联系方式
    st.header("📡 第2步：抓取联系方式")
    st.warning("⏳ 正在逐个访问网站抓取邮箱和电话，预计需要几分钟...")

    with st.spinner("抓取中..."):
        scraped_leads = batch_scrape(all_leads[:max_results])
        progress.progress(0.7, text="抓取完成")

    # 统计有联系方式的线索
    with_contact = [l for l in scraped_leads if l.get("emails") or l.get("phones")]
    st.success(f"✅ 抓取完成：**{len(with_contact)}/{len(scraped_leads)}** 条线索有联系方式")

    if with_contact:
        with st.expander("📧 有联系方式的线索", expanded=True):
            contact_data = [{
                "公司": l["title"],
                "邮箱": "; ".join(l.get("emails", [])),
                "电话": "; ".join(l.get("phones", [])),
            } for l in with_contact[:20]]
            st.dataframe(contact_data, use_container_width=True)

    progress.progress(0.8, text="AI评分中...")

    # 步骤3: AI评分
    st.header("🤖 第3步：AI评分 + 排序")
    with st.spinner("正在评分..."):
        scored_leads = batch_score(scraped_leads, product, target_market)
        progress.progress(0.9, text="评分完成")

    st.success("✅ 评分完成！")

    # 展示评分结果
    df = pd.DataFrame([{
        "优先级": "🔴" + l.get("priority", "") if l.get("priority") == "高" else ("🟡" + l.get("priority", "") if l.get("priority") == "中" else "🟢" + l.get("priority", "")),
        "评分": l.get("total_score", 0),
        "公司名称": l["title"],
        "邮箱": "; ".join(l.get("emails", [])),
        "电话": "; ".join(l.get("phones", [])),
        "推荐理由": l.get("reason", ""),
    } for l in scored_leads])

    st.dataframe(df, use_container_width=True, hide_index=True)

    progress.progress(0.95, text="生成开发信...")

    # 步骤4: 生成开发信
    if sender_name or config.LLM_API_KEY:
        st.header("✉️ 第4步：生成开发信")
        with st.spinner("正在生成个性化开发信..."):
            final_leads = batch_generate_emails(
                scored_leads,
                product,
                target_market,
                language=language,
                sender_name=sender_name,
                sender_company=sender_company,
                whatsapp=whatsapp,
                company_strength=company_strength,
            )
        st.success("✅ 开发信生成完成！")

        # 展示开发信
        for lead in final_leads[:5]:
            if lead.get("email_subject"):
                with st.expander(f"📧 {lead['title'][:40]}..."):
                    st.markdown(f"**主题:** {lead['email_subject']}")
                    st.markdown(f"**正文:**\n\n{lead['email_body']}")

    # 步骤4.5: 推广我自己
    if promote_myself and config.LLM_API_KEY:
        st.header("🌟 第4.5步：生成推广文案（被动获客）")
        st.caption("以下文案可直接复制到对应平台发布，让买家主动找到你。不会自动发布。")

        from tools.promote_generator import generate_promote_content

        promote_contents = generate_promote_content(
            product=promote_product or product,
            company=sender_company or "我司",
            website=promote_website,
            markets=promote_markets if promote_markets else [target_market],
            channels=promote_channels,
            sender_name=sender_name,
            whatsapp=whatsapp,
            company_strength=company_strength,
            language=language,
        )

        st.success(f"✅ 已生成 {len(promote_contents)} 个渠道的推广文案，复制后直接发布即可！")

        for channel, content in promote_contents.items():
            with st.expander(f"📢 {channel}", expanded=True):
                st.markdown(content)
                # 使用 st.code + 复制按钮让文案更易复制
                st_copy = st.text_area(f"复制区域: {channel}", value=content.strip(), height=200, label_visibility="collapsed")


    progress.progress(1.0, text="全部完成！")

    # 步骤5: 导出
    st.header("💾 导出结果")
    output_path = export_to_excel(scored_leads if 'final_leads' not in locals() else final_leads)

    with open(output_path, "rb") as f:
        st.download_button(
            label="📥 下载Excel文件",
            data=f,
            file_name=os.path.basename(output_path),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.balloons()
    st.success(f"🎉 全部完成！结果已保存到: `{output_path}`")

else:
    # 未提交时显示使用说明
    st.info("""
    👈 **开始使用：**
    1. 输入产品名称，选择目标市场（支持自定义）
    2. 选择数据源（Web/商业目录/LinkedIn/社交媒体，默认全选）
    3. 填写发件人信息（可选）
    4. 开启「生成推广文案」可生成社媒/目录推广内容（需手动复制发布）
    5. 点击「开始搜索」
    6. 下载Excel文件

    💡 **提示：** 配置 `.env` 文件中的 `LLM_API_KEY` 可启用AI评分和开发信生成
    """)

    # 展示功能亮点
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("### 🔍 智能搜索")
        st.caption("Web + 商业目录 + LinkedIn + 社媒")
    with col2:
        st.markdown("### 📧 自动抓取")
        st.caption("访问公司网站，自动提取邮箱和电话")
    with col3:
        st.markdown("### 🤖 AI赋能")
        st.caption("LLM评分 + 多语言开发信生成")
    with col4:
        st.markdown("### 🌟 推广助手")
        st.caption("生成社媒/目录内容，让客户找到你")

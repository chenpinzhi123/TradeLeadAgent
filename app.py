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

# ============ 页面配置 ============
st.set_page_config(
    page_title="TradeLeadAgent - 外贸客户线索搜索",
    page_icon="🌍",
    layout="wide",
)

# ============ Session State 初始化 ============
if "target_market_sel" not in st.session_state:
    st.session_state.target_market_sel = list(config.MARKET_KEYWORDS.keys())[0]
if "target_market_custom" not in st.session_state:
    st.session_state.target_market_custom = ""
if "data_sources" not in st.session_state:
    st.session_state.data_sources = ["Web搜索", "商业目录"]

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
        2. 自动搜索潜在进口商/分销商
        3. 抓取联系方式
        4. AI评分 + 生成开发信
        5. 导出Excel

        **数据源：** Web搜索 / 商业目录 / LinkedIn / 社交媒体（可选）
        """)

# ============ 主界面 ============
st.title("🌍 外贸客户线索搜索 Agent")
st.caption("输入你的产品和目标市场，让AI帮你找客户")

# ============ 目标市场选择（在表单外部，支持动态切换）============
st.subheader("🎯 目标市场")
col_m1, col_m2 = st.columns([1, 2])
with col_m1:
    target_market_sel = st.selectbox(
        "选择目标市场",
        options=list(config.MARKET_KEYWORDS.keys()) + ["自定义"],
        index=0,
        key="target_market_sel",
        label_visibility="collapsed",
    )
with col_m2:
    if st.session_state.target_market_sel == "自定义":
        target_market_custom = st.text_input(
            "输入目标市场",
            value=st.session_state.target_market_custom,
            placeholder="例如：Brazil、France、Nigeria",
            key="target_market_custom",
            label_visibility="collapsed",
        )
    else:
        st.markdown("")  # 占位，保持布局

# 最终使用的目标市场
final_target_market = (
    st.session_state.target_market_custom.strip()
    if st.session_state.target_market_sel == "自定义"
    else st.session_state.target_market_sel
)

# ============ 输入表单 ============
with st.form("search_form"):
    col1, col2 = st.columns(2)

    with col1:
        product = st.text_input(
            "🔧 产品名称",
            placeholder="例如：LED显示屏、不锈钢紧固件、光伏组件",
            help="尽量用目标市场的语言描述产品",
        )
        buyer_type = st.selectbox(
            "👥 客户类型",
            options=["importer", "distributor", "wholesaler", "retailer"],
            index=0,
        )
        max_results = st.slider("📊 搜索结果数量", 10, 50, 20)

    with col2:
        language = st.selectbox(
            "📧 开发信语言",
            options=["auto", "中文", "English", "Español"],
            index=0,
            help="auto：根据目标市场自动选择",
        )
        data_sources = st.multiselect(
            "📡 数据源（可多选）",
            options=["Web搜索", "商业目录", "LinkedIn", "社交媒体"],
            default=["Web搜索", "商业目录"],
            help="LinkedIn/社交媒体需要网络访问，可能增加搜索时间",
        )
        st.caption(f"当前目标市场：**{final_target_market}**")

    # 发件人信息（用于生成开发信）
    with st.expander("✉️ 发件人信息（可选，用于生成开发信）"):
        col_a, col_b = st.columns(2)
        with col_a:
            sender_name = st.text_input("你的姓名/公司联系人", "")
            sender_company = st.text_input("公司名称", "")
        with col_b:
            whatsapp = st.text_input("WhatsApp（带国际区号）", "")
            company_strength = st.text_area("公司优势（一句话）", "", height=80)

    submitted = st.form_submit_button("🚀 开始搜索", use_container_width=True)

# ============ 主逻辑 ============
if submitted:
    if not product:
        st.error("⚠️ 请输入产品名称")
        st.stop()

    if st.session_state.target_market_sel == "自定义" and not st.session_state.target_market_custom.strip():
        st.error("⚠️ 请在「自定义」中输入目标市场")
        st.stop()

    target_market = final_target_market

    # 步骤1: 搜索
    st.header("🔍 第1步：搜索潜在客户")
    progress = st.progress(0.0, text="正在搜索...")

    all_leads = []
    step_weight = 0.0

    # Web 搜索
    if "Web搜索" in data_sources:
        with st.spinner("正在从Web搜索潜在客户..."):
            web_results = search_web(product, target_market, max_results, buyer_type)
            step_weight += 0.2
            progress.progress(step_weight, text=f"Web搜索完成，找到 {len(web_results)} 条")
            all_leads.extend(web_results)

    # 商业目录搜索
    if "商业目录" in data_sources:
        with st.spinner("正在搜索商业目录..."):
            dir_results = search_business_directories(product, target_market, max_results // 2)
            step_weight += 0.15
            progress.progress(step_weight, text=f"目录搜索完成，找到 {len(dir_results)} 条")
            all_leads.extend(dir_results)

    # LinkedIn 搜索
    if "LinkedIn" in data_sources:
        with st.spinner("正在搜索 LinkedIn..."):
            linkedin_results = search_linkedin(product, target_market, max_results // 3)
            step_weight += 0.15
            progress.progress(step_weight, text=f"LinkedIn搜索完成，找到 {len(linkedin_results)} 条")
            all_leads.extend(linkedin_results)

    # 社交媒体搜索
    if "社交媒体" in data_sources:
        with st.spinner("正在搜索社交媒体（Facebook/Instagram）..."):
            social_results = search_social_media(product, target_market, max_results // 3)
            step_weight += 0.1
            progress.progress(step_weight, text=f"社交媒体搜索完成，找到 {len(social_results)} 条")
            all_leads.extend(social_results)

    all_leads = deduplicate_leads(all_leads)
    st.success(f"✅ 共找到 **{len(all_leads)}** 条潜在客户（已去重）")

    if not all_leads:
        st.warning("未找到结果，请尝试调整搜索关键词或目标市场")
        st.stop()

    # 预览搜索结果
    with st.expander("👀 预览搜索结果", expanded=True):
        preview_data = [{"公司名称": l["title"], "网址": l["url"], "来源": l["source"]} for l in all_leads[:10]]
        st.dataframe(preview_data, use_container_width=True)
        if len(all_leads) > 10:
            st.caption(f"...还有 {len(all_leads) - 10} 条结果")

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
    1. 选择目标市场（支持自定义输入）
    2. 输入产品名称
    3. 选择数据源（Web/商业目录/LinkedIn/社交媒体）
    4. 点击「开始搜索」
    5. 等待AI自动完成搜索、抓取、评分、生成开发信
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
        st.markdown("### 🌍 全球市场")
        st.caption("支持全球目标市场，含自定义")

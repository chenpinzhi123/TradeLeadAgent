"""
utils/helpers.py
辅助函数：数据导出、格式化、日志配置
"""

import logging
from pathlib import Path
from typing import List, Dict
import pandas as pd
import config


def setup_logging(level: str = "INFO"):
    """配置日志"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def leads_to_dataframe(leads: List[Dict]) -> pd.DataFrame:
    """
    将 leads 列表转换为 DataFrame，便于展示和导出
    """
    rows = []
    for lead in leads:
        rows.append({
            "优先级": lead.get("priority", ""),
            "评分": lead.get("total_score", 0),
            "公司名称": lead.get("title", ""),
            "网站": lead.get("url", ""),
            "邮箱": "; ".join(lead.get("emails", [])),
            "电话": "; ".join(lead.get("phones", [])),
            "公司简介": lead.get("description", "")[:200],
            "来源": lead.get("source", ""),
            "匹配度": lead.get("match_score", ""),
            "采购能力": lead.get("capability_score", ""),
            "推荐理由": lead.get("reason", ""),
            "接触建议": lead.get("suggested_approach", ""),
            "开发信主题": lead.get("email_subject", ""),
            "开发信正文": lead.get("email_body", ""),
        })
    return pd.DataFrame(rows)


def export_to_excel(leads: List[Dict], filename: str = "") -> str:
    """
    导出 leads 到 Excel，返回文件路径
    """
    if not filename:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"leads_{timestamp}.xlsx"

    output_path = config.OUTPUT_DIR / filename
    df = leads_to_dataframe(leads)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="潜在客户", index=False)

        # 自动调整列宽
        worksheet = writer.sheets["潜在客户"]
        for col in worksheet.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_len:
                        max_len = len(str(cell.value))
                except Exception:
                    pass
            worksheet.column_dimensions[col_letter].width = min(max_len + 2, 50)

    return str(output_path)


def format_lead_card(lead: Dict) -> str:
    """格式化单个 lead 为可读文本（用于Streamlit展示）"""
    lines = [
        f"**{lead.get('title', '未知公司')}**",
        f"🌐 网站: {lead.get('url', 'N/A')}",
    ]

    emails = lead.get("emails", [])
    if emails:
        lines.append(f"📧 邮箱: {', '.join(emails)}")

    phones = lead.get("phones", [])
    if phones:
        lines.append(f"📞 电话: {', '.join(phones)}")

    score = lead.get("total_score", 0)
    priority = lead.get("priority", "")
    lines.append(f"⭐ 评分: {score}/10 | 优先级: {priority}")

    reason = lead.get("reason", "")
    if reason:
        lines.append(f"💡 推荐理由: {reason}")

    desc = lead.get("description", "")
    if desc:
        lines.append(f"📝 简介: {desc[:150]}...")

    return "\n".join(lines)

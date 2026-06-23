# TradeLeadAgent - 长期项目记忆

## 项目概述
Streamlit 外贸客源获取工具，部署于 Streamlit Cloud。

## 核心模块
- `app.py` - Streamlit 前端
- `config.py` - 全局配置
- `tools/searcher.py` - 多渠道搜索（Web、商业目录、LinkedIn、海关/展会）
- `tools/scraper.py` - 网页抓取 + 邮箱/电话提取
- `tools/lead_scorer.py` - 潜在客户评分
- `tools/email_generator.py` - 邮件文案生成
- `tools/promote_generator.py` - 推广文案生成
- `tools/helpers.py` - 辅助函数
- `scripts/health_check.py` - 健康检查
- `scripts/auto_fix.py` - 自动修复
- `scripts/self_heal_loop.py` - 本地持续监控循环

## 关键技术决策
- **搜索量**：每 query 最少 10 条，max_results 滑块 10-200，默认 50
- **过滤策略**：白名单域名（Kompass/Europages/ThomasNet/ImportGenius）直接保留；排除 `.cn` 域名（非中文目标市场）；垃圾信号（招聘/登录/新闻）过滤
- **MARKET_KEYWORDS 命名**：`config.py` 定义 `MARKET_KEYWORDS`，`searcher.py` 使用 `getattr(config, "MARKET_KEY_WORDS", None) or getattr(config, "MARKET_KEYWORDS", {})` 双兼容
- **自修复体系**：双层架构（云端每小时 Automation + 本地 self_heal_loop.py）

## 踩坑经验
- `replace_in_file` 多次匹配时无法使用，需写临时 Python 脚本用正则批量替换
- PowerShell 复杂引号内联 Python 容易语法错误，尽量写临时 `.py` 文件执行
- Streamlit Cloud 部署报错时先检查本地能否复现，再排查环境差异（如 config 模块名是否被缓存）

## 用户偏好
- 偏好中文简洁输出，结论先行
- 授权词 "批准" 即允许 AI 自主执行
- 高确定性改动直接推进，无需逐行确认
- 审美要求高，图像任务需先自验证

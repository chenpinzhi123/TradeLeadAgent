# TradeLeadAgent 🌍

帮助外贸商户智能寻找潜在客户的 Agent 工具。

## 功能亮点

- 🔍 **多源搜索**：Web搜索 + 商业目录（Kompass、Europages等）
- 📧 **自动抓取**：访问公司网站，自动提取邮箱、电话、公司简介
- 🤖 **AI评分**：LLM驱动的线索评分和优先级排序（无LLM时自动降级为规则评分）
- ✉️ **开发信生成**：根据客户优先级生成个性化开发信（中英文）
- 💾 **Excel导出**：一键导出所有线索和开发信

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置（可选）

复制 `.env.template` 为 `.env`，填入你的LLM API Key（可选，不填也能用模板模式）：

```bash
cp .env.template .env
# 编辑 .env，填入 LLM_API_KEY
```

### 3. 运行

```bash
streamlit run app.py
```

然后在浏览器打开 `http://localhost:8501`

## 使用流程

1. 输入产品名称（如"LED显示屏"、"不锈钢紧固件"）
2. 选择目标市场（美国/欧盟/东南亚等）
3. 点击「开始搜索」
4. 等待AI完成：搜索 → 抓取 → 评分 → 生成开发信
5. 下载Excel文件

## 目录结构

```
TradeLeadAgent/
├── app.py                  # Streamlit主界面
├── config.py               # 配置管理
├── tools/
│   ├── searcher.py         # Web搜索工具
│   ├── scraper.py          # 联系方式抓取
│   ├── lead_scorer.py      # LLM线索评分
│   └── email_generator.py  # 开发信生成
├── utils/
│   └── helpers.py          # 辅助函数（导出等）
├── data/                   # 输出目录
└── requirements.txt
```

## 注意事项

- Web抓取有延迟（礼貌爬虫），搜索20个线索约需2-3分钟
- 无LLM API Key时，评分和开发信使用模板，效果较基础
- 建议配置OpenAI/Anthropic API Key以获得最佳效果

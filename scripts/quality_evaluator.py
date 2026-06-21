"""
scripts/quality_evaluator.py
质量评估引擎 - 模拟用户输入、评估 TradeLeadAgent 输出质量

核心能力：
1. 生成模拟用户输入（覆盖不同产品、市场、客户类型）
2. 运行完整搜索流程（不依赖 Streamlit UI）
3. 多维度评估输出质量
4. 生成结构化评估报告
"""

import json
import logging
import time
import sys
import os
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tools.searcher import (
    search_web, search_business_directories,
    search_customs_and_tradeshow, deduplicate_leads,
)
from tools.scraper import batch_scrape
from tools.lead_scorer import batch_score

logger = logging.getLogger(__name__)


# ============ 模拟用户输入数据集 ============

TEST_CASES = [
    # 产品, 目标市场, 客户类型, 期望结果特征
    {"product": "LED显示屏", "target_market": "美国", "buyer_type": "importer", "max_results": 30,
     "expected_traits": ["electronics", "display", "USA", "importer"]},
    {"product": "不锈钢紧固件", "target_market": "德国", "buyer_type": "distributor", "max_results": 30,
     "expected_traits": ["fastener", "stainless", "Germany", "distributor"]},
    {"product": "光伏组件", "target_market": "欧盟", "buyer_type": "wholesaler", "max_results": 30,
     "expected_traits": ["solar", "panel", "Europe", "wholesale"]},
    {"product": "瑜伽垫", "target_market": "东南亚", "buyer_type": "retailer", "max_results": 30,
     "expected_traits": ["yoga", "fitness", "Southeast Asia", "retail"]},
    {"product": "电动工具", "target_market": "巴西", "buyer_type": "distributor", "max_results": 30,
     "expected_traits": ["power tool", "Brazil", "distribuidor"]},
    {"product": "医疗器械", "target_market": "中东", "buyer_type": "importer", "max_results": 30,
     "expected_traits": ["medical", "device", "Middle East", "import"]},
    {"product": "智能家居", "target_market": "日本", "buyer_type": "distributor", "max_results": 30,
     "expected_traits": ["smart home", "Japan", "distributor"]},
    {"product": "服装", "target_market": "墨西哥", "buyer_type": "importer", "max_results": 30,
     "expected_traits": ["apparel", "clothing", "Mexico", "importador"]},
]


# ============ 评估维度与评分标准 ============

@dataclass
class QualityScore:
    """单个测试用例的质量评分"""
    test_case_id: int
    product: str
    target_market: str
    
    # 搜索质量 (0-25)
    result_count: int = 0           # 返回结果数量
    result_count_score: float = 0.0  # 数量评分 (期望至少10条)
    diversity_score: float = 0.0     # 来源多样性 (web/dir/customs/linkedin)
    relevance_score: float = 0.0   # 相关性 (标题/域名匹配度)
    search_quality: float = 0.0    # 搜索质量总分
    
    # 抓取质量 (0-25)
    scrape_success_rate: float = 0.0  # 成功抓取率
    contact_rate: float = 0.0         # 有联系方式的比例
    email_quality: float = 0.0        # 邮箱质量 (优先联系类邮箱)
    phone_quality: float = 0.0        # 电话质量
    scrape_quality: float = 0.0       # 抓取质量总分
    
    # 评分质量 (0-25)
    score_distribution: Dict = field(default_factory=dict)  # 高/中/低分布
    score_reasonableness: float = 0.0  # 评分是否合理
    top_lead_quality: float = 0.0      # 头部线索质量
    scoring_quality: float = 0.0       # 评分质量总分
    
    # 整体可用性 (0-25)
    actionable_leads: int = 0         # 可行动线索数 (有邮箱+评分>=5)
    overall_usability: float = 0.0    # 整体可用性
    
    total_score: float = 0.0          # 总分 (0-100)
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


# ============ 评估器核心 ============

class QualityEvaluator:
    """质量评估器：运行测试用例并生成质量报告"""
    
    def __init__(self, max_scrape: int = 15):
        self.max_scrape = max_scrape  # 每个用例最多抓取15条，控制耗时
        self.results: List[QualityScore] = []
    
    def run_all_tests(self) -> List[QualityScore]:
        """运行所有测试用例"""
        logger.info(f"开始质量评估，共 {len(TEST_CASES)} 个测试用例")
        
        for i, case in enumerate(TEST_CASES):
            logger.info(f"\n{'='*60}")
            logger.info(f"测试用例 {i+1}/{len(TEST_CASES)}: {case['product']} → {case['target_market']}")
            logger.info(f"{'='*60}")
            
            score = self._run_single_test(i, case)
            self.results.append(score)
            
            # 测试间隔，避免触发限流
            time.sleep(3)
        
        return self.results
    
    def _run_single_test(self, case_id: int, case: Dict) -> QualityScore:
        """运行单个测试用例"""
        score = QualityScore(
            test_case_id=case_id,
            product=case["product"],
            target_market=case["target_market"],
        )
        
        product = case["product"]
        target_market = case["target_market"]
        buyer_type = case["buyer_type"]
        max_results = case["max_results"]
        expected_traits = case.get("expected_traits", [])
        
        # ===== 步骤1: 搜索 =====
        logger.info(f"[Step 1] 搜索: {product} → {target_market}")
        
        all_leads = []
        
        # Web搜索
        try:
            web_results = search_web(product, target_market, max_results, buyer_type)
            all_leads.extend(web_results)
            logger.info(f"  Web搜索: {len(web_results)} 条")
        except Exception as e:
            logger.warning(f"  Web搜索失败: {e}")
            score.issues.append(f"Web搜索失败: {e}")
        
        # 商业目录
        try:
            dir_results = search_business_directories(product, target_market, max_results)
            all_leads.extend(dir_results)
            logger.info(f"  商业目录: {len(dir_results)} 条")
        except Exception as e:
            logger.warning(f"  商业目录搜索失败: {e}")
        
        # 海关/展会
        try:
            customs_results = search_customs_and_tradeshow(product, target_market, max_results)
            all_leads.extend(customs_results)
            logger.info(f"  海关/展会: {len(customs_results)} 条")
        except Exception as e:
            logger.warning(f"  海关/展会搜索失败: {e}")
        
        all_leads = deduplicate_leads(all_leads)
        score.result_count = len(all_leads)
        logger.info(f"  去重后总计: {len(all_leads)} 条")
        
        # 评估搜索质量
        score._evaluate_search_quality(all_leads, expected_traits)
        
        if not all_leads:
            score.issues.append("搜索结果为空")
            score.suggestions.append("检查搜索query构建逻辑，增加多语言query")
            score._calculate_total()
            return score
        
        # ===== 步骤2: 抓取联系方式 =====
        logger.info(f"[Step 2] 抓取联系方式 (前{self.max_scrape}条)")
        
        try:
            scraped = batch_scrape(all_leads[:self.max_scrape])
            score._evaluate_scrape_quality(scraped)
        except Exception as e:
            logger.warning(f"  抓取失败: {e}")
            score.issues.append(f"抓取失败: {e}")
            scraped = all_leads[:self.max_scrape]  # 使用未抓取数据继续
        
        # ===== 步骤3: AI评分 =====
        logger.info(f"[Step 3] AI评分")
        
        try:
            scored_leads = batch_score(scraped, product, target_market)
            score._evaluate_scoring_quality(scored_leads)
        except Exception as e:
            logger.warning(f"  评分失败: {e}")
            score.issues.append(f"评分失败: {e}")
            scored_leads = scraped
        
        # 评估整体可用性
        score._evaluate_usability(scored_leads)
        score._calculate_total()
        
        logger.info(f"[完成] 总分: {score.total_score:.1f}/100")
        return score
    
    def generate_report(self) -> Dict:
        """生成综合评估报告"""
        if not self.results:
            return {"error": "未运行测试"}
        
        total_scores = [r.total_score for r in self.results]
        search_scores = [r.search_quality for r in self.results]
        scrape_scores = [r.scrape_quality for r in self.results]
        scoring_scores = [r.scoring_quality for r in self.results]
        usability_scores = [r.overall_usability for r in self.results]
        
        all_issues = []
        all_suggestions = []
        for r in self.results:
            all_issues.extend(r.issues)
            all_suggestions.extend(r.suggestions)
        
        # 去重
        unique_issues = list(dict.fromkeys(all_issues))
        unique_suggestions = list(dict.fromkeys(all_suggestions))
        
        report = {
            "summary": {
                "test_cases_run": len(self.results),
                "avg_total_score": round(sum(total_scores) / len(total_scores), 2),
                "avg_search_quality": round(sum(search_scores) / len(search_scores), 2),
                "avg_scrape_quality": round(sum(scrape_scores) / len(scrape_scores), 2),
                "avg_scoring_quality": round(sum(scoring_scores) / len(scoring_scores), 2),
                "avg_usability": round(sum(usability_scores) / len(usability_scores), 2),
                "min_score": round(min(total_scores), 2),
                "max_score": round(max(total_scores), 2),
                "pass_rate": round(sum(1 for s in total_scores if s >= 60) / len(total_scores) * 100, 1),
            },
            "per_test_case": [asdict(r) for r in self.results],
            "issues": unique_issues,
            "suggestions": unique_suggestions,
            "priority_fixes": self._generate_priority_fixes(unique_issues, unique_suggestions),
            "timestamp": datetime.now().isoformat(),
        }
        
        return report
    
    def _generate_priority_fixes(self, issues: List[str], suggestions: List[str]) -> List[Dict]:
        """根据问题生成优先级修复建议"""
        fixes = []
        
        # 分析问题模式，映射到修复方案
        issue_text = " ".join(issues).lower()
        
        if "搜索结果为空" in issue_text or "result_count" in issue_text:
            fixes.append({
                "priority": "P0",
                "target": "tools/searcher.py",
                "problem": "搜索结果过少或为空",
                "solution": "扩展搜索query数量，增加多语言query，放宽过滤条件",
                "estimated_impact": "高",
            })
        
        if "抓取失败" in issue_text or "scrape" in issue_text:
            fixes.append({
                "priority": "P1",
                "target": "tools/scraper.py",
                "problem": "网页抓取失败率高",
                "solution": "增加请求重试机制，使用 rotating user-agent，增加超时容错",
                "estimated_impact": "中",
            })
        
        if "评分" in issue_text or "score" in issue_text:
            fixes.append({
                "priority": "P1",
                "target": "tools/lead_scorer.py",
                "problem": "评分逻辑不合理",
                "solution": "优化模板评分权重，增加更多评分维度",
                "estimated_impact": "中",
            })
        
        if "contact" in issue_text or "邮箱" in issue_text or "电话" in issue_text:
            fixes.append({
                "priority": "P0",
                "target": "tools/scraper.py",
                "problem": "联系方式提取率低",
                "solution": "增加更多邮箱/电话正则模式，尝试更多页面（About/Contact/Team）",
                "estimated_impact": "高",
            })
        
        # 如果 fixes 太少，添加通用建议
        if len(fixes) < 2:
            fixes.append({
                "priority": "P2",
                "target": "tools/searcher.py",
                "problem": "搜索query可能不够精准",
                "solution": "基于测试结果优化 query 模板，增加行业特定关键词",
                "estimated_impact": "中",
            })
        
        return fixes


# ============ QualityScore 评估方法 ============

def _evaluate_search_quality(self, leads: List[Dict], expected_traits: List[str]):
    """评估搜索质量"""
    # 数量评分：期望至少10条，最多25分
    self.result_count_score = min(25, self.result_count / 10 * 25)
    
    # 多样性评分：检查来源多样性
    sources = {}
    for l in leads:
        src = l.get("source", "unknown")
        sources[src] = sources.get(src, 0) + 1
    
    source_types = len(sources)
    self.diversity_score = min(25, source_types / 4 * 25)  # 4种来源 = 满分
    
    # 相关性评分：检查标题/URL是否包含期望特征
    if leads and expected_traits:
        matches = 0
        for l in leads[:10]:
            combined = f"{l.get('title', '')} {l.get('url', '')} {l.get('snippet', '')}".lower()
            if any(t.lower() in combined for t in expected_traits):
                matches += 1
        self.relevance_score = min(25, matches / 5 * 25)  # 5条匹配 = 满分
    else:
        self.relevance_score = 10  # 默认给基础分
    
    # 搜索质量总分
    self.search_quality = round(
        (self.result_count_score + self.diversity_score + self.relevance_score) / 3, 2
    )
    
    # 生成建议
    if self.result_count < 10:
        self.suggestions.append(f"搜索结果仅{self.result_count}条，建议增加query数量或放宽过滤")
    if source_types < 2:
        self.suggestions.append("来源单一，建议启用更多数据源")


def _evaluate_scrape_quality(self, scraped: List[Dict]):
    """评估抓取质量"""
    total = len(scraped)
    if total == 0:
        self.scrape_quality = 0
        self.issues.append("抓取结果为空")
        return
    
    # 成功抓取率
    scraped_count = sum(1 for l in scraped if l.get("scraped"))
    self.scrape_success_rate = round(scraped_count / total * 100, 1)
    
    # 有联系方式的比例
    with_contact = sum(1 for l in scraped if l.get("emails") or l.get("phones"))
    self.contact_rate = round(with_contact / total * 100, 1)
    
    # 邮箱质量：优先联系类邮箱的比例
    priority_emails = 0
    total_emails = 0
    for l in scraped:
        emails = l.get("emails", [])
        total_emails += len(emails)
        for e in emails:
            if any(k in e for k in ["info", "contact", "sales", "hello", "enquiry"]):
                priority_emails += 1
    
    self.email_quality = round(priority_emails / max(total_emails, 1) * 100, 1) if total_emails > 0 else 0
    
    # 电话质量：有效号码比例（简单判断：有号码就算有效）
    with_phone = sum(1 for l in scraped if l.get("phones"))
    self.phone_quality = round(with_phone / total * 100, 1)
    
    # 抓取质量总分
    self.scrape_quality = round(
        (self.scrape_success_rate * 0.3 + self.contact_rate * 0.4 + 
         self.email_quality * 0.15 + self.phone_quality * 0.15), 2
    )
    
    if self.contact_rate < 30:
        self.suggestions.append(f"联系方式提取率仅{self.contact_rate}%，建议优化抓取策略")
    if self.scrape_success_rate < 50:
        self.suggestions.append(f"抓取成功率仅{self.scrape_success_rate}%，建议增加重试机制")


def _evaluate_scoring_quality(self, scored: List[Dict]):
    """评估评分质量"""
    if not scored:
        self.scoring_quality = 0
        return
    
    # 评分分布
    high = sum(1 for l in scored if l.get("priority") == "高")
    medium = sum(1 for l in scored if l.get("priority") == "中")
    low = sum(1 for l in scored if l.get("priority") == "低")
    
    self.score_distribution = {"高": high, "中": medium, "低": low}
    
    # 合理性：检查是否有评分差异（不能全是同一级别）
    distinct_scores = len(set(l.get("priority") for l in scored if l.get("priority")))
    self.score_reasonableness = min(25, distinct_scores / 3 * 25)  # 3种级别 = 满分
    
    # 头部质量：检查top 3是否有联系方式
    top_leads = scored[:3]
    top_with_contact = sum(1 for l in top_leads if l.get("emails") or l.get("phones"))
    self.top_lead_quality = round(top_with_contact / 3 * 25, 2) if len(top_leads) >= 3 else 0
    
    # 评分质量总分
    self.scoring_quality = round(
        (self.score_reasonableness + self.top_lead_quality) / 2, 2
    )
    
    if distinct_scores < 2:
        self.suggestions.append("评分分布过于集中，建议优化评分逻辑")


def _evaluate_usability(self, scored: List[Dict]):
    """评估整体可用性"""
    # 可行动线索：有邮箱 + 评分 >= 5
    actionable = [
        l for l in scored
        if l.get("emails") and l.get("total_score", 0) >= 5
    ]
    self.actionable_leads = len(actionable)
    
    # 可用性评分：至少3条可行动线索 = 满分
    self.overall_usability = min(25, self.actionable_leads / 3 * 25)
    
    if self.actionable_leads < 3:
        self.suggestions.append(f"可行动线索仅{self.actionable_leads}条，建议提升联系方式提取率")


def _calculate_total(self):
    """计算总分"""
    self.total_score = round(
        self.search_quality + self.scrape_quality + 
        self.scoring_quality + self.overall_usability, 2
    )


# 绑定方法到 QualityScore 类
QualityScore._evaluate_search_quality = _evaluate_search_quality
QualityScore._evaluate_scrape_quality = _evaluate_scrape_quality
QualityScore._evaluate_scoring_quality = _evaluate_scoring_quality
QualityScore._evaluate_usability = _evaluate_usability
QualityScore._calculate_total = _calculate_total


# ============ 主入口 ============

def main():
    """独立运行评估"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    
    evaluator = QualityEvaluator(max_scrape=10)
    evaluator.run_all_tests()
    
    report = evaluator.generate_report()
    
    # 输出报告
    print("\n" + "="*70)
    print("📊 TradeLeadAgent 质量评估报告")
    print("="*70)
    
    summary = report["summary"]
    print(f"\n测试用例数: {summary['test_cases_run']}")
    print(f"平均总分: {summary['avg_total_score']:.1f}/100")
    print(f"  - 搜索质量: {summary['avg_search_quality']:.1f}/25")
    print(f"  - 抓取质量: {summary['avg_scrape_quality']:.1f}/25")
    print(f"  - 评分质量: {summary['avg_scoring_quality']:.1f}/25")
    print(f"  - 整体可用性: {summary['avg_usability']:.1f}/25")
    print(f"最低分: {summary['min_score']:.1f} | 最高分: {summary['max_score']:.1f}")
    print(f"通过率(>=60): {summary['pass_rate']:.0f}%")
    
    if report["issues"]:
        print(f"\n⚠️ 发现的问题:")
        for issue in report["issues"][:10]:
            print(f"  - {issue}")
    
    if report["priority_fixes"]:
        print(f"\n🔧 优先修复建议:")
        for fix in report["priority_fixes"]:
            print(f"  [{fix['priority']}] {fix['target']}: {fix['problem']}")
            print(f"    → {fix['solution']}")
    
    # 保存报告
    report_path = os.path.join(
        os.path.dirname(__file__), "..", ".workbuddy", "memory",
        f"quality-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n💾 报告已保存: {report_path}")
    
    return report


if __name__ == "__main__":
    main()

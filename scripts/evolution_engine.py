"""
scripts/evolution_engine.py
进化引擎 - 根据质量评估报告，自动生成代码改进方案并应用

核心能力：
1. 解析质量报告，识别需要改进的模块
2. 基于预设的改进策略，生成代码修改
3. 安全地应用修改（备份 + 验证）
4. 记录所有变更

设计原则：
- 只修改已知模块（searcher/scraper/lead_scorer/email_generator）
- 每次修改前创建备份
- 修改后运行 health_check 验证语法
- 不修改配置文件和用户数据
"""

import json
import logging
import os
import re
import shutil
import sys
from datetime import datetime
from typing import Dict, List, Optional, Callable

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logger = logging.getLogger(__name__)

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

# 可修改的文件白名单
MODIFIABLE_FILES = {
    "searcher": os.path.join(PROJECT_ROOT, "tools", "searcher.py"),
    "scraper": os.path.join(PROJECT_ROOT, "tools", "scraper.py"),
    "lead_scorer": os.path.join(PROJECT_ROOT, "tools", "lead_scorer.py"),
    "email_generator": os.path.join(PROJECT_ROOT, "tools", "email_generator.py"),
    "promote_generator": os.path.join(PROJECT_ROOT, "tools", "promote_generator.py"),
}


# ============ 改进策略库 ============

class EvolutionStrategy:
    """改进策略基类"""
    
    def __init__(self, name: str, target_file: str):
        self.name = name
        self.target_file = target_file
        self.applied = False
        self.result = None
    
    def check_applicable(self, report: Dict) -> bool:
        """检查此策略是否适用于当前报告"""
        raise NotImplementedError
    
    def apply(self) -> Dict:
        """应用改进，返回结果"""
        raise NotImplementedError
    
    def _backup_file(self):
        """创建备份"""
        backup_path = f"{self.target_file}.backup.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        shutil.copy2(self.target_file, backup_path)
        return backup_path
    
    def _read_file(self) -> str:
        with open(self.target_file, "r", encoding="utf-8") as f:
            return f.read()
    
    def _write_file(self, content: str):
        with open(self.target_file, "w", encoding="utf-8") as f:
            f.write(content)


class IncreaseQueryCountStrategy(EvolutionStrategy):
    """策略1：搜索结果过少时，增加搜索query数量"""
    
    def __init__(self):
        super().__init__("增加搜索query数量", MODIFIABLE_FILES["searcher"])
    
    def check_applicable(self, report: Dict) -> bool:
        avg_search = report.get("summary", {}).get("avg_search_quality", 25)
        # 搜索质量低于15分（满分25）时触发
        return avg_search < 15
    
    def apply(self) -> Dict:
        backup = self._backup_file()
        content = self._read_file()
        
        # 在 _build_search_queries 中增加更多query
        # 策略：在现有 queries 列表后追加更多变体
        additional_queries = '''
        # 自动追加：更多搜索变体（由 evolution_engine 添加）
        queries.extend([
            f'{product} {market_suffix} "buying" OR "sourcing" "contact"',
            f'{product} {market_suffix} "trade" OR "import" company list',
            f'{product} {market_suffix} B2B marketplace "supplier"',
        ])'''
        
        # 找到 queries 列表定义结束的位置（return queries 之前）
        pattern = r'(queries\.append\(f\'\{product\} \{market_suffix\} "expo" exhibitor directory\'\))\s*\n\s*return queries'
        if re.search(pattern, content):
            content = re.sub(
                pattern,
                r'\1\n' + additional_queries + r'\n    return queries',
                content
            )
            self._write_file(content)
            self.applied = True
            return {
                "success": True,
                "strategy": self.name,
                "backup": backup,
                "changes": "在 _build_search_queries 中追加3个额外query变体",
            }
        
        return {"success": False, "reason": "未找到插入点"}


class ImproveContactExtractionStrategy(EvolutionStrategy):
    """策略2：联系方式提取率低时，优化抓取逻辑"""
    
    def __init__(self):
        super().__init__("优化联系方式提取", MODIFIABLE_FILES["scraper"])
    
    def check_applicable(self, report: Dict) -> bool:
        # 检查是否有抓取相关的问题
        issues = " ".join(report.get("issues", [])).lower()
        suggestions = " ".join(report.get("suggestions", [])).lower()
        return "contact" in issues or "邮箱" in issues or "contact" in suggestions or "抓取" in issues
    
    def apply(self) -> Dict:
        backup = self._backup_file()
        content = self._read_file()
        
        # 策略：增加更多页面类型的抓取尝试
        # 在 scrape_lead 中增加对 /team, /careers, /partners 页面的尝试
        old_block = '''            for link in about_links[:3]:  # 最多试3个
                about_html = _fetch_page(link, config.SCRAPE_TIMEOUT)'''
        
        new_block = '''            # 扩展：也尝试 team/partners 页面
            extra_patterns = ["team", "partners", "our-team", "staff"]
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                text = a.get_text(strip=True, separator=" ")
                if any(p in href.lower() or p in text.lower() for p in extra_patterns):
                    full_url = href if href.startswith("http") else url.rstrip("/") + "/" + href.lstrip("/")
                    if full_url not in about_links:
                        about_links.append(full_url)
            
            for link in about_links[:5]:  # 最多试5个（由 evolution_engine 扩展）
                about_html = _fetch_page(link, config.SCRAPE_TIMEOUT)'''
        
        if old_block in content:
            content = content.replace(old_block, new_block)
            self._write_file(content)
            self.applied = True
            return {
                "success": True,
                "strategy": self.name,
                "backup": backup,
                "changes": "扩展 About/Contact 抓取：增加 team/partners 页面，最多尝试5个链接",
            }
        
        return {"success": False, "reason": "未找到目标代码块"}


class ImproveScoringStrategy(EvolutionStrategy):
    """策略3：评分过于集中时，优化评分逻辑"""
    
    def __init__(self):
        super().__init__("优化评分逻辑", MODIFIABLE_FILES["lead_scorer"])
    
    def check_applicable(self, report: Dict) -> bool:
        avg_scoring = report.get("summary", {}).get("avg_scoring_quality", 25)
        return avg_scoring < 15
    
    def apply(self) -> Dict:
        backup = self._backup_file()
        content = self._read_file()
        
        # 策略：增加评分维度，让评分更分散
        old_score = '''    # 有邮箱 +2
    if lead.get("emails"):
        score += 2
    # 有电话 +1
    if lead.get("phones"):
        score += 1'''
        
        new_score = '''    # 有邮箱 +2（优先联系类邮箱额外+1）
    emails = lead.get("emails", [])
    if emails:
        score += 2
        priority_emails = [e for e in emails if any(k in e for k in ["info", "contact", "sales", "hello"])]
        if priority_emails:
            score += 1
    # 有电话 +1（国际格式额外+1）
    phones = lead.get("phones", [])
    if phones:
        score += 1
        if any(p.startswith("+") for p in phones):
            score += 1
    # 有公司描述 +1（长度>100额外+1）
    desc = lead.get("description", "")
    if desc:
        score += 1
        if len(desc) > 100:
            score += 1'''
        
        if old_score in content:
            content = content.replace(old_score, new_score)
            self._write_file(content)
            self.applied = True
            return {
                "success": True,
                "strategy": self.name,
                "backup": backup,
                "changes": "细化模板评分：优先邮箱+1、国际电话+1、长描述+1，增加评分区分度",
            }
        
        return {"success": False, "reason": "未找到目标代码块"}


class AddLanguageSupportStrategy(EvolutionStrategy):
    """策略4：增加多语言搜索支持"""
    
    def __init__(self):
        super().__init__("增加多语言query", MODIFIABLE_FILES["searcher"])
    
    def check_applicable(self, report: Dict) -> bool:
        # 检查是否有非英语市场的用例表现不佳
        per_case = report.get("per_test_case", [])
        for case in per_case:
            if case.get("target_market") in ["巴西", "墨西哥", "日本", "德国"]:
                if case.get("total_score", 100) < 50:
                    return True
        return False
    
    def apply(self) -> Dict:
        backup = self._backup_file()
        content = self._read_file()
        
        # 在 _build_search_queries 中增加更多语言分支
        old_lang = '''    # 西班牙语市场
    if target_market in ["墨西哥", "南美", "巴西"]:
        queries.append(f'{product} importador {market_suffix} "contacto"')
        queries.append(f'{product} distribuidor {market_suffix} "email"')'''
        
        new_lang = '''    # 西班牙语市场
    if target_market in ["墨西哥", "南美", "巴西"]:
        queries.append(f'{product} importador {market_suffix} "contacto"')
        queries.append(f'{product} distribuidor {market_suffix} "email"')
        queries.append(f'{product} {market_suffix} "empresa" importadora')
    # 日语市场
    if target_market in ["日本"]:
        queries.append(f'{product} 輸入 日本 "会社"')
        queries.append(f'{product} 日本 代理店 問い合わせ')
    # 德语市场
    if target_market in ["德国"]:
        queries.append(f'{product} {market_suffix} "Importeur" "Kontakt"')
        queries.append(f'{product} {market_suffix} "Händler" "Großhandel"')'''
        
        if old_lang in content:
            content = content.replace(old_lang, new_lang)
            self._write_file(content)
            self.applied = True
            return {
                "success": True,
                "strategy": self.name,
                "backup": backup,
                "changes": "增加日语、德语市场搜索query",
            }
        
        return {"success": False, "reason": "未找到目标代码块"}


# ============ 进化引擎主类 ============

class EvolutionEngine:
    """进化引擎：根据评估报告自动选择和执行改进策略"""
    
    STRATEGIES = [
        IncreaseQueryCountStrategy,
        ImproveContactExtractionStrategy,
        ImproveScoringStrategy,
        AddLanguageSupportStrategy,
    ]
    
    def __init__(self):
        self.applied_strategies: List[Dict] = []
        self.skipped_strategies: List[Dict] = []
    
    def evolve(self, report: Dict) -> Dict:
        """
        根据质量报告执行进化
        返回进化结果报告
        """
        logger.info("=" * 60)
        logger.info("🧬 进化引擎启动")
        logger.info("=" * 60)
        
        for strategy_class in self.STRATEGIES:
            strategy = strategy_class()
            
            # 检查是否适用
            if not strategy.check_applicable(report):
                self.skipped_strategies.append({
                    "name": strategy.name,
                    "reason": "当前报告不满足触发条件",
                })
                logger.info(f"  ⏭️ 跳过: {strategy.name} (不满足条件)")
                continue
            
            # 应用策略
            logger.info(f"  🔧 应用: {strategy.name}")
            try:
                result = strategy.apply()
                
                if result.get("success"):
                    self.applied_strategies.append(result)
                    logger.info(f"  ✅ 成功: {result['changes']}")
                else:
                    self.skipped_strategies.append({
                        "name": strategy.name,
                        "reason": result.get("reason", "应用失败"),
                    })
                    logger.warning(f"  ⚠️ 失败: {result.get('reason')}")
            
            except Exception as e:
                self.skipped_strategies.append({
                    "name": strategy.name,
                    "reason": f"异常: {e}",
                })
                logger.error(f"  ❌ 异常: {e}")
        
        # 验证修改后的代码语法
        syntax_ok = self._verify_syntax()
        
        return {
            "evolved_at": datetime.now().isoformat(),
            "applied": self.applied_strategies,
            "skipped": self.skipped_strategies,
            "syntax_verified": syntax_ok,
            "has_changes": len(self.applied_strategies) > 0,
        }
    
    def _verify_syntax(self) -> bool:
        """验证所有修改后的文件语法正确"""
        import py_compile
        
        all_ok = True
        for name, path in MODIFIABLE_FILES.items():
            try:
                py_compile.compile(path, doraise=True)
                logger.info(f"  ✅ 语法检查通过: {name}")
            except py_compile.PyCompileError as e:
                logger.error(f"  ❌ 语法错误: {name} - {e}")
                all_ok = False
        
        return all_ok


# ============ 主入口 ============

def main(report_path: Optional[str] = None):
    """
    独立运行进化引擎
    
    Args:
        report_path: 质量报告JSON路径，None则使用默认路径
    """
    # Windows GBK console fix
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    
    # 读取质量报告
    if report_path is None:
        # 查找最新的质量报告
        memory_dir = os.path.join(PROJECT_ROOT, ".workbuddy", "memory")
        reports = [f for f in os.listdir(memory_dir) if f.startswith("quality-report-")]
        if reports:
            reports.sort()
            report_path = os.path.join(memory_dir, reports[-1])
        else:
            logger.error("未找到质量报告，请先运行 quality_evaluator.py")
            return
    
    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)
    
    # 执行进化
    engine = EvolutionEngine()
    result = engine.evolve(report)
    
    # 输出结果
    print("\n" + "=" * 70)
    print("[EVOLUTION] Evolution Result Report")
    print("=" * 70)
    print(f"Applied strategies: {len(result['applied'])}")
    print(f"Skipped strategies: {len(result['skipped'])}")
    print(f"Syntax verified: {'PASS' if result['syntax_verified'] else 'FAIL'}")
    
    if result["applied"]:
        print(f"\nApplied improvements:")
        for s in result["applied"]:
            print(f"  [OK] {s['strategy']}: {s['changes']}")
    
    if result["skipped"]:
        print(f"\nSkipped strategies:")
        for s in result["skipped"]:
            print(f"  [SKIP] {s['name']}: {s['reason']}")
    
    # 保存进化报告
    evolution_path = os.path.join(
        PROJECT_ROOT, ".workbuddy", "memory",
        f"evolution-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    with open(evolution_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVED] Evolution report saved: {evolution_path}")
    
    return result


if __name__ == "__main__":
    import sys
    report_path = sys.argv[1] if len(sys.argv) > 1 else None
    main(report_path)

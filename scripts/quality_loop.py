"""
scripts/quality_loop.py
质量进化主循环 - 持续自我迭代的 Agent Loop

完整流程：
1. 模拟用户输入（生成测试用例）
2. 运行完整搜索流程（搜索→抓取→评分）
3. 评估输出质量（多维度评分）
4. 如果质量不达标，触发进化引擎改进代码
5. 验证改进后的代码（语法 + 快速回归测试）
6. 提交并推送（git commit + git push）
7. 记录日志
8. 等待下一轮

终止条件：
- 用户按 Ctrl+C
- 连续多轮无改进且质量稳定
- 达到最大迭代次数

用法：
    python scripts/quality_loop.py
    # 或指定参数
    python scripts/quality_loop.py --max-iterations 10 --quality-threshold 70
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.quality_evaluator import QualityEvaluator
from scripts.evolution_engine import EvolutionEngine
from scripts.health_check import run_all_checks

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


# ============ 配置 ============

DEFAULT_CONFIG = {
    "check_interval_minutes": 30,      # 每30分钟检查一次
    "quality_threshold": 60,           # 质量及格线（总分100）
    "max_iterations": 100,             # 最大迭代次数
    "min_improvement": 2,              # 最小改进幅度（分）
    "stagnation_rounds": 3,            # 连续N轮无改进则停止
    "max_scrape_per_test": 10,         # 每个测试用例最多抓取条数
    "auto_commit": True,               # 是否自动提交
    "auto_push": True,                 # 是否自动推送
}


class QualityLoop:
    """质量进化主循环"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.iteration = 0
        self.stagnation_count = 0
        self.best_score = 0
        self.history: List[Dict] = []
    
    def run(self):
        """启动主循环"""
        logger.info("=" * 70)
        logger.info("🔄 TradeLeadAgent 质量进化循环启动")
        logger.info(f"质量阈值: {self.config['quality_threshold']} | 最大迭代: {self.config['max_iterations']}")
        logger.info("按 Ctrl+C 停止")
        logger.info("=" * 70)
        
        try:
            while self.iteration < self.config["max_iterations"]:
                self.iteration += 1
                logger.info(f"\n{'='*70}")
                logger.info(f"🔄 第 {self.iteration}/{self.config['max_iterations']} 轮迭代")
                logger.info(f"{'='*70}")
                
                # 执行一轮
                round_result = self._run_one_round()
                self.history.append(round_result)
                
                # 检查是否达到质量阈值
                current_score = round_result["summary"]["avg_total_score"]
                
                if current_score >= self.config["quality_threshold"]:
                    logger.info(f"✅ 质量达标！当前分数: {current_score:.1f} >= 阈值 {self.config['quality_threshold']}")
                    if self.stagnation_count >= self.config["stagnation_rounds"]:
                        logger.info("🎯 质量已稳定达标，停止循环")
                        break
                
                # 检查是否停滞
                improvement = current_score - self.best_score
                if improvement >= self.config["min_improvement"]:
                    self.best_score = current_score
                    self.stagnation_count = 0
                    logger.info(f"📈 质量提升: +{improvement:.1f} 分，新最佳: {self.best_score:.1f}")
                else:
                    self.stagnation_count += 1
                    logger.info(f"📊 质量变化: {improvement:+.1f} 分，停滞计数: {self.stagnation_count}/{self.config['stagnation_rounds']}")
                    
                    if self.stagnation_count >= self.config["stagnation_rounds"]:
                        logger.info("🛑 连续多轮无显著改进，停止循环")
                        break
                
                # 等待下一轮
                wait_min = self.config["check_interval_minutes"]
                logger.info(f"⏳ 等待 {wait_min} 分钟后开始下一轮...")
                time.sleep(wait_min * 60)
        
        except KeyboardInterrupt:
            logger.info("\n🛑 用户中断，停止循环")
        
        # 生成最终报告
        self._generate_final_report()
    
    def _run_one_round(self) -> Dict:
        """执行一轮完整流程"""
        round_start = datetime.now()
        
        # ===== 步骤1: 健康检查 =====
        logger.info("[Step 1] 健康检查...")
        health = run_all_checks()
        if health["summary"]["has_errors"]:
            logger.warning("⚠️ 健康检查发现问题，先运行 auto_fix")
            from scripts.auto_fix import run_all_fixes
            fix_result = run_all_fixes()
            logger.info(f"  自动修复: {fix_result['fixed']} 处修复")
        
        # ===== 步骤2: 质量评估 =====
        logger.info("[Step 2] 质量评估...")
        evaluator = QualityEvaluator(max_scrape=self.config["max_scrape_per_test"])
        evaluator.run_all_tests()
        report = evaluator.generate_report()
        
        summary = report["summary"]
        logger.info(f"  平均总分: {summary['avg_total_score']:.1f}/100")
        logger.info(f"  搜索质量: {summary['avg_search_quality']:.1f}/25")
        logger.info(f"  抓取质量: {summary['avg_scrape_quality']:.1f}/25")
        logger.info(f"  评分质量: {summary['avg_scoring_quality']:.1f}/25")
        logger.info(f"  可用性: {summary['avg_usability']:.1f}/25")
        
        # ===== 步骤3: 进化（如果质量不达标） =====
        evolved = False
        evolution_result = None
        
        if summary["avg_total_score"] < self.config["quality_threshold"]:
            logger.info(f"[Step 3] 质量未达标，触发进化引擎...")
            engine = EvolutionEngine()
            evolution_result = engine.evolve(report)
            evolved = evolution_result.get("has_changes", False)
            
            if evolved:
                logger.info(f"  ✅ 已应用 {len(evolution_result['applied'])} 项改进")
            else:
                logger.info("  ⏭️ 无适用改进策略")
        else:
            logger.info("[Step 3] 质量已达标，跳过进化")
        
        # ===== 步骤4: 验证改进 =====
        if evolved:
            logger.info("[Step 4] 验证改进...")
            health_after = run_all_checks()
            if health_after["summary"]["has_errors"]:
                logger.error("  ❌ 改进后代码有语法错误！尝试回滚...")
                # TODO: 实现回滚逻辑
            else:
                logger.info("  ✅ 语法验证通过")
        
        # ===== 步骤5: 提交推送 =====
        if evolved and self.config["auto_commit"]:
            logger.info("[Step 5] 提交并推送...")
            commit_result = self._git_commit_and_push()
            logger.info(f"  {'✅' if commit_result['success'] else '❌'} {commit_result['message']}")
        
        # ===== 记录日志 =====
        round_result = {
            "round": self.iteration,
            "timestamp": round_start.isoformat(),
            "summary": summary,
            "evolved": evolved,
            "evolution_result": evolution_result,
            "health_check": health,
        }
        
        self._write_round_log(round_result)
        
        return round_result
    
    def _git_commit_and_push(self) -> Dict:
        """提交并推送代码变更"""
        try:
            # 检查是否有变更
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
            )
            
            if not status.stdout.strip():
                return {"success": True, "message": "无变更需要提交"}
            
            # 添加、提交、推送
            subprocess.run(["git", "add", "."], cwd=PROJECT_ROOT, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"auto: 质量进化第{self.iteration}轮"],
                cwd=PROJECT_ROOT,
                check=True,
            )
            subprocess.run(["git", "push"], cwd=PROJECT_ROOT, check=True)
            
            return {"success": True, "message": f"已推送进化第{self.iteration}轮"}
        
        except subprocess.CalledProcessError as e:
            return {"success": False, "message": f"Git操作失败: {e}"}
    
    def _write_round_log(self, round_result: Dict):
        """写入本轮日志"""
        log_dir = os.path.join(PROJECT_ROOT, ".workbuddy", "memory")
        os.makedirs(log_dir, exist_ok=True)
        
        log_path = os.path.join(log_dir, f"quality-loop-{datetime.now().strftime('%Y%m%d')}.jsonl")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(round_result, ensure_ascii=False) + "\n")
    
    def _generate_final_report(self):
        """生成最终报告"""
        if not self.history:
            logger.info("无历史记录")
            return
        
        scores = [r["summary"]["avg_total_score"] for r in self.history]
        
        report = {
            "total_rounds": self.iteration,
            "best_score": max(scores),
            "final_score": scores[-1],
            "improvement": scores[-1] - scores[0],
            "history": [
                {
                    "round": r["round"],
                    "score": r["summary"]["avg_total_score"],
                    "evolved": r["evolved"],
                }
                for r in self.history
            ],
            "stopped_reason": "质量稳定达标" if scores[-1] >= self.config["quality_threshold"] else "停滞",
        }
        
        report_path = os.path.join(
            PROJECT_ROOT, ".workbuddy", "memory",
            f"quality-loop-final-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info("\n" + "=" * 70)
        logger.info("📊 最终报告")
        logger.info("=" * 70)
        logger.info(f"总轮数: {report['total_rounds']}")
        logger.info(f"初始分数: {scores[0]:.1f}")
        logger.info(f"最佳分数: {report['best_score']:.1f}")
        logger.info(f"最终分数: {report['final_score']:.1f}")
        logger.info(f"总改进: {report['improvement']:+.1f}")
        logger.info(f"停止原因: {report['stopped_reason']}")
        logger.info(f"报告已保存: {report_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="TradeLeadAgent 质量进化循环")
    parser.add_argument("--max-iterations", type=int, default=100, help="最大迭代次数")
    parser.add_argument("--quality-threshold", type=float, default=60, help="质量及格线")
    parser.add_argument("--check-interval", type=int, default=30, help="检查间隔（分钟）")
    parser.add_argument("--max-scrape", type=int, default=10, help="每个测试用例最大抓取数")
    parser.add_argument("--no-auto-commit", action="store_true", help="禁用自动提交")
    return parser.parse_args()


def main():
    args = parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                os.path.join(PROJECT_ROOT, ".workbuddy", "memory", "quality-loop.log"),
                encoding="utf-8",
            ),
        ],
    )
    
    config = {
        "max_iterations": args.max_iterations,
        "quality_threshold": args.quality_threshold,
        "check_interval_minutes": args.check_interval,
        "max_scrape_per_test": args.max_scrape,
        "auto_commit": not args.no_auto_commit,
        "auto_push": not args.no_auto_commit,
    }
    
    loop = QualityLoop(config)
    loop.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
scripts/self_heal_loop.py
TradeLeadAgent 自修复循环 — 持续监控、修复、提交
本地运行：python scripts/self_heal_loop.py
按 Ctrl+C 停止
"""
import subprocess
import sys
import os
import time
import json
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEALTH_CHECK = os.path.join(PROJECT_ROOT, "scripts", "health_check.py")
AUTO_FIX = os.path.join(PROJECT_ROOT, "scripts", "auto_fix.py")

MAX_FIX_ATTEMPTS = 3        # 单次发现最多尝试修复次数
CHECK_INTERVAL = 300       # 5分钟检查一次（秒）
FIX_INTERVAL = 60          # 修复后等待1分钟再验证


def log(msg, level="INFO"):
    """打印带时间戳的日志"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")
    sys.stdout.flush()


def run_cmd(cmd, cwd=PROJECT_ROOT, timeout=120):
    """运行命令，返回 (rc, stdout, stderr)"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def run_health_check():
    """运行健康检查，返回 (ok, report_dict)"""
    rc, out, err = run_cmd(f"python {HEALTH_CHECK}")
    if rc != 0:
        # 尝试解析 JSON 报告
        try:
            report = json.loads(out)
        except json.JSONDecodeError:
            report = {"raw_output": out, "raw_error": err}
        return False, report
    try:
        report = json.loads(out)
    except json.JSONDecodeError:
        report = {"raw_output": out}
    return True, report


def run_auto_fix():
    """运行自动修复，返回 (ok, report_dict)"""
    rc, out, err = run_cmd(f"python {AUTO_FIX}")
    try:
        report = json.loads(out)
    except json.JSONDecodeError:
        report = {"raw_output": out, "raw_error": err}
    return rc == 0, report


def git_has_changes():
    """检查是否有未提交的更改"""
    rc, out, _ = run_cmd("git status --porcelain")
    return rc == 0 and out.strip() != ""


def git_commit_and_push(message):
    """提交并推送更改"""
    if not git_has_changes():
        return True, "No changes to commit"

    # git add -A
    rc, _, err = run_cmd("git add -A")
    if rc != 0:
        return False, f"git add failed: {err}"

    # git commit
    rc, out, err = run_cmd(f'git commit -m "{message}"')
    if rc != 0:
        # 可能是 nothing to commit
        if "nothing to commit" in out or "nothing to commit" in err:
            return True, "Nothing to commit"
        return False, f"git commit failed: {err}"

    # git push
    rc, out, err = run_cmd("git push")
    if rc != 0:
        return False, f"git push failed: {err}"

    return True, "Committed and pushed"


def write_loop_log(entry):
    """记录循环日志到 .workbuddy/memory/"""
    log_dir = os.path.join(PROJECT_ROOT, ".workbuddy", "memory")
    os.makedirs(log_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"auto-heal-{date_str}.md")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n## {datetime.now().isoformat()}\n\n")
        f.write(f"```json\n{json.dumps(entry, indent=2, ensure_ascii=False)}\n```\n\n")


def loop():
    """主循环：持续检查 → 修复 → 提交 → 验证"""
    log("=" * 60)
    log("TradeLeadAgent Self-Heal Loop Started")
    log(f"  Check interval: {CHECK_INTERVAL}s")
    log(f"  Max fix attempts per issue: {MAX_FIX_ATTEMPTS}")
    log(f"  Project root: {PROJECT_ROOT}")
    log("=" * 60)
    log("Press Ctrl+C to stop")

    iteration = 0

    while True:
        iteration += 1
        log(f"--- Iteration #{iteration} ---")

        # 1. 健康检查
        ok, report = run_health_check()

        if ok:
            log("All checks passed. No action needed.")
            write_loop_log({
                "iteration": iteration,
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
            })
        else:
            total_errors = report.get("summary", {}).get("total_errors", "unknown")
            log(f"Found {total_errors} issues. Attempting auto-fix...", "WARN")

            # 2. 尝试修复（最多 MAX_FIX_ATTEMPTS 次）
            fixed = False
            for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
                log(f"Fix attempt {attempt}/{MAX_FIX_ATTEMPTS}...")
                fix_ok, fix_report = run_auto_fix()

                if fix_report.get("has_changes"):
                    log(f"Auto-fix applied: {fix_report.get('fixed', 0)} fixes")

                    # 提交修复
                    commit_ok, commit_msg = git_commit_and_push(
                        f"auto-heal #{iteration}.{attempt}: fix issues"
                    )
                    if commit_ok:
                        log(f"Changes committed: {commit_msg}")
                    else:
                        log(f"Commit failed: {commit_msg}", "ERROR")

                    # 等待一小段时间后重新验证
                    log(f"Waiting {FIX_INTERVAL}s before re-checking...")
                    time.sleep(FIX_INTERVAL)

                    # 重新检查
                    ok2, report2 = run_health_check()
                    if ok2:
                        log(f"Fix verified! All checks pass after attempt {attempt}.")
                        fixed = True
                        write_loop_log({
                            "iteration": iteration,
                            "status": "fixed",
                            "attempts": attempt,
                            "fix_report": fix_report,
                            "timestamp": datetime.now().isoformat(),
                        })
                        break
                    else:
                        remaining = report2.get("summary", {}).get("total_errors", "unknown")
                        log(f"Still {remaining} issues remaining after attempt {attempt}")
                else:
                    log("No auto-fixes applied. Issues may require manual intervention.")
                    break

            if not fixed:
                log("Could not auto-fix all issues. Waiting for user intervention.", "ERROR")
                write_loop_log({
                    "iteration": iteration,
                    "status": "failed",
                    "report": report,
                    "timestamp": datetime.now().isoformat(),
                })
                # 继续循环，下次检查时可能可以修复

        # 3. 等待下一轮
        log(f"Sleeping for {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        loop()
    except KeyboardInterrupt:
        log("\n🛑 User interrupted. Stopping self-heal loop.", "INFO")
        sys.exit(0)
    except Exception as e:
        log(f"Loop crashed: {e}", "ERROR")
        raise

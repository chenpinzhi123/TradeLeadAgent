#!/usr/bin/env python3
"""
scripts/health_check.py
TradeLeadAgent 全面健康检查脚本
检查维度：语法、导入、模块兼容性、接口一致性
"""
import ast
import importlib.util
import json
import os
import re
import sys

# 项目根目录（scripts/ 的上一级）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_syntax(filepath):
    """检查单个 .py 文件语法"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        ast.parse(source)
        return True, None
    except SyntaxError as e:
        return False, f"SyntaxError at line {e.lineno}: {e.msg}"
    except UnicodeDecodeError as e:
        return False, f"UnicodeDecodeError: {e}"


def check_all_syntax():
    """检查所有 .py 文件语法"""
    errors = []
    skip_dirs = {".git", "__pycache__", ".venv", "venv", "env", ".workbuddy", "node_modules"}
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                ok, err = check_syntax(filepath)
                if not ok:
                    errors.append({"file": os.path.relpath(filepath, PROJECT_ROOT), "error": err})
    return errors


def check_module_imports():
    """尝试 import 所有项目模块"""
    errors = []
    sys.path.insert(0, PROJECT_ROOT)

    modules = [
        "config",
        "tools.searcher",
        "tools.scraper",
        "tools.lead_scorer",
        "tools.email_generator",
        "tools.promote_generator",
        "utils.helpers",
    ]

    for mod_name in modules:
        try:
            spec = importlib.util.find_spec(mod_name)
            if spec is None:
                errors.append({"module": mod_name, "error": "Module not found in PYTHONPATH"})
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            errors.append({"module": mod_name, "error": f"{type(e).__name__}: {e}"})

    return errors


def check_config_searcher_compatibility():
    """检查 config.py 和 searcher.py 的兼容性（命名一致性等）"""
    errors = []
    sys.path.insert(0, PROJECT_ROOT)

    try:
        import config

        # 检查 MARKET_KEY_WORDS / MARKET_KEYWORDS 命名
        has_kw = hasattr(config, "MARKET_KEYWORDS")
        has_kw_alt = hasattr(config, "MARKET_KEY_WORDS")

        if not has_kw and not has_kw_alt:
            errors.append({
                "check": "config_market_keywords",
                "error": "Missing both MARKET_KEYWORDS and MARKET_KEY_WORDS in config.py",
            })
        elif has_kw and not has_kw_alt:
            errors.append({
                "check": "config_market_keywords",
                "warning": True,
                "error": "config has MARKET_KEYWORDS but not MARKET_KEY_WORDS; searcher.py may crash",
                "fix": "Add MARKET_KEY_WORDS = MARKET_KEYWORDS to config.py",
            })

        # 检查 searcher.py 引用的所有 config.XXX 属性
        searcher_path = os.path.join(PROJECT_ROOT, "tools", "searcher.py")
        with open(searcher_path, "r", encoding="utf-8") as f:
            searcher_content = f.read()

        # 提取所有 config.XXX 引用（排除函数调用、getattr等）
        refs = set(re.findall(r"config\.([A-Z_][A-Z_0-9]*)\b", searcher_content))
        for ref in refs:
            if not hasattr(config, ref):
                errors.append({
                    "check": "config_attribute",
                    "error": f"searcher.py references config.{ref} but config.py doesn't define it",
                    "fix": f"Add {ref} to config.py or fix searcher.py reference",
                })

    except Exception as e:
        errors.append({"check": "config_import", "error": f"Failed to import config: {e}"})

    return errors


def check_app_imports_match():
    """检查 app.py 从各模块导入的函数是否真实存在"""
    errors = []
    sys.path.insert(0, PROJECT_ROOT)

    import_re = re.compile(
        r'from\s+([\w.]+)\s+import\s*\((.*?)\)', re.DOTALL
    )

    app_path = os.path.join(PROJECT_ROOT, "app.py")
    with open(app_path, "r", encoding="utf-8") as f:
        content = f.read()

    for match in import_re.finditer(content):
        module_name = match.group(1)
        imports_block = match.group(2)
        # 提取函数名（去除换行和逗号）
        func_names = [n.strip().strip(",") for n in imports_block.replace("\n", " ").split(",")]

        try:
            module = importlib.import_module(module_name)
            for func_name in func_names:
                if not func_name or func_name.startswith("#"):
                    continue
                if not hasattr(module, func_name):
                    errors.append({
                        "check": "app_import",
                        "error": f"app.py imports {func_name} from {module_name} but it doesn't exist",
                        "fix": f"Add {func_name} to {module_name} or remove import",
                    })
        except Exception as e:
            errors.append({
                "check": "app_import",
                "error": f"Failed to import {module_name}: {e}",
            })

    return errors


def check_function_signatures():
    """检查 app.py 调用函数的参数是否与模块定义一致"""
    errors = []
    # 这是一个启发式检查，主要检查常见的参数不匹配问题
    # 例如 search_web 的参数是否包含 max_results 和 buyer_type
    sys.path.insert(0, PROJECT_ROOT)

    try:
        import tools.searcher as searcher
        import inspect

        # 检查 search_web 签名
        sig = inspect.signature(searcher.search_web)
        params = list(sig.parameters.keys())
        expected = ["product", "target_market", "max_results", "buyer_type"]
        for p in expected:
            if p not in params:
                errors.append({
                    "check": "search_web_signature",
                    "error": f"search_web() missing parameter '{p}'",
                    "fix": f"Add {p} to search_web() signature",
                })

        # 检查 search_customs_and_tradeshow 是否存在
        if not hasattr(searcher, "search_customs_and_tradeshow"):
            errors.append({
                "check": "searcher_export",
                "error": "search_customs_and_tradeshow not found in searcher.py",
                "fix": "Add search_customs_and_tradeshow() to searcher.py",
            })

    except Exception as e:
        errors.append({"check": "function_signature", "error": f"Failed to check: {e}"})

    return errors


def check_scraper_config():
    """检查 scraper.py 使用的 config 属性是否存在"""
    errors = []
    sys.path.insert(0, PROJECT_ROOT)

    try:
        import config
        scraper_path = os.path.join(PROJECT_ROOT, "tools", "scraper.py")
        with open(scraper_path, "r", encoding="utf-8") as f:
            content = f.read()

        refs = set(re.findall(r"config\.([A-Z_][A-Z_0-9]*)\b", content))
        for ref in refs:
            if not hasattr(config, ref):
                errors.append({
                    "check": "scraper_config",
                    "error": f"scraper.py references config.{ref} but config.py doesn't define it",
                    "fix": f"Add {ref} to config.py",
                })
    except Exception as e:
        errors.append({"check": "scraper_config", "error": f"Failed: {e}"})

    return errors


def run_all_checks():
    """运行所有检查并返回结构化报告"""
    results = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "project": "TradeLeadAgent",
        "checks": {
            "syntax": check_all_syntax(),
            "module_imports": check_module_imports(),
            "config_compat": check_config_searcher_compatibility(),
            "app_imports": check_app_imports_match(),
            "function_signatures": check_function_signatures(),
            "scraper_config": check_scraper_config(),
        },
    }

    total_errors = sum(len(v) for v in results["checks"].values())
    results["summary"] = {
        "total_errors": total_errors,
        "has_errors": total_errors > 0,
        "fixable_auto": sum(
            1 for category in results["checks"].values()
            for item in category
            if item.get("fix") and not item.get("warning")
        ),
    }

    return results


if __name__ == "__main__":
    results = run_all_checks()
    print(json.dumps(results, indent=2, ensure_ascii=False))

    if results["summary"]["has_errors"]:
        print(f"\n[FAIL] Found {results['summary']['total_errors']} issues")
        sys.exit(1)
    else:
        print("\n[PASS] All checks passed")
        sys.exit(0)

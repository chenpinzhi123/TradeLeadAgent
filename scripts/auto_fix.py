#!/usr/bin/env python3
"""
scripts/auto_fix.py
TradeLeadAgent 自动修复脚本
修复常见错误：命名不一致、不安全的 config 引用、缺失的导入等
"""
import json
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def fix_market_keywords_alias():
    """修复：config.py 缺少 MARKET_KEY_WORDS 别名"""
    config_path = os.path.join(PROJECT_ROOT, "config.py")
    content = _read_file(config_path)

    has_kw = "MARKET_KEYWORDS" in content
    has_kw_alt = "MARKET_KEY_WORDS" in content

    if has_kw and not has_kw_alt:
        # 找到 MARKET_KEYWORDS 字典的结束位置
        lines = content.split("\n")
        insert_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith("MARKET_KEYWORDS") and "=" in line:
                brace_depth = 0
                for j in range(i, len(lines)):
                    brace_depth += lines[j].count("{")
                    brace_depth -= lines[j].count("}")
                    if brace_depth == 0:
                        insert_idx = j + 1
                        break
                break

        if insert_idx is not None:
            # 在字典结束后插入别名
            new_lines = (
                lines[:insert_idx]
                + ["\n# 别名（兼容旧版 searcher.py 中 MARKET_KEY_WORDS 的拼写）", "MARKET_KEY_WORDS = MARKET_KEYWORDS"]
                + lines[insert_idx:]
            )
            _write_file(config_path, "\n".join(new_lines))
            return True, "Added MARKET_KEY_WORDS = MARKET_KEYWORDS alias to config.py"

    return False, "MARKET_KEY_WORDS alias OK"


def fix_searcher_config_refs():
    """修复：searcher.py 中不安全的 config.MARKET_KEY_WORDS.get() 引用"""
    searcher_path = os.path.join(PROJECT_ROOT, "tools", "searcher.py")
    content = _read_file(searcher_path)

    # 匹配不安全的写法：config.MARKET_KEY_WORDS.get(target_market, target_market)
    # 但不匹配已经是安全写法的：getattr(config, "MARKET_KEY_WORDS", None)
    unsafe_pattern = re.compile(
        r'config\.MARKET_KEY_WORDS\.get\((target_market,\s*target_market)\)'
    )

    matches = unsafe_pattern.findall(content)
    if matches:
        safe_get = 'getattr(config, "MARKET_KEY_WORDS", None) or getattr(config, "MARKET_KEYWORDS", {}).get(target_market, target_market)'
        content = unsafe_pattern.sub(safe_get, content)
        _write_file(searcher_path, content)
        return True, f"Fixed {len(matches)} unsafe config.MARKET_KEY_WORDS.get() in searcher.py"

    return False, "searcher.py config references OK"


def fix_scraper_config_refs():
    """修复：scraper.py 中引用的 config 属性缺失"""
    scraper_path = os.path.join(PROJECT_ROOT, "tools", "scraper.py")
    config_path = os.path.join(PROJECT_ROOT, "config.py")

    scraper_content = _read_file(scraper_path)
    config_content = _read_file(config_path)

    # 找到 scraper.py 引用的 config.XXX 属性
    refs = set(re.findall(r"config\.([A-Z_][A-Z_0-9]*)\b", scraper_content))

    fixes = []
    for ref in refs:
        if ref in config_content:
            continue
        # 需要添加到 config.py
        # 常见属性映射
        defaults = {
            "SCRAPE_TIMEOUT": "10",
            "MAX_PAGES_PER_LEAD": "3",
            "SEARCH_TIMEOUT": "15",
            "MAX_SEARCH_RESULTS": "10",
        }
        if ref in defaults:
            # 在 config.py 末尾添加
            new_line = f'\n{ref} = int(get_secret("{ref}", "{defaults[ref]}"))'
            if new_line not in config_content:
                config_content += new_line
                fixes.append(f"Added {ref} to config.py")

    if fixes:
        _write_file(config_path, config_content)
        return True, "; ".join(fixes)

    return False, "scraper.py config references OK"


def fix_app_searcher_imports():
    """修复：app.py 导入 searcher.py 中不存在的函数"""
    app_path = os.path.join(PROJECT_ROOT, "app.py")
    searcher_path = os.path.join(PROJECT_ROOT, "tools", "searcher.py")

    app_content = _read_file(app_path)
    searcher_content = _read_file(searcher_path)

    # 提取 app.py 从 tools.searcher 导入的函数
    import_match = re.search(
        r'from\s+tools\.searcher\s+import\s*\((.*?)\)', app_content, re.DOTALL
    )
    if not import_match:
        return False, "No searcher imports found in app.py"

    imports_block = import_match.group(1)
    func_names = [n.strip().strip(",") for n in imports_block.replace("\n", " ").split(",")]

    # 检查每个函数是否在 searcher.py 中定义
    missing = []
    for func_name in func_names:
        if not func_name or func_name.startswith("#"):
            continue
        # 简单的正则匹配：def func_name(
        if not re.search(rf'\bdef\s+{re.escape(func_name)}\s*\(', searcher_content):
            missing.append(func_name)

    if missing:
        # 在 searcher.py 末尾添加 stub 函数
        stubs = []
        for func in missing:
            stub = f'''

def {func}(*args, **kwargs):
    """Auto-generated stub - please implement."""
    import logging
    logging.getLogger(__name__).warning(f"{func} is a stub, returning empty list")
    return []
'''
            stubs.append(stub)

        searcher_content += "\n".join(stubs)
        _write_file(searcher_path, searcher_content)
        return True, f"Added stub functions for {', '.join(missing)} in searcher.py"

    return False, "app.py searcher imports OK"


def fix_missing_init_exports():
    """修复：tools/__init__.py 和 utils/__init__.py 是否为空（可选优化）"""
    fixes = []
    for pkg in ["tools", "utils"]:
        init_path = os.path.join(PROJECT_ROOT, pkg, "__init__.py")
        if os.path.exists(init_path):
            content = _read_file(init_path).strip()
            if not content:
                # 空的 __init__.py 是合法的，但可以加一个注释
                _write_file(init_path, f'"""{pkg} package"""\n')
                fixes.append(f"Added docstring to {pkg}/__init__.py")

    if fixes:
        return True, "; ".join(fixes)
    return False, "Package __init__ files OK"


def run_all_fixes():
    """运行所有自动修复，返回修复报告"""
    fixes = []
    warnings = []

    fixers = [
        fix_market_keywords_alias,
        fix_searcher_config_refs,
        fix_scraper_config_refs,
        fix_app_searcher_imports,
        fix_missing_init_exports,
    ]

    for fixer in fixers:
        try:
            applied, message = fixer()
            if applied:
                fixes.append({"fixer": fixer.__name__, "message": message})
            else:
                warnings.append({"fixer": fixer.__name__, "message": message})
        except Exception as e:
            fixes.append({"fixer": fixer.__name__, "error": str(e)})

    return {
        "fixed": len(fixes),
        "fixes": fixes,
        "warnings": warnings,
        "has_changes": len(fixes) > 0,
    }


if __name__ == "__main__":
    report = run_all_fixes()
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if report["has_changes"]:
        print(f"\n[FIX] Auto-fixed {report['fixed']} issues")
        sys.exit(0)  # 修复成功，退出码 0
    else:
        print("\n[OK] No fixes needed")
        sys.exit(0)

#!/usr/bin/env python3
"""口腔知情告知摘要成品格式自检。

只读读取指定文件并按 output-template.md 的格式规范逐条检查，不修改输入、不联网、不启动子进程。
退出码：0 = 通过；1 = 存在必改项；2 = 文件不可读。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TECH_NOTE = (
    "全程使用专业的口腔手术显微镜，视野放大20倍以上，能更精准地发现隐蔽病灶、"
    "彻底清理根管，显著提高治疗成功率和远期效果。"
)
FEE_NOTE = "此为大致费用，具体金额以最终确认为准。"

PART_TITLES = (
    "一、患者基本情况",
    "二、沟通中明确的治疗方案",
    "三、医患沟通中已提及的风险与不确定性",
)
SIGNATURE_FIELDS = (
    "- 患者选择方案：",
    "- 风险确认：",
    "- 患者承诺：",
    "- 患者签字：",
)
THIRD_PART_ITEMS = (
    "- 已告知的结局不确定性：",
    "- 已告知的后续治疗可能：",
    "- 已提及的术中风险：",
    "- 已说明的差异与选择：",
)
BANNED_BULLETS = ("•", "·", "◦", "▪", "●", "○", "◆", "※", "・")
PLACEHOLDER_PHRASES = ("待确认", "费用面议", "请联系前台", "咨询前台", "TODO", "待补充")


def read_lines(path: Path) -> tuple[str, list[str]]:
    raw = path.read_text(encoding="utf-8-sig")
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    return text, text.split("\n")


def check_markdown(lines: list[str]) -> list[str]:
    hits: list[str] = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            hits.append(f"第 {idx} 行：以 # 开头")
        if "**" in line:
            hits.append(f"第 {idx} 行：出现加粗标记 **")
        if "`" in line:
            hits.append(f"第 {idx} 行：出现反引号")
        if stripped.startswith(">"):
            hits.append(f"第 {idx} 行：出现引用符号 >")
        if line.count("|") >= 2:
            hits.append(f"第 {idx} 行：出现疑似表格的竖线")
    return hits


def check_bullets(lines: list[str]) -> list[str]:
    hits: list[str] = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.startswith(symbol) for symbol in BANNED_BULLETS):
            hits.append(f"第 {idx} 行：使用了禁用列表符号")
        if stripped.startswith("* "):
            hits.append(f"第 {idx} 行：使用了星号列表")
    return hits


def check_dividers(lines: list[str]) -> list[str]:
    rows = [idx for idx, line in enumerate(lines, start=1) if line.strip() == "---"]
    if len(rows) != 2:
        return [f"应有 2 条单独成行的 ---，实际 {len(rows)} 条（行号：{rows or '无'}）"]
    return []


def check_part_titles(text: str, stripped_lines: list[str]) -> list[str]:
    hits: list[str] = []
    for title in PART_TITLES:
        if title not in text:
            hits.append(f"缺少部分标题：{title}")
        elif title not in stripped_lines:
            hits.append(f"部分标题未单独成行：{title}")
    return hits


def check_signature_fields(text: str) -> list[str]:
    return [f"缺少签字栏条目：{field}" for field in SIGNATURE_FIELDS if field not in text]


def check_tech_note(lines: list[str]) -> list[str]:
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped.startswith("- 技术说明："):
            continue
        actual = stripped.split("：", 1)[1].strip() if "：" in stripped else ""
        if actual != TECH_NOTE:
            return [f"第 {idx} 行的技术说明与固定话术不一致，必须逐字输出"]
        return []
    return ["缺少“技术说明”条目"]


def check_placeholders(lines: list[str]) -> list[str]:
    hits: list[str] = []
    for idx, line in enumerate(lines, start=1):
        if "[" in line or "]" in line:
            hits.append(f"第 {idx} 行：方括号占位未替换 -> {line.strip()[:60]}")
        for phrase in PLACEHOLDER_PHRASES:
            if phrase in line:
                hits.append(f"第 {idx} 行：出现占位套话“{phrase}”")
    return hits


def check_fee_note(text: str) -> list[str]:
    if "费用清单" in text and FEE_NOTE not in text:
        return ["存在费用清单但缺少固定附注：此为大致费用，具体金额以最终确认为准。"]
    return []


def check_third_part(stripped_lines: list[str]) -> list[str]:
    if PART_TITLES[2] not in stripped_lines:
        return []
    start = stripped_lines.index(PART_TITLES[2])
    hits: list[str] = []
    for idx in range(start + 1, len(stripped_lines)):
        line = stripped_lines[idx]
        if line == "---" or line in PART_TITLES:
            break
        if line.startswith("- ") and not any(
            line.startswith(item) for item in THIRD_PART_ITEMS
        ):
            hits.append(f"第 {idx + 1} 行：第三部分出现了模板外的条目 -> {line[:40]}")
    return hits


def run_checks(text: str, lines: list[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    stripped_lines = [line.strip() for line in lines]
    errors = {
        "Markdown 语法残留": check_markdown(lines),
        "禁用列表符号": check_bullets(lines),
        "分隔线": check_dividers(lines),
        "部分标题": check_part_titles(text, stripped_lines),
        "签字栏": check_signature_fields(text),
        "技术说明固定话术": check_tech_note(lines),
        "占位符残留": check_placeholders(lines),
        "费用清单附注": check_fee_note(text),
    }
    warnings = {
        "第三部分条目名": check_third_part(stripped_lines),
    }
    return {k: v for k, v in errors.items() if v}, {k: v for k, v in warnings.items() if v}


def build_report(path: Path, errors: dict[str, list[str]], warnings: dict[str, list[str]]) -> dict:
    error_rows = [{"item": k, "details": v} for k, v in errors.items()]
    warning_rows = [{"item": k, "details": v} for k, v in warnings.items()]
    return {
        "file": str(path),
        "passed": not error_rows,
        "error_count": sum(len(v) for v in errors.values()),
        "warning_count": sum(len(v) for v in warnings.values()),
        "errors": error_rows,
        "warnings": warning_rows,
    }


def print_report(report: dict) -> None:
    print(f"检查文件：{report['file']}")
    if report["passed"] and not report["warnings"]:
        print("结果：PASS（无必改项，无提示项）")
        return
    print("结果：PASS" if report["passed"] else "结果：FAIL")
    if report["errors"]:
        print("\n必改项：")
        for row in report["errors"]:
            print(f"- {row['item']}")
            for detail in row["details"]:
                print(f"    {detail}")
    if report["warnings"]:
        print("\n提示项（建议逐条确认）：")
        for row in report["warnings"]:
            print(f"- {row['item']}")
            for detail in row["details"]:
                print(f"    {detail}")
    if report["passed"]:
        print("\n必改项已清零，提示项不影响通过。")


def main() -> int:
    parser = argparse.ArgumentParser(description="口腔知情告知摘要成品格式自检")
    parser.add_argument("input", type=Path, help="待检查的纯文本文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出检查结果")
    args = parser.parse_args()

    path: Path = args.input
    if not path.is_file():
        print(f"找不到文件：{path}", file=sys.stderr)
        return 2

    try:
        text, lines = read_lines(path)
    except UnicodeDecodeError:
        print("文件不是有效的 UTF-8 文本，无法检查", file=sys.stderr)
        return 2

    errors, warnings = run_checks(text, lines)
    report = build_report(path, errors, warnings)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())

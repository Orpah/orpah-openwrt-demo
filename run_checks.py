#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_checks.py — ORPAH Router（OpenWrt 侧）一键自检

    python run_checks.py            # 跑全部离线套件，出报告 checks_report.md

判定 = **退出码 0 且输出里没有 `FAIL` / `Traceback`**。
为什么两个都要看：有些脚本自己把异常吞了还继续往下跑，只看退出码会漏。

三套件都不需要 OpenWrt、不需要真机、不需要上游模拟器（用进程内的假 AP / 假 Server）：

  1. 配置解析（UCI 文本、简写格式、非法值必须报错）
  2. 打包文件一致性（UCI↔init↔LuCI 字段名、Makefile TAB、shell/JS/JSON 语法）
  3. daemon 端到端（上行转发 / 下行注入 / 走失表查表 / 状态文件）
"""

import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "checks_report.md")

SUITES = [
    ("配置解析（UCI / 简写 / 非法值）", "tests/test_config.py"),
    ("打包文件一致性 + 语法检查", "tests/test_package_files.py"),
    ("daemon 端到端（假 AP + 假 Server）", "tests/test_daemon.py"),
]

PY = sys.executable or "python"


def head_sha():
    try:
        r = subprocess.run(["git", "-C", HERE, "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True)
        return r.stdout.strip() or "(非 git 仓库)"
    except OSError:
        return "(取不到)"


def run_suite(script):
    """跑一个套件 → (通过?, 用时秒, 输出文本)。"""
    t0 = time.time()
    r = subprocess.run([PY, os.path.join(HERE, script)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=HERE)
    out = (r.stdout or "") + (r.stderr or "")
    ok = (r.returncode == 0) and not re.search(r"\bFAIL\b|Traceback", out)
    return ok, time.time() - t0, out, r.returncode


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:                      # noqa: BLE001
            pass

    print("=" * 72)
    print("ORPAH Router 自检（OpenWrt 侧）  HEAD=%s  python=%s"
          % (head_sha(), sys.version.split()[0]))
    print("=" * 72)

    results = []
    for title, script in SUITES:
        print("\n### %s  (%s)" % (title, script))
        if not os.path.isfile(os.path.join(HERE, script)):
            print("  [FAIL] 套件文件不存在")
            results.append((title, False, 0.0, "套件文件不存在", 127))
            continue
        ok, secs, out, code = run_suite(script)
        # 只把套件输出的**关键行**铺到终端（PASS/FAIL/ok/跳过），细节进报告
        for line in out.splitlines():
            if re.search(r"\[?(PASS|FAIL|ERROR|OK|skipped|Ran |FAILED)", line):
                print("  " + line.strip())
        print("  → %s（%.2fs，退出码 %d）" % ("通过" if ok else "**失败**", secs, code))
        results.append((title, ok, secs, out, code))

    passed = sum(1 for r in results if r[1])
    total = len(results)

    # ---------------- 报告 ----------------
    lines = ["# ORPAH Router 自检报告（OpenWrt 侧）", "",
             "- 生成时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"),
             "- HEAD：`%s`" % head_sha(),
             "- Python：%s" % sys.version.split()[0],
             "- 结果：**%d/%d 通过**" % (passed, total), "",
             "> 全部套件都**不需要** OpenWrt / 真机 / 上游模拟器（进程内假 AP + 假 Server）。",
             "> 判定 = 退出码 0 **且** 输出无 `FAIL` / `Traceback`。", "",
             "| 套件 | 结果 | 用时 | 退出码 |", "|---|---|---|---|"]
    for title, ok, secs, _out, code in results:
        lines.append("| %s | %s | %.2fs | %d |" % (title, "通过" if ok else "失败", secs, code))
    for title, ok, _secs, out, _code in results:
        lines += ["", "## %s" % title, "", "```", out.strip() or "(无输出)", "```"]
    lines.append("")

    with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

    print("\n" + "=" * 72)
    print("结果：%d/%d 通过；报告 → %s" % (passed, total, os.path.basename(REPORT)))
    print("=" * 72)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

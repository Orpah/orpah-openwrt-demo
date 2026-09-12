# -*- coding: utf-8 -*-
"""tests/test_package_files.py — OpenWrt 打包文件的静态自检（不需要 OpenWrt）

查的都是**真会出事故**的那类问题（不是风格问题）：

  ① 字段名三处不一致 → 「改了配置像没改」（UCI 文件 / init 脚本 / LuCI 表单）
  ② LuCI 菜单里的 ACL 名与 acl.d 里的对象名不一致 → 页面永远 403
  ③ Makefile 的 recipe 行用空格代替 TAB → make 报 missing separator
  ④ Makefile 装的文件不存在 / 装到的路径与 daemon 的 import 期望不一致
  ⑤ `/etc/config/orpah` 忘了写进 conffiles → 升级时把用户配置覆盖掉
  ⑥ shell / JS / JSON 语法错（装机后才发现最麻烦）
  ⑦ .gitignore 漏了 `__pycache__` → 首次 `git add -A` 把字节码吃进库（上游踩过，27 个 .pyc）
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: F401,E402  （必须先设置 import 路径）

from orpahd import config                                   # noqa: E402  （复用同一份 UCI 解析器）

ROOT = _paths.ROOT
FILES = os.path.join(ROOT, "files")
UCI = os.path.join(FILES, "etc", "config", "orpah")
INIT = os.path.join(FILES, "etc", "init.d", "orpah")
RPCD = os.path.join(FILES, "usr", "libexec", "rpcd", "orpah")
MENU = os.path.join(FILES, "usr", "share", "luci", "menu.d", "orpah.json")
ACL = os.path.join(FILES, "usr", "share", "rpcd", "acl.d", "orpah.json")
VIEW = os.path.join(FILES, "www", "luci-static", "resources", "view", "orpah", "router.js")
MAKEFILE = os.path.join(ROOT, "Makefile")
GITIGNORE = os.path.join(ROOT, ".gitignore")


def read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def sh_exe():
    """找一个 POSIX shell 做语法检查。

    优先 Git for Windows 自带的 `sh.exe`：`C:\\Windows\\System32\\bash.exe` 是 **WSL** 的 bash，
    它看不到 Windows 路径（`F:/...` → `No such file or directory`），会给出**假失败**。
    本机探到但没有可用的 shell 时返回 None —— 调用方要**明确跳过**，不能默默当通过。
    """
    for p in (r"D:\Program Files\Git\bin\sh.exe", r"C:\Program Files\Git\bin\sh.exe",
              r"D:\Program Files\Git\usr\bin\sh.exe",
              r"C:\Program Files\Git\usr\bin\sh.exe"):
        if os.path.isfile(p):
            return p
    p = shutil.which("sh") or shutil.which("dash")
    if p:
        return p
    p = shutil.which("bash")
    if p and "system32" not in p.lower():      # 排除 WSL 的 bash
        return p
    return None


def node_exe():
    for name in ("node", "node.exe"):
        p = shutil.which(name)
        if p:
            return p
    return None


class TestFieldNames(unittest.TestCase):
    """字段名一致性：UCI 文件是单一源，init 脚本与 LuCI 表单引用的字段都必须在那里。"""

    def setUp(self):
        self.uci = config.parse_uci(read(UCI))

    def test_uci_declares_every_daemon_field(self):
        for k in config.FIELDS:
            self.assertIn(k, self.uci, "UCI 配置缺少字段 %s" % k)
        self.assertIn("enabled", self.uci)

    def test_init_script_fields_declared(self):
        """init 脚本从 UCI 只读 `enabled`（其余全交给 daemon）—— 读的字段必须在 UCI 里。"""
        fields = re.findall(r"config_get(?:_bool)?\s+\w+\s+main\s+(\w+)", read(INIT))
        self.assertTrue(fields, "init 脚本里一个 config_get 都没找到（脚本改过了？）")
        for f in fields:
            self.assertIn(f, self.uci, "init 脚本读了 UCI 里不存在的字段：%s" % f)

    def test_luci_form_fields_declared(self):
        fields = re.findall(r"s\.option\(form\.\w+,\s*'(\w+)'", read(VIEW))
        self.assertGreaterEqual(len(fields), 6, "LuCI 表单字段太少，正则可能失效：%s" % fields)
        for f in fields:
            self.assertIn(f, self.uci, "LuCI 表单引用了 UCI 里不存在的字段：%s" % f)

    def test_daemon_covers_luci_editable_fields(self):
        """LuCI 能改的字段，daemon 必须真的消费（否则是「填了没用」的假开关）。"""
        editable = set(re.findall(r"s\.option\(form\.\w+,\s*'(\w+)'", read(VIEW))) - {"enabled"}
        missing = editable - set(config.FIELDS)
        self.assertEqual(missing, set(), "LuCI 可改但 daemon 不消费的字段：%s" % missing)


class TestLuciWiring(unittest.TestCase):

    def test_json_files_valid(self):
        for p in (MENU, ACL):
            with self.subTest(path=os.path.basename(p)):
                json.loads(read(p))          # 语法错会抛

    def test_menu_acl_matches_acl_file(self):
        """菜单里声明的 ACL 名必须与 acl.d 里的对象名一致，否则页面永远打不开。"""
        menu = json.loads(read(MENU))
        acl = json.loads(read(ACL))
        names = [v.get("depends", {}).get("acl", []) for v in menu.values()]
        flat = [n for sub in names for n in sub]
        self.assertTrue(flat, "menu.d 里没有声明 acl 依赖")
        for n in flat:
            self.assertIn(n, acl, "menu.d 引用的 ACL %r 在 acl.d 里不存在" % n)

    def test_view_path_matches_install_target(self):
        """菜单 action.path 与视图文件路径、Makefile 安装路径三者必须对得上。"""
        menu = json.loads(read(MENU))
        paths = [v["action"]["path"] for v in menu.values() if v.get("action")]
        self.assertEqual(paths, ["orpah/router"])
        self.assertTrue(os.path.isfile(VIEW))
        self.assertIn("$(1)/www/luci-static/resources/view/orpah/", read(MAKEFILE))

    def test_rpcd_script_exposes_status(self):
        text = read(RPCD)
        self.assertIn('"status"', text)      # list 里声明的方法
        self.assertIn("status)", text)       # call 分支


class TestMakefile(unittest.TestCase):

    def setUp(self):
        self.text = read(MAKEFILE)

    def test_install_recipes_use_tabs(self):
        """recipe 行必须以 TAB 开头（用空格 make 直接报 missing separator）。"""
        blocks, cur, inside = [], [], False
        for line in self.text.splitlines():
            if line.startswith("define ") and line.rstrip().endswith("/install"):
                inside, cur = True, []
                continue
            if inside and line.strip() == "endef":
                inside = False
                blocks.append(cur)
                continue
            if inside:
                cur.append(line)
        self.assertGreaterEqual(len(blocks), 2, "没找到 install 块")
        for i, blk in enumerate(blocks):
            for line in blk:
                if line.strip():
                    self.assertTrue(line.startswith("\t"),
                                    "第 %d 个 install 块里有非 TAB 开头的行：%r" % (i + 1, line))

    def test_installed_files_exist(self):
        """Makefile 里 $(CURDIR)/… 引用的每个文件都必须真的在仓库里。"""
        refs = set(re.findall(r"\$\(CURDIR\)/([^\s)]+)", self.text))
        self.assertTrue(refs)
        for ref in sorted(refs):
            if "*" in ref:
                hits = glob.glob(os.path.join(ROOT, ref))
                self.assertTrue(hits, "通配符 %s 没匹配到任何文件" % ref)
            else:
                self.assertTrue(os.path.isfile(os.path.join(ROOT, ref)),
                                "Makefile 引用但仓库里没有：%s" % ref)

    def test_daemon_layout_matches_import_path(self):
        """安装布局必须让 daemon 的相对 vendor 路径成立（<root>/{orpahd,vendor/orpah}）。"""
        self.assertIn("$(1)/usr/lib/orpah/orpahd", self.text)
        self.assertIn("$(1)/usr/lib/orpah/vendor/orpah", self.text)

    def test_config_is_conffile(self):
        self.assertIn("/etc/config/orpah", self.text)
        self.assertIn("Package/orpah/conffiles", self.text)


class TestSyntax(unittest.TestCase):

    def test_shell_scripts(self):
        sh = sh_exe()
        if not sh:
            self.skipTest("没找到 sh/dash/bash，跳过 shell 语法检查（本机请装 Git for Windows）")
        for p in (INIT, RPCD):
            with self.subTest(path=os.path.basename(p)):
                # 两个 Windows 坑：① 输出要按 UTF-8 解（默认按 GBK/953 会在读线程里炸，
                # stderr 变成 None）；② 在仓库根用**相对正斜杠路径**（MSYS sh 不认反斜杠）。
                rel = os.path.relpath(p, ROOT).replace("\\", "/")
                r = subprocess.run([sh, "-n", rel], cwd=ROOT,
                                   capture_output=True, encoding="utf-8", errors="replace")
                self.assertEqual(r.returncode, 0, "%s 语法错：%s"
                                 % (p, (r.stderr or r.stdout or "(无输出)").strip()))

    def test_luci_view_js(self):
        node = node_exe()
        if not node:
            self.skipTest("没找到 node，跳过 LuCI 视图 JS 语法检查")
        r = subprocess.run([node, "--check", VIEW],
                           capture_output=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, "router.js 语法错：%s"
                         % ((r.stderr or r.stdout or "(无输出)").strip()))


class TestRepoHygiene(unittest.TestCase):

    def test_gitignore_covers_bytecode(self):
        text = read(GITIGNORE)
        for pat in ("__pycache__/", "*.pyc"):
            self.assertIn(pat, text, ".gitignore 少了 %s（字节码会被 git add -A 吃进库）" % pat)

    def test_no_tracked_pyc(self):
        """仓库里不该有被跟踪的字节码（上游踩过：迁出时 27 个 .pyc 被误提交）。"""
        tracked = subprocess.run(["git", "-C", ROOT, "ls-files", "*.pyc"],
                                 capture_output=True, text=True).stdout.split()
        self.assertEqual(tracked, [], "有 .pyc 被 git 跟踪：%s" % tracked[:5])


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    unittest.main(verbosity=2)

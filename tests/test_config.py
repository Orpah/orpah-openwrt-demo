# -*- coding: utf-8 -*-
"""tests/test_config.py — 配置解析自检（不需要 OpenWrt）

重点是被 orpahd/config.py 注释里那段取舍所依赖的性质：
  · 仓库里那份 **OpenWrt 的 UCI 配置**在 PC 上也能解析（同一份文件两处用）
  · 非法值要**抛错**（宁可起不来，也不要「改了配置像没改」）
  · `enabled` 不属于 daemon 的字段（它只由 init 脚本消费）
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: F401,E402  （必须先设置 import 路径）

from orpahd import config  # noqa: E402

UCI_FILE = os.path.join(_paths.ROOT, "files", "etc", "config", "orpah")

SIMPLE = """
# PC 上手调时的简写格式
station_id = AP-02
ap_host = 10.0.0.5
ap_port = 9421
log_level = warn
"""


class TestParseUci(unittest.TestCase):

    def test_repo_uci_file_parsed(self):
        """仓库里那份 OpenWrt 配置能被 PC 端解析器读出来（字段齐全、值正确）。"""
        self.assertTrue(os.path.isfile(UCI_FILE), "找不到 %s" % UCI_FILE)
        cfg = config.load(UCI_FILE)
        for k in config.FIELDS:
            self.assertIn(k, cfg)
        self.assertEqual(cfg["ap_port"], 9421)
        self.assertEqual(cfg["server_port"], 19447)
        self.assertEqual(cfg["station_id"], "AP-01")
        self.assertEqual(cfg["log_level"], "info")
        self.assertEqual(cfg["self_mac"], "4A:06:59:80:00:01")

    def test_parse_uci_only_collects_own_section(self):
        text = ("config other 'x'\n\toption ap_port '1'\n"
                "config orpah 'main'\n\toption ap_port '9421'\n")
        self.assertEqual(config.parse_uci(text), {"ap_port": "9421"})

    def test_enabled_is_not_a_daemon_field(self):
        """`enabled` 只给 init 脚本用：解析出来可以，但不能进 daemon 的字段集。"""
        self.assertIn("enabled", config.parse_uci(open(UCI_FILE, encoding="utf-8").read()))
        self.assertNotIn("enabled", config.FIELDS)

    def test_unknown_keys_ignored(self):
        """UCI 里别的包的字段/未来字段不该让 daemon 崩。"""
        text = "config orpah 'main'\n\toption ap_port '9421'\n\toption 未来字段 'x'\n"
        cfg = config.load(None, {})          # 先确认默认值可用
        self.assertEqual(cfg["ap_port"], 9421)
        raw = config.parse_uci(text)
        self.assertIn("未来字段", raw)         # 解析器收，load() 用 FIELDS 筛


class TestParseSimple(unittest.TestCase):

    def test_simple_format(self):
        cfg = config.load(None, config.parse_simple(SIMPLE))
        self.assertEqual(cfg["station_id"], "AP-02")
        self.assertEqual(cfg["ap_host"], "10.0.0.5")
        self.assertEqual(cfg["log_level"], "warn")
        self.assertEqual(cfg["server_port"], 19447)      # 未给 → 默认值

    def test_auto_detect_by_content(self):
        self.assertEqual(config.parse_text("config orpah 'main'\n"), {})
        self.assertEqual(config.parse_text("ap_port = 1\n"), {"ap_port": "1"})

    def test_comments_and_blank_lines(self):
        self.assertEqual(config.parse_simple("# x\n\n  ap_port = 9421  # 行尾\n"),
                         {"ap_port": "9421"})


class TestValidation(unittest.TestCase):
    """非法值一律抛 ConfigError（宁可退出码非 0，也别静默用默认值跑）。"""

    def test_missing_file(self):
        with self.assertRaises(config.ConfigError):
            config.load(os.path.join(_paths.ROOT, "no-such-file.conf"))

    def test_port_not_a_number(self):
        with self.assertRaises(config.ConfigError):
            config.load(None, {"ap_port": "abc"})

    def test_port_out_of_range(self):
        for bad in ("0", "70000", "-1"):
            with self.assertRaises(config.ConfigError):
                config.load(None, {"ap_port": bad})

    def test_bad_log_level(self):
        with self.assertRaises(config.ConfigError):
            config.load(None, {"log_level": "debug"})    # 只做 info/warn 两级

    def test_bad_mac(self):
        for bad in ("", "4A:06:59:80:00", "4A:06:59:80:00:01:02", "zz:06:59:80:00:01"):
            with self.assertRaises(config.ConfigError):
                config.load(None, {"self_mac": bad})

    def test_empty_host(self):
        with self.assertRaises(config.ConfigError):
            config.load(None, {"server_host": "   "})


class TestMacToBytes(unittest.TestCase):

    def test_forms(self):
        want = bytes([0x4A, 0x06, 0x59, 0x80, 0x00, 0x01])
        self.assertEqual(config.mac_to_bytes("4A:06:59:80:00:01"), want)
        self.assertEqual(config.mac_to_bytes("4a-06-59-80-00-01"), want)   # 小写 + 横杠
        self.assertEqual(config.mac_to_bytes(want), want)                  # bytes 直接给

    def test_invalid(self):
        for bad in ("", "nope", "01:02:03", bytes([1, 2, 3]), "01:02:03:04:05:1000"):
            self.assertIsNone(config.mac_to_bytes(bad))


class TestOverrides(unittest.TestCase):

    def test_cli_overrides_file(self):
        """命令行覆盖 > 文件 > 默认值（排查时临时指一个 Server 用）。"""
        cfg = config.load(UCI_FILE, {"server_host": "192.0.2.9", "log_level": "warn"})
        self.assertEqual(cfg["server_host"], "192.0.2.9")
        self.assertEqual(cfg["log_level"], "warn")
        self.assertEqual(cfg["ap_port"], 9421)              # 文件里的仍然生效

    def test_none_override_means_no_override(self):
        cfg = config.load(None, {"ap_port": None})
        self.assertEqual(cfg["ap_port"], config.DEFAULTS["ap_port"])


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    unittest.main(verbosity=2)

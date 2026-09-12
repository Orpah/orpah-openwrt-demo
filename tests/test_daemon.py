# -*- coding: utf-8 -*-
"""tests/test_daemon.py — daemon 端到端自检（进程内；不需要 OpenWrt，也不需要上游模拟器）

用**假 AP（TCP host 口）＋ 假 Server（UDP）**把 `Daemon` 真跑起来，沿真实帧格式打一遍
上下行，断言四件业务事实：

  · 上行 REPORT / ID-REPORT 真的到了 Server（内容一致，且两种计数**分开**）
  · Server 的下行 TRACKING-STATUS 真的被注入回空口（Client 才收得到回执）
  · REQ-CONNECT 按**本地走失缓存**答 NOT-TRACKED / TRACKED，命中时额外报 FOUND
  · 状态文件（rpcd / LuCI 读的那份）内容与真实计数一致
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: F401,E402  （必须先设置 import 路径）

import fake_air                                                          # noqa: E402
from orpahd import config, daemon                                        # noqa: E402
from orpah_proto import (MSG_ACCESS_INFO, MSG_FOUND, MSG_ID_REPORT,      # noqa: E402
                         MSG_LOST_TABLE_REQ, MSG_REPORT, MSG_TRACKING_STATUS,
                         ST_LOG_OK, ST_NOT_TRACKED, ST_TRACKED,
                         build_id_report, build_report, build_req_connect,
                         build_tracking_status)
from waiting import wait_until                                           # noqa: E402

SN = "CN-WH01-9AF3C1D2"


class DaemonE2E(unittest.TestCase):
    """每个用例一个干净的 daemon + 假空口 + 假 Server。"""

    def setUp(self):
        self.ap = fake_air.FakeAp()
        self.srv = fake_air.FakeServer()
        self.tmp = tempfile.mkdtemp(prefix="orpah-openwrt-demo-test-")
        self.status_file = os.path.join(self.tmp, "run", "status.json")

        cfg = dict(config.DEFAULTS)
        cfg.update(station_id="AP-TEST", ap_host="127.0.0.1", ap_port=self.ap.port,
                   server_host="127.0.0.1", server_port=self.srv.port,
                   log_level="warn", status_file=self.status_file)
        self.d = daemon.Daemon(cfg)

        self.assertTrue(self.d.start(), "daemon 起不来（连不上假 AP？）")
        self.assertTrue(self.ap.wait_connected(timeout=5.0), "假 AP 没等到 daemon 连上来")
        # 启动即拉一次走失表：等它完成 → 之后 REQ-CONNECT 的行为是确定的（不会中途再拉表）
        self.assertIsNotNone(self.srv.wait_msg(MSG_LOST_TABLE_REQ, timeout=5.0),
                             "没等到 daemon 的启动拉表请求")
        self.assertTrue(wait_until(lambda: self.d.status()["synced"], timeout=5.0),
                        "走失表没同步上（FakeServer 应自动应答 LOST-TABLE-REQ）")

    def tearDown(self):
        self.d.stop()
        self.ap.close()
        self.srv.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------- 上行 ----------------
    def test_report_forwarded_to_server(self):
        self.ap.inject(fake_air.sta_frame(build_report(SN, seq=7)))
        msg = self.srv.wait_msg(MSG_REPORT)
        self.assertIsNotNone(msg, "Server 没收到 REPORT")
        self.assertEqual(msg["sn"], SN)
        self.assertEqual(msg["seq"], 7)
        self.assertEqual(self.d.status()["up_count"], 1)

    def test_id_report_forwarded_and_counted_separately(self):
        """ID-REPORT 走同一条通路但**不占 REPORT 计数**（页面按内容分色就靠这两个数分开）。"""
        self.ap.inject(fake_air.sta_frame(
            build_id_report({"hdr": {"alg": "ES256"}, "payload": {"sn": SN}, "sig": "x"})))
        msg = self.srv.wait_msg(MSG_ID_REPORT)
        self.assertIsNotNone(msg, "Server 没收到 ID-REPORT")
        st = self.d.status()
        self.assertEqual(st["id_up_count"], 1)
        self.assertEqual(st["up_count"], 0)

    def test_unparsable_frame_is_ignored(self):
        """非 ORPAH 以太类型 / 垃圾载荷不该让 daemon 崩，也不该产生上行。"""
        self.ap.inject(bytes([0xFF] * 6) + fake_air.STA_MAC + b"\x08\x00" + b"not-orpah")
        self.ap.inject(fake_air.sta_frame(build_report(SN, seq=1)))
        self.assertIsNotNone(self.srv.wait_msg(MSG_REPORT, timeout=5.0),
                             "垃圾帧之后正常帧不通了")
        self.assertEqual(self.srv.count(MSG_REPORT), 1)

    # ---------------- 下行 ----------------
    def test_tracking_status_injected_back_to_air(self):
        self.srv.send(build_tracking_status(SN, ST_LOG_OK))
        msg = self.ap.recv_msg(timeout=5.0)
        self.assertIsNotNone(msg, "下行 TRACKING-STATUS 没被注入回空口")
        self.assertEqual(msg["type"], MSG_TRACKING_STATUS)
        self.assertEqual(msg["sn"], SN)
        self.assertEqual(msg["status"], ST_LOG_OK)
        self.assertGreaterEqual(self.d.status()["down_count"], 1)

    # ---------------- 走失表：查表应答 + 命中报发现 ----------------
    def test_req_connect_not_tracked_when_cache_empty(self):
        self.ap.inject(fake_air.sta_frame(build_req_connect(SN)))
        msg = self.ap.recv_msg(timeout=5.0)
        self.assertIsNotNone(msg, "REQ-CONNECT 没有回 ACCESS-INFO")
        self.assertEqual(msg["type"], MSG_ACCESS_INFO)
        self.assertFalse(msg["tracked"])
        self.assertEqual(msg["status"], ST_NOT_TRACKED)
        self.assertEqual(self.srv.count(MSG_FOUND), 0, "未命中不该报 FOUND")

    def test_lost_table_push_makes_it_tracked_and_reports_found(self):
        """Server 主动推一张表（带该 sn 且 tracked）→ 之后命中：答 TRACKED 并报 ORPAH-FOUND。"""
        self.assertTrue(self.srv.send_lost_table([{"sn": SN, "tracked": True, "note": "测试"}]),
                        "推走失表失败（Server 还不知道 daemon 的地址？）")
        self.assertTrue(wait_until(lambda: self.d.status()["lost_cache"] == 1, timeout=5.0),
                        "走失缓存没更新")
        # 无 rid = 主动推送 → 计一次「收到走失表下发」；启动拉表的应答**不该**计进来
        self.assertEqual(self.d.status()["lost_push_recv"], 1)

        self.ap.inject(fake_air.sta_frame(build_req_connect(SN)))
        msg = self.ap.recv_msg(timeout=5.0)
        self.assertIsNotNone(msg)
        self.assertEqual(msg["type"], MSG_ACCESS_INFO)
        self.assertTrue(msg["tracked"])
        self.assertEqual(msg["status"], ST_TRACKED)

        found = self.srv.wait_msg(MSG_FOUND, timeout=5.0)
        self.assertIsNotNone(found, "命中走失表却没报 ORPAH-FOUND")
        self.assertEqual(found["sn"], SN)
        self.assertEqual(self.d.status()["found_count"], 1)

    def test_lost_table_untrack_removes_it(self):
        """撤销走失（tracked=False）后要回到 NOT-TRACKED。"""
        self.srv.send_lost_table([{"sn": SN, "tracked": True}])
        self.assertTrue(wait_until(lambda: self.d.status()["lost_cache"] == 1, timeout=5.0))
        self.srv.send_lost_table([{"sn": SN, "tracked": False}])
        # 条数不变（还是 1 条），要看的是**内容** —— 所以直接读桥里的缓存
        self.assertTrue(wait_until(
            lambda: self.d.bridge.lost_cache.get(SN, {}).get("tracked") is False, timeout=5.0),
            "撤销下发后缓存里仍是 tracked")
        self.ap.inject(fake_air.sta_frame(build_req_connect(SN)))
        msg = self.ap.recv_msg(timeout=5.0)
        self.assertIsNotNone(msg)
        self.assertEqual(msg["status"], ST_NOT_TRACKED)

    # ---------------- 状态文件（rpcd / LuCI 读的那份） ----------------
    def test_status_file_written_and_parseable(self):
        self.assertTrue(os.path.isfile(self.status_file), "启动时没落状态文件")
        with open(self.status_file, encoding="utf-8") as f:
            st = json.load(f)
        self.assertTrue(st["ok"])
        self.assertEqual(st["station_id"], "AP-TEST")
        self.assertEqual(st["ap"], "127.0.0.1:%d" % self.ap.port)
        self.assertEqual(st["server"], "127.0.0.1:%d" % self.srv.port)
        self.assertEqual(st["log_level"], "warn")
        for k in ("up_count", "down_count", "id_up_count", "found_count",
                  "lost_cache", "lost_push_recv", "synced", "uptime"):
            self.assertIn(k, st)

    def test_status_file_reflects_traffic(self):
        self.ap.inject(fake_air.sta_frame(build_report(SN, seq=1)))
        self.assertIsNotNone(self.srv.wait_msg(MSG_REPORT))
        self.assertEqual(self.d.status()["up_count"], 1)

    def test_status_file_missing_is_not_fatal(self):
        """不给 --status-file 时不该写文件、也不该报错（PC 上临时跑）。"""
        cfg = dict(config.DEFAULTS)
        cfg.update(log_level="warn", status_file=None)
        d = daemon.Daemon(cfg)
        d._write_status()          # 不抛即可


class TestConfigErrorPath(unittest.TestCase):

    def test_main_returns_2_on_bad_config(self):
        """配置坏掉要以退出码 2 退出并打出原因（procd 日志里能看见；不静默用默认值跑）。"""
        tmp = tempfile.mkdtemp(prefix="orpah-openwrt-demo-badcfg-")
        try:
            p = os.path.join(tmp, "orpah.conf")
            with open(p, "w", encoding="utf-8") as f:
                f.write("ap_port = 不是数字\n")
            self.assertEqual(daemon.main(["--config", p]), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_main_returns_2_when_file_missing(self):
        self.assertEqual(daemon.main(["--config", os.path.join(
            tempfile.gettempdir(), "orpah-definitely-missing.conf")]), 2)


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    unittest.main(verbosity=2)

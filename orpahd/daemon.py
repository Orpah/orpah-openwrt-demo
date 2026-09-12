# -*- coding: utf-8 -*-
"""orpahd.daemon — ORPAH Router 守护进程（把「配置」与「桥」接起来）

本文件是**薄壳**，业务逻辑一行都不在这里 —— 全在 `vendor/orpah/router.py` 的
`RouterBridge`（协议与业务的唯一源，见 `vendor/orpah/VENDOR.md`）。这里只做四件事：

  ① 读配置（`orpahd.config`）
  ② 按配置构造 `RouterBridge`（本机 MAC / 日志级别）
  ③ 每 5s 把状态**原子写**一份 JSON 到 `--status-file`，供 rpcd / LuCI 读
  ④ 收 SIGTERM / SIGINT 干净退出（procd 的 stop 就是发 SIGTERM）

## 为什么状态落盘，而不是让 rpcd 去问 daemon

rpcd 脚本是短命进程，与 daemon 之间没有 IPC 通道。落一个文件最省事，而且
**可以在 PC 上验证**（测试直接读这个文件断言内容），不需要 OpenWrt 环境。
写用「先写 .tmp 再 os.replace」—— rpcd 端永远读不到半截 JSON。
"""

import argparse
import json
import os
import signal
import sys
import threading
import time

# vendor/orpah 里的模块之间是**扁平 import**（`from host_bus import HostBus`），
# 所以必须把该目录本身加进 sys.path。仓库与 OpenWrt 包的目录形态一致
# （<root>/{orpahd,vendor/orpah}），所以这一句两边都成立。
_HERE = os.path.dirname(os.path.abspath(__file__))
_VENDOR_ORPAH = os.path.join(os.path.dirname(_HERE), "vendor", "orpah")
if os.path.isdir(_VENDOR_ORPAH) and _VENDOR_ORPAH not in sys.path:
    sys.path.insert(0, _VENDOR_ORPAH)

import router as orpah_router          # noqa: E402  （必须在 sys.path 之后）
from orpahd import config              # noqa: E402

#: 状态落盘周期（秒）。LuCI 页面 poll 5s，正好一轮看一次。
STATUS_INTERVAL = 5.0


class Daemon:
    """一个 ORPAH Router 进程：配置 → RouterBridge → 状态落盘。"""

    def __init__(self, cfg):
        self.cfg = dict(cfg)
        self.status_file = self.cfg.get("status_file")
        self.started_at = time.time()
        self._stop = threading.Event()
        self._status_thread = None

        # 日志级别：上游 RouterBridge 只有「打不打逐帧日志」一个开关（模块级 LOG）。
        # 更细的分级要改上游，本仓不擅自改（见 vendor/orpah/VENDOR.md）。
        orpah_router.LOG = (self.cfg["log_level"] != "warn")

        self.bridge = orpah_router.RouterBridge(
            ap_port=self.cfg["ap_port"],
            ap_host=self.cfg["ap_host"],
            server_port=self.cfg["server_port"],
            server_host=self.cfg["server_host"],
            self_mac=config.mac_to_bytes(self.cfg["self_mac"]),
        )

    # ---------------- 生命周期 ----------------
    def start(self):
        """连空口 + 起桥线程；连不上返回 False（由调用方决定让 procd 稍后重试）。"""
        if not self.bridge.start():
            return False
        self._write_status()           # 立刻落一份：LuCI/排障不用等第一个周期
        self._status_thread = threading.Thread(target=self._status_loop,
                                               name="orpah-status", daemon=True)
        self._status_thread.start()
        return True

    def stop(self):
        self._stop.set()
        try:
            self.bridge.stop()
        except Exception as e:          # noqa: BLE001 - 收尾失败不该掩盖正常退出
            print("[orpah] 退出收尾时出错：%r" % (e,), flush=True)

    # ---------------- 状态（给 rpcd / LuCI 读） ----------------
    def status(self):
        b = self.bridge
        return {
            "ok": True,
            "station_id": self.cfg["station_id"],
            "ap": "%s:%d" % (self.cfg["ap_host"], self.cfg["ap_port"]),
            "server": "%s:%d" % (self.cfg["server_host"], self.cfg["server_port"]),
            "log_level": self.cfg["log_level"],
            "up_count": int(b.up_count),           # 转发给 Server 的 REPORT 条数
            "id_up_count": int(b.id_up_count),     # 透传的 ID-REPORT 条数（不占 up_count）
            "down_count": int(b.down_count),       # 注入回空口的帧数
            "found_count": int(b.found_count),     # ORPAH-FOUND 发现上报次数
            "lost_push_recv": int(getattr(b, "lost_push_recv", 0)),  # 收到 Server 主动推送的走失表次数
            "lost_cache": len(b.lost_cache),       # 本地走失缓存条数
            # 上游私有字段（RouterBridge._synced）：改上游时要跟着改这里。
            # 语义 = 是否成功拿到过权威走失表（拿不到时 REQ-CONNECT 只能答 NOT-TRACKED）。
            "synced": bool(getattr(b, "_synced", False)),
            "started_at": int(self.started_at),
            "uptime": int(time.time() - self.started_at),
        }

    def _write_status(self):
        """原子写状态文件；写失败只记不抛（状态可视性不该把主进程拖垮）。"""
        if not self.status_file:
            return
        try:
            d = os.path.dirname(os.path.abspath(self.status_file))
            if d:
                os.makedirs(d, exist_ok=True)
            tmp = self.status_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.status(), f, ensure_ascii=False)
            os.replace(tmp, self.status_file)
        except OSError as e:
            print("[orpah] 状态写入失败（%s）：%s" % (self.status_file, e), flush=True)

    def _status_loop(self):
        while not self._stop.wait(STATUS_INTERVAL):
            self._write_status()


def build_parser():
    ap = argparse.ArgumentParser(
        prog="router_daemon.py",
        description="ORPAH Router 守护进程（空口接入点 host 口 ⇄ UDP ⇄ Server）")
    ap.add_argument("--config", metavar="FILE",
                    help="UCI 文件（OpenWrt 上就是 /etc/config/orpah）或 key=value 文件；"
                         "不给则只用内置默认值")
    ap.add_argument("--status-file", metavar="FILE",
                    help="状态 JSON 落盘路径（rpcd/LuCI 读）；不给则不写")
    # 下面这些是「临时覆盖」用（排查时手动指一个 Server），正常运行都由 --config 提供
    ap.add_argument("--station-id")
    ap.add_argument("--ap-host")
    ap.add_argument("--ap-port", type=int)
    ap.add_argument("--server-host")
    ap.add_argument("--server-port", type=int)
    ap.add_argument("--self-mac")
    ap.add_argument("--log-level", choices=list(config.LOG_LEVELS))
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    overrides = {}
    for k in config.FIELDS:
        v = getattr(args, k.replace("-", "_"), None)
        if v is not None:
            overrides[k] = v

    try:
        cfg = config.load(args.config, overrides)
    except config.ConfigError as e:
        # 打清楚、退出码非 0：启动失败要能在 logread 里一眼看到原因
        print("[orpah] 配置错误：%s" % e, file=sys.stderr, flush=True)
        return 2
    cfg["status_file"] = args.status_file

    print("[orpah] 启动 站位=%s 空口=%s:%d Server=%s:%d 日志=%s%s"
          % (cfg["station_id"] or "(未命名)", cfg["ap_host"], cfg["ap_port"],
             cfg["server_host"], cfg["server_port"], cfg["log_level"],
             "" if not cfg["status_file"] else " 状态文件=%s" % cfg["status_file"]),
          flush=True)

    stop = threading.Event()

    def _on_signal(signum, _frame):
        print("[orpah] 收到信号 %d，准备退出" % signum, flush=True)
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):     # 非主线程 / 平台不支持
            pass

    daemon = Daemon(cfg)
    if not daemon.start():
        print("[orpah] 启动失败：连不上空口接入点 %s:%d（procd 会稍后重试）"
              % (cfg["ap_host"], cfg["ap_port"]), file=sys.stderr, flush=True)
        daemon.stop()
        return 1

    try:
        while not stop.wait(0.5):
            pass
    finally:
        daemon.stop()
    print("[orpah] 已退出", flush=True)
    return 0

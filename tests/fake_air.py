# -*- coding: utf-8 -*-
"""tests/fake_air.py — 假空口 / 假 Server（测试夹具，不是产品代码）

用它们把 daemon **真跑起来**（进程内）验证上下行，不需要 OpenWrt、也不需要上游的模拟器：

    FakeAp     = 「AP 模块的 host 数据口」：TCP 服务端 + `AA 55 …` 帧格式
    FakeServer = ORPAH Server：UDP，收到 LOST-TABLE-REQ 自动回一份表（否则 daemon
                 启动拉表要白等 1.5s 超时，测试会变慢且不确定）

⚠ 帧的编解码**复用上游 `host_bus.py`**（把已 accept 的连接装进一个 `HostBus` 实例），
   不在这里另写一份帧格式实现 —— 否则测的是夹具而不是被测代码，夹具对了代码错了也测不出来。
"""

import socket
import threading

from host_bus import HostBus                     # 上游：帧编解码 + 收发线程
from orpah_proto import (MSG_LOST_TABLE_REQ, build_eth_frame, build_lost_table,
                         decode_msg, encode_msg, parse_eth_frame)
from waiting import wait_until

__all__ = ["STA_MAC", "sta_frame", "FakeAp", "FakeServer"]

#: 假 STA 的 MAC（源地址；daemon 侧只按以太类型过滤，这里给个确定的可断言值）
STA_MAC = bytes([0x02, 0x00, 0x00, 0x00, 0x00, 0x11])


def sta_frame(msg):
    """报文 → STA 发往 AP 的以太网帧（空口上行方向的字节流）。"""
    return build_eth_frame(encode_msg(msg), src_mac=STA_MAC)


class FakeAp:
    """假 AP 模块的 host 数据口（TCP 服务端）。"""

    def __init__(self):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))          # 端口 0 = 让内核挑一个空闲端口
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.bus = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        self.srv.settimeout(0.2)
        while not self._stop.is_set():
            try:
                conn, _ = self.srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            bus = HostBus("127.0.0.1", 0, name="fake-ap")
            bus.sock = conn                      # 直接装上已 accept 的连接，复用上游的收发/解析
            bus._reader = threading.Thread(target=bus._read_loop, daemon=True)
            bus._reader.start()
            self.bus = bus
            return

    def wait_connected(self, timeout=10.0):
        """等 daemon 连上来（连上才能注入/收帧）。"""
        return wait_until(lambda: self.bus is not None, timeout=timeout)

    # ---------------- 空口 → host（daemon） ----------------
    def inject(self, eth_frame):
        """模拟「AP 从空口收到一帧」→ 推给 daemon。"""
        if self.bus is None:
            return False
        return self.bus.send_frame(eth_frame)

    # ---------------- host（daemon）→ 空口 ----------------
    def recv_frame(self, timeout=2.0):
        """取 daemon 注入的下行以太网帧（无则 None）。"""
        return self.bus.recv_frame(timeout=timeout) if self.bus else None

    def recv_msg(self, timeout=2.0):
        """取一帧并解析成报文（无 / 解析不出则 None）。"""
        eth = self.recv_frame(timeout=timeout)
        if eth is None:
            return None
        parsed = parse_eth_frame(eth)
        return decode_msg(parsed[1]) if parsed else None

    def close(self):
        self._stop.set()
        try:
            self.srv.close()
        except OSError:
            pass
        if self.bus:
            self.bus.close()


class FakeServer:
    """假 ORPAH Server（UDP 一侧）。"""

    def __init__(self, lost_entries=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.lost_entries = list(lost_entries or [])
        self.msgs = []                    # 收到的上行报文（按到达顺序）
        self.client = None                # 最近一次上行的来源地址（回下行要用）
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            msg = decode_msg(data)
            if msg is None:
                continue
            with self._lock:
                self.msgs.append(msg)
                self.client = addr
            if msg.get("type") == MSG_LOST_TABLE_REQ:
                # 自动应答拉表（带 rid 原样回显）——否则 daemon 启动要等满超时
                self.send_lost_table(rid=msg.get("rid"))

    # ---------------- 发下行 ----------------
    def send(self, msg):
        with self._lock:
            addr = self.client
        if addr is None:                  # 还没收到过上行 → 不知道回给谁
            return False
        self.sock.sendto(encode_msg(msg), addr)
        return True

    def send_lost_table(self, entries=None, rid=None):
        """下发走失表：不给 rid = **主动推送**（daemon 计 lost_push_recv）；给 rid = 拉表应答。"""
        e = self.lost_entries if entries is None else entries
        return self.send(build_lost_table(e, rid=rid))

    # ---------------- 收上行 ----------------
    def count(self, mtype):
        with self._lock:
            return sum(1 for m in self.msgs if m.get("type") == mtype)

    def wait_msg(self, mtype, timeout=5.0):
        """等**累计第 1 条**该类型上行；超时返回 None（调用方必须断言，别静默继续）。"""
        if not wait_until(lambda: self.count(mtype) >= 1, timeout=timeout):
            return None
        with self._lock:
            return next(m for m in self.msgs if m.get("type") == mtype)

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass

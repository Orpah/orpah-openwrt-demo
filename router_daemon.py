#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ORPAH Router 守护进程入口（PC 与 OpenWrt 通用）

PC 上直接跑（用仓库里那份 OpenWrt 配置，不需要改任何东西）：

    python router_daemon.py --config files/etc/config/orpah --status-file status.json

OpenWrt 上由 `/etc/init.d/orpah`（procd）调起：

    /usr/bin/python3 -u /usr/lib/orpah/router_daemon.py \\
        --config /etc/config/orpah --status-file /var/run/orpah/status.json

这里只负责「让 import 能用」与「stdout/stderr 编码」；进程编排在 `orpahd/daemon.py`。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Windows 控制台默认代码页 GBK/cp936：中文输出会乱码，遇到 emoji 还会抛
# UnicodeEncodeError。可执行脚本一律强制 UTF-8（上游 orpah 各脚本同一做法）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                  # noqa: BLE001 - 老解释器/被重定向时不强求
        pass

from orpahd.daemon import main         # noqa: E402  （必须在 sys.path 设置之后）

if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""orpahd — ORPAH Router 守护进程（OpenWrt 侧业务壳）。

本包只放「壳」：
  · `config.py` —— 配置读取（单一源 = UCI 文件）
  · `daemon.py` —— 进程编排（配置 → RouterBridge → 状态落盘 → 信号）
业务逻辑（报文、走失表缓存、上下行桥接）**不在这里**，在 `vendor/orpah/router.py`
（从 orpah-over-halow 逐字节复制，见 `vendor/orpah/VENDOR.md`）。
"""

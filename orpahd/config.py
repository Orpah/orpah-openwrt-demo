# -*- coding: utf-8 -*-
"""orpahd.config — 配置读取（字段的单一源 = OpenWrt 的 UCI 文件）

## 为什么 daemon 自己读 UCI，而不让 init 脚本逐项 `config_get` 后传命令行参数

OpenWrt 惯例是 init 脚本读 UCI → 拼参数。那样同一个字段名会同时出现在**三处**
（① `/etc/config/orpah` ② `/etc/init.d/orpah` ③ LuCI 表单），任何一处拼错都是
「配置静默失效」——最难查的一类 bug（改了个像生效的值，进程却按旧默认值跑）。
本仓只保留**一处**：

  · init 脚本只为 `enabled` 读一次 UCI（决定要不要起进程），其余一概不管；
  · daemon 自己解析 `/etc/config/orpah`（下面 30 行 UCI 文本解析，不依赖 `uci` 命令）；
  · LuCI 表单直接读写同一份 UCI。

额外好处：PC 上可以直接拿仓库里那份 `files/etc/config/orpah` 跑起来，不用装 OpenWrt。
代价：UCI 语法只认用得到的 `config` / `option`（`list`、嵌套段等未实现，本仓也用不到）。

## 字段

`FIELDS` 是 daemon 消费的字段全集。`enabled` **故意不在** `FIELDS` 里 —— 它只由
init 脚本消费（daemon 起不起进程由 procd 决定，不由自己判断）。
"""

import os
import re

__all__ = ["ConfigError", "FIELDS", "LOG_LEVELS", "DEFAULTS", "looks_like_uci",
           "parse_uci", "parse_simple", "parse_text", "mac_to_bytes", "load"]


class ConfigError(Exception):
    """配置不可用。消息要能直接给人看：说清**哪个字段、读到了什么、期望什么**。"""


#: daemon 消费的字段（顺序 = README/文档里的展示顺序；名称必须与 files/etc/config/orpah 一致）
FIELDS = ("station_id", "ap_host", "ap_port", "server_host", "server_port",
          "self_mac", "log_level")

PORT_FIELDS = ("ap_port", "server_port")

#: 目前只做两级：info = 逐帧日志（上游 RouterBridge 的默认）；warn = 关掉逐帧日志只留错误。
#: 更细的级别需要上游 `router.py` 支持分级日志，本仓不擅自改（见 vendor/orpah/VENDOR.md）。
LOG_LEVELS = ("info", "warn")

DEFAULTS = {
    "station_id": "",
    "ap_host": "127.0.0.1",
    "ap_port": 9421,           # 模拟器 host 数据口（sim.py --host <port>）
    "server_host": "127.0.0.1",
    "server_port": 19447,      # ORPAH UDP 端口（orpah_proto.ORPAH_UDP_PORT）
    "self_mac": "4A:06:59:80:00:01",
    "log_level": "info",
}

_RE_CONFIG = re.compile(r"^\s*config\s+(\S+)(?:\s+(\S+))?\s*$")
_RE_OPTION = re.compile(r"^\s*option\s+(\S+)\s+(.*?)\s*$")
_RE_SIMPLE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _unquote(value):
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _strip_comment(line):
    """去掉行尾注释。本仓的值里不会出现 `#`（都是地址/端口/MAC/级别）。"""
    return line.split("#", 1)[0]


def looks_like_uci(text):
    """含 `config <type>` 行 → 当 UCI 解析（文件后缀无关，PC 上直接喂 UCI 文件）。"""
    return any(_RE_CONFIG.match(l) for l in text.splitlines())


def parse_uci(text, section_type="orpah"):
    """UCI 文本 → {字段: 字符串}。

    只收集 `config <section_type>` 段下的 `option`；**名字段也收**（是否属于本包由
    调用方用 `FIELDS` 筛）—— 这样别的段（比如别包的配置）会被自然忽略。
    """
    out = {}
    in_section = False
    for line in text.splitlines():
        s = _strip_comment(line).rstrip()
        if not s.strip():
            continue
        m = _RE_CONFIG.match(s)
        if m:
            in_section = (m.group(1) == section_type)
            continue
        if not in_section:
            continue
        m = _RE_OPTION.match(s)
        if m:
            out[m.group(1)] = _unquote(m.group(2))
    return out


def parse_simple(text):
    """`key = value` 文本 → dict（PC 上手工调参用的简写格式）。"""
    out = {}
    for line in text.splitlines():
        s = _strip_comment(line).strip()
        if not s:
            continue
        m = _RE_SIMPLE.match(s)
        if m:
            out[m.group(1)] = _unquote(m.group(2))
    return out


def parse_text(text):
    """按内容自动选择 UCI / 简单格式。"""
    return parse_uci(text) if looks_like_uci(text) else parse_simple(text)


def mac_to_bytes(mac):
    """`'4A:06:59:80:00:01'`（或 `-` 分隔、或 6 字节 bytes）→ 6 字节 bytes；非法返回 None。"""
    if isinstance(mac, (bytes, bytearray)):
        return bytes(mac) if len(mac) == 6 else None
    parts = str(mac).strip().replace("-", ":").split(":")
    if len(parts) != 6 or any(not p for p in parts):
        return None
    try:
        return bytes(int(p, 16) for p in parts)
    except ValueError:
        return None


def _int_field(name, raw):
    try:
        v = int(str(raw).strip())
    except (TypeError, ValueError):
        raise ConfigError("%s 必须是整数，实际读到 %r" % (name, raw))
    if not (1 <= v <= 65535):
        raise ConfigError("%s 必须在 1..65535 之间，实际 %d" % (name, v))
    return v


def load(path=None, overrides=None):
    """读出配置 dict。

    path      —— 配置文件（UCI 或 key=value）；None = 只用默认值
    overrides —— 命令行覆盖（**只认 FIELDS 里的键**，值为 None 表示不覆盖）

    非法值一律抛 `ConfigError`（宁可退出码非 0 让 procd 日志里看得见，也不静默用默认值跑 ——
    「改了配置像没改」比「起不来」难查得多）。
    """
    raw = {}
    if path:
        if not os.path.isfile(path):
            raise ConfigError("配置文件不存在：%s" % path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = parse_text(f.read())

    cfg = dict(DEFAULTS)
    for k, v in raw.items():
        if k in FIELDS:            # 未知键忽略：`enabled` 等由别的组件消费
            cfg[k] = v
    for k, v in (overrides or {}).items():
        if v is not None and k in FIELDS:
            cfg[k] = v

    for k in PORT_FIELDS:
        cfg[k] = _int_field(k, cfg[k])

    for k in ("station_id", "ap_host", "server_host"):
        cfg[k] = str(cfg[k]).strip()
    if not cfg["ap_host"]:
        raise ConfigError("ap_host 不能为空（空口接入点地址/主机名）")
    if not cfg["server_host"]:
        raise ConfigError("server_host 不能为空（ORPAH Server 地址/主机名）")

    lvl = str(cfg["log_level"]).strip().lower()
    if lvl not in LOG_LEVELS:
        raise ConfigError("log_level 只能是 %s，实际读到 %r"
                          % ("/".join(LOG_LEVELS), cfg["log_level"]))
    cfg["log_level"] = lvl

    if mac_to_bytes(cfg["self_mac"]) is None:
        raise ConfigError("self_mac 不是合法 MAC（6 组十六进制，如 4A:06:59:80:00:01）：%r"
                          % (cfg["self_mac"],))
    return cfg

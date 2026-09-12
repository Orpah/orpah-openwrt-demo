# vendor/orpah — 从 orpah-over-halow 逐字节复制（本目录文件一律不改）

本目录是**路由器侧要用的那部分协议/桥接代码**，来源仓库是
`orpah-over-halow`（ORPAH 业务逻辑的**唯一源**）。选择「复制」而不是「引用」，
是为了让本仓**自带一份可运行副本**：`orpah-openwrt-demo` 不需要邻居仓库就能起 daemon
（与 `orpah-over-halow` 自带 `vendor/halow/` 是同一个理由）。

## 来源与逐字节核对

- 来源仓库：`F:\git\orpah-over-halow`（GitHub `Orpah/orpah-over-halow`，Apache-2.0）
- 来源提交：`de29736`（2026-09-12）

| 文件 | 上游 git blob hash | 用途 |
|---|---|---|
| `orpah_proto.py` | `07cce85359eabf80b4cb34c0af1a8ef734c10b8c` | 报文定义 / JSON 编解码 / 以太网封装（L1+L2） |
| `host_bus.py` | `28bdda86c37839c9d2a9d64592f19d931935e374` | 模拟器 host 数据口驱动（TCP + `AA 55 …` 帧格式） |
| `router.py` | `3499d83f720a37b0e032bcbee3f7714199e713fe` | `RouterBridge`：AP ⇄ UDP ⇄ Server 双向桥（**业务主体**） |
| `waiting.py` | `eda7d432220e74c6a50e5d1603f9426c1cd652dd` | `wait_until` / `wait_new`（测试与脚本等待用；禁止「猜次数」等待） |

复制（上游改完后重跑；本仓不要手改这些文件）：

```powershell
cd F:\git\orpah-openwrt-demo
foreach ($f in @('orpah_proto.py','host_bus.py','router.py','waiting.py')) {
  Copy-Item "F:\git\orpah-over-halow\$f" vendor\orpah\
}
```

核对（两边输出必须逐个相同）：

```powershell
foreach ($f in @('orpah_proto.py','host_bus.py','router.py','waiting.py')) {
  git hash-object "vendor/orpah/$f"
  git -C F:\git\orpah-over-halow hash-object $f
}
```

## 纪律

1. **本目录的文件不许改。** 要改就回 `orpah-over-halow` 改，改完重新复制过来并更新上面的
   hash 表 —— 否则两份实现漂移，真机上出的问题会无法复现（这正是上游
   `vendor/halow/VENDOR.md` 立下的同一规矩）。
2. 上游 `router.py` 面向的是「PC + 模拟器（TCP host 口）」。真机上「空口」是 TH-RJ45 模组
   经 **RJ45** 送来的 802.3 帧（以太类型 `0x88B5`），**不是** TCP host 口 —— 真机上线需要给
   `RouterBridge` 开一个「可注入传输」的口子（**尚未做**，属下一阶段，见 README「未做」）。
   本阶段（PC 可跑）用的就是上游原样的 TCP 传输。
3. 上游的 `waiting.py` 规则同样适用：任何等待都要能回答「等的是什么条件、超时多少、超时后怎么办」，
   禁止 `for _ in range(N): sleep(...)` 这种猜次数等待。

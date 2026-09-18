# ORPAH Router（OpenWrt 侧）开发规则 — `orpah-openwrt-demo`

本仓 = ORPAH 三个仓库里的**第三个**：把「路由器那一段」搬上 OpenWrt。
分工：`halow-demo` = 空口/设备/长距（不碰业务）；`orpah-over-halow` = 业务全链路（纯 PC）；
**本仓 = 路由器侧**（daemon + OpenWrt 包 + LuCI 薄前端）。

> 详细踩坑记录与架构说明见 `README.md`；上游业务规则见 `orpah-over-halow/AGENTS.md`。

## 0. 范围原则：**不碰真机**（2026-09-13 用户定，阶段 B）

- 用户明确选定：**先只做「能在普通 Linux/PC 上跑的 daemon + OpenWrt 包骨架」，不碰真机**。
- 因此：**不做**板级烧录/刷机/上机；**不承诺**「在 OpenWrt 上验证过」。所有与真机相关的
  部分（SDK 构建、LuCI 真渲染、网口传输、AT 配无线）一律**如实标注「未验证/未做」**，
  不许写成「已支持」。
- 需要真机动作时：只做调研、备好文件与步骤，**由用户执行**。

## 1. 业务逻辑不在本仓（vendor 纪律）

- `vendor/orpah/{orpah_proto,host_bus,router,waiting}.py` 是从 `orpah-over-halow`
  **逐字节复制**的，**不许改**。
- 要改业务/协议 → 回 `orpah-over-halow` 改 → 重新复制 → **更新 `vendor/orpah/VENDOR.md`
  的来源提交与 hash 表**（改完必须用 `git hash-object` 两边对照一次）。
- 本仓的代码只允许做两件事：**配置来源**（UCI）与**传输实现**（PC 的 TCP host 口；
  真机 AF_PACKET 待做）。发现「需要改 vendor 才能实现」时，先停下来与用户对齐。

## 2. 配置：字段的单一源 = `/etc/config/orpah`

- 字段名只允许写在 `files/etc/config/orpah`；init 脚本**只读 `enabled`**，其余由 daemon
  自己解析（`orpahd/config.py` 里的取舍说明）。
- 新增字段要同时改：UCI 默认文件、`orpahd/config.py` 的 `FIELDS`/`DEFAULTS`、
  LuCI 视图表单（如需可改）——`tests/test_package_files.py` 会守住三处一致性。
- 非法配置一律**抛 `ConfigError` 并以退出码 2 退出**（宁可起不来 + logread 里有原因，
  也不要「改了配置像没改」这种静默失效）。

## 3. 自检口径

- **改完任何东西先跑 `python run_checks.py`**（三套件，约 1 秒，都不需要 OpenWrt/真机/模拟器）。
- 判定 = 退出码 0 **且** 输出无 `FAIL` / `Traceback`（有些脚本自己吞异常还会往下跑）。
- 报告 `checks_report.md` 入库（同上游惯例），便于「上次是不是全绿」。
- 静态检查也在套件里：`sh -n`（两个 shell 脚本）、`node --check`（LuCI 视图）、JSON 可解析、
  Makefile recipe 必须 TAB、`$(CURDIR)/…` 引用的文件必须存在、安装路径与 daemon 的
  import 期望一致。本机缺 `sh`/`node` 时**明确跳过**（不能默默当通过）。
- 端到端套件用 `tests/fake_air.py`（假 AP + 假 Server，**复用上游 host_bus 的帧编解码**）。
  **不要**在夹具里另写一份帧格式 —— 那会变成「测夹具」而不是「测代码」。

## 4. 等待与超时（沿用上游铁律）

- 任何等待都用 `wait_until(cond, timeout=…)`（`vendor/orpah/waiting.py`），**禁止**
  `for _ in range(N): time.sleep(…)` 这种猜次数等待；超时要**可见地失败**，不许静默继续。
- 判据要能回答：「等的是什么条件、超时多少、超时后怎么办」。

## 5. 环境坑（Windows 本机，都是真踩过的）

- **`subprocess` 输出默认按 GBK/936 解码**：`sh`/`node` 的输出是 UTF-8 → 读线程里抛
  `UnicodeDecodeError`，且 `stderr` 变成 `None`（连带断言消息自己炸）。
  必须写 `capture_output=True, encoding="utf-8", errors="replace"`。
- **`shutil.which("sh")` 会找到 WSL 的 `bash.exe`**（`C:\Windows\System32\bash.exe`），
  它看不到 `F:/…` 路径 → 假失败。优先用 Git 自带的 `D:\Program Files\Git\bin\sh.exe`，
  并在仓库根用**相对正斜杠路径**（MSYS sh 不认反斜杠）。
- **`create_and_run_task` 的命令 JSON 会吃掉 ASCII 双引号** → `python -c "…"`、`-Value "…"`
  一律坏；改开临时脚本，或用单引号/`-LiteralPath`。
- **同步终端撞上 `>>` 续行提示会永久卡死** → 换新任务终端；`git log` 要带 `--no-pager`。
- **不要用 PowerShell 改含中文的源码**（`Get-Content` 按 ANSI 读会毁掉 UTF-8，编译直接语法错）；
  文件一律 UTF-8。脚本里打印中文要先 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`。
- `.gitignore` 必须显式写 `__pycache__/` + `*.pyc`：上游踩过「迁出子集时规则不跟着走 →
  首次 `git add -A` 把 27 个 .pyc 吃进库」（`orpah-over-halow` 的 `de29736`）。

## 6. 协作约定

- **★ 只提交「我自己创建的文件」**（2026-09-18 用户定，**适用于所有项目**）：我写的源码/文档/脚本 =
  我们的成果（有版权），可以入库；**不是我创建的一律不提交** —— 厂商手册 PDF、SDK 源码、固件 bin、
  安装包、下载的第三方素材**都没有版权**，入库即无授权传播。提交前 `git rev-parse --show-toplevel`
  确认仓库，**禁止 `git add -A`**（一律显式写路径），提交后 `git show --stat` 核一遍清单。
  ★ 反面教训（2026-09-16）：终端丢掉 `Set-Location` → `git add -A` 落到 `F:\git\tianlu`
  （19 个厂商 PDF + 整个 SDK 投放物 6937 文件被提交成 `e2e8a89`）。已撤销。
- **push 永远由用户自己做**；提交前先跑 `run_checks.py`。
- 改公共/打包文件（`Makefile`、`files/`、`vendor/`）前先与用户对齐。
- 不确定的物理/协议事实**先问清再动手**，不要自由发挥（上游同名规则）。

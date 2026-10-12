# ORPAH Router 自检报告（OpenWrt 侧）

- 生成时间：2026-10-12 15:27:09
- HEAD：`0127d66`
- Python：3.13.14
- 结果：**3/3 通过**

> 全部套件都**不需要** OpenWrt / 真机 / 上游模拟器（进程内假 AP + 假 Server）。
> 判定 = 退出码 0 **且** 输出无 `FAIL` / `Traceback`。

| 套件 | 结果 | 用时 | 退出码 |
|---|---|---|---|
| 配置解析（UCI / 简写 / 非法值） | 通过 | 0.24s | 0 |
| 打包文件一致性 + 语法检查 | 通过 | 0.46s | 0 |
| daemon 端到端（假 AP + 假 Server） | 通过 | 0.84s | 0 |

## 配置解析（UCI / 简写 / 非法值）

```
test_forms (__main__.TestMacToBytes.test_forms) ... ok
test_invalid (__main__.TestMacToBytes.test_invalid) ... ok
test_cli_overrides_file (__main__.TestOverrides.test_cli_overrides_file)
命令行覆盖 > 文件 > 默认值（排查时临时指一个 Server 用）。 ... ok
test_none_override_means_no_override (__main__.TestOverrides.test_none_override_means_no_override) ... ok
test_auto_detect_by_content (__main__.TestParseSimple.test_auto_detect_by_content) ... ok
test_comments_and_blank_lines (__main__.TestParseSimple.test_comments_and_blank_lines) ... ok
test_simple_format (__main__.TestParseSimple.test_simple_format) ... ok
test_enabled_is_not_a_daemon_field (__main__.TestParseUci.test_enabled_is_not_a_daemon_field)
`enabled` 只给 init 脚本用：解析出来可以，但不能进 daemon 的字段集。 ... F:\git\orpah-openwrt-demo\tests/test_config.py:51: ResourceWarning: unclosed file <_io.TextIOWrapper name='F:\\git\\orpah-openwrt-demo\\files\\etc\\config\\orpah' mode='r' encoding='utf-8'>
  self.assertIn("enabled", config.parse_uci(open(UCI_FILE, encoding="utf-8").read()))
ResourceWarning: Enable tracemalloc to get the object allocation traceback
ok
test_parse_uci_only_collects_own_section (__main__.TestParseUci.test_parse_uci_only_collects_own_section) ... ok
test_repo_uci_file_parsed (__main__.TestParseUci.test_repo_uci_file_parsed)
仓库里那份 OpenWrt 配置能被 PC 端解析器读出来（字段齐全、值正确）。 ... ok
test_unknown_keys_ignored (__main__.TestParseUci.test_unknown_keys_ignored)
UCI 里别的包的字段/未来字段不该让 daemon 崩。 ... ok
test_bad_log_level (__main__.TestValidation.test_bad_log_level) ... ok
test_bad_mac (__main__.TestValidation.test_bad_mac) ... ok
test_empty_host (__main__.TestValidation.test_empty_host) ... ok
test_missing_file (__main__.TestValidation.test_missing_file) ... ok
test_port_not_a_number (__main__.TestValidation.test_port_not_a_number) ... ok
test_port_out_of_range (__main__.TestValidation.test_port_out_of_range) ... ok

----------------------------------------------------------------------
Ran 17 tests in 0.035s

OK
```

## 打包文件一致性 + 语法检查

```
test_daemon_covers_luci_editable_fields (__main__.TestFieldNames.test_daemon_covers_luci_editable_fields)
LuCI 能改的字段，daemon 必须真的消费（否则是「填了没用」的假开关）。 ... ok
test_init_script_fields_declared (__main__.TestFieldNames.test_init_script_fields_declared)
init 脚本从 UCI 只读 `enabled`（其余全交给 daemon）—— 读的字段必须在 UCI 里。 ... ok
test_luci_form_fields_declared (__main__.TestFieldNames.test_luci_form_fields_declared) ... ok
test_uci_declares_every_daemon_field (__main__.TestFieldNames.test_uci_declares_every_daemon_field) ... ok
test_json_files_valid (__main__.TestLuciWiring.test_json_files_valid) ... ok
test_menu_acl_matches_acl_file (__main__.TestLuciWiring.test_menu_acl_matches_acl_file)
菜单里声明的 ACL 名必须与 acl.d 里的对象名一致，否则页面永远打不开。 ... ok
test_rpcd_script_exposes_status (__main__.TestLuciWiring.test_rpcd_script_exposes_status) ... ok
test_view_path_matches_install_target (__main__.TestLuciWiring.test_view_path_matches_install_target)
菜单 action.path 与视图文件路径、Makefile 安装路径三者必须对得上。 ... ok
test_config_is_conffile (__main__.TestMakefile.test_config_is_conffile) ... ok
test_daemon_layout_matches_import_path (__main__.TestMakefile.test_daemon_layout_matches_import_path)
安装布局必须让 daemon 的相对 vendor 路径成立（<root>/{orpahd,vendor/orpah}）。 ... ok
test_install_recipes_use_tabs (__main__.TestMakefile.test_install_recipes_use_tabs)
recipe 行必须以 TAB 开头（用空格 make 直接报 missing separator）。 ... ok
test_installed_files_exist (__main__.TestMakefile.test_installed_files_exist)
Makefile 里 $(CURDIR)/… 引用的每个文件都必须真的在仓库里。 ... ok
test_gitignore_covers_bytecode (__main__.TestRepoHygiene.test_gitignore_covers_bytecode) ... ok
test_no_tracked_pyc (__main__.TestRepoHygiene.test_no_tracked_pyc)
仓库里不该有被跟踪的字节码（上游踩过：迁出时 27 个 .pyc 被误提交）。 ... ok
test_luci_view_js (__main__.TestSyntax.test_luci_view_js) ... ok
test_shell_scripts (__main__.TestSyntax.test_shell_scripts) ... ok

----------------------------------------------------------------------
Ran 16 tests in 0.336s

OK
```

## daemon 端到端（假 AP + 假 Server）

```
test_id_report_forwarded_and_counted_separately (__main__.DaemonE2E.test_id_report_forwarded_and_counted_separately)
ID-REPORT 走同一条通路但**不占 REPORT 计数**（页面按内容分色就靠这两个数分开）。 ... ok
test_lost_table_push_makes_it_tracked_and_reports_found (__main__.DaemonE2E.test_lost_table_push_makes_it_tracked_and_reports_found)
Server 主动推一张表（带该 sn 且 tracked）→ 之后命中：答 TRACKED 并报 ORPAH-FOUND。 ... ok
test_lost_table_untrack_removes_it (__main__.DaemonE2E.test_lost_table_untrack_removes_it)
撤销走失（tracked=False）后要回到 NOT-TRACKED。 ... ok
test_report_forwarded_to_server (__main__.DaemonE2E.test_report_forwarded_to_server) ... ok
test_req_connect_not_tracked_when_cache_empty (__main__.DaemonE2E.test_req_connect_not_tracked_when_cache_empty) ... ok
test_status_file_missing_is_not_fatal (__main__.DaemonE2E.test_status_file_missing_is_not_fatal)
不给 --status-file 时不该写文件、也不该报错（PC 上临时跑）。 ... ok
test_status_file_reflects_traffic (__main__.DaemonE2E.test_status_file_reflects_traffic) ... ok
test_status_file_written_and_parseable (__main__.DaemonE2E.test_status_file_written_and_parseable) ... ok
test_tracking_status_injected_back_to_air (__main__.DaemonE2E.test_tracking_status_injected_back_to_air) ... ok
test_unparsable_frame_is_ignored (__main__.DaemonE2E.test_unparsable_frame_is_ignored)
非 ORPAH 以太类型 / 垃圾载荷不该让 daemon 崩，也不该产生上行。 ... ok
test_main_returns_2_on_bad_config (__main__.TestConfigErrorPath.test_main_returns_2_on_bad_config)
配置坏掉要以退出码 2 退出并打出原因（procd 日志里能看见；不静默用默认值跑）。 ... [orpah] 配置错误：ap_port 必须是整数，实际读到 '不是数字'
ok
test_main_returns_2_when_file_missing (__main__.TestConfigErrorPath.test_main_returns_2_when_file_missing) ... [orpah] 配置错误：配置文件不存在：C:\Users\SHI~1.JIN\AppData\Local\Temp\orpah-definitely-missing.conf
ok

----------------------------------------------------------------------
Ran 12 tests in 0.558s

OK
```

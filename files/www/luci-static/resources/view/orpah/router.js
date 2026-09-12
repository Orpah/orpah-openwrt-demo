'use strict';
'require view';
'require form';
'require rpc';
'require poll';

/*
 * ORPAH Router —— LuCI 薄前端
 *
 * 两块内容：
 *   ① 运行状态：读 `ubus call orpah status`（rpcd 脚本把 daemon 落的
 *      /var/run/orpah/status.json 透出来），每 5s 刷新一次；
 *   ② 配置表单：直接读写 /etc/config/orpah（字段的单一源），提交后由
 *      procd 的 reload trigger 重启 daemon。
 *
 * 刻意**不做**的：不做 HaLow 无线参数（SSID / 频点 / 带宽 / PSK）——
 *   本 demo 的无线侧在 TH-RJ45 模组里，用 AT 命令经 CH340 串口配置，
 *   不是 OpenWrt 的 wlan/hostapd 那条路（见 README「LuCI 管到哪、不管什么」）。
 *
 * ⚠ 未在真机 / 真 LuCI 上运行验证（只做过 JS 语法检查），页面 DOM 细节以真机为准。
 */

var callStatus = rpc.declare({
	object: 'orpah',
	method: 'status',
	expect: { }
});

function fmt(value, dash) {
	if (value === undefined || value === null || value === '')
		return (dash !== undefined && dash !== null) ? dash : '—';
	return String(value);
}

function row(label, content) {
	return E('div', { 'class': 'cbi-value' }, [
		E('label', { 'class': 'cbi-value-title' }, label),
		E('div', { 'class': 'cbi-value-field' }, content)
	]);
}

return view.extend({
	load: function () {
		return callStatus();
	},

	render: function (status) {
		var nodes = { };
		var m, s, o;

		/* 会变的值放 <span>，poll 时只改文本，不重建 DOM */
		function live(label, key, dash) {
			var span = E('span', {}, '—');
			nodes[key] = { el: span, dash: (dash === undefined) ? null : dash };
			return row(label, span);
		}

		function applyStatus(st) {
			st = st || { };

			Object.keys(nodes).forEach(function (k) {
				nodes[k].el.textContent = fmt(st[k], nodes[k].dash);
			});

			nodes.state.el.textContent = st.ok
				? _('运行中（状态文件在更新）')
				: _('未运行（没有状态文件）');
			nodes.synced.el.textContent = st.synced ? _('已同步') : _('未同步');
			nodes.uptime.el.textContent = fmt(st.uptime, '0') + ' s';
		}

		var statusSection = E('div', { 'class': 'cbi-section' }, [
			E('h3', {}, _('运行状态')),
			live(_('状态'), 'state'),
			live(_('站位'), 'station_id'),
			live(_('空口接入点'), 'ap'),
			live(_('服务器'), 'server'),
			live(_('上行 REPORT'), 'up_count', '0'),
			live(_('上行 ID-REPORT'), 'id_up_count', '0'),
			live(_('下行注入'), 'down_count', '0'),
			live(_('发现上报'), 'found_count', '0'),
			live(_('走失缓存'), 'lost_cache', '0'),
			live(_('走失表同步'), 'synced'),
			live(_('运行时长'), 'uptime', '0'),
			live(_('日志级别'), 'log_level')
		]);

		applyStatus(status);
		poll.add(function () {
			return callStatus().then(applyStatus);
		}, 5);

		m = new form.Map('orpah', _('ORPAH Router'),
			_('字段的单一源是 /etc/config/orpah；保存并应用后 procd 会自动重启守护进程。'));

		s = m.section(form.NamedSection, 'main', 'orpah', _('设置'));
		s.addremove = false;

		o = s.option(form.Flag, 'enabled', _('启用'));
		o.rmempty = false;
		o.description = _('关闭时 /etc/init.d/orpah 不会启动守护进程（也不会随开机启动）。');

		o = s.option(form.Value, 'station_id', _('站位标识'));
		o.placeholder = 'AP-01';
		o.description = _('只用于日志与状态页显示 —— 路由器侧观测尚未实现，它目前不进任何报文。');

		o = s.option(form.Value, 'ap_host', _('空口接入点地址'));
		o.datatype = 'hostname';
		o = s.option(form.Value, 'ap_port', _('空口接入点端口'));
		o.datatype = 'port';

		o = s.option(form.Value, 'server_host', _('服务器地址'));
		o.datatype = 'hostname';
		o = s.option(form.Value, 'server_port', _('服务器端口'));
		o.datatype = 'port';

		o = s.option(form.Value, 'self_mac', _('本机 MAC'));
		o.datatype = 'macaddr';
		o.description = _('下行注入帧的源地址。');

		o = s.option(form.ListValue, 'log_level', _('日志级别'));
		o.value('info', _('info（逐帧日志）'));
		o.value('warn', _('warn（只留错误）'));

		/* form.Map.render() 返回 Promise（内部先加载 uci），所以要接住再拼 */
		return m.render().then(function (mapEl) {
			return E([ statusSection, mapEl ]);
		});
	}
});

# ORPAH Router —— OpenWrt 包（骨架）
#
# ⚠ **未在 OpenWrt SDK 上构建验证**（本机没有 SDK；构建与上机属真机阶段，由用户执行）。
#    这份 Makefile 的作用是把「包形态」先定下来：装到哪些路径、哪个文件是 conffile、
#    为什么 daemon 与 LuCI 分成两个包。
#
# 用法（在 OpenWrt 源码树里）：
#     cp -r orpah-openwrt-demo package/orpah
#     make menuconfig          # Network → orpah ；LuCI → Applications → luci-app-orpah
#     make package/orpah/compile V=s

include $(TOPDIR)/rules.mk

PKG_NAME:=orpah
PKG_VERSION:=0.1.0
PKG_RELEASE:=1

PKG_LICENSE:=Apache-2.0
PKG_LICENSE_FILES:=LICENSE
PKG_MAINTAINER:=Orpah

# 纯 Python + JS + shell，与目标架构无关
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/orpah
  SECTION:=net
  CATEGORY:=Network
  TITLE:=ORPAH router daemon (HaLow lost-person tracking)
  URL:=https://github.com/Orpah/orpah-openwrt-demo
  DEPENDS:=+python3-light
endef

define Package/orpah/description
 ORPAH-over-HaLow 路由器侧业务守护进程：把空口收到的 ORPAH 报文桥到 Server（UDP），
 并把 Server 的下行（跟踪状态 / 走失表）注入回空口。业务逻辑逐字节复用
 orpah-over-halow 的 RouterBridge（见 vendor/orpah/VENDOR.md）。
endef

define Package/orpah/conffiles
/etc/config/orpah
endef

define Package/orpah/install
	$(INSTALL_DIR) $(1)/usr/lib/orpah/orpahd $(1)/usr/lib/orpah/vendor/orpah
	$(INSTALL_DATA) $(CURDIR)/router_daemon.py $(1)/usr/lib/orpah/
	$(INSTALL_DATA) $(CURDIR)/orpahd/*.py $(1)/usr/lib/orpah/orpahd/
	$(INSTALL_DATA) $(CURDIR)/vendor/orpah/*.py $(1)/usr/lib/orpah/vendor/orpah/
	$(INSTALL_DIR) $(1)/etc/init.d $(1)/etc/config
	$(INSTALL_BIN) $(CURDIR)/files/etc/init.d/orpah $(1)/etc/init.d/orpah
	$(INSTALL_CONF) $(CURDIR)/files/etc/config/orpah $(1)/etc/config/orpah
endef

define Package/luci-app-orpah
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=LuCI support for ORPAH router
  DEPENDS:=+orpah +luci-base +rpcd
endef

define Package/luci-app-orpah/description
 ORPAH Router 的 LuCI 薄前端：一个状态页（读 daemon 落盘的状态 JSON）+ /etc/config/orpah
 的表单。无线侧参数**不在**本页 —— 见 README「LuCI 管到哪、不管什么」。
endef

define Package/luci-app-orpah/install
	$(INSTALL_DIR) $(1)/usr/share/luci/menu.d $(1)/usr/share/rpcd/acl.d
	$(INSTALL_DIR) $(1)/usr/libexec/rpcd
	$(INSTALL_DIR) $(1)/www/luci-static/resources/view/orpah
	$(INSTALL_DATA) $(CURDIR)/files/usr/share/luci/menu.d/orpah.json $(1)/usr/share/luci/menu.d/
	$(INSTALL_DATA) $(CURDIR)/files/usr/share/rpcd/acl.d/orpah.json $(1)/usr/share/rpcd/acl.d/
	$(INSTALL_BIN) $(CURDIR)/files/usr/libexec/rpcd/orpah $(1)/usr/libexec/rpcd/orpah
	$(INSTALL_DATA) $(CURDIR)/files/www/luci-static/resources/view/orpah/router.js $(1)/www/luci-static/resources/view/orpah/
endef

$(eval $(call BuildPackage,orpah))
$(eval $(call BuildPackage,luci-app-orpah))

SHELL := /bin/bash
ROOT  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SCRIPT := $(ROOT)/ufw.sh
DEFAULTS_ENV := $(ROOT)/defaults.env

comma := ,
empty :=
space := $(empty) $(empty)

# ── 默认配置（来自 defaults.env，单点维护）──────────────────────────────────
TARGET_PORTS ?= $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_DEFAULT_TARGET_PORTS")
WHITELIST_IPS ?= $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_DEFAULT_WHITELIST")
H20_43_PORTS     := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_H20_43_PORTS")
H20_43_WHITELIST := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_H20_43_WHITELIST")
H20_44_PORTS     := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_H20_44_PORTS")
H20_44_WHITELIST := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_H20_44_WHITELIST")
H100_42_PORTS     := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_H100_42_PORTS")
H100_42_WHITELIST := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_H100_42_WHITELIST")
A800_40_PORTS     := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_A800_40_PORTS")
A800_40_WHITELIST := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_A800_40_WHITELIST")
A800_43_PORTS     := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_A800_43_PORTS")
A800_43_WHITELIST := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_A800_43_WHITELIST")

# 支持逗号分隔：WHITELIST_IPS=1.2.3.4,10.0.0.0/8
WHITELIST_LIST := $(strip $(subst $(comma),$(space),$(WHITELIST_IPS)))
PORTS_LIST     := $(strip $(subst $(comma),$(space),$(TARGET_PORTS)))

export TARGET_PORTS := $(PORTS_LIST)
export WHITELIST_IPS := $(WHITELIST_LIST)

.PHONY: help enable disable status dry-run log blocked-ips \
	h20-43 h20-43-dry-run H20-43 H20-43-dry-run \
	h20-44 h20-44-dry-run H20-44 H20-44-dry-run \
	h100-42 h100-42-dry-run H100-42 H100-42-dry-run \
	a800-40 a800-40-dry-run A800-40 A800-40-dry-run \
	a800-43 a800-43-dry-run A800-43 A800-43-dry-run

DAYS ?= 1
BLOCKED_SINCE ?=

help:
	@echo "UFW + Docker DOCKER-USER 白名单防火墙"
	@echo ""
	@echo "用法:"
	@echo "  make enable                              应用规则并启用 UFW（默认仅开放 22/SSH）"
	@echo "  make disable                             关闭 UFW，恢复 DOCKER-USER"
	@echo "  make status                              查看 UFW / DOCKER-USER 状态"
	@echo "  make log                                 查看最近拦截（默认最近 1 天，表格汇总）"
	@echo "  make log DAYS=3                          查看最近 3 天拦截统计"
	@echo "  make dry-run                             打印即将使用的配置（不执行）"
	@echo "  make h20-43 | make H20-43                    主机预设：端口 22 30001 30002 2000:10000 20000，白名单=默认"
	@echo "  make h20-43-dry-run | make H20-43-dry-run    预览 h20-43 配置"
	@echo "  make h20-44 | make H20-44                    主机预设：端口 22 30002 2000:10000 20000，白名单=默认"
	@echo "  make h20-44-dry-run | make H20-44-dry-run    预览 h20-44 配置"
	@echo "  make h100-42 | make H100-42                    主机预设：端口 22 30001，白名单=默认"
	@echo "  make h100-42-dry-run | make H100-42-dry-run    预览 H100-42 配置"
	@echo "  make a800-40 | make A800-40                  主机预设：端口 22 9131 9116 10010:10034（/home/taojun/ufw.sh）"
	@echo "  make a800-40-dry-run | make A800-40-dry-run  预览 A800-40 配置"
	@echo "  make a800-43 | make A800-43                  主机预设：端口 22 8080 9111 9116 20170:20172 27171 30008 30009，白名单=默认"
	@echo "  make a800-43-dry-run | make A800-43-dry-run  预览 A800-43 配置"
	@echo ""
	@echo "覆盖配置（make 参数或 export 环境变量）:"
	@echo "  TARGET_PORTS    开放端口，空格或逗号分隔（必填，不能为空）"
	@echo "  WHITELIST_IPS   白名单，空格或逗号分隔（必填，不能为空）"
	@echo "  EXTERNAL_INTERFACE  出口网卡（可选，默认自动检测）"
	@echo "  DAYS            make log 统计最近天数（默认 1）"
	@echo "  BLOCKED_SINCE   自定义时间窗口，如 \"7 days\" / \"24 hours\"（优先于 DAYS）"
	@echo ""
	@echo "示例:"
	@echo "  make enable TARGET_PORTS=\"22 8080\""
	@echo "  make enable WHITELIST_IPS=\"211.99.216.18,192.168.0.0/16\""
	@echo "  make enable TARGET_PORTS=22 WHITELIST_IPS=1.2.3.4"
	@echo "  make h20-43                              # 或 H20-43，端口 22,30001,30002,2000:10000,20000"
	@echo "  make h20-44                              # 或 H20-44，端口 22,30002,2000:10000,20000"
	@echo "  make h100-42                             # 或 H100-42，端口 22,30001"
	@echo "  make a800-40                             # 或 A800-40，端口 22,9131,9116,10010:10034"
	@echo "  make a800-43                             # 或 A800-43，端口 22,8080,9111,9116,20170:20172,27171,30008,30009"
	@echo "  make log                                 # 最近 1 天 DOCKER-USER 拦截统计"
	@echo "  make log DAYS=7                          # 最近 7 天"
	@echo ""
	@echo "当前默认值（来自 defaults.env）:"
	@echo "  TARGET_PORTS=$(TARGET_PORTS)"
	@echo "  WHITELIST_IPS=$(WHITELIST_IPS)"

dry-run:
	@echo "TARGET_PORTS=$(PORTS_LIST)"
	@echo "WHITELIST_IPS=$(WHITELIST_LIST)"
	@if [[ -n "$(strip $(EXTERNAL_INTERFACE))" ]]; then \
		echo "EXTERNAL_INTERFACE=$(EXTERNAL_INTERFACE)"; \
	else \
		echo "EXTERNAL_INTERFACE=<自动检测>"; \
	fi

enable:
	@echo ">>> TARGET_PORTS=$(PORTS_LIST)"
	@echo ">>> WHITELIST_IPS=$(WHITELIST_LIST)"
	@EXTERNAL_INTERFACE="$(EXTERNAL_INTERFACE)" bash "$(SCRIPT)" enable

disable:
	@bash "$(SCRIPT)" disable

log blocked-ips:
	@if [[ -n "$(strip $(BLOCKED_SINCE))" ]]; then \
		BLOCKED_SINCE="$(BLOCKED_SINCE)" bash "$(SCRIPT)" blocked-ips 0; \
	elif ! [[ "$(DAYS)" =~ ^[0-9]+$$ ]] || [[ "$(DAYS)" -lt 1 ]]; then \
		echo "错误：DAYS 须为正整数（当前: $(DAYS)）" >&2; exit 1; \
	else \
		BLOCKED_SINCE="$(DAYS) days" bash "$(SCRIPT)" blocked-ips 0; \
	fi

h20-43-dry-run:
	@$(MAKE) dry-run TARGET_PORTS="$(H20_43_PORTS)" WHITELIST_IPS="$(H20_43_WHITELIST)"

h20-43:
	@$(MAKE) enable TARGET_PORTS="$(H20_43_PORTS)" WHITELIST_IPS="$(H20_43_WHITELIST)"

H20-43-dry-run: h20-43-dry-run
H20-43: h20-43

h20-44-dry-run:
	@$(MAKE) dry-run TARGET_PORTS="$(H20_44_PORTS)" WHITELIST_IPS="$(H20_44_WHITELIST)"

h20-44:
	@$(MAKE) enable TARGET_PORTS="$(H20_44_PORTS)" WHITELIST_IPS="$(H20_44_WHITELIST)"

H20-44-dry-run: h20-44-dry-run
H20-44: h20-44

h100-42-dry-run:
	@$(MAKE) dry-run TARGET_PORTS="$(H100_42_PORTS)" WHITELIST_IPS="$(H100_42_WHITELIST)"

h100-42:
	@$(MAKE) enable TARGET_PORTS="$(H100_42_PORTS)" WHITELIST_IPS="$(H100_42_WHITELIST)"

H100-42-dry-run: h100-42-dry-run
H100-42: h100-42

A800-40-dry-run:
	@$(MAKE) dry-run TARGET_PORTS="$(A800_40_PORTS)" WHITELIST_IPS="$(A800_40_WHITELIST)"

A800-40:
	@$(MAKE) enable TARGET_PORTS="$(A800_40_PORTS)" WHITELIST_IPS="$(A800_40_WHITELIST)"

a800-40-dry-run: A800-40-dry-run
a800-40: A800-40

A800-43-dry-run:
	@$(MAKE) dry-run TARGET_PORTS="$(A800_43_PORTS)" WHITELIST_IPS="$(A800_43_WHITELIST)"

A800-43:
	@$(MAKE) enable TARGET_PORTS="$(A800_43_PORTS)" WHITELIST_IPS="$(A800_43_WHITELIST)"

a800-43-dry-run: A800-43-dry-run
a800-43: A800-43

status:
	@echo "=== UFW ==="
	@sudo ufw status verbose 2>/dev/null || echo "UFW 未安装或未配置"
	@echo ""
	@echo "=== iptables DOCKER-USER ==="
	@sudo iptables -L DOCKER-USER -n --line-numbers 2>/dev/null || echo "（链不存在）"
	@echo ""
	@echo "=== ip6tables DOCKER-USER ==="
	@sudo ip6tables -L DOCKER-USER -n --line-numbers 2>/dev/null || echo "（链不存在）"

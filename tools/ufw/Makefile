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
H100_42_PORTS     := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_H100_42_PORTS")
H100_42_WHITELIST := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_H100_42_WHITELIST")
A800_40_PORTS     := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_A800_40_PORTS")
A800_40_WHITELIST := $(shell . "$(DEFAULTS_ENV)" && printf '%s' "$$UFW_A800_40_WHITELIST")

# 支持逗号分隔：WHITELIST_IPS=1.2.3.4,10.0.0.0/8
WHITELIST_LIST := $(strip $(subst $(comma),$(space),$(WHITELIST_IPS)))
PORTS_LIST     := $(strip $(subst $(comma),$(space),$(TARGET_PORTS)))

export TARGET_PORTS := $(PORTS_LIST)
export WHITELIST_IPS := $(WHITELIST_LIST)

.PHONY: help enable disable status dry-run blocked-ips h20-43 h20-43-dry-run H100-42 H100-42-dry-run A800-40 A800-40-dry-run

BLOCKED_LINES ?= 50

help:
	@echo "UFW + Docker DOCKER-USER 白名单防火墙"
	@echo ""
	@echo "用法:"
	@echo "  make enable                              应用规则并启用 UFW（默认仅开放 22/SSH）"
	@echo "  make disable                             关闭 UFW，恢复 DOCKER-USER"
	@echo "  make status                              查看 UFW / DOCKER-USER 状态"
	@echo "  make blocked-ips                         查看 DOCKER-USER 拦截 IP（kern.log）"
	@echo "  make dry-run                             打印即将使用的配置（不执行）"
	@echo "  make h20-43                              主机预设：端口 22 30001 30002，白名单=默认+10.212.0.0/16"
	@echo "  make h20-43-dry-run                      预览 h20-43 配置"
	@echo "  make H100-42                             主机预设：端口 22 30001，白名单=默认"
	@echo "  make H100-42-dry-run                     预览 H100-42 配置"
	@echo "  make A800-40                             主机预设：端口 22 9131 9116 10010:10034（/home/taojun/ufw.sh）"
	@echo "  make A800-40-dry-run                     预览 A800-40 配置"
	@echo ""
	@echo "覆盖配置（make 参数或 export 环境变量）:"
	@echo "  TARGET_PORTS    开放端口，空格或逗号分隔（必填，不能为空）"
	@echo "  WHITELIST_IPS   白名单，空格或逗号分隔（必填，不能为空）"
	@echo "  EXTERNAL_INTERFACE  出口网卡（可选，默认自动检测）"
	@echo ""
	@echo "示例:"
	@echo "  make enable TARGET_PORTS=\"22 8080\""
	@echo "  make enable WHITELIST_IPS=\"211.99.216.18,192.168.0.0/16\""
	@echo "  make enable TARGET_PORTS=22 WHITELIST_IPS=1.2.3.4"
	@echo "  make h20-43                              # 端口 22,30001,30002"
	@echo "  make H100-42                             # 端口 22,30001"
	@echo "  make A800-40                             # 端口 22,9131,9116,10010:10034"
	@echo "  export WHITELIST_IPS=\"10.0.0.1 10.0.0.2\"; make enable"
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

blocked-ips:
	@bash "$(SCRIPT)" blocked-ips "$(BLOCKED_LINES)"

h20-43-dry-run:
	@$(MAKE) dry-run TARGET_PORTS="$(H20_43_PORTS)" WHITELIST_IPS="$(H20_43_WHITELIST)"

h20-43:
	@$(MAKE) enable TARGET_PORTS="$(H20_43_PORTS)" WHITELIST_IPS="$(H20_43_WHITELIST)"

H100-42-dry-run:
	@$(MAKE) dry-run TARGET_PORTS="$(H100_42_PORTS)" WHITELIST_IPS="$(H100_42_WHITELIST)"

H100-42:
	@$(MAKE) enable TARGET_PORTS="$(H100_42_PORTS)" WHITELIST_IPS="$(H100_42_WHITELIST)"

A800-40-dry-run:
	@$(MAKE) dry-run TARGET_PORTS="$(A800_40_PORTS)" WHITELIST_IPS="$(A800_40_WHITELIST)"

A800-40:
	@$(MAKE) enable TARGET_PORTS="$(A800_40_PORTS)" WHITELIST_IPS="$(A800_40_WHITELIST)"

status:
	@echo "=== UFW ==="
	@sudo ufw status verbose 2>/dev/null || echo "UFW 未安装或未配置"
	@echo ""
	@echo "=== iptables DOCKER-USER ==="
	@sudo iptables -L DOCKER-USER -n --line-numbers 2>/dev/null || echo "（链不存在）"
	@echo ""
	@echo "=== ip6tables DOCKER-USER ==="
	@sudo ip6tables -L DOCKER-USER -n --line-numbers 2>/dev/null || echo "（链不存在）"

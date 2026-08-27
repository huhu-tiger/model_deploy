# DeepSeek-V4-Flash-0731 双节点 IB（SGLang）
# 必须在 master（cluster.env 的 MASTER_IP，默认 172.31.0.43）执行 make restart

SHELL := /bin/bash
ROOT  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ENV_FILE := $(ROOT)/cluster.env
RUN := $(ROOT)/run.sh

ifeq ($(wildcard $(ENV_FILE)),)
$(warning 未找到 $(ENV_FILE)，双节点请先: make init)
endif

ifneq ($(wildcard $(ENV_FILE)),)
include $(ENV_FILE)
export
endif

export MASTER_IP WORKER_IP MASTER_DIST_PORT REMOTE_USER REMOTE_DEPLOY_DIR
export MASTER_DIST_WAIT_SEC MODEL_HOST_PATH DOCKER_IMAGE

.PHONY: help init config-check start restart stop check hosts firewall status logs master sync worker

help:
	@echo "DeepSeek-V4-Flash-0731 双节点 IB（配置: cluster.env）"
	@echo ""
	@echo "  make init          从 cluster.env.example 创建 cluster.env"
	@echo "  make config-check  校验 cluster.env"
	@echo "  make restart       重启双节点（推荐，必须在 master $(or $(MASTER_IP),172.31.0.43) 执行）"
	@echo "  make start         启动双节点"
	@echo "  make stop          停止双节点"
	@echo "  make check         环境预检（hosts / ufw / GPU / IB / 镜像）"
	@echo "  make hosts         配置 /etc/hosts"
	@echo "  make firewall      配置 ufw 集群互通"
	@echo "  make status        双节点容器状态"
	@echo "  make logs          本机 SGLang 日志"
	@echo "  make master        仅本机 master"
	@echo "  make sync          同步 worker 配置到远程"
	@echo "  make worker        仅远程 worker"
	@echo ""
	@echo "也可: ./run.sh <命令>"

init:
	@if [[ -f "$(ENV_FILE)" ]]; then \
		echo "已存在 $(ENV_FILE)，跳过"; \
	else \
		cp "$(ROOT)/cluster.env.example" "$(ENV_FILE)"; \
		echo "已创建 $(ENV_FILE)，请编辑 MASTER_IP / WORKER_IP 等"; \
	fi

config-check: $(ENV_FILE)
	@set -a; source "$(ENV_FILE)"; set +a; \
	for v in MASTER_IP WORKER_IP; do \
		[[ -n "$${!v}" ]] || { echo "ERROR: cluster.env 缺少 $$v"; exit 1; }; \
	done; \
	echo "cluster.env OK: master=$${MASTER_IP} worker=$${WORKER_IP} dist=$${MASTER_DIST_PORT:-20000}"

$(ENV_FILE):
	@$(MAKE) init

start restart stop check hosts firewall status logs master sync worker:
	@$(MAKE) config-check
	@$(RUN) $@

.DEFAULT_GOAL := help

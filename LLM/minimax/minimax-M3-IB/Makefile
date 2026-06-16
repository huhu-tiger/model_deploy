# MiniMax-M3 双节点部署（配置见 cluster.env，勿在脚本中写死 IP）
SHELL := /bin/bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ENV_FILE := $(ROOT)/cluster.env
RUN := $(ROOT)/run.sh

ifeq ($(wildcard $(ENV_FILE)),)
$(warning 未找到 $(ENV_FILE)，将使用: make init)
endif

ifneq ($(wildcard $(ENV_FILE)),)
include $(ENV_FILE)
export
endif

export MASTER_IP WORKER_IP MASTER_DIST_PORT REMOTE_USER REMOTE_DEPLOY_DIR
export MASTER_DIST_WAIT_SEC MODEL_HOST_PATH DOCKER_IMAGE

.PHONY: help init config-check start restart stop check hosts firewall status logs master sync worker

help:
	@echo "MiniMax-M3 双节点（配置: cluster.env）"
	@echo ""
	@echo "  make init       从 cluster.env.example 创建 cluster.env"
	@echo "  make config-check  校验 cluster.env 必填项"
	@echo "  make restart    重启双节点（默认）"
	@echo "  make start      启动双节点"
	@echo "  make stop       停止双节点"
	@echo "  make check      环境预检（hosts / ufw / GPU）"
	@echo "  make hosts      配置 /etc/hosts"
	@echo "  make firewall   配置 ufw 集群互通"
	@echo "  make status     容器状态"
	@echo "  make logs       本机 sg-llm 日志"
	@echo "  make master     仅本机 master"
	@echo "  make sync       同步 worker 配置到远程"
	@echo "  make worker     仅远程 worker"
	@echo ""
	@echo "也可: ./run <命令>（会自动加载 cluster.env）"

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
	echo "cluster.env OK: master=$${MASTER_IP} worker=$${WORKER_IP} (hostname 由命令自动获取)"

$(ENV_FILE):
	@$(MAKE) init

start restart stop check hosts firewall status logs master sync worker:
	@$(MAKE) config-check
	@$(RUN) $@

# 默认目标
.DEFAULT_GOAL := help

# 最大输入/输出长度探测（16K→32K→64K→…→512K，报错即停）
#
# 用法:
#   make help
#   make test
#   make test API_URL=http://127.0.0.1:30003/v1/chat/completions MODEL_NAME=MiniMax-M2.7
#   make test-input
#   make test-minimax-2.7

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
RUN_SH := $(DIR)/run.sh

# ── 可覆盖变量 ────────────────────────────────────────────────────────────────
API_URL      ?= http://127.0.0.1:30003/v1/chat/completions
MODEL_NAME   ?= Qwen3.6-35B-A3B
API_KEY      ?=
START_K      ?= 16
MAX_K        ?= 512
STEP_K       ?= 0
K_UNIT       ?= 1024
TIMEOUT      ?= 600
JOINT_INPUT_K ?= 0

export API_URL MODEL_NAME API_KEY START_K MAX_K STEP_K K_UNIT TIMEOUT JOINT_INPUT_K
ifdef EXTRA_BODY
export EXTRA_BODY
endif

.PHONY: help test test-input test-output test-minimax-2.7 test-minimax-m3

help: ## 显示帮助
	@echo "最大输入/输出长度探测"
	@echo ""
	@echo "目标:"
	@grep -E '^[a-zA-Z0-9_.-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  %-22s %s\n", $$1, $$2}'
	@echo ""
	@echo "变量 (make test VAR=val):"
	@echo "  API_URL      $(API_URL)"
	@echo "  MODEL_NAME   $(MODEL_NAME)"
	@echo "  START_K      $(START_K)   (起始档位，16=16K)"
	@echo "  MAX_K        $(MAX_K)   (最大档位，512=512K)"
	@echo "  STEP_K        $(STEP_K)    (步进，0=翻倍，正整数=等步进，如 16)"
	@echo "  K_UNIT        $(K_UNIT)  (1K 对应字符数)"
	@echo "  JOINT_INPUT_K $(JOINT_INPUT_K)    (联合测试：固定 N K 输入探最大输出，0=不做)"
	@echo "  TIMEOUT      $(TIMEOUT) (单次请求超时秒数)"
	@echo ""
	@echo "示例:"
	@echo "  make test API_URL=http://127.0.0.1:30003/v1/chat/completions MODEL_NAME=MiniMax-M2.7"

test: ## 探测最大输入 + 最大输出
	@$(RUN_SH)

test-input: ## 仅探测最大输入
	@SKIP_OUTPUT=1 $(RUN_SH)

test-output: ## 仅探测最大输出
	@SKIP_INPUT=1 $(RUN_SH)

# ── 常用模型预设 ──────────────────────────────────────────────────────────────
test-minimax-2.7: ## MiniMax M2.7 (默认 30003)
	@$(MAKE) test MODEL_NAME=/nvme01/MiniMax/MiniMax-M2.7

test-minimax-m3: ## MiniMax M3 (经 nginx 30001 代理)
	@$(MAKE) test \
		API_URL=http://127.0.0.1:30001/v1/chat/completions \
		MODEL_NAME=MiniMax-M3

test-qwen: ## Qwen3.6-35B-A3B (30003)
	@$(MAKE) test \
		MODEL_NAME=Qwen3.6-35B-A3B

.DEFAULT_GOAL := help

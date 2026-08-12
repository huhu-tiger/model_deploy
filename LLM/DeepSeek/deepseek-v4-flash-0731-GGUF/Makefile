# DeepSeek-V4-Flash-0731 GGUF (UD-Q8_K_XL) — llama.cpp
# ModelScope: https://modelscope.cn/models/unsloth/DeepSeek-V4-Flash-0731-GGUF/tree/master/UD-Q8_K_XL

SHELL := /bin/bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
COMPOSE := docker compose -f $(ROOT)/docker-compose-h100.yml

IMAGE  ?= model.vnet.com/sjhl/server-cuda13-b9265
MODEL  ?= /media/llm/unsloth/DeepSeek-V4-Flash-0731-GGUF/UD-Q8_K_XL/DeepSeek-V4-Flash-0731-UD-Q8_K_XL-00001-of-00005.gguf
ALIAS  ?= DeepSeek-V4-Flash-0731-GGUF
CTX    ?= 262144
NP     ?= 2
WEIGHT_DIR := /media/llm/unsloth/DeepSeek-V4-Flash-0731-GGUF

.PHONY: help pull download up down restart logs ps

help:
	@echo "DeepSeek-V4-Flash-0731 GGUF (UD-Q8_K_XL)"
	@echo ""
	@echo "  make download   下载 Q4+（IQ4/Q4/Q8）与 dspark 到 $(WEIGHT_DIR)"
	@echo "  make pull       拉取 llama.cpp 镜像 $(IMAGE)"
	@echo "  make up         启动 nginx(:30001) + llama-server(:30003)"
	@echo "  make down       停止"
	@echo "  make restart    重建并重启"
	@echo "  make logs       跟踪日志"
	@echo "  make ps         查看状态"
	@echo ""
	@echo "可调变量: IMAGE MODEL ALIAS CTX NP"

pull:
	docker pull $(IMAGE)

download:
	@command -v modelscope >/dev/null || { echo "需要: pip install modelscope"; exit 1; }
	# Q4 及以上：IQ4_* / Q4_K_XL / Q8_K_XL + DSpark draft
	modelscope download --model unsloth/DeepSeek-V4-Flash-0731-GGUF \
	  --local_dir $(WEIGHT_DIR) \
	  --include 'UD-IQ4_NL/*' \
	  --include 'UD-IQ4_XS/*' \
	  --include 'UD-Q4_K_XL/*' \
	  --include 'UD-Q8_K_XL/*' \
	  --include 'dspark-DeepSeek-V4-Flash-0731-Q8_0.gguf' \
	  --include 'dspark/*'

up: pull
	@test -f "$(MODEL)" || { echo "ERROR: 权重不存在: $(MODEL)"; echo "先执行: make download"; exit 1; }
	IMAGE=$(IMAGE) MODEL=$(MODEL) ALIAS=$(ALIAS) CTX=$(CTX) NP=$(NP) $(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) down && IMAGE=$(IMAGE) MODEL=$(MODEL) ALIAS=$(ALIAS) CTX=$(CTX) NP=$(NP) $(COMPOSE) up -d

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

.DEFAULT_GOAL := help

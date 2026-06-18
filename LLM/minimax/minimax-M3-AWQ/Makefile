# MiniMax-M3-AWQ-INT4 vLLM 镜像
# ModelScope: https://modelscope.cn/models/cyankiwi/MiniMax-M3-AWQ-INT4

SHELL := /bin/bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
COMPOSE := docker compose -f $(ROOT)/docker-compose.yml

# ── 推荐: minimax-m3 底座 + 本地 patch 文件（零网络依赖，~1min）──
IMAGE_PATCH ?= model.vnet.com/sjhl/vllm-openai:minimax-m3-awq
DOCKERFILE_PATCH := $(ROOT)/Dockerfile.minimax-m3-patch
PATCH_FILE := $(ROOT)/minimax-m3-awq.patch

# ── 备用: minimax-m3 底座 + 构建时 git clone（需 GitHub 代理，~10min）──
IMAGE_A ?= model.vnet.com/sjhl/vllm-openai:minimax-m3-awq-gitclone
DOCKERFILE_A := $(ROOT)/Dockerfile.minimax-m3

BASE_IMAGE_A ?= model.vnet.com/sjhl/vllm-openai:minimax-m3

# toncao 补丁分支及 upstream 基底（用于 make patch 和方案 A）
PATCH_COMMIT   ?= 8f1350ebf25f188a77022c70b575731f0df6a61a
UPSTREAM_COMMIT ?= a7fdfeef72323eb3db6f0620e4ea200290d0ca5a

# git clone 代理（仅 make patch 和方案 A 的 git 步骤；pip 仍走阿里云源且禁用代理）
# 直连 GitHub 时: make patch HTTP_PROXY= HTTPS_PROXY=
HTTP_PROXY  ?= http://172.31.0.55:20171
HTTPS_PROXY ?= http://172.31.0.55:20171

IMAGE ?= $(IMAGE_PATCH)

BUILD_ARGS :=
ifneq ($(strip $(HTTP_PROXY)),)
BUILD_ARGS += --build-arg HTTP_PROXY=$(HTTP_PROXY)
BUILD_ARGS += --build-arg HTTPS_PROXY=$(or $(HTTPS_PROXY),$(HTTP_PROXY))
endif

.PHONY: help patch build build-a up up-a down restart logs ps pull-base

help:
	@echo "MiniMax-M3-AWQ-INT4"
	@echo ""
	@echo "推荐方案 — 本地 patch 文件，零网络依赖，构建 ~1min"
	@echo "  make patch       生成/更新 $(PATCH_FILE)（仅需一次，需 GitHub 代理）"
	@echo "  make build       构建镜像 $(IMAGE_PATCH)（需先 make patch）"
	@echo "  make up          构建并 docker compose up -d"
	@echo "  make pull-base   拉取基础镜像 $(BASE_IMAGE_A)"
	@echo ""
	@echo "备用方案 — 构建时 git clone（需 GitHub 代理，~10min）"
	@echo "  make build-a     构建镜像 $(IMAGE_A)"
	@echo "  make up-a        构建并启动"
	@echo ""
	@echo "运维: make down | restart | logs | ps"
	@echo ""
	@echo "可调变量:"
	@echo "  BASE_IMAGE_A=$(BASE_IMAGE_A)"
	@echo "  PATCH_COMMIT=$(PATCH_COMMIT)"
	@echo "  UPSTREAM_COMMIT=$(UPSTREAM_COMMIT)"
	@echo "  HTTP_PROXY=$(HTTP_PROXY)   # 仅 git 步骤；禁用: HTTP_PROXY="
	@echo "  HTTPS_PROXY=$(HTTPS_PROXY)"

# 一次性生成 patch 文件（克隆 toncao/vllm 到临时目录，提取 diff，删除克隆）
patch:
	@echo ">>> 生成 $(PATCH_FILE) ..."
	@tmpdir=$$(mktemp -d) && \
	  trap 'rm -rf "$$tmpdir"' EXIT && \
	  if [ -n "$(HTTP_PROXY)" ]; then \
	    export HTTP_PROXY="$(HTTP_PROXY)" HTTPS_PROXY="$(HTTPS_PROXY)" \
	           http_proxy="$(HTTP_PROXY)" https_proxy="$(HTTPS_PROXY)"; \
	  fi && \
	  git clone https://github.com/toncao/vllm.git "$$tmpdir/vllm" && \
	  cd "$$tmpdir/vllm" && \
	  git remote add upstream https://github.com/vllm-project/vllm.git && \
	  git fetch upstream "$(UPSTREAM_COMMIT)" && \
	  git checkout minimax-m3-compressed-tensors && \
	  git checkout "$(PATCH_COMMIT)" && \
	  git diff "$(UPSTREAM_COMMIT)" HEAD > "$(PATCH_FILE)" && \
	  echo ">>> patch saved: $(PATCH_FILE) ($$(wc -l < "$(PATCH_FILE)") lines)"

# 推荐: COPY 本地 patch，零网络
build:
	@test -f "$(PATCH_FILE)" || { echo "ERROR: $(PATCH_FILE) not found. Run: make patch"; exit 1; }
	docker build -t $(IMAGE_PATCH) \
	  --build-arg BASE_IMAGE=$(BASE_IMAGE_A) \
	  -f $(DOCKERFILE_PATCH) $(ROOT)

# 备用: 构建时 git clone
build-a:
	docker build -t $(IMAGE_A) $(BUILD_ARGS) \
	  --build-arg BASE_IMAGE=$(BASE_IMAGE_A) \
	  -f $(DOCKERFILE_A) $(ROOT)

up: build
	IMAGE=$(IMAGE_PATCH) $(COMPOSE) up -d

up-a: build-a
	IMAGE=$(IMAGE_A) $(COMPOSE) up -d

pull-base:
	docker pull $(BASE_IMAGE_A)

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

.DEFAULT_GOAL := help

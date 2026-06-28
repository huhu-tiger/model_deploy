# MiniMax-M3-AWQ-INT4 vLLM 镜像
# ModelScope: https://modelscope.cn/models/cyankiwi/MiniMax-M3-AWQ-INT4

SHELL := /bin/bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
COMPOSE       := docker compose -f $(ROOT)/docker-compose.yml
COMPOSE_NGINX := docker compose -f $(ROOT)/docker-compose-nginx.yml

# ── 推荐: minimax-m3 底座 + 本地 patch 文件（零网络依赖，~1min）──
IMAGE ?= model.vnet.com/sjhl/vllm-openai:minimax-m3-awq
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

BUILD_ARGS :=
ifneq ($(strip $(HTTP_PROXY)),)
BUILD_ARGS += --build-arg HTTP_PROXY=$(HTTP_PROXY)
BUILD_ARGS += --build-arg HTTPS_PROXY=$(or $(HTTPS_PROXY),$(HTTP_PROXY))
endif

.PHONY: help patch build build-a up up-a down restart logs ps pull-base nginx-up nginx-down nginx-restart nginx-logs nginx-ps

help:
	@echo "MiniMax-M3-AWQ-INT4"
	@echo ""
	@echo "推荐方案 — 本地 patch 文件，零网络依赖，构建 ~1min"
	@echo "  make patch       生成/更新 $(PATCH_FILE)（仅需一次，需 GitHub 代理）"
	@echo "  make build       构建镜像 $(IMAGE)（需先 make patch）"
	@echo "  make up          docker compose up -d（镜像: $(IMAGE)）"
	@echo "  make pull-base   拉取基础镜像 $(BASE_IMAGE_A)"
	@echo ""
	@echo "备用方案 — 构建时 git clone（需 GitHub 代理，~10min）"
	@echo "  make build-a     构建镜像 $(IMAGE_A)"
	@echo "  make up-a        构建并启动"
	@echo ""
	@echo "运维 - vLLM 直连模式:"
	@echo "  make down              停止服务"
	@echo "  make restart           重启服务"
	@echo "  make logs              跟踪日志"
	@echo "  make ps                查看容器状态"
	@echo ""
	@echo "运维 - nginx 代理模式:"
	@echo "  make nginx-up          启动 vLLM + nginx 代理      (nginx 端口 30001, vLLM 内部 30003)"
	@echo "  make nginx-down        停止所有服务（含 vLLM）"
	@echo "  make nginx-restart     仅重建 nginx 容器（不影响 vLLM）"
	@echo "  make nginx-logs        跟踪所有日志"
	@echo "  make nginx-ps          查看容器状态"
	@echo ""
	@echo "可调变量:"
	@echo "  IMAGE=$(IMAGE)"
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
	docker build -t $(IMAGE) \
	  --build-arg BASE_IMAGE=$(BASE_IMAGE_A) \
	  -f $(DOCKERFILE_PATCH) $(ROOT)

# 备用: 构建时 git clone
build-a:
	docker build -t $(IMAGE_A) $(BUILD_ARGS) \
	  --build-arg BASE_IMAGE=$(BASE_IMAGE_A) \
	  -f $(DOCKERFILE_A) $(ROOT)

up:
	IMAGE=$(IMAGE) $(COMPOSE) up -d

up-a: build-a
	IMAGE=$(IMAGE_A) $(COMPOSE) up -d

pull-base:
	docker pull $(BASE_IMAGE_A)

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) down && IMAGE=$(IMAGE) $(COMPOSE) up -d

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

nginx-up:
	IMAGE=$(IMAGE) $(COMPOSE_NGINX) up -d

nginx-down:
	$(COMPOSE_NGINX) down

nginx-restart:
	$(COMPOSE_NGINX) up -d --force-recreate nginx-llm-proxy

nginx-logs:
	$(COMPOSE_NGINX) logs -f --tail=200

nginx-ps:
	$(COMPOSE_NGINX) ps

.DEFAULT_GOAL := help

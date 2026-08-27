# MiniMax-M3-AWQ-INT4 vLLM 镜像
# ModelScope: https://modelscope.cn/models/cyankiwi/MiniMax-M3-AWQ-INT4

SHELL := /bin/bash
ROOT  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

COMPOSE_DIRECT := docker-compose -f $(ROOT)/docker-compose.yml
COMPOSE_NGINX  := docker-compose -f $(ROOT)/docker-compose-nginx.yml

# ── 镜像 ──────────────────────────────────────────────────────────────────────
IMAGE ?= model.vnet.com/sjhl/vllm-openai:minimax-m3-awq
DOCKERFILE_PATCH := $(ROOT)/Dockerfile.minimax-m3-patch
PATCH_FILE       := $(ROOT)/minimax-m3-awq.patch

IMAGE_A      ?= model.vnet.com/sjhl/vllm-openai:minimax-m3-awq-gitclone
DOCKERFILE_A := $(ROOT)/Dockerfile.minimax-m3
BASE_IMAGE_A ?= model.vnet.com/sjhl/vllm-openai:minimax-m3

PATCH_COMMIT    ?= 8f1350ebf25f188a77022c70b575731f0df6a61a
UPSTREAM_COMMIT ?= a7fdfeef72323eb3db6f0620e4ea200290d0ca5a

# git 代理（仅 make patch / build-a；直连 GitHub 时: HTTP_PROXY=）
HTTP_PROXY  ?= http://172.31.0.55:20171
HTTPS_PROXY ?= http://172.31.0.55:20171

BUILD_ARGS :=
ifneq ($(strip $(HTTP_PROXY)),)
BUILD_ARGS += --build-arg HTTP_PROXY=$(HTTP_PROXY)
BUILD_ARGS += --build-arg HTTPS_PROXY=$(or $(HTTPS_PROXY),$(HTTP_PROXY))
endif

# ── 目标声明 ──────────────────────────────────────────────────────────────────
.PHONY: help patch build build-a pull-base \
        up down restart logs ps \
        nginx-up nginx-down nginx-stop nginx-restart nginx-logs nginx-ps

help:
	@echo "MiniMax-M3-AWQ-INT4"
	@echo ""
	@echo "镜像构建:"
	@echo "  make patch       生成/更新 minimax-m3-awq.patch（仅需一次，需 GitHub 代理）"
	@echo "  make build       构建推荐镜像 $(IMAGE)（需先 make patch）"
	@echo "  make build-a     构建备用镜像 $(IMAGE_A)（需 GitHub 代理）"
	@echo "  make pull-base   拉取基础镜像 $(BASE_IMAGE_A)"
	@echo ""
	@echo "直连模式  (vLLM 直接监听 :30001, 用 docker-compose.yml):"
	@echo "  make up          启动 vLLM"
	@echo "  make down        停止 vLLM"
	@echo "  make restart     重启 vLLM"
	@echo "  make logs        跟踪日志"
	@echo "  make ps          查看容器状态"
	@echo ""
	@echo "nginx 代理模式  (nginx:30001 → vLLM:30003, 用 docker-compose-nginx.yml):"
	@echo "  make nginx-up      启动 nginx + vLLM"
	@echo "  make nginx-down    停止 nginx + vLLM"
	@echo "  make nginx-stop    仅停止 nginx 容器（vLLM 继续运行）"
	@echo "  make nginx-restart 仅重建 nginx 容器（不重启 vLLM）"
	@echo "  make nginx-logs    跟踪日志"
	@echo "  make nginx-ps      查看容器状态"
	@echo ""
	@echo "可调变量:"
	@echo "  IMAGE=$(IMAGE)"
	@echo "  BASE_IMAGE_A=$(BASE_IMAGE_A)"
	@echo "  HTTP_PROXY=$(HTTP_PROXY)"

# ── 镜像构建 ──────────────────────────────────────────────────────────────────
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

build:
	@test -f "$(PATCH_FILE)" || { echo "ERROR: $(PATCH_FILE) not found. Run: make patch"; exit 1; }
	docker build -t $(IMAGE) \
	  --build-arg BASE_IMAGE=$(BASE_IMAGE_A) \
	  -f $(DOCKERFILE_PATCH) $(ROOT)

build-a:
	docker build -t $(IMAGE_A) $(BUILD_ARGS) \
	  --build-arg BASE_IMAGE=$(BASE_IMAGE_A) \
	  -f $(DOCKERFILE_A) $(ROOT)

pull-base:
	docker pull $(BASE_IMAGE_A)

# ── 直连模式（docker-compose.yml）────────────────────────────────────────────
up:
	IMAGE=$(IMAGE) $(COMPOSE_DIRECT) up -d

down:
	$(COMPOSE_DIRECT) down

restart:
	$(COMPOSE_DIRECT) down && IMAGE=$(IMAGE) $(COMPOSE_DIRECT) up -d

logs:
	$(COMPOSE_DIRECT) logs -f --tail=200

ps:
	$(COMPOSE_DIRECT) ps

# ── nginx 代理模式（docker-compose-nginx.yml）────────────────────────────────
nginx-up:
	IMAGE=$(IMAGE) $(COMPOSE_NGINX) up -d

nginx-down:
	$(COMPOSE_NGINX) down

nginx-stop:
	$(COMPOSE_NGINX) stop nginx-llm-proxy

nginx-restart:
	$(COMPOSE_NGINX) up -d --no-deps --force-recreate nginx-llm-proxy

nginx-logs:
	$(COMPOSE_NGINX) logs -f --tail=200

nginx-ps:
	$(COMPOSE_NGINX) ps

.DEFAULT_GOAL := help

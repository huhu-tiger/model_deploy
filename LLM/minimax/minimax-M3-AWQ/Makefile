# MiniMax-M3-AWQ-INT4 vLLM 镜像
# ModelScope: https://modelscope.cn/models/cyankiwi/MiniMax-M3-AWQ-INT4

SHELL := /bin/bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
COMPOSE := docker compose -f $(ROOT)/docker-compose.yml

# ── 官方 README: nvidia/cuda:devel + uv + VLLM_USE_PRECOMPILED ──
IMAGE_PRECOMPILED ?= model.vnet.com/sjhl/vllm-openai:minimax-m3-awq-precompiled
DOCKERFILE_PRECOMPILED := $(ROOT)/Dockerfile.precompiled
CUDA_VERSION ?= 13.0.2
CUDA_BASE ?= nvidia/cuda:$(CUDA_VERSION)-devel-ubuntu22.04

# ── 方案 B: a7fdfeef 补丁分支 + 源码编译 CUDA（慢，约 1～3h）──
IMAGE_B ?= model.vnet.com/sjhl/vllm-openai:minimax-m3-awq-source
DOCKERFILE_B := $(ROOT)/Dockerfile
BASE_IMAGE_B ?= model.vnet.com/sjhl/vllm-openai:v0.23.0
MAX_JOBS ?= 64
NVCC_THREADS ?= 4

# ── 方案 A（默认/推荐）: minimax-m3 底座 + git diff 补丁 ──
IMAGE_A ?= model.vnet.com/sjhl/vllm-openai:minimax-m3-awq
DOCKERFILE_A := $(ROOT)/Dockerfile.minimax-m3
BASE_IMAGE_A ?= model.vnet.com/sjhl/vllm-openai:minimax-m3

# git clone 代理（仅 Dockerfile 中 git 步骤；pip 仍走阿里云源且禁用代理）
# 直连 GitHub 时: make build HTTP_PROXY= HTTPS_PROXY=
HTTP_PROXY ?= http://172.31.0.55:20171
HTTPS_PROXY ?= http://172.31.0.55:20171

# 默认走方案 A
IMAGE ?= $(IMAGE_A)

BUILD_ARGS :=
ifneq ($(strip $(HTTP_PROXY)),)
BUILD_ARGS += --build-arg HTTP_PROXY=$(HTTP_PROXY)
BUILD_ARGS += --build-arg HTTPS_PROXY=$(or $(HTTPS_PROXY),$(HTTP_PROXY))
endif

.PHONY: help build build-b build-a build-precompiled up up-b up-a up-precompiled \
        down restart logs ps pull-base-b pull-base-a pull-base-precompiled

help:
	@echo "MiniMax-M3-AWQ-INT4"
	@echo ""
	@echo "方案 A — minimax-m3 底座 + git diff 补丁（默认/推荐，约 5～10min）"
	@echo "  make build              构建镜像 $(IMAGE_A)"
	@echo "  make up                 构建并 docker compose up -d"
	@echo "  make pull-base-a        拉取基础镜像 $(BASE_IMAGE_A)"
	@echo ""
	@echo "方案 B — 源码编译（约 1～3h，与 a7fdfeef 严格对齐，网络要求高）"
	@echo "  make build-b            构建镜像 $(IMAGE_B)"
	@echo "  make up-b               构建并启动"
	@echo "  make pull-base-b        拉取基础镜像 $(BASE_IMAGE_B)"
	@echo ""
	@echo "官方 README — nvidia/cuda:devel + uv 预编译（可能缺 M3 算子）"
	@echo "  make build-precompiled  构建镜像 $(IMAGE_PRECOMPILED)"
	@echo "  make up-precompiled     构建并启动"
	@echo "  make pull-base-precompiled  拉取 $(CUDA_BASE)"
	@echo ""
	@echo "运维: make down | restart | logs | ps"
	@echo ""
	@echo "可调变量:"
	@echo "  BASE_IMAGE_B=$(BASE_IMAGE_B)"
	@echo "  BASE_IMAGE_A=$(BASE_IMAGE_A)"
	@echo "  CUDA_BASE=$(CUDA_BASE)"
	@echo "  IMAGE_PRECOMPILED=$(IMAGE_PRECOMPILED)"
	@echo "  MAX_JOBS=$(MAX_JOBS)              # 方案 B 源码编译并行度，make build-b MAX_JOBS=32 可覆盖"
	@echo "  NVCC_THREADS=$(NVCC_THREADS)      # 方案 B nvcc 线程数，make build-b NVCC_THREADS=2 可覆盖"
	@echo "  HTTP_PROXY=$(HTTP_PROXY)   # 仅 git clone；禁用: make build HTTP_PROXY="
	@echo "  HTTPS_PROXY=$(HTTPS_PROXY)"

build build-a:
	docker build -t $(IMAGE_A) $(BUILD_ARGS) \
	  --build-arg BASE_IMAGE=$(BASE_IMAGE_A) \
	  -f $(DOCKERFILE_A) $(ROOT)

build-b:
	docker build -t $(IMAGE_B) $(BUILD_ARGS) \
	  --build-arg BASE_IMAGE=$(BASE_IMAGE_B) \
	  --build-arg MAX_JOBS=$(MAX_JOBS) \
	  --build-arg NVCC_THREADS=$(NVCC_THREADS) \
	  -f $(DOCKERFILE_B) $(ROOT)

build-precompiled:
	docker build -t $(IMAGE_PRECOMPILED) $(BUILD_ARGS) \
	  --build-arg BASE_IMAGE=$(CUDA_BASE) \
	  --build-arg CUDA_VERSION=$(CUDA_VERSION) \
	  --build-arg MAX_JOBS=$(MAX_JOBS) \
	  --build-arg NVCC_THREADS=$(NVCC_THREADS) \
	  -f $(DOCKERFILE_PRECOMPILED) $(ROOT)

up-precompiled: build-precompiled
	IMAGE=$(IMAGE_PRECOMPILED) $(COMPOSE) up -d

up up-a: build-a
	IMAGE=$(IMAGE_A) $(COMPOSE) up -d

up-b: build-b
	IMAGE=$(IMAGE_B) $(COMPOSE) up -d

pull-base-precompiled:
	docker pull $(CUDA_BASE)

pull-base-b:
	docker pull $(BASE_IMAGE_B)

pull-base-a:
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

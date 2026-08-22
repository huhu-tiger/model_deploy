# GLM-5.2-AWQ-INT4 vLLM
# ModelScope: https://modelscope.cn/models/cyankiwi/GLM-5.2-AWQ-INT4

SHELL := /bin/bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

COMPOSE_DIRECT := docker-compose -f $(ROOT)/docker-compose.yml
COMPOSE_NGINX  := docker-compose -f $(ROOT)/docker-compose-nginx.yml

IMAGE ?= vllm/vllm-openai:v0.27.1

.PHONY: help pull up down restart logs ps \
        nginx-up nginx-down nginx-stop nginx-restart nginx-logs nginx-ps

help:
	@echo "GLM-5.2-AWQ-INT4"
	@echo ""
	@echo "  make pull        拉取镜像 $(IMAGE)"
	@echo ""
	@echo "直连模式  (vLLM 直接监听 :30002, 用 docker-compose.yml):"
	@echo "  make up          拉取镜像并启动 vLLM"
	@echo "  make down        停止 vLLM"
	@echo "  make restart     重启 vLLM"
	@echo "  make logs        跟踪日志"
	@echo "  make ps          查看容器状态"
	@echo ""
	@echo "nginx 代理模式  (宿主机:30002 → nginx:80 → vLLM:30003, 用 docker-compose-nginx.yml):"
	@echo "  make nginx-up      启动 nginx + vLLM"
	@echo "  make nginx-down    停止 nginx + vLLM"
	@echo "  make nginx-stop    仅停止 nginx 容器（vLLM 继续运行）"
	@echo "  make nginx-restart 仅重建 nginx 容器（不重启 vLLM）"
	@echo "  make nginx-logs    跟踪日志"
	@echo "  make nginx-ps      查看容器状态"
	@echo ""
	@echo "可调变量:"
	@echo "  IMAGE=$(IMAGE)"

pull:
	docker pull $(IMAGE)

# ── 直连模式（docker-compose.yml）────────────────────────────────────────────
up: pull
	IMAGE=$(IMAGE) $(COMPOSE_DIRECT) up -d

down:
	$(COMPOSE_DIRECT) down

restart:
	$(COMPOSE_DIRECT) restart

logs:
	$(COMPOSE_DIRECT) logs -f --tail=200

ps:
	$(COMPOSE_DIRECT) ps

# ── nginx 代理模式（docker-compose-nginx.yml）────────────────────────────────
nginx-up: pull
	IMAGE=$(IMAGE) $(COMPOSE_NGINX) up -d

nginx-down:
	$(COMPOSE_NGINX) down

nginx-stop:
	$(COMPOSE_NGINX) stop nginx-llm-proxy

nginx-restart:
	$(COMPOSE_NGINX) up -d --force-recreate nginx-llm-proxy

nginx-logs:
	$(COMPOSE_NGINX) logs -f --tail=200

nginx-ps:
	$(COMPOSE_NGINX) ps

.DEFAULT_GOAL := help

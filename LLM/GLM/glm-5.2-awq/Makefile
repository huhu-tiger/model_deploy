# GLM-5.2-AWQ-INT4 vLLM
# ModelScope: https://modelscope.cn/models/cyankiwi/GLM-5.2-AWQ-INT4

SHELL := /bin/bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

COMPOSE_DIRECT := docker compose -f $(ROOT)/docker-compose.yml
COMPOSE_NGINX  := docker compose -f $(ROOT)/docker-compose-nginx.yml

MODEL_SERVICE := glm-5.2-awq-int4-vllm
NGINX_SERVICE := nginx-llm-proxy
IMAGE ?= model.vnet.com/sjhl/vllm-openai:v0.27.1

.PHONY: help pull up down restart logs ps \
        nginx-up nginx-down nginx-stop nginx-restart nginx-logs nginx-ps \
        model-up model-down model-stop model-restart model-logs model-ps \
        stack-up stack-down stack-restart stack-logs stack-ps

help:
	@echo "GLM-5.2-AWQ-INT4"
	@echo ""
	@echo "  make pull          拉取 vLLM 镜像 $(IMAGE)"
	@echo ""
	@echo "直连模式（vLLM 直接监听 :30002，使用 docker-compose.yml）:"
	@echo "  make up            启动 vLLM"
	@echo "  make down          停止并删除 vLLM"
	@echo "  make restart       重启 vLLM"
	@echo "  make logs          跟踪日志"
	@echo "  make ps            查看状态"
	@echo ""
	@echo "代理模式（使用 docker-compose-nginx.yml，Nginx 与模型独立管理）:"
	@echo "  make nginx-up      仅启动 Nginx"
	@echo "  make nginx-down    仅停止并删除 Nginx"
	@echo "  make nginx-stop    仅停止 Nginx"
	@echo "  make nginx-restart 仅重建 Nginx"
	@echo "  make nginx-logs    跟踪 Nginx 日志"
	@echo "  make nginx-ps      查看 Nginx 状态"
	@echo "  make model-up      仅启动 GLM 模型"
	@echo "  make model-down    仅停止并删除 GLM 模型"
	@echo "  make model-stop    仅停止 GLM 模型"
	@echo "  make model-restart 仅重建 GLM 模型"
	@echo "  make model-logs    跟踪 GLM 模型日志"
	@echo "  make model-ps      查看 GLM 模型状态"
	@echo "  make stack-up      启动 Nginx 和 GLM 模型"
	@echo "  make stack-down    停止并删除整套服务"
	@echo "  make stack-restart 重建整套服务"
	@echo "  make stack-logs    跟踪整套服务日志"
	@echo "  make stack-ps      查看整套服务状态"
	@echo ""
	@echo "可调变量: IMAGE=$(IMAGE)"

pull:
	docker pull $(IMAGE)

# ── 直连模式（docker-compose.yml）────────────────────────────────────────────
up: pull
	IMAGE=$(IMAGE) $(COMPOSE_DIRECT) up -d

down:
	$(COMPOSE_DIRECT) down

restart:
	IMAGE=$(IMAGE) $(COMPOSE_DIRECT) up -d --force-recreate

logs:
	$(COMPOSE_DIRECT) logs -f --tail=200

ps:
	$(COMPOSE_DIRECT) ps

# ── Nginx（代理模式，独立于模型）─────────────────────────────────────────────
nginx-up:
	$(COMPOSE_NGINX) up -d --no-deps $(NGINX_SERVICE)

nginx-down:
	$(COMPOSE_NGINX) stop $(NGINX_SERVICE)
	$(COMPOSE_NGINX) rm -f $(NGINX_SERVICE)

nginx-stop:
	$(COMPOSE_NGINX) stop $(NGINX_SERVICE)

nginx-restart:
	$(COMPOSE_NGINX) up -d --no-deps --force-recreate $(NGINX_SERVICE)

nginx-logs:
	$(COMPOSE_NGINX) logs -f --tail=200 $(NGINX_SERVICE)

nginx-ps:
	$(COMPOSE_NGINX) ps $(NGINX_SERVICE)

# ── GLM 模型（代理模式，独立于 Nginx）────────────────────────────────────────
model-up:
	IMAGE=$(IMAGE) $(COMPOSE_NGINX) up -d --no-deps $(MODEL_SERVICE)

model-down:
	$(COMPOSE_NGINX) stop $(MODEL_SERVICE)
	$(COMPOSE_NGINX) rm -f $(MODEL_SERVICE)

model-stop:
	$(COMPOSE_NGINX) stop $(MODEL_SERVICE)

model-restart:
	IMAGE=$(IMAGE) $(COMPOSE_NGINX) up -d --no-deps --force-recreate $(MODEL_SERVICE)

model-logs:
	$(COMPOSE_NGINX) logs -f --tail=200 $(MODEL_SERVICE)

model-ps:
	$(COMPOSE_NGINX) ps $(MODEL_SERVICE)

# ── 整套代理服务 ──────────────────────────────────────────────────────────────
stack-up:
	IMAGE=$(IMAGE) $(COMPOSE_NGINX) up -d

stack-down:
	$(COMPOSE_NGINX) down

stack-restart:
	IMAGE=$(IMAGE) $(COMPOSE_NGINX) up -d --force-recreate

stack-logs:
	$(COMPOSE_NGINX) logs -f --tail=200

stack-ps:
	$(COMPOSE_NGINX) ps

.DEFAULT_GOAL := help

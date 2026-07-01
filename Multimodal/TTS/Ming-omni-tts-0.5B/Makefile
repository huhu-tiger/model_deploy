# Ming-omni-tts-0.5B | vLLM-Omni Docker Compose
#
# 用法:
#   make up                  # 启动
#   make logs                # 查看日志
#   make down                # 停止
#   make test                # TTS 请求测试
#   make up GPU=4 PORT=9132  # 指定 GPU / 端口

COMPOSE_FILE := docker-compose.yml
COMPOSE_PROJECT_NAME ?= ming-omni-tts
GPU ?= 6
PORT ?= 9132
MODEL_PATH ?= /media/llm/inclusionAI/Ming-omni-tts-0.5B
SERVED_NAME ?= Ming-omni-tts-0.5B
CONTAINER_NAME := vllm-ming-omni-tts

export GPU PORT COMPOSE_PROJECT_NAME

DOCKER_COMPOSE := docker compose -f $(COMPOSE_FILE)

.PHONY: help up start down stop restart logs ps status health test config

help:
	@echo "Ming-omni-tts-0.5B 部署命令"
	@echo ""
	@echo "  make up|start     启动服务 (默认 GPU=$(GPU), PORT=$(PORT))"
	@echo "  make down|stop    停止服务"
	@echo "  make restart      重启服务"
	@echo "  make logs         查看日志"
	@echo "  make ps|status    查看容器状态"
	@echo "  make health       健康检查"
	@echo "  make test         发送 TTS 测试请求"
	@echo "  make config       校验 compose 配置"
	@echo ""
	@echo "环境变量: GPU PORT MODEL_PATH SERVED_NAME COMPOSE_PROJECT_NAME"

up start: check-model
	@echo "启动 Ming-omni-tts-0.5B"
	@echo "  模型: $(MODEL_PATH)"
	@echo "  GPU:  $(GPU)"
	@echo "  端口: $(PORT) -> 8091"
	$(DOCKER_COMPOSE) up -d
	@echo ""
	@echo "健康检查: make health"

down stop:
	$(DOCKER_COMPOSE) down

restart: down up

logs:
	$(DOCKER_COMPOSE) logs -f --tail=200

ps status:
	$(DOCKER_COMPOSE) ps

health:
	curl -fsS "http://localhost:$(PORT)/health" && echo

test:
	PORT=$(PORT) SERVED_NAME=$(SERVED_NAME) ./test_curl.sh

config:
	$(DOCKER_COMPOSE) config

check-model:
	@test -d "$(MODEL_PATH)" || (echo "错误: 模型目录不存在: $(MODEL_PATH)" >&2; exit 1)

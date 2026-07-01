# PP-OCRv6 medium | PaddleX OCR 服务化
#
# 用法:
#   make up                  # 构建并启动
#   make logs                # 查看日志
#   make down                # 停止
#   make test                # OCR 请求测试
#   make up GPU=4 PORT=9410 # 指定 GPU / 端口

COMPOSE_FILE := docker-compose.yml
COMPOSE_PROJECT_NAME ?= pp-ocrv6
GPU ?= 0
PORT ?= 9410
DET_MODEL_PATH ?= /media/llm/PaddlePaddle/PP-OCRv6_medium_det
REC_MODEL_PATH ?= /media/llm/PaddlePaddle/PP-OCRv6_medium_rec
CONTAINER_NAME := pp-ocrv6-api

export GPU PORT COMPOSE_PROJECT_NAME PADDLEOCR_IMAGE_TAG PADDLE_PDX_MODEL_SOURCE

DOCKER_COMPOSE := docker compose -f $(COMPOSE_FILE)

.PHONY: help up start down stop restart logs ps status health test config build pull

help:
	@echo "PP-OCRv6 medium OCR 部署命令"
	@echo ""
	@echo "  make build        构建镜像"
	@echo "  make up|start     构建并启动 (默认 GPU=$(GPU), PORT=$(PORT))"
	@echo "  make down|stop    停止服务"
	@echo "  make restart      重启服务"
	@echo "  make logs         查看日志"
	@echo "  make ps|status    查看容器状态"
	@echo "  make health       健康检查"
	@echo "  make test         发送 OCR 测试请求"
	@echo "  make config       校验 compose 配置"
	@echo ""
	@echo "环境变量: GPU PORT DET_MODEL_PATH REC_MODEL_PATH PADDLEOCR_IMAGE_TAG PADDLE_PDX_MODEL_SOURCE"

build:
	$(DOCKER_COMPOSE) build

pull:
	$(DOCKER_COMPOSE) pull

up start: check-models build
	@echo "启动 PP-OCRv6 OCR 服务"
	@echo "  检测模型: $(DET_MODEL_PATH)"
	@echo "  识别模型: $(REC_MODEL_PATH)"
	@echo "  GPU:      $(GPU)"
	@echo "  端口:     $(PORT) -> 8080"
	$(DOCKER_COMPOSE) up -d
	@echo ""
	@echo "健康检查: make health"
	@echo "测试请求: make test"

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
	PORT=$(PORT) ./test_curl.sh

config:
	$(DOCKER_COMPOSE) config

check-models: check-det-model check-rec-model

check-det-model:
	@test -d "$(DET_MODEL_PATH)" || (echo "错误: 检测模型目录不存在: $(DET_MODEL_PATH)" >&2; exit 1)
	@test -f "$(DET_MODEL_PATH)/inference.pdiparams" || (echo "错误: 缺少 inference.pdiparams: $(DET_MODEL_PATH)" >&2; exit 1)

check-rec-model:
	@test -d "$(REC_MODEL_PATH)" || (echo "错误: 识别模型目录不存在: $(REC_MODEL_PATH)" >&2; exit 1)
	@test -f "$(REC_MODEL_PATH)/inference.pdiparams" || (echo "错误: 缺少 inference.pdiparams: $(REC_MODEL_PATH)" >&2; exit 1)

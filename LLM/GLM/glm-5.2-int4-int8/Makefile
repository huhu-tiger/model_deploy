# GLM-5.2-Int4-Int8Mix vLLM
# ModelScope: https://modelscope.cn/models/tclf90/GLM-5.2-Int4-Int8Mix

SHELL := /bin/bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
COMPOSE := docker compose -f $(ROOT)/docker-compose.yml

IMAGE ?= model.vnet.com/sjhl/vllm-openai:glm52

.PHONY: help pull up down restart logs ps

help:
	@echo "GLM-5.2-Int4-Int8Mix (tclf90)"
	@echo ""
	@echo "  make pull        拉取镜像 $(IMAGE)"
	@echo "  make up          拉取镜像并启动服务（端口 30002）"
	@echo ""
	@echo "运维: make down | restart | logs | ps"
	@echo ""
	@echo "可调变量:"
	@echo "  IMAGE=$(IMAGE)"

pull:
	docker pull $(IMAGE)

up: pull
	IMAGE=$(IMAGE) $(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

.DEFAULT_GOAL := help

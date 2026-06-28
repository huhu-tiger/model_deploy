# GLM-5.2-Int4-Int8Mix vLLM
# ModelScope: https://modelscope.cn/models/tclf90/GLM-5.2-Int4-Int8Mix

SHELL := /bin/bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
COMPOSE      := docker compose -f $(ROOT)/docker-compose.yml
COMPOSE_NGINX := docker compose -f $(ROOT)/docker-compose-nginx.yml

IMAGE ?= model.vnet.com/sjhl/vllm-openai:glm52

.PHONY: help pull up down restart logs ps nginx-up nginx-down nginx-restart nginx-logs nginx-ps

help:
	@echo "GLM-5.2-Int4-Int8Mix (tclf90)"
	@echo ""
	@echo "启动:"
	@echo "  make pull              拉取镜像 $(IMAGE)"
	@echo "  make up                启动 vLLM 直连服务          (端口 30001)"
	@echo "  make nginx-up          启动 vLLM + nginx 代理      (nginx 端口 30001, vLLM 内部 30003)"
	@echo ""
	@echo "运维 - vLLM 直连模式:"
	@echo "  make down              停止服务"
	@echo "  make restart           重建并重启服务"
	@echo "  make logs              跟踪日志"
	@echo "  make ps                查看容器状态"
	@echo ""
	@echo "运维 - nginx 代理模式:"
	@echo "  make nginx-down        停止所有服务（含 vLLM）"
	@echo "  make nginx-restart     仅重建 nginx 容器（不影响 vLLM）"
	@echo "  make nginx-logs        跟踪所有日志"
	@echo "  make nginx-ps          查看容器状态"
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
	$(COMPOSE) down && IMAGE=$(IMAGE) $(COMPOSE) up -d

logs:
	$(COMPOSE) logs -f --tail=200

ps:
	$(COMPOSE) ps

nginx-up: pull
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

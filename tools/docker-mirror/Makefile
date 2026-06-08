.PHONY: help push list login

SCRIPT := ./pull_and_push.sh
RECORD := pushed_images.txt

comma := ,
empty :=
space := $(empty) $(empty)
# 支持空格或逗号分隔（make 中逗号是函数参数分隔符，需用变量表示）
IMAGE_LIST := $(strip $(subst $(comma),$(space),$(IMAGE) $(IMAGES)))

help:
	@echo "Docker 镜像同步工具"
	@echo ""
	@echo "用法:"
	@echo "  make push IMAGE=<源镜像>                         同步单个镜像"
	@echo "  make push IMAGE=<镜像1>,<镜像2>                  同步多个镜像（逗号分隔）"
	@echo "  make push IMAGES=\"<镜像1> <镜像2>\"               同步多个镜像（空格分隔）"
	@echo "  make list                                        查看已推送记录"
	@echo "  make login                                       登录内网仓库"
	@echo ""
	@echo "示例:"
	@echo "  make push IMAGE=vllm/vllm-openai:v0.22.1"
	@echo "  make push IMAGE=vllm/vllm-omni:v0.22.0,vllm/vllm-openai:v0.22.1"
	@echo "  make push IMAGES=\"vllm/vllm-openai:v0.22.1 nvidia/cuda:12.0.0-base\""

push:
ifeq ($(strip $(IMAGE)$(IMAGES)),)
	@echo "错误: 请指定 IMAGE 或 IMAGES" >&2
	@echo "示例: make push IMAGE=vllm/vllm-openai:v0.22.1" >&2
	@exit 1
endif
	@$(SCRIPT) $(IMAGE_LIST)

list:
	@if [ -f "$(RECORD)" ] && [ -s "$(RECORD)" ]; then \
		cat "$(RECORD)"; \
	else \
		echo "暂无推送记录: $(RECORD)"; \
	fi

login:
	@docker login model.vnet.com

# ============================================================================
# EvalScope 能力评测 Makefile
# ============================================================================
# 用法示例：
#   make help                                         # 列出全部 target
#   make quick                                        # 默认参数跑冒烟
#   make quick LIMIT=50 MODEL_NAME=Qwen3.6-35B-A3B    # 覆盖参数
#   make full GROUPS="chinese reasoning" LIMIT=100    # Python 脚本传参
#   make tool-v4 SUBSETS="simple_python multiple" LIMIT=20
#   make check                                        # 查看推理服务已注册模型
#   make clean                                        # 删除 outputs/
#
# 所有可传参数（命令行 X=Y 或 export X=Y 均可）：
#   API_HOST          推理服务主机（默认 61.49.53.41）
#   API_PORT          推理服务端口（默认 30001）
#   API_URL           完整 URL，覆盖 API_HOST + API_PORT
#   MODELSCOPE_CACHE  数据集缓存目录（默认 ./datasets，可复用）
#   HTTPS_PROXY       下载数据集用的代理（默认空 = 直连；可显式传值挂代理）
#   HTTP_PROXY        同上
#   NLTK_PROXY        NLTK 下载专用代理（默认 http://172.22.220.21:20171）
#   NO_PROXY          代理白名单（默认含 API_HOST，避免推理走代理）
#   MODEL_NAME        模型名（默认 /media/llm/Qwen/Qwen3.6-35B-A3B，与 make check 一致）
#   API_KEY           API key（默认 EMPTY）
#   LIMIT             每数据集采样数
#   EVAL_BATCH_SIZE   并发请求数
#   ENABLE_THINKING   true/false
#   MAX_TOKENS        生成长度上限
#   BFCL_FC_MODE      true=原生 fc，false=prompt 模式
#   LCB_START/LCB_END LiveCodeBench 时间窗
#   GROUPS            eval_full.py 分组
#   DATASETS          eval_reasoning_deep.py 数据集（注意：与 DL_DATASETS 不同）
#   DL_DATASETS       download 要下载的 ModelScope 仓库 ID 列表（默认 = 全量 DATASETS_ALL）
#   FORCE_DOWNLOAD    设为 1 强制重新下载（忽略缓存检查）
#   NLTK_RESOURCES    download-nltk 要下载的 NLTK 资源（默认 punkt punkt_tab）
#   SUBSETS           eval_tool_calling.py 子集
#   COMPARE           eval_reasoning_deep.py thinking on/off 对比（1=开）
#   NO_THINKING       eval_full.py 全关 thinking（1=开）
#   NO_FC             eval_tool_calling.py prompt 模式（1=开）
#   BFCL_VERSION      v3 或 v4（默认 v3）
#   CONDA_ENV         conda 环境名（默认 model_test）
# ============================================================================

SHELL := /bin/bash

# ---- 默认值（可被 make X=Y 或 env 覆盖）---------------------------------
# 推理服务
API_HOST        ?= 61.49.53.41
API_PORT        ?= 30001
API_URL         ?= http://$(API_HOST):$(API_PORT)/v1/
MODEL_NAME      ?= /media/llm/Qwen/Qwen3.6-35B-A3B
API_KEY         ?= EMPTY

# 通用采样 / 并发
LIMIT           ?= 50
EVAL_BATCH_SIZE ?= 16

# thinking 模式（quick / reasoning / reasoning-hard 生效；chinese 不读）
ENABLE_THINKING ?= true

# 生成长度上限：留空，各脚本自定（quick=8192, reasoning_hard=32000）
MAX_TOKENS      ?=

# BFCL：false=prompt 模式（最稳，无需服务端 tool parser）
BFCL_FC_MODE    ?= false

# LiveCodeBench 时间窗（建议取模型 cutoff 之后）
LCB_START       ?= 2024-08-01
LCB_END         ?= 2026-06-01

# 脚本所在目录（绝对路径，避免 cd 后 ./ 失效）
SCRIPT_DIR       := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

# 数据集缓存（固定目录，可跨 target 复用；下载一次即可）
# 默认放脚本同级 ./datasets/ 下，跟随项目走、便于打包/迁移
MODELSCOPE_CACHE ?= $(SCRIPT_DIR)/datasets

# 代理：
#   - 数据集下载（download）：默认不挂代理，ModelScope 国内访问通常直连可用
#   - NLTK 下载（download-nltk）：必须挂代理（GitHub 国内不通）
#   - 评测 target：永远不挂代理
# 想给数据集下载也挂代理，显式传：make download HTTPS_PROXY=http://...
HTTPS_PROXY     ?=
HTTP_PROXY      ?=
# NLTK 专用代理（与上面分离，便于"数据集直连 + NLTK 走代理"的常见组合）
NLTK_PROXY      ?= http://172.22.220.21:20171
NO_PROXY        ?= localhost,127.0.0.1,$(API_HOST)

# 数据集列表（quick = 冒烟必需；all = 全部脚本可能用到的）
# 注意：使用 ModelScope 仓库 ID，不是 evalscope 的内部数据集名
# 以下 ID 与 evalscope 1.8.1 源码中各 BenchmarkMeta.dataset_id 一一对应
# （查询命令：python -c 'from evalscope.api.registry import get_benchmark; print(get_benchmark("xxx").dataset_id)'）
DATASETS_QUICK := AI-ModelScope/gsm8k opencompass/ifeval AI-ModelScope/gpqa_diamond
DATASETS_ALL   := $(DATASETS_QUICK) \
                  evalscope/ceval evalscope/cmmlu \
                  cais/mmlu TIGER-Lab/MMLU-Pro \
                  opencompass/humaneval AI-ModelScope/MATH-500 \
                  evalscope/aime25
# reasoning-hard 专用；LCB 默认只下 release_latest 子集（~2.4GB，非全量 48GB）
LCB_DATASET    := evalscope/livecodebench_code_generation_lite_parquet
LCB_SUBSET     ?= release_latest
DATASETS_HARD  := AI-ModelScope/gpqa_diamond evalscope/aime25 $(LCB_DATASET)
# 如某 ID 在国内访问慢，可改用打包 zip：make download-zip

# 官方打包（含 arc/bbh/ceval/cmmlu/competition_math/gsm8k/hellaswag/humaneval/mmlu/race/trivia_qa/truthful_qa）
DATA_ZIP_URL := https://modelscope.oss-cn-beijing.aliyuncs.com/open_data/benchmark/data.zip

# NLTK 资源（ifeval 用到的分词器；GitHub 下载需走代理）
NLTK_RESOURCES := punkt punkt_tab

# Python 脚本可选开关 / 多值参数（留空 = 走脚本默认）
GROUPS          ?=
DATASETS        ?=
SUBSETS         ?=
COMPARE         ?=
NO_THINKING     ?=
NO_FC           ?=
BFCL_VERSION    ?= v3
CONDA_ENV       ?= model_test

# 数据集缓存预检：跑评测 target 前自动检查 MODELSCOPE_CACHE 是否有所需数据集
# 缺失则警告并提示 make download；SKIP_DATASET_CHECK=1 可跳过
SKIP_DATASET_CHECK ?=

# 每个 target 需要预下载的数据集（ModelScope ID，与 DATASETS_QUICK/ALL 同口径）
# 注意：变量名里不能用 "-"（Make 会当减号），target 名带 - 时变量改用 _
NEED_quick          := AI-ModelScope/gsm8k opencompass/ifeval AI-ModelScope/gpqa_diamond
NEED_chinese        := evalscope/ceval evalscope/cmmlu
NEED_reasoning      := AI-ModelScope/gsm8k AI-ModelScope/MATH-500 opencompass/humaneval
NEED_reasoning_hard := AI-ModelScope/gpqa_diamond evalscope/aime25 evalscope/livecodebench_code_generation_lite_parquet
NEED_reasoning_deep := AI-ModelScope/gsm8k AI-ModelScope/MATH-500 evalscope/aime25
NEED_full           := evalscope/ceval evalscope/cmmlu cais/mmlu \
                       TIGER-Lab/MMLU-Pro AI-ModelScope/gsm8k AI-ModelScope/MATH-500 \
                       opencompass/humaneval opencompass/ifeval
# tool-calling 用 bfcl-eval 包内置数据，不在 modelscope cache，留空跳过检查
NEED_tool           :=

# ---- 导出到所有子进程 ---------------------------------------------------
export API_HOST API_PORT API_URL MODEL_NAME API_KEY LIMIT EVAL_BATCH_SIZE
export ENABLE_THINKING MAX_TOKENS BFCL_FC_MODE LCB_START LCB_END LCB_SUBSET CODE_BENCH
export MODELSCOPE_CACHE NO_PROXY
USE_MODELSCOPE_HUB := 1
export USE_MODELSCOPE_HUB

# ---- argparse 参数拼装 -------------------------------------------------
FULL_ARGS  :=
ifneq ($(strip $(LIMIT)),)
FULL_ARGS  += --limit $(LIMIT)
endif
ifneq ($(strip $(EVAL_BATCH_SIZE)),)
FULL_ARGS  += --eval-batch-size $(EVAL_BATCH_SIZE)
endif
ifneq ($(strip $(GROUPS)),)
FULL_ARGS  += --groups $(GROUPS)
endif
ifeq ($(NO_THINKING),1)
FULL_ARGS  += --no-thinking
endif

DEEP_ARGS  :=
ifneq ($(strip $(LIMIT)),)
DEEP_ARGS  += --limit $(LIMIT)
endif
ifneq ($(strip $(EVAL_BATCH_SIZE)),)
DEEP_ARGS  += --eval-batch-size $(EVAL_BATCH_SIZE)
endif
ifneq ($(strip $(DATASETS)),)
DEEP_ARGS  += --datasets $(DATASETS)
endif
ifeq ($(COMPARE),1)
DEEP_ARGS  += --compare
endif

TOOL_ARGS  := --version $(BFCL_VERSION)
ifneq ($(strip $(LIMIT)),)
TOOL_ARGS  += --limit $(LIMIT)
endif
ifneq ($(strip $(EVAL_BATCH_SIZE)),)
TOOL_ARGS  += --eval-batch-size $(EVAL_BATCH_SIZE)
endif
ifneq ($(strip $(SUBSETS)),)
TOOL_ARGS  += --subsets $(SUBSETS)
endif
ifeq ($(NO_FC),1)
TOOL_ARGS  += --no-fc
endif

# ---- conda 激活 + 执行 Python 脚本（用 define 避免变量二次展开）---------
# 使用：$(call run_py,脚本名,参数)
define run_py
	@bash -lc 'source "$$(conda info --base)/etc/profile.d/conda.sh" && \
	    conda activate $(CONDA_ENV) && \
	    cd "$(SCRIPT_DIR)" && \
	    python $(1) $(2)'
endef

# ---- 数据集缓存预检 ------------------------------------------------------
# 使用：$(call check_datasets,数据集ID列表)
# - 列表为空 → 静默跳过（如 BFCL）
# - SKIP_DATASET_CHECK=1 → 静默跳过
# - 缺失任一数据集 → 打印警告 + 提示 make download + 3 秒后继续（Ctrl+C 可中止）
# ModelScope 会同时建斜杠版（org/name）和三下划线版（org___name）目录，任一存在即视为已缓存
define check_datasets
	@if [ "$(SKIP_DATASET_CHECK)" != "1" ] && [ -n "$(strip $(1))" ]; then \
	  need_dl=""; \
	  for d in $(1); do \
	    flat=$$(echo "$$d" | sed 's|/|___|'); \
	    if [ ! -d "$(MODELSCOPE_CACHE)/datasets/$$d" ] && \
	       [ ! -d "$(MODELSCOPE_CACHE)/datasets/$$flat" ] && \
	       [ ! -d "$(MODELSCOPE_CACHE)/hub/datasets/$$d" ] && \
	       [ ! -d "$(MODELSCOPE_CACHE)/hub/datasets/$$flat" ]; then \
	      need_dl="$$need_dl $$d"; \
	    fi; \
	  done; \
	  if [ -n "$$need_dl" ]; then \
	    echo ""; \
	    echo "============================================================"; \
	    echo "  [WARN] 以下数据集未在缓存中找到："; \
	    echo "         $(MODELSCOPE_CACHE)"; \
	    for d in $$need_dl; do echo "           - $$d"; done; \
	    echo ""; \
	    echo "  评测会尝试在线访问 www.modelscope.cn，若网络受限可能 SSL 失败。"; \
	    echo "  推荐先执行：  make download                 # 走配置的代理"; \
	    echo "  自定义列表：  make download DL_DATASETS=\"$$need_dl\""; \
	    echo "  绕过检查：    SKIP_DATASET_CHECK=1 make ..."; \
	    echo "============================================================"; \
	    echo ""; \
	    echo "  >>> 3 秒后继续评测，Ctrl+C 中止..."; \
	    sleep 3; \
	  fi; \
	fi
endef

# ============================================================================
.PHONY: help install check quick chinese reasoning reasoning-hard reasoning-deep \
        full tool-calling tool-v3 tool-v4 all clean print-config \
        download download-hard download-nltk download-zip

help:
	@echo ""
	@echo "EvalScope 能力评测  Makefile"
	@echo "============================================================"
	@echo "  make quick               冒烟（gsm8k/ifeval/gpqa/bfcl_v3）"
	@echo "  make chinese             中文综合（ceval + cmmlu）"
	@echo "  make reasoning           推理基础（gsm8k + math_500 + humaneval）"
	@echo "  make reasoning-hard      推理硬骨头（gpqa_diamond + aime25 + lcb）"
	@echo "  make reasoning-deep      推理深度（gsm8k + math_500 + aime25）"
	@echo "  make full                综合 5 维度（Python）"
	@echo "  make tool-calling        工具调用 BFCL v3（= make tool-v3）"
	@echo "  make tool-v3             BFCL v3"
	@echo "  make tool-v4             BFCL v4（含 web_search / memory）"
	@echo "  make all                 quick + chinese + reasoning + tool-v3"
	@echo "  make install             安装依赖（evalscope + bfcl-eval）"
	@echo "  make check               查询推理服务已注册模型"
	@echo "  make download            预下载全部数据集 + NLTK（已缓存自动跳过）"
	@echo "  make download-hard       预下载 reasoning-hard（LCB 仅 release_latest ~2.4GB）"
	@echo "  make download-nltk       仅下载 NLTK 资源（ifeval 必需，需走代理）"
	@echo "  make download-zip        官方打包 zip（含 ceval/cmmlu/mmlu/gsm8k/...）"
	@echo "  make print-config        打印当前生效的参数"
	@echo "  make clean               清理 outputs/（含交互确认）"
	@echo ""
	@echo "传参示例："
	@echo "  make quick LIMIT=50 EVAL_BATCH_SIZE=16"
	@echo "  make full  GROUPS=\"chinese reasoning\" LIMIT=100"
	@echo "  make tool-v4 SUBSETS=\"simple_python multiple\" LIMIT=20"
	@echo "  make reasoning-deep COMPARE=1 LIMIT=30"
	@echo "  make quick API_PORT=30000 MODEL_NAME=Qwen3.6-35B-A3B"
	@echo "  make quick API_HOST=10.0.0.5 API_PORT=8000     # 用 host+port，URL 自动拼"
	@echo "  make quick API_URL=http://10.0.0.5:8000/v1     # 直接整段覆盖"
	@echo "  make download HTTPS_PROXY=http://proxy:8080    # 数据集下载挂代理（默认不挂）"
	@echo "  make download DL_DATASETS=\"AI-ModelScope/gsm8k\" # 只下指定数据集"
	@echo "  make download-hard                           # reasoning-hard（LCB 仅 ~2.4GB）"
	@echo "  CODE_BENCH=humaneval make reasoning-hard     # 用 humaneval 替代 LCB（~几 MB）"
	@echo "  FORCE_DOWNLOAD=1 make download                 # 强制重新下载（忽略缓存）"
	@echo "  make download MODELSCOPE_CACHE=/data/ms_cache  # 缓存到共享盘"
	@echo "  make download-nltk NLTK_PROXY=http://x:y       # 换 NLTK 代理"
	@echo "  SKIP_DATASET_CHECK=1 make quick               # 跳过数据集预检"
	@echo ""

print-config:
	@echo "API_HOST        = $(API_HOST)"
	@echo "API_PORT        = $(API_PORT)"
	@echo "API_URL         = $(API_URL)"
	@echo "MODELSCOPE_CACHE= $(MODELSCOPE_CACHE)"
	@echo "HTTPS_PROXY     = $(HTTPS_PROXY)  (空=直连，data 下载用)"
	@echo "NLTK_PROXY      = $(NLTK_PROXY)  (NLTK 下载专用)"
	@echo "NO_PROXY        = $(NO_PROXY)"
	@echo "MODEL_NAME      = $(MODEL_NAME)"
	@echo "API_KEY         = $(API_KEY)"
	@echo "LIMIT           = $(LIMIT)"
	@echo "EVAL_BATCH_SIZE = $(EVAL_BATCH_SIZE)"
	@echo "ENABLE_THINKING = $(ENABLE_THINKING)"
	@echo "MAX_TOKENS      = $(MAX_TOKENS)"
	@echo "BFCL_FC_MODE    = $(BFCL_FC_MODE)"
	@echo "BFCL_VERSION    = $(BFCL_VERSION)"
	@echo "GROUPS          = $(GROUPS)"
	@echo "DATASETS        = $(DATASETS)"
	@echo "SUBSETS         = $(SUBSETS)"
	@echo "COMPARE         = $(COMPARE)"
	@echo "NO_THINKING     = $(NO_THINKING)"
	@echo "NO_FC           = $(NO_FC)"
	@echo "CONDA_ENV       = $(CONDA_ENV)"
	@echo "----"
	@echo "FULL_ARGS       = $(FULL_ARGS)"
	@echo "DEEP_ARGS       = $(DEEP_ARGS)"
	@echo "TOOL_ARGS       = $(TOOL_ARGS)"

install:
	@bash -lc 'source "$$(conda info --base)/etc/profile.d/conda.sh" && \
	    conda activate $(CONDA_ENV) && \
	    pip install --timeout 60 --retries 3 "evalscope[all]==1.8.1" && \
	    pip install --timeout 60 --retries 3 -i https://pypi.org/simple/ bfcl-eval==2025.10.27.1'

check:
	@echo "推理服务 $(API_HOST):$(API_PORT) 已注册模型："
	@curl -s "http://$(API_HOST):$(API_PORT)/v1/models" | (jq -r '.data[] | "  id: \(.id)  max_len: \(.max_model_len // "n/a")"' 2>/dev/null || cat) \
		|| echo "[ERROR] 推理服务未启动或 $(API_HOST):$(API_PORT) 不正确"
	@echo ""
	@echo "当前 MODEL_NAME = $(MODEL_NAME)"
	@echo "若不一致，请：make quick MODEL_NAME=\"<上面 id>\""

# ---- 数据集预下载 ---------------------------------------------------------
# 用法：
#   make download                              # 下全部常规数据集 + NLTK（已缓存自动跳过）
#   make download-hard                         # 下 reasoning-hard 专用（含 LCB ~48GB）
#   make download DL_DATASETS="org/a org/b"    # 只下指定数据集
#   make download HTTPS_PROXY=http://x:y       # 挂代理
#   make download MODELSCOPE_CACHE=/data/ms    # 改缓存目录
#   FORCE_DOWNLOAD=1 make download             # 强制重新下载（忽略缓存检查）
#   make download-nltk                         # 仅下 NLTK 资源
#   make download-zip                          # 官方打包 zip（含 ceval/cmmlu/mmlu/gsm8k/...）
# 代理变量仅在下载子进程内生效，不影响评测 target。
DL_DATASETS    ?= $(DATASETS_ALL)
FORCE_DOWNLOAD ?=

download-hard:
	@$(MAKE) download DL_DATASETS="$(DATASETS_HARD)"

download:
	@mkdir -p "$(MODELSCOPE_CACHE)"
	@echo "============================================================"
	@echo "数据集预下载"
	@echo "缓存根目录   :  $(MODELSCOPE_CACHE)"
	@echo "数据集子目录 :  $(MODELSCOPE_CACHE)/datasets/<org>/<name>"
	@if [ -n "$(HTTPS_PROXY)" ]; then \
	  echo "代理         :  $(HTTPS_PROXY)"; \
	else \
	  echo "代理         :  无（直连 ModelScope；加代理：HTTPS_PROXY=http://...）"; \
	fi
	@if [ "$(FORCE_DOWNLOAD)" = "1" ]; then \
	  echo "模式         :  强制重新下载（FORCE_DOWNLOAD=1）"; \
	else \
	  echo "模式         :  已缓存自动跳过（FORCE_DOWNLOAD=1 可强制重下）"; \
	fi
	@echo "数据集 ($(words $(DL_DATASETS)) 个):"
	@for d in $(DL_DATASETS); do echo "    - $$d"; done
	@echo "============================================================"
	@bash -lc 'source "$$(conda info --base)/etc/profile.d/conda.sh" && \
	    conda activate $(CONDA_ENV) && \
	    proxy="$(HTTPS_PROXY)"; \
	    if [ -n "$$proxy" ]; then \
	      export HTTPS_PROXY="$$proxy" HTTP_PROXY="$$proxy" \
	             https_proxy="$$proxy" http_proxy="$$proxy"; \
	    else \
	      unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy; \
	    fi; \
	    export NO_PROXY="$(NO_PROXY)" no_proxy="$(NO_PROXY)" \
	           MODELSCOPE_CACHE="$(MODELSCOPE_CACHE)" \
	           PYTHONUNBUFFERED=1; \
	    ok=0; skip=0; fail=0; \
	    cache="$(MODELSCOPE_CACHE)"; \
	    watch_download_progress() { \
	      local d="$$1" pid="$$2"; \
	      local flat subset start elapsed best_dir best_bytes human cnt sz_bytes p; \
	      flat=$$(echo "$$d" | sed "s|/|___|g"); \
	      subset="$(LCB_SUBSET)"; \
	      start=$$(date +%s); \
	      while kill -0 "$$pid" 2>/dev/null; do \
	        sleep 3; \
	        elapsed=$$(( $$(date +%s) - start )); \
	        best_dir=""; best_bytes=0; \
	        for p in \
	          "$$cache/datasets/._____temp/$$d" \
	          "$$cache/datasets/._____temp/$$flat" \
	          "$$cache/datasets/$$d/$$subset" \
	          "$$cache/datasets/$$flat/$$subset" \
	          "$$cache/datasets/$$d" \
	          "$$cache/datasets/$$flat" \
	          "$$cache/hub/datasets/$$d" \
	          "$$cache/hub/datasets/$$flat"; do \
	          if [ -d "$$p" ]; then \
	            sz_bytes=$$(du -sb "$$p" 2>/dev/null | cut -f1); \
	            if [ "$${sz_bytes:-0}" -gt "$$best_bytes" ] 2>/dev/null; then \
	              best_bytes="$$sz_bytes"; best_dir="$$p"; \
	            fi; \
	          fi; \
	        done; \
	        if [ -n "$$best_dir" ]; then \
	          human=$$(du -sh "$$best_dir" 2>/dev/null | cut -f1); \
	          cnt=$$(find "$$best_dir" -type f 2>/dev/null | wc -l); \
	          echo "    [PROGRESS] $$human  文件:$$cnt  用时:$${elapsed}s"; \
	        else \
	          echo "    [PROGRESS] 连接中...  用时:$${elapsed}s"; \
	        fi; \
	      done; \
	    }; \
	    run_modelscope_download() { \
	      local d="$$1"; \
	      if [ "$$d" = "$(LCB_DATASET)" ]; then \
	        echo "    [INFO] 仅下载 LCB 子集 $(LCB_SUBSET)/ (~2.4GB)"; \
	        modelscope download --dataset "$$d" --include "$(LCB_SUBSET)/**"; \
	      else \
	        modelscope download --dataset "$$d"; \
	      fi; \
	    }; \
	    download_one() { \
	      local d="$$1" pid rc; \
	      echo "    [INFO] 开始下载（ModelScope tqdm + 下方定时进度）..."; \
	      run_modelscope_download "$$d" & \
	      pid=$$!; \
	      watch_download_progress "$$d" "$$pid"; \
	      wait "$$pid"; rc=$$?; \
	      if [ $$rc -eq 0 ]; then \
	        echo "    [DONE] 下载完成"; \
	      else \
	        echo "    [FAIL] 下载失败 (exit $$rc)"; \
	      fi; \
	      return $$rc; \
	    }; \
	    find_cached() { \
	      local d="$$1" flat subset; \
	      flat=$$(echo "$$d" | sed "s|/|___|g"); \
	      if [ "$$d" = "$(LCB_DATASET)" ]; then \
	        subset="$(LCB_SUBSET)"; \
	        for p in "$$cache/datasets/$$d/$$subset" "$$cache/datasets/$$flat/$$subset" \
	                 "$$cache/hub/datasets/$$d/$$subset" "$$cache/hub/datasets/$$flat/$$subset"; do \
	          if [ -d "$$p" ] && \
	             [ -n "$$(find "$$p" -type f \( -name "*.parquet" -o -name "*.jsonl" -o -name "*.json" -o -name "*.csv" -o -name "*.arrow" \) -print -quit 2>/dev/null)" ]; then \
	            echo "$$p"; return 0; \
	          fi; \
	        done; \
	        return 1; \
	      fi; \
	      for p in "$$cache/datasets/$$d" "$$cache/datasets/$$flat" \
	               "$$cache/hub/datasets/$$d" "$$cache/hub/datasets/$$flat"; do \
	        if [ -d "$$p" ] && \
	           [ -n "$$(find "$$p" -type f \( -name "*.parquet" -o -name "*.jsonl" -o -name "*.json" -o -name "*.csv" -o -name "*.arrow" \) -print -quit 2>/dev/null)" ]; then \
	          echo "$$p"; return 0; \
	        fi; \
	      done; return 1; \
	    }; \
	    for d in $(DL_DATASETS); do \
	      echo ""; echo ">>> $$d"; \
	      cached=$$(find_cached "$$d" || true); \
	      if [ "$(FORCE_DOWNLOAD)" != "1" ] && [ -n "$$cached" ]; then \
	        size=$$(du -sh "$$cached" 2>/dev/null | cut -f1); \
	        echo "    [SKIP] 已缓存 ($$size)  $$cached"; \
	        skip=$$((skip+1)); \
	      elif download_one "$$d"; then \
	        ok=$$((ok+1)); \
	      else \
	        echo "    [WARN] 下载失败（可能数据集名变更或网络抖动，可重试）"; \
	        fail=$$((fail+1)); \
	      fi; \
	    done; \
	    unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy; \
	    echo ""; \
	    echo "============================================================"; \
	    echo "ModelScope：跳过 $$skip / 新下载 $$ok / 失败 $$fail"; \
	    echo "缓存目录：$(MODELSCOPE_CACHE)/datasets/"; \
	    echo "代理已在本进程退出时清除"'
	@$(MAKE) download-nltk

# 官方打包 zip（最稳，适合 ModelScope 访问慢时使用）
# 解包到 MODELSCOPE_CACHE/data/，含 arc/bbh/ceval/cmmlu/gsm8k/humaneval/mmlu/...
# 已解包时自动跳过（FORCE_DOWNLOAD=1 重新下载）
download-zip:
	@mkdir -p "$(MODELSCOPE_CACHE)/data"
	@echo "============================================================"
	@echo "官方打包数据集 zip"
	@echo "URL    :  $(DATA_ZIP_URL)"
	@echo "解包到 :  $(MODELSCOPE_CACHE)/data/"
	@echo "============================================================"
	@bash -lc 'dest="$(MODELSCOPE_CACHE)/data"; \
	    if [ "$(FORCE_DOWNLOAD)" != "1" ] && \
	       [ -d "$$dest" ] && [ -n "$$(ls -A "$$dest" 2>/dev/null)" ]; then \
	      echo "    [SKIP] $$dest/ 已有内容，跳过（FORCE_DOWNLOAD=1 强制重下）"; \
	      exit 0; \
	    fi; \
	    proxy="$(HTTPS_PROXY)"; \
	    if [ -n "$$proxy" ]; then \
	      export HTTPS_PROXY="$$proxy" HTTP_PROXY="$$proxy" \
	             https_proxy="$$proxy" http_proxy="$$proxy"; \
	    else \
	      unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy; \
	    fi; \
	    export NO_PROXY="$(NO_PROXY)" no_proxy="$(NO_PROXY)"; \
	    tmp="$(MODELSCOPE_CACHE)/data.zip"; \
	    echo ">>> 下载 $(DATA_ZIP_URL)"; \
	    if curl -fL --progress-bar --retry 3 --retry-delay 5 -o "$$tmp" "$(DATA_ZIP_URL)"; then \
	      echo ""; \
	      echo ">>> 解包到 $$dest/"; \
	      unzip -q -o "$$tmp" -d "$$dest/" && rm -f "$$tmp" && \
	      echo "完成：解包到 $$dest/"; \
	    else \
	      echo "[ERROR] 下载失败，可尝试挂代理：make download-zip HTTPS_PROXY=http://..."; \
	      exit 1; \
	    fi'

# NLTK 资源（ifeval 分词必需；已缓存自动跳过）
# 如需走独立代理：make download-nltk NLTK_PROXY=http://...
download-nltk:
	@echo "============================================================"
	@echo "NLTK 资源下载"
	@echo "代理   :  $(if $(NLTK_PROXY),$(NLTK_PROXY),无)"
	@echo "资源   :  $(NLTK_RESOURCES)"
	@echo "============================================================"
	@bash -lc 'source "$$(conda info --base)/etc/profile.d/conda.sh" && \
	    conda activate $(CONDA_ENV) && \
	    echo "NLTK 搜索路径："; \
	    python -c "import nltk; [print(\"    \" + p) for p in nltk.data.path]"; \
	    echo ""; \
	    if [ -n "$(NLTK_PROXY)" ]; then \
	      export HTTPS_PROXY="$(NLTK_PROXY)" HTTP_PROXY="$(NLTK_PROXY)" \
	             https_proxy="$(NLTK_PROXY)" http_proxy="$(NLTK_PROXY)"; \
	    else \
	      unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy; \
	    fi; \
	    export NO_PROXY="$(NO_PROXY)" no_proxy="$(NO_PROXY)" \
	           PYTHONUNBUFFERED=1; \
	    ok=0; skip=0; fail=0; \
	    nltk_dir=$$(python -c "import nltk; print(nltk.data.path[0])" 2>/dev/null || echo "$$HOME/nltk_data"); \
	    watch_nltk_progress() { \
	      local pid="$$1" start elapsed human cnt; \
	      start=$$(date +%s); \
	      while kill -0 "$$pid" 2>/dev/null; do \
	        sleep 2; \
	        elapsed=$$(( $$(date +%s) - start )); \
	        if [ -d "$$nltk_dir" ]; then \
	          human=$$(du -sh "$$nltk_dir" 2>/dev/null | cut -f1); \
	          cnt=$$(find "$$nltk_dir" -type f 2>/dev/null | wc -l); \
	          echo "    [PROGRESS] $$human  文件:$$cnt  用时:$${elapsed}s"; \
	        else \
	          echo "    [PROGRESS] 连接中...  用时:$${elapsed}s"; \
	        fi; \
	      done; \
	    }; \
	    for r in $(NLTK_RESOURCES); do \
	      echo ""; echo ">>> $$r"; \
	      if [ "$(FORCE_DOWNLOAD)" != "1" ] && \
	         python -c "import nltk; nltk.data.find(\"tokenizers/$$r\")" 2>/dev/null; then \
	        echo "    [SKIP] 已缓存，跳过"; \
	        skip=$$((skip+1)); \
	      else \
	        echo "    [INFO] 开始下载..."; \
	        python -m nltk.downloader "$$r" & \
	        pid=$$!; \
	        watch_nltk_progress "$$pid"; \
	        if wait "$$pid"; then \
	          echo "    [DONE] 下载完成"; \
	          ok=$$((ok+1)); \
	        else \
	          echo "    [FAIL] 下载失败"; fail=$$((fail+1)); \
	        fi; \
	      fi; \
	    done; \
	    unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy; \
	    echo ""; \
	    echo "============================================================"; \
	    echo "NLTK：跳过 $$skip / 新下载 $$ok / 失败 $$fail"; \
	    echo "缓存目录：$$(python -c "import nltk; print(nltk.data.path[0])" 2>/dev/null || echo "~/nltk_data")"; \
	    echo "代理已在本进程退出时清除"'

# ---- Shell 脚本 target（脚本内部已 conda activate，环境变量经 export 透传）---
quick:
	$(call check_datasets,$(NEED_quick))
	cd "$(SCRIPT_DIR)" && ./eval_quick.sh

chinese:
	$(call check_datasets,$(NEED_chinese))
	cd "$(SCRIPT_DIR)" && ./eval_chinese.sh

reasoning:
	$(call check_datasets,$(NEED_reasoning))
	cd "$(SCRIPT_DIR)" && ./eval_reasoning.sh

reasoning-hard:
	$(call check_datasets,$(NEED_reasoning_hard))
	cd "$(SCRIPT_DIR)" && ./eval_reasoning_hard.sh

# ---- Python 脚本 target ----------------------------------------------------
reasoning-deep:
	$(call check_datasets,$(NEED_reasoning_deep))
	$(call run_py,eval_reasoning_deep.py,$(DEEP_ARGS))

full:
	$(call check_datasets,$(NEED_full))
	$(call run_py,eval_full.py,$(FULL_ARGS))

tool-calling: tool-v3

tool-v3:
	$(MAKE) _tool BFCL_VERSION=v3

tool-v4:
	$(MAKE) _tool BFCL_VERSION=v4

_tool:
	$(call check_datasets,$(NEED_tool))
	$(call run_py,eval_tool_calling.py,$(TOOL_ARGS))

# ---- 组合 target ----------------------------------------------------------
all: quick chinese reasoning tool-v3

clean:
	@if [ -t 0 ]; then \
	    read -p "确认删除 outputs/ 下全部评测结果? [y/N] " ans; \
	else \
	    echo "[clean] 非交互模式，直接清理 outputs/"; ans="y"; \
	fi; \
	if [ "$$ans" = "y" ] || [ "$$ans" = "Y" ]; then \
	    rm -rf "$(SCRIPT_DIR)/outputs/"; echo "已清理 outputs/"; \
	else \
	    echo "已取消"; \
	fi

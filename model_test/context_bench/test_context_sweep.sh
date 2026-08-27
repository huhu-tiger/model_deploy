#!/bin/bash
# ============================================================================
# 长上下文分档压测（按接口 max_model_len 自动切档 + 并发扫描 + 超时保护）
# ============================================================================
# 公共能力在 common/，本文件只编排流程。后续其它脚本可 source / 调用 common。
#
# 用法:
#   ./test_context_sweep.sh
#   API_BASE=http://172.31.0.32:30001 ./test_context_sweep.sh
#   CONTEXT_LEVELS=128,96,64,32,16 PARALLEL=4 ./test_context_sweep.sh
#   PREFIX_MODES=cache_miss ./test_context_sweep.sh
#   CONFIG=/path/to/content.json ./test_context_sweep.sh
#
# 默认同时跑 cache_miss（冷缓存）和 cache_hit（共享前缀预热后的热缓存）。
# 默认档位为 4/8/16/32/64/128/256/300K，128K 并发为 2。
# 正文用汉字「测」铺满（与 max_length 相同），末尾要求连续输出数字，而不是只回复 OK。
# 正文/填充/模式在 config/content.json。
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common/env.sh
source "${SCRIPT_DIR}/common/env.sh"
# shellcheck source=common/timeout.sh
source "${SCRIPT_DIR}/common/timeout.sh"

cd "${SCRIPT_DIR}"

# --- 目标服务 ---------------------------------------------------------------
API_BASE="${API_BASE:-http://127.0.0.1:30001}"
CACHE_BASE_URL="${CACHE_BASE_URL:-}"
API_KEY="${API_KEY:-}"
MODEL_NAME="${MODEL_NAME:-}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-}"

# --- 上下文档位 -------------------------------------------------------------
CONTEXT_LEVELS="${CONTEXT_LEVELS:-}"
CONTEXT_MAX_K="${CONTEXT_MAX_K:-}"
MIN_CONTEXT_K="${MIN_CONTEXT_K:-}"
K_UNIT="${K_UNIT:-1024}"
MAX_TOKENS="${MAX_TOKENS:-}"
RESERVE_TOKENS="${RESERVE_TOKENS:-}"
CONTEXT_FRACTIONS="${CONTEXT_FRACTIONS:-}"

# --- 并发 / 超时 ------------------------------------------------------------
# PARALLEL 单个数字 = PARALLEL_ANCHOR_K 档位的并发；上下文每升/降一档，并发减半/翻倍。
# 未设环境变量时从 config/content.json 读取。
PARALLEL="${PARALLEL:-}"
PARALLEL_MAX="${PARALLEL_MAX:-}"
PARALLEL_ANCHOR_K="${PARALLEL_ANCHOR_K:-}"
NUMBER_MULT="${NUMBER_MULT:-}"
NUMBER_MAX="${NUMBER_MAX:-}"
CONNECT_TIMEOUT="${CONNECT_TIMEOUT:-30}"
READ_TIMEOUT="${READ_TIMEOUT:-}"
TOTAL_TIMEOUT="${TOTAL_TIMEOUT:-}"
DURATION="${DURATION:-}"

# --- 其它 -------------------------------------------------------------------
if [[ -z "${EXTRA_ARGS:-}" ]]; then
  EXTRA_ARGS='{"chat_template_kwargs":{"enable_thinking":false},"ignore_eos":true}'
fi
SWANLAB="${SWANLAB:-0}"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-8}"
BENCH_NAME="${BENCH_NAME:-}"
CONFIG="${CONFIG:-${SCRIPT_DIR}/config/content.json}"
PREFIX_MODES="${PREFIX_MODES:-}"

if [[ -z "${CACHE_BASE_URL}" ]]; then
  CACHE_BASE_URL="$(python3 -c '
import sys
from urllib.parse import urlsplit, urlunsplit
url = urlsplit(sys.argv[1])
host = url.hostname or "127.0.0.1"
netloc = f"[{host}]" if ":" in host else host
if url.username:
    auth = url.username + ((":" + url.password) if url.password else "")
    netloc = auth + "@" + netloc
netloc += ":30003"
print(urlunsplit((url.scheme or "http", netloc, "", "", "")))
' "${API_BASE}")" || die "无法从 API_BASE 推导 CACHE_BASE_URL"
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_ROOT="${SCRIPT_DIR}/outputs/${STAMP}/context_sweep"
DATA_DIR="${OUT_ROOT}/prompts"
mkdir -p "${DATA_DIR}"
[[ -f "${CONFIG}" ]] || die "找不到内容配置: ${CONFIG}"
cp -f "${CONFIG}" "${OUT_ROOT}/content.json"

API_PY="${COMMON_PY}/api.py"
CTX_PY="${COMMON_PY}/context.py"
PROMPT_PY="${COMMON_PY}/prompts.py"
REPORT_PY="${COMMON_PY}/report.py"
CONFIG_PY="${COMMON_PY}/config.py"

cfg_get() {
  python3 "${CONFIG_PY}" --config "${CONFIG}" get "$1"
}

[[ -n "${PARALLEL}" ]] || PARALLEL="$(cfg_get parallel)"
[[ -n "${PARALLEL_MAX}" ]] || PARALLEL_MAX="$(cfg_get parallel_max)"
[[ -n "${PARALLEL_ANCHOR_K}" ]] || PARALLEL_ANCHOR_K="$(cfg_get parallel_anchor_k)"
[[ -n "${NUMBER_MULT}" ]] || NUMBER_MULT="$(cfg_get number_mult)"
[[ -n "${NUMBER_MAX}" ]] || NUMBER_MAX="$(cfg_get number_max)"
[[ -n "${MAX_TOKENS}" ]] || MAX_TOKENS="$(cfg_get max_tokens)"
[[ -n "${RESERVE_TOKENS}" ]] || RESERVE_TOKENS="$(cfg_get reserve_tokens)"
[[ -n "${MIN_CONTEXT_K}" ]] || MIN_CONTEXT_K="$(cfg_get min_context_k)"
[[ -n "${CONTEXT_LEVELS}" ]] || CONTEXT_LEVELS="$(cfg_get context_levels)"
[[ -n "${CONTEXT_FRACTIONS}" ]] || CONTEXT_FRACTIONS="$(cfg_get context_fractions)"
[[ -n "${PARALLEL}" ]] || die "parallel 未配置"
[[ -n "${PARALLEL_MAX}" ]] || PARALLEL_MAX=64
[[ -n "${PARALLEL_ANCHOR_K}" ]] || PARALLEL_ANCHOR_K=128
[[ -n "${NUMBER_MULT}" ]] || NUMBER_MULT=2
[[ -n "${NUMBER_MAX}" ]] || NUMBER_MAX=16
[[ -n "${MAX_TOKENS}" ]] || MAX_TOKENS=256
[[ -n "${RESERVE_TOKENS}" ]] || RESERVE_TOKENS=512
[[ -n "${MIN_CONTEXT_K}" ]] || MIN_CONTEXT_K=8

record_run() {
  python3 "${REPORT_PY}" record --root "${OUT_ROOT}" "$@"
}

# --- 拉 /v1/models ----------------------------------------------------------
log "查询模型信息: ${API_BASE}/v1/models"
FETCH_ARGS=(--base "${API_BASE}" --timeout 20)
[[ -n "${MODEL_NAME}" ]] && FETCH_ARGS+=(--model "${MODEL_NAME}")
[[ -n "${API_KEY}" ]] && FETCH_ARGS+=(--api-key "${API_KEY}")

MODEL_INFO="$(python3 "${API_PY}" "${FETCH_ARGS[@]}")" || die "无法访问 ${API_BASE}/v1/models"
echo "${MODEL_INFO}" | python3 -m json.tool || die "模型信息不是合法 JSON"
echo "${MODEL_INFO}" > "${OUT_ROOT}/api_info.json"

API_URL="$(python3 "${API_PY}" --base "${API_BASE}" --print-chat-url)"

if [[ -z "${MODEL_NAME}" ]]; then
  MODEL_NAME="$(echo "${MODEL_INFO}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"] or "")')"
fi
[[ -n "${MODEL_NAME}" ]] || die "未得到模型名，请设 MODEL_NAME"

if [[ -z "${MAX_MODEL_LEN}" ]]; then
  MAX_MODEL_LEN="$(echo "${MODEL_INFO}" | python3 -c 'import json,sys; v=json.load(sys.stdin).get("max_model_len"); print(v or "")')"
fi
[[ -n "${MAX_MODEL_LEN}" ]] || die "接口未返回 max_model_len，请设 MAX_MODEL_LEN"
[[ "${MAX_MODEL_LEN}" =~ ^[0-9]+$ ]] || die "max_model_len 不是整数: ${MAX_MODEL_LEN}"

# --- 计算档位 ---------------------------------------------------------------
LEVEL_ARGS=(levels --max-model-len "${MAX_MODEL_LEN}" --k-unit "${K_UNIT}" --min-k "${MIN_CONTEXT_K}")
[[ -n "${CONTEXT_MAX_K}" ]] && LEVEL_ARGS+=(--cap-k "${CONTEXT_MAX_K}")
[[ -n "${CONTEXT_LEVELS}" ]] && LEVEL_ARGS+=(--explicit "${CONTEXT_LEVELS}")
[[ -n "${CONTEXT_FRACTIONS}" ]] && LEVEL_ARGS+=(--fractions "${CONTEXT_FRACTIONS}")
LEVELS_CSV="$(python3 "${CTX_PY}" "${LEVEL_ARGS[@]}")" || die "无法计算上下文档位"
IFS=',' read -r -a CONTEXT_KS <<< "${LEVELS_CSV}"
[[ ${#CONTEXT_KS[@]} -gt 0 ]] || die "没有可用的上下文档位"
# 长上下文、低并发先跑，避免一上来就是 64K×高并发
CONTEXT_KS_REV=()
for ((i=${#CONTEXT_KS[@]}-1; i>=0; i--)); do
  CONTEXT_KS_REV+=("${CONTEXT_KS[i]}")
done
CONTEXT_KS=("${CONTEXT_KS_REV[@]}")

PAR_PLAN="$(
  python3 "${CTX_PY}" plan --levels "${LEVELS_CSV}" --spec "${PARALLEL}" --max-parallel "${PARALLEL_MAX}" --anchor-k "${PARALLEL_ANCHOR_K}"
)" || die "计算并发方案失败"

MODE_ARGS=(--config "${CONFIG}" modes)
[[ -n "${PREFIX_MODES}" ]] && MODE_ARGS+=(--only "${PREFIX_MODES}")
MODES_CSV="$(python3 "${CONFIG_PY}" "${MODE_ARGS[@]}")" || die "读取前缀模式失败: ${CONFIG}"
IFS=',' read -r -a PREFIX_MODE_IDS <<< "${MODES_CSV}"
[[ ${#PREFIX_MODE_IDS[@]} -gt 0 ]] || die "没有启用的前缀模式"

OUT_ROOT="${OUT_ROOT}" MODEL_NAME="${MODEL_NAME}" API_URL="${API_URL}" CACHE_BASE_URL="${CACHE_BASE_URL}" MAX_MODEL_LEN="${MAX_MODEL_LEN}" \
PREFIX_MODES_CSV="${MODES_CSV}" CONFIG_PATH="${CONFIG}" PAR_PLAN="${PAR_PLAN}" PARALLEL_SPEC="${PARALLEL}" PARALLEL_ANCHOR_K="${PARALLEL_ANCHOR_K}" python3 -c '
import json, os, pathlib
p = pathlib.Path(os.environ["OUT_ROOT"]) / "sweep_meta.json"
p.write_text(json.dumps({
    "model": os.environ["MODEL_NAME"],
    "url": os.environ["API_URL"],
    "cache_base_url": os.environ["CACHE_BASE_URL"],
    "max_model_len": int(os.environ["MAX_MODEL_LEN"]),
    "prefix_modes": [x for x in os.environ.get("PREFIX_MODES_CSV", "").split(",") if x],
    "config": os.environ.get("CONFIG_PATH", ""),
    "parallel_spec": os.environ.get("PARALLEL_SPEC", ""),
    "parallel_anchor_k": int(os.environ.get("PARALLEL_ANCHOR_K", "0") or 0),
    "parallel_plan": os.environ.get("PAR_PLAN", ""),
}, ensure_ascii=False, indent=2), encoding="utf-8")
'

MODEL_SHORT="${MODEL_NAME##*/}"
[[ -n "${BENCH_NAME}" ]] || BENCH_NAME="${MODEL_SHORT}_context_sweep"

echo "=========================================="
echo "长上下文分档压测"
echo "=========================================="
echo "API:           ${API_URL}"
echo "Model:         ${MODEL_NAME}"
echo "max_model_len: ${MAX_MODEL_LEN} tokens  ($((MAX_MODEL_LEN / K_UNIT))K)"
echo "档位:          ${CONTEXT_KS[*]} K"
echo "并发方案:      ${PAR_PLAN}  (${PARALLEL_ANCHOR_K}K 并发=${PARALLEL}，上下文逐档减半/翻倍，上限 ${PARALLEL_MAX})"
echo "请求数:        parallel×${NUMBER_MULT}，单档最多 ${NUMBER_MAX}"
echo "前缀模式:      ${PREFIX_MODE_IDS[*]}  (配置 ${CONFIG})"
echo "max_tokens:    ${MAX_TOKENS}  reserve=${RESERVE_TOKENS}"
echo "输出目录:      ${OUT_ROOT}"
echo "=========================================="
echo ""

ensure_evalscope

wrote_report=0
write_summary() {
  [[ "${wrote_report}" == "1" ]] && return 0
  wrote_report=1
  python3 "${REPORT_PY}" write --root "${OUT_ROOT}" || log "汇总报告生成失败"
}
trap 'log "收到中断，写出汇总后退出"; write_summary; exit 130' INT TERM

SWAN_ARGS=()
if [[ "${SWANLAB}" == "1" ]]; then
  SWAN_ARGS=(--visualizer swanlab --swanlab-api-key local)
fi
AUTH_ARGS=()
if [[ -n "${API_KEY}" ]]; then
  AUTH_ARGS=(--api-key "${API_KEY}")
fi

run_one() {
  local ctx_k="$1"
  local parallel="$2"
  local prompt_tokens="$3"
  local n_req="$4"
  local read_to="$5"
  local total_to="$6"
  local duration="$7"
  local hard_to="$8"
  local prompt_file="$9"
  local mode="${10}"
  local warmup="${11}"

  local run_name="${BENCH_NAME}_ctx${ctx_k}k_${mode}_${prompt_tokens}t_p${parallel}"
  local run_dir="${OUT_ROOT}/ctx_${ctx_k}k_${mode}_p${parallel}"
  mkdir -p "${run_dir}"

  log "开始  ctx=${ctx_k}K  mode=${mode}  parallel=${parallel}  number=${n_req}  warmup=${warmup}  prompt≈${prompt_tokens}"

  local cmd=(
    evalscope perf
    --model "${MODEL_NAME}"
    --url "${API_URL}"
    --api openai
    --dataset line_by_line
    --dataset-path "${prompt_file}"
    --parallel "${parallel}"
    --number "${n_req}"
    --warmup-num "${warmup}"
    --min-prompt-length 1
    --max-prompt-length "$((prompt_tokens + 4096))"
    --max-tokens "${MAX_TOKENS}"
    --temperature 0.1
    --top-p 1.0
    --stream
    --connect-timeout "${CONNECT_TIMEOUT}"
    --read-timeout "${read_to}"
    --total-timeout "${total_to}"
    --duration "${duration}"
    --extra-args "${EXTRA_ARGS}"
    --name "${run_name}"
    --outputs-dir "${run_dir}"
    --no-timestamp
  )
  if ((${#AUTH_ARGS[@]})); then cmd+=("${AUTH_ARGS[@]}"); fi
  if ((${#SWAN_ARGS[@]})); then cmd+=("${SWAN_ARGS[@]}"); fi

  local log_file="${run_dir}/evalscope.log"
  local rc
  set +o pipefail
  run_with_timeout "${hard_to}" "${cmd[@]}" 2>&1 \
    | tee "${log_file}" \
    | python3 -u "${COMMON_PY}/filter_output.py"
  rc=${PIPESTATUS[0]}
  set -o pipefail
  find "${run_dir}" -name 'perf_report.html' -delete 2>/dev/null || true
  if (( rc == 0 )); then
    python3 "${COMMON_PY}/filter_output.py" summary "${run_dir}" || true
  fi
  return "${rc}"
}

reset_cache_or_die() {
  local ctx_k="$1"
  local mode="$2"
  local attempt reset_json
  local reset_args=(--base "${CACHE_BASE_URL}" --reset-cache --timeout 30)
  [[ -n "${API_KEY}" ]] && reset_args+=(--api-key "${API_KEY}")
  for attempt in 1 2 3 4 5 6; do
    reset_json="$(python3 "${API_PY}" "${reset_args[@]}" 2>/dev/null || true)"
    if echo "${reset_json}" | python3 -c 'import json,sys; sys.exit(0 if json.load(sys.stdin).get("ok") else 1)' 2>/dev/null; then
      log "已清空 prefix cache  ctx=${ctx_k}K mode=${mode} attempt=${attempt}"
      return 0
    fi
    log "清空 prefix cache 失败  ctx=${ctx_k}K mode=${mode} attempt=${attempt}/6；5 秒后重试"
    sleep 5
  done
  die "无法清空 prefix cache，停止测试以避免污染冷/热结果: ${reset_json}"
}

overall_fail=0
for mode in "${PREFIX_MODE_IDS[@]}"; do
  warmup="$(python3 "${CONFIG_PY}" --config "${CONFIG}" warmup --mode "${mode}")" || die "读取 warmup 失败: ${mode}"
  for ctx_k in "${CONTEXT_KS[@]}"; do
    reset_cache_or_die "${ctx_k}" "${mode}"
    prompt_tokens="$(
      python3 "${CTX_PY}" budget \
        --max-model-len "${MAX_MODEL_LEN}" \
        --max-tokens "${MAX_TOKENS}" \
        --reserve "${RESERVE_TOKENS}" \
        --target-k "${ctx_k}" \
        --k-unit "${K_UNIT}"
    )" || die "计算 prompt 预算失败 ctx=${ctx_k}K"
    if (( prompt_tokens < K_UNIT * MIN_CONTEXT_K )); then
      log "跳过 ${ctx_k}K：窗口扣除输出后不足（prompt_tokens=${prompt_tokens}）"
      continue
    fi
    target_tokens=$((ctx_k * K_UNIT))
    if (( prompt_tokens < target_tokens )); then
      log "${ctx_k}K 档 prompt 从 ${target_tokens} 收到 ${prompt_tokens}（预留 max_tokens+reserve）"
    fi

    PAR_ARGS=(parallel --ctx-k "${ctx_k}" --levels "${LEVELS_CSV}" --spec "${PARALLEL}" --max-parallel "${PARALLEL_MAX}" --anchor-k "${PARALLEL_ANCHOR_K}")
    par_list="$(python3 "${CTX_PY}" "${PAR_ARGS[@]}")" || die "计算并发列表失败 ctx=${ctx_k}K"
    [[ -n "${par_list}" ]] || die "并发列表为空 ctx=${ctx_k}K"

    max_n=1
    for p in ${par_list}; do
      n=$((p * NUMBER_MULT))
      if (( n > NUMBER_MAX )); then n="${NUMBER_MAX}"; fi
      if (( n > max_n )); then max_n="${n}"; fi
    done
    gen_n=$((max_n + warmup))

    prompt_file="${DATA_DIR}/ctx_${ctx_k}k_${mode}.txt"
    python3 "${PROMPT_PY}" \
      --path "${prompt_file}" \
      --n-chars "${prompt_tokens}" \
      --n-req "${gen_n}" \
      --config "${CONFIG}" \
      --mode "${mode}" \
      || die "生成 prompt 失败: ${prompt_file}"

    skip_higher=0
    for parallel in ${par_list}; do
      run_rel="ctx_${ctx_k}k_${mode}_p${parallel}"
      if (( skip_higher )); then
        log "跳过 ctx=${ctx_k}K mode=${mode} parallel=${parallel}（上一档已失败/超时）"
        record_run --ctx-k "${ctx_k}" --parallel "${parallel}" --prefix-mode "${mode}" --status skip --rc 0 \
          --prompt-tokens "${prompt_tokens}" --n-req 0 --dir "${run_rel}"
        continue
      fi
      n_req=$((parallel * NUMBER_MULT))
      if (( n_req > NUMBER_MAX )); then
        log "ctx=${ctx_k}K parallel=${parallel} 请求数从 ${n_req} 封顶到 ${NUMBER_MAX}"
        n_req="${NUMBER_MAX}"
      fi
      TO_ARGS=(timeouts --ctx-k "${ctx_k}" --parallel "${parallel}" --n-req "${n_req}")
      [[ -n "${READ_TIMEOUT}" ]] && TO_ARGS+=(--read-timeout "${READ_TIMEOUT}")
      [[ -n "${TOTAL_TIMEOUT}" ]] && TO_ARGS+=(--total-timeout "${TOTAL_TIMEOUT}")
      [[ -n "${DURATION}" ]] && TO_ARGS+=(--duration "${DURATION}")
      TO_JSON="$(python3 "${CTX_PY}" "${TO_ARGS[@]}")" || die "计算超时失败 ctx=${ctx_k}K parallel=${parallel}"
      read_timeout_json "${TO_JSON}" || die "解析超时 JSON 失败: ${TO_JSON}"

      log "超时  read=${READ_TO}s total=${TOTAL_TO}s duration=${RUN_DURATION}s hard=${HARD_TO}s"
      run_one "${ctx_k}" "${parallel}" "${prompt_tokens}" "${n_req}" \
        "${READ_TO}" "${TOTAL_TO}" "${RUN_DURATION}" "${HARD_TO}" \
        "${prompt_file}" "${mode}" "${warmup}"
      rc=$?

      if (( rc == 0 )); then
        log "完成  ctx=${ctx_k}K mode=${mode} parallel=${parallel}  prompt=${prompt_tokens}"
        record_run --ctx-k "${ctx_k}" --parallel "${parallel}" --prefix-mode "${mode}" --status ok --rc 0 \
          --prompt-tokens "${prompt_tokens}" --n-req "${n_req}" --dir "${run_rel}"
      else
        if (( rc == 124 || rc == 137 )); then
          log "超时  ctx=${ctx_k}K mode=${mode} parallel=${parallel}  rc=${rc}，跳过本模式更高并发"
          record_run --ctx-k "${ctx_k}" --parallel "${parallel}" --prefix-mode "${mode}" --status timeout --rc "${rc}" \
            --prompt-tokens "${prompt_tokens}" --n-req "${n_req}" --dir "${run_rel}"
        else
          log "失败  ctx=${ctx_k}K mode=${mode} parallel=${parallel}  rc=${rc}，跳过本模式更高并发"
          record_run --ctx-k "${ctx_k}" --parallel "${parallel}" --prefix-mode "${mode}" --status fail --rc "${rc}" \
            --prompt-tokens "${prompt_tokens}" --n-req "${n_req}" --dir "${run_rel}"
        fi
        skip_higher=1
        overall_fail=1
      fi
      sleep "${SLEEP_BETWEEN}"
    done
  done
done

echo ""
echo "=========================================="
echo "分档压测结束  输出: ${OUT_ROOT}"
echo "=========================================="
write_summary
exit "${overall_fail}"

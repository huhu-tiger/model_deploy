#!/usr/bin/env bash
# 环境检测（原子 + 组合）

# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# shellcheck source=hosts.sh
source "$(dirname "${BASH_SOURCE[0]}")/hosts.sh"
# shellcheck source=firewall.sh
source "$(dirname "${BASH_SOURCE[0]}")/firewall.sh"

check_local_is_master() {
  log "检查当前机器是否为 master ${MASTER_IP}..."
  if local_has_ip; then
    log "本机 IP 匹配 master ${MASTER_IP}"
    return 0
  fi
  die "请在 master (${MASTER_IP}) 上执行，当前不是该 IP。worker 是 ${WORKER_IP}"
}

check_local_docker() {
  log "检查本机 Docker..."
  docker info >/dev/null 2>&1 || die "本机 Docker 未运行或无权限（需 root 或 docker 组）"
}

check_local_compose_cli() {
  log "检查本机 docker-compose..."
  LOCAL_COMPOSE_CMD="$(detect_compose_cmd)" \
    || die "本机未找到 docker-compose / docker compose"
  log "本机 compose 命令: ${LOCAL_COMPOSE_CMD}"
}

check_local_compose_config() {
  local file="$1" label="$2"
  log "校验本机 ${label} compose 配置..."
  [[ -f "${file}" ]] || die "缺少 ${file}"
  compose -f "${file}" config >/dev/null || die "本机 ${label} compose 配置无效"
}

check_remote_ssh() {
  log "检查远程 SSH ${REMOTE_USER}@${REMOTE_HOST}..."
  remote "true" || die "无法 SSH 到 ${REMOTE_HOST}（需免密或 BatchMode）"
}

check_remote_docker() {
  log "检查远程 Docker..."
  remote "docker info >/dev/null 2>&1" || die "远程 Docker 未运行或无权限"
}

check_remote_compose_cli() {
  log "检查远程 docker-compose..."
  if remote "command -v docker-compose >/dev/null 2>&1"; then
    REMOTE_COMPOSE_CMD="docker-compose"
  elif remote "docker compose version >/dev/null 2>&1"; then
    REMOTE_COMPOSE_CMD="docker compose"
  else
    die "远程未安装 docker-compose / docker compose（${REMOTE_HOST}）"
  fi
  log "远程 compose 命令: ${REMOTE_COMPOSE_CMD}"
}

check_local_gpu() {
  log "检查本机 GPU..."
  nvidia-smi >/dev/null 2>&1 || die "本机 nvidia-smi 不可用（需 NVIDIA 驱动 / GPU）"
}

check_remote_gpu() {
  log "检查远程 GPU..."
  remote "nvidia-smi >/dev/null 2>&1" || die "远程 nvidia-smi 不可用（${REMOTE_HOST}）"
}

check_local_ib() {
  log "检查本机 IB 设备 /dev/infiniband..."
  [[ -e /dev/infiniband/uverbs0 ]] || die "本机缺少 /dev/infiniband（无法走 IB RDMA）"
}

check_remote_ib() {
  log "检查远程 IB 设备 /dev/infiniband..."
  remote "test -e /dev/infiniband/uverbs0" \
    || die "远程缺少 /dev/infiniband（${REMOTE_HOST}）"
}

check_local_model_path() {
  log "检查本机模型目录 ${MODEL_HOST_PATH}..."
  [[ -d "${MODEL_HOST_PATH}" ]] || die "本机缺少模型目录 ${MODEL_HOST_PATH}"
}

check_local_patches() {
  log "检查 SGLang 补丁 ${PATCH_SRC}..."
  [[ -f "${PATCH_SRC}/${PATCH_DETECTOR}" ]] \
    || die "缺少 ${PATCH_SRC}/${PATCH_DETECTOR}（引用 deepseek-v4-flash-0731/sglang-patches）"
  [[ -f "${PATCH_SRC}/${PATCH_REASONING}" ]] \
    || die "缺少 ${PATCH_SRC}/${PATCH_REASONING}（引用 deepseek-v4-flash-0731/sglang-patches）"
  [[ -f "${PATCH_SRC}/${PATCH_DSV4}" ]] \
    || die "缺少 ${PATCH_SRC}/${PATCH_DSV4}（PR #31700 DP attention gather 补丁）"
  [[ -f "${PATCH_SRC}/${PATCH_DSV4_NEXTN}" ]] \
    || die "缺少 ${PATCH_SRC}/${PATCH_DSV4_NEXTN}（PR #31700 NextN gather 补丁）"
  [[ -f "${PATCH_SRC}/${PATCH_LONG_CTX_EOS}" ]] \
    || die "缺少 ${PATCH_SRC}/${PATCH_LONG_CTX_EOS}（长上下文 ignore_eos 补丁）"
  [[ -f "${PATCH_SRC}/${PATCH_SITECUSTOMIZE}" ]] \
    || die "缺少 ${PATCH_SRC}/${PATCH_SITECUSTOMIZE}（sitecustomize 入口）"
  [[ -e "${PATCH_DIR}/${PATCH_DETECTOR}" ]] \
    || die "缺少 ${PATCH_DIR}/${PATCH_DETECTOR}（请保持 sglang-patches → 0731 的 symlink）"
  [[ -e "${PATCH_DIR}/${PATCH_DSV4}" ]] \
    || die "缺少 ${PATCH_DIR}/${PATCH_DSV4}（请保持 sglang-patches → 0731 的 symlink）"
}

check_remote_model_path() {
  log "检查远程模型目录 ${MODEL_HOST_PATH}..."
  remote "test -d '${MODEL_HOST_PATH}'" || die "远程缺少模型目录 ${MODEL_HOST_PATH}（${REMOTE_HOST}）"
}

check_local_image() {
  log "检查本机镜像 ${DOCKER_IMAGE}..."
  docker image inspect "${DOCKER_IMAGE}" >/dev/null 2>&1 \
    || die "本机缺少镜像 ${DOCKER_IMAGE}（请先 docker pull）"
}

check_remote_image() {
  log "检查远程镜像 ${DOCKER_IMAGE}..."
  remote "docker image inspect '${DOCKER_IMAGE}' >/dev/null 2>&1" \
    || die "远程缺少镜像 ${DOCKER_IMAGE}（${REMOTE_HOST}，请先 docker pull 或 docker load）"
}

check_remote_compose_config() {
  local file="${1:-${WORKER_COMPOSE}}"
  local remote_tmp="/tmp/deepseek-v4-flash-compose-check-$$.yml"
  local remote_env="/tmp/deepseek-v4-flash-cluster-check-$$.env"

  cleanup_remote_compose_tmp() {
    remote "rm -f '${remote_tmp}' '${remote_env}'" 2>/dev/null || true
  }

  log "校验远程 docker-compose 能否解析 worker 配置（含 cluster.env）..."
  trap cleanup_remote_compose_tmp RETURN
  scp -q "${file}" "${REMOTE_USER}@${REMOTE_HOST}:${remote_tmp}"
  scp -q "${CLUSTER_ENV_FILE}" "${REMOTE_USER}@${REMOTE_HOST}:${remote_env}"
  remote "WORKER_HOSTNAME=\$(hostname -s 2>/dev/null || hostname) && \
    export WORKER_HOSTNAME && \
    ${REMOTE_COMPOSE_CMD} --env-file '${remote_env}' -f '${remote_tmp}' config >/dev/null" \
    || die "远程 docker-compose 配置校验失败"
  trap - RETURN
  cleanup_remote_compose_tmp
}

# scope: local | master | worker_file | remote | remote_worker | sync | full
ensure_env() {
  local scope="${1:-full}"
  case "${scope}" in
    local)
      check_local_docker
      check_local_compose_cli
      ;;
    master)
      check_local_is_master
      check_local_docker
      check_local_compose_cli
      check_local_compose_config "${COMPOSE_FILE}" "node-43"
      ensure_local_hosts
      ensure_local_firewall
      check_local_gpu
      check_local_ib
      check_local_model_path
      check_local_patches
      check_local_image
      log "本机 master 环境检查通过"
      ;;
    worker_file)
      check_local_compose_config "${WORKER_COMPOSE}" "node-44"
      ;;
    remote)
      check_remote_ssh
      check_remote_docker
      check_remote_compose_cli
      log "远程环境检查通过"
      ;;
    remote_worker)
      check_remote_ssh
      ensure_remote_hosts
      ensure_remote_firewall
      check_remote_docker
      check_remote_compose_cli
      check_local_compose_config "${WORKER_COMPOSE}" "node-44"
      check_remote_compose_config "${WORKER_COMPOSE}"
      check_remote_gpu
      check_remote_ib
      check_remote_model_path
      check_remote_image
      log "远程 worker 环境检查通过"
      ;;
    sync)
      check_local_compose_config "${WORKER_COMPOSE}" "node-44"
      check_local_patches
      check_remote_ssh
      log "同步前环境检查通过"
      ;;
    full)
      log "======== 启动前环境检查 ========"
      check_local_is_master
      check_local_docker
      check_local_compose_cli
      check_local_compose_config "${COMPOSE_FILE}" "node-43"
      check_local_compose_config "${WORKER_COMPOSE}" "node-44"
      ensure_local_hosts
      ensure_local_firewall
      check_local_gpu
      check_local_ib
      check_local_model_path
      check_local_patches
      check_local_image
      check_remote_ssh
      ensure_remote_hosts
      ensure_remote_firewall
      check_remote_docker
      check_remote_compose_cli
      check_remote_compose_config "${WORKER_COMPOSE}"
      check_remote_gpu
      check_remote_ib
      check_remote_model_path
      check_remote_image
      log "环境检查全部通过"
      ;;
    *)
      die "未知检测范围: ${scope}"
      ;;
  esac
}

preflight_check() {
  ensure_env full
}

#!/usr/bin/env bash
# 镜像引用解析、国内仓匹配、SRC_PREFIX、认证文件
# （由 pull_and_push.sh source，勿直接执行）

# 从镜像引用解析 registry host（无显式 registry 时视为 docker.io）
registry_host_from_ref() {
    local ref="$1"
    local path first

    ref="${ref#docker://}"
    path="${ref%%@*}"
    first="${path%%/*}"

    if [[ "$path" != */* ]]; then
        echo "docker.io"
        return 0
    fi

    # namespace/repo（无点号）→ Docker Hub；host:port/repo 或 host/repo → 显式仓库
    if [[ "$first" == *.* || "$first" == localhost || "$first" =~ ^[^/]+:[0-9]+$ ]]; then
        if [[ "$first" =~ ^[^/]+:[0-9]+$ ]]; then
            echo "${first%:*}"
        else
            echo "$first"
        fi
    else
        echo "docker.io"
    fi
}

load_domestic_registries() {
    local file="$1"
    local line

    DOMESTIC_PATTERNS=()
    DOMESTIC_LOADED=1

    if [[ ! -f "$file" ]]; then
        log "" "警告: 国内仓配置不存在: $file（海外源将按代理策略访问）" >&2
        return 1
    fi

    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -n "$line" ]] || continue
        DOMESTIC_PATTERNS+=("${line,,}")
    done < "$file"
}

# pattern: exact | *.suffix | .suffix
match_domestic_pattern() {
    local host="$1"
    local pattern="$2"
    local suffix

    if [[ "$pattern" == \*.* ]]; then
        suffix="${pattern#\*}"
        [[ "$host" == *"$suffix" || "$host" == "${suffix#.}" ]]
    elif [[ "$pattern" == .* ]]; then
        [[ "$host" == *"$pattern" || "$host" == "${pattern#.}" ]]
    else
        [[ "$host" == "$pattern" ]]
    fi
}

# 国内 / 内网仓库：直连，不走 HTTP 代理（规则见 domestic_registries.conf）
is_domestic_registry() {
    local host="${1,,}"
    local pattern
    host="${host%%:*}"

    if [[ "$DOMESTIC_LOADED" -eq 0 ]]; then
        load_domestic_registries "$DOMESTIC_REGISTRIES_FILE" || true
    fi

    for pattern in "${DOMESTIC_PATTERNS[@]+"${DOMESTIC_PATTERNS[@]}"}"; do
        if match_domestic_pattern "$host" "$pattern"; then
            return 0
        fi
    done
    return 1
}

resolve_docker_authfile() {
    if [[ -n "${DOCKER_CONFIG:-}" && -f "${DOCKER_CONFIG}/config.json" ]]; then
        DOCKER_AUTH_FILE="${DOCKER_CONFIG}/config.json"
    elif [[ -f "${HOME}/.docker/config.json" ]]; then
        DOCKER_AUTH_FILE="${HOME}/.docker/config.json"
    else
        DOCKER_AUTH_FILE=""
    fi
}

resolve_src_ref() {
    local src="$1"
    local prefix="${SRC_PREFIX:-}"

    if [[ -z "$prefix" ]]; then
        echo "$src"
        return 0
    fi

    prefix="${prefix#docker://}"
    prefix="${prefix%/}"
    src="${src#docker.io/}"
    src="${src#registry-1.docker.io/}"
    echo "${prefix}/${src}"
}

to_local_image() {
    local src="$1"
    local name image_name tag

    if [[ "$src" == *@* ]]; then
        echo "错误: 暂不支持带 digest 的镜像引用: $src" >&2
        return 1
    fi

    # 按路径最后一段解析 tag，避免 host:port/repo 被误拆
    name="${src##*/}"
    if [[ "$name" == *:* ]]; then
        tag="${name##*:}"
        image_name="${name%:*}"
    else
        tag="latest"
        image_name="$name"
    fi

    if [[ -z "$image_name" || -z "$tag" ]]; then
        echo "错误: 无法解析镜像名: $src" >&2
        return 1
    fi

    echo "${REGISTRY}/${image_name}:${tag}"
}

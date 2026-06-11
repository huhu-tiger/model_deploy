#!/usr/bin/env bash
# 对比宿主机 vs 容器内下载 wan.vnet.com 图片的速率与连通性
# 用法:
#   ./bench-image-download.sh
#   ./bench-image-download.sh "https://..." 
#   RUNS=5 ./bench-image-download.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTAINER_NAME="${CONTAINER_NAME:-vllm-qwen3-vl-8b}"
RUNS="${RUNS:-3}"
CURL_MAX_TIME="${CURL_MAX_TIME:-120}"
OUT_DIR="${OUT_DIR:-/tmp/bench-image-download-$$}"

DEFAULT_URL='https://wan.vnet.com/ailowcode/api/common/file/read/wFApin1o70evgAAAABJRU5ErkJggg==.png?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJidWNrZXROYW1lIjoiY2hhdCIsInRlYW1JZCI6IjY3ZTRmYjMzYWE4MTlmNjc4OTk5ZWVlZSIsInVpZCI6IjE3OTE0IiwiZmlsZUlkIjoiNmExN2JhNDUxYWQxYzY0NzIxOTlkNWE1IiwiZXhwIjoxNzgwNTQ0NzA5LCJpYXQiOjE3Nzk5Mzk5MDl9.cM7G7fKicVNDZZMQt0-FSj1FHycKp2SKKJHi-yxYlGM'

IMAGE_URL="${1:-$DEFAULT_URL}"
HOSTNAME_TARGET="$(echo "$IMAGE_URL" | sed -E 's#https?://([^/]+)/.*#\1#')"

mkdir -p "$OUT_DIR"

red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow(){ printf '\033[0;33m%s\033[0m\n' "$*"; }
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }

hr() { printf '%.0s-' {1..72}; echo; }

# curl 写入格式: http_code size time_connect time_starttransfer time_total speed
CURL_FMT='http=%{http_code} size=%{size_download} connect=%{time_connect} ttfb=%{time_starttransfer} total=%{time_total} speed=%{speed_download}'

run_curl_download() {
  local label="$1"
  local outfile="$2"
  local errfile="$3"

  # shellcheck disable=SC2086
  curl -sS -L -o "$outfile" -w "$CURL_FMT\n" \
    --max-time "$CURL_MAX_TIME" \
    -H "User-Agent: bench-image-download/1.0 ($label)" \
    "$IMAGE_URL" 2>"$errfile"
}

avg_field() {
  local file="$1" field="$2"
  awk -v f="$field" '
    function colidx(name,   i, n) {
      split($0, tmp, / /)
      for (i=1; i<=NF; i++) {
        split(tmp[i], kv, "=")
        if (kv[1] == name) return kv[2]
      }
      return ""
    }
    { v=colidx(f); if (v != "" && v+0 == v) { s+=v; n++ } }
    END { if (n>0) printf "%.6f", s/n; else print "NA" }
  ' "$file"
}

summarize_runs() {
  local label="$1"
  local log="$2"

  bold "[$label] curl 统计 (${RUNS} 次)"
  if [[ ! -s "$log" ]]; then
    red "  无有效结果"
    return
  fi

  local ok fail
  ok=$(grep -c 'http=200' "$log" || true)
  fail=$((RUNS - ok))

  printf "  成功: %s / %s\n" "$ok" "$RUNS"
  [[ "$fail" -gt 0 ]] && yellow "  失败: $fail (见下方单次明细)"

  if [[ "$ok" -gt 0 ]]; then
    grep 'http=200' "$log" > "${log}.ok" || true
    local avg_connect avg_ttfb avg_total avg_speed avg_size
    avg_connect=$(avg_field "${log}.ok" connect)
    avg_ttfb=$(avg_field "${log}.ok" ttfb)
    avg_total=$(avg_field "${log}.ok" total)
    avg_speed=$(avg_field "${log}.ok" speed)
    avg_size=$(avg_field "${log}.ok" size)

    printf "  平均 connect: %.3fs\n" "$avg_connect"
    printf "  平均 ttfb:     %.3fs\n" "$avg_ttfb"
    printf "  平均 total:    %.3fs\n" "$avg_total"
    printf "  平均速度:      %.0f B/s (%.2f KB/s, %.2f MB/s)\n" \
      "$avg_speed" "$(echo "$avg_speed/1024" | bc -l)" "$(echo "$avg_speed/1048576" | bc -l)"
    printf "  平均大小:      %.0f bytes\n" "$avg_size"
  fi

  echo "  单次明细:"
  nl -ba "$log" | sed 's/^/    /'
}

check_dns() {
  local where="$1"
  local cmd="$2"
  bold "[$where] DNS: $HOSTNAME_TARGET"
  if eval "$cmd" 2>/dev/null; then
    :
  else
    yellow "  DNS 查询失败或命令不可用"
  fi
}

check_container() {
  if ! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    red "容器不存在: $CONTAINER_NAME"
    red "请先启动: docker compose -f $SCRIPT_DIR/docker-compose-vllm.yml up -d"
    exit 1
  fi
  local net_mode
  net_mode=$(docker inspect "$CONTAINER_NAME" --format '{{.HostConfig.NetworkMode}}')
  bold "容器: $CONTAINER_NAME  network_mode=$net_mode"
  if [[ "$net_mode" != "host" ]]; then
    yellow "  提示: 非 host 网络时，容器与宿主机路由/DNS 可能不同"
  fi
}

bench_side() {
  local side="$1"   # host | container
  local log="$OUT_DIR/${side}.log"
  : >"$log"

  bold ">>> 开始测试: $side (${RUNS} 次)"
  local i
  for ((i=1; i<=RUNS; i++)); do
    local outfile="$OUT_DIR/${side}-run${i}.bin"
    local errfile="$OUT_DIR/${side}-run${i}.err"
    local line

    if [[ "$side" == "host" ]]; then
      line=$(run_curl_download "host-run$i" "$outfile" "$errfile" || true)
    else
      line=$(docker exec "$CONTAINER_NAME" curl -sS -L -o /tmp/bench-dl.bin -w "$CURL_FMT\n" \
        --max-time "$CURL_MAX_TIME" \
        -H "User-Agent: bench-image-download/1.0 (container-run$i)" \
        "$IMAGE_URL" 2>"$errfile" || true)
      docker cp "$CONTAINER_NAME:/tmp/bench-dl.bin" "$outfile" 2>/dev/null || true
      docker exec "$CONTAINER_NAME" rm -f /tmp/bench-dl.bin 2>/dev/null || true
    fi

    echo "run$i $line" >>"$log"
    if [[ -s "$errfile" ]]; then
      echo "run$i stderr: $(tr '\n' ' ' <"$errfile")" >>"$OUT_DIR/${side}-errors.log"
    fi

    # 非 200 时打印响应体片段
    if ! echo "$line" | grep -q 'http=200'; then
      if [[ -f "$outfile" && -s "$outfile" ]]; then
        echo "run$i body: $(head -c 300 "$outfile")" >>"$OUT_DIR/${side}-errors.log"
      fi
    fi

    sleep 0.5
  done

  summarize_runs "$side" "$log"
}

bench_python() {
  local side="$1"
  local py="$OUT_DIR/python-${side}.txt"

  local pycode='
import time, ssl, urllib.request, json, sys
url = sys.argv[1]
ctx = ssl.create_default_context()
t0 = time.perf_counter()
try:
    with urllib.request.urlopen(url, context=ctx, timeout=120) as r:
        data = r.read()
    dt = time.perf_counter() - t0
    speed = len(data) / dt if dt > 0 else 0
    print(json.dumps({"ok": True, "status": 200, "bytes": len(data), "seconds": round(dt, 3), "speed_bps": round(speed, 1)}))
except Exception as e:
    dt = time.perf_counter() - t0
    print(json.dumps({"ok": False, "error": str(e), "seconds": round(dt, 3)}))
'

  bold ">>> Python urllib 测试 ($side) — 模拟部分 HTTP 客户端行为"
  if [[ "$side" == "host" ]]; then
    python3 -c "$pycode" "$IMAGE_URL" | tee "$py"
  else
    docker exec "$CONTAINER_NAME" python3 -c "$pycode" "$IMAGE_URL" | tee "$py"
  fi
}

compare_results() {
  hr
  bold "对比结论"

  local host_ok cont_ok
  host_ok=$(grep -c 'http=200' "$OUT_DIR/host.log" 2>/dev/null || echo 0)
  cont_ok=$(grep -c 'http=200' "$OUT_DIR/container.log" 2>/dev/null || echo 0)

  if [[ "$host_ok" -eq 0 && "$cont_ok" -eq 0 ]]; then
    red "宿主机与容器均未成功下载 (非 HTTP 200)"
    yellow "请检查 URL/token 是否有效，或查看: $OUT_DIR/*-errors.log"
    return
  fi

  if [[ "$host_ok" -gt 0 && "$cont_ok" -gt 0 ]]; then
    grep 'http=200' "$OUT_DIR/host.log" > "$OUT_DIR/host.log.ok"
    grep 'http=200' "$OUT_DIR/container.log" > "$OUT_DIR/container.log.ok"

    local h_speed c_speed h_total c_total
    h_speed=$(avg_field "$OUT_DIR/host.log.ok" speed)
    c_speed=$(avg_field "$OUT_DIR/container.log.ok" speed)
    h_total=$(avg_field "$OUT_DIR/host.log.ok" total)
    c_total=$(avg_field "$OUT_DIR/container.log.ok" total)

    local ratio
    ratio=$(echo "scale=2; if ($h_speed>0) $c_speed/$h_speed else 0" | bc -l)

    printf "  宿主机平均速度: %.0f B/s (%.2f KB/s)\n" "$h_speed" "$(echo "$h_speed/1024" | bc -l)"
    printf "  容器平均速度:   %.0f B/s (%.2f KB/s)\n" "$c_speed" "$(echo "$c_speed/1024" | bc -l)"
    printf "  容器/宿主机速度比: %sx\n" "$ratio"
    printf "  宿主机平均耗时: %.3fs | 容器: %.3fs\n" "$h_total" "$c_total"

    local diff_pct
    diff_pct=$(echo "scale=1; if ($h_speed>0) ($c_speed-$h_speed)*100/$h_speed else 0" | bc -l)
    local abs_diff
    abs_diff=$(echo "${diff_pct#-}" | bc -l)

    if (( $(echo "$abs_diff < 15" | bc -l) )); then
      green "  判断: 速率差异 < 15%，网络层基本一致，问题更可能在服务端限速/鉴权或 vLLM 超时配置"
    elif (( $(echo "$c_speed < $h_speed" | bc -l) )); then
      yellow "  判断: 容器明显慢于宿主机，检查 network_mode、DNS、代理环境变量"
    else
      yellow "  判断: 容器快于宿主机，可能是测试波动或多连接竞争"
    fi
  elif [[ "$host_ok" -gt 0 ]]; then
    yellow "  仅宿主机成功，容器失败 — 重点排查容器网络/DNS/代理"
  else
    yellow "  仅容器成功，宿主机失败 — 少见，检查宿主机代理或防火墙"
  fi

  echo ""
  bold "产物目录: $OUT_DIR"
}

main() {
  bold "图片下载对比测试"
  echo "URL: ${IMAGE_URL:0:80}..."
  echo "容器: $CONTAINER_NAME | 次数: $RUNS | 超时: ${CURL_MAX_TIME}s"
  hr

  check_container
  hr

  check_dns "宿主机" "getent hosts $HOSTNAME_TARGET || nslookup $HOSTNAME_TARGET"
  check_dns "容器" "docker exec $CONTAINER_NAME getent hosts $HOSTNAME_TARGET 2>/dev/null || docker exec $CONTAINER_NAME python3 -c \"import socket; print(socket.gethostbyname('$HOSTNAME_TARGET'))\""
  hr

  echo "宿主机代理环境:"
  env | grep -iE '^(http|https|no)_proxy=' || echo "  (无)"
  echo "容器代理环境:"
  docker exec "$CONTAINER_NAME" env 2>/dev/null | grep -iE '^(http|https|no)_proxy=' || echo "  (无)"
  hr

  bench_side host
  hr
  bench_side container
  hr
  bench_python host
  bench_python container
  compare_results
}

main "$@"

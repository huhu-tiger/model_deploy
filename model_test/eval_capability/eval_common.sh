# shellcheck shell=bash
# 各 eval_*.sh 共用：评测结束后写 logs/eval_summary.log

write_eval_summary() {
    local work_dir="$1"
    echo ""
    echo "生成总结日志..."
    python "${SCRIPT_DIR}/write_eval_summary.py" "${work_dir}" || \
        echo "[WARN] 总结日志生成失败: ${work_dir}"
}

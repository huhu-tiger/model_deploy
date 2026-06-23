"""
校准数据集解析、下载、混合工具。

设计要点:
    - 支持单集或逗号分隔多集混合
    - 别名机制（cyankiwi → cyankiwi/calibration）
    - 自动识别数据集 split 名（train / train_sft / ...）
    - 自动将任意数据集统一为单一 'text' 列（messages → chat_template / 字符串列拼接）
    - 预下载快速失败，避免模型加载几小时后才发现网络异常
    - HuggingFace 离线锁补丁，支持代理环境

完整数据集推荐与选型见: ../docs/dataset.md
"""

from __future__ import annotations

import os


# ══════════════════════════════════════════════════════════════════
# 别名表 —— 短名 → HuggingFace dataset ID
# ══════════════════════════════════════════════════════════════════

DATASET_ALIASES: dict[str, str] = {
    # ── 通用 / 对话 ────────────────────────────────
    "cyankiwi":      "cyankiwi/calibration",                         # 默认，中英 384 条
    "ultrachat":     "HuggingFaceH4/ultrachat_200k",                 # 英文指令对话，官方首选
    "neuralmagic":   "neuralmagic/LLM_compression_calibration",      # NM 官方默认混合校准
    "open-platypus": "garage-bAInd/Open-Platypus",                   # STEM / 数学 / 推理精选
    # ── 推理 / STEM / 代码 ────────────────────────
    "nemotron-v1":   "nvidia/Llama-Nemotron-Post-Training-Dataset",  # 数学 + 代码
    "nemotron-v2":   "nvidia/Nemotron-Post-Training-Dataset-v2",     # 多语言推理
    "swebench":      "princeton-nlp/SWE-bench_Verified",             # 代码 / Bug 修复
    "hermes-fc":     "NousResearch/hermes-function-calling-v1",      # 函数调用 / Agent
    # ── 长上下文 / 基础语料 ────────────────────────
    "longbench":     "THUDM/LongBench",                              # 长文档 QA
    "pile":          "mit-han-lab/pile-val-backup",                  # AutoAWQ 默认
    "wikitext":      "wikitext",                                     # 基线 PPL
    "c4":            "allenai/c4",                                   # 大规模网页文本
    # ── 中文 ───────────────────────────────────────
    "belle":         "BelleGroup/train_2M_CN",
    "alpaca-zh":     "silk-road/alpaca-data-gpt4-chinese",
    "firefly":       "YeungNLP/firefly-train-1.1M",
}


def resolve_dataset_id(name_or_id: str) -> str:
    """别名 → HuggingFace dataset ID。未命中时原样返回。"""
    return DATASET_ALIASES.get(name_or_id, name_or_id)


# ══════════════════════════════════════════════════════════════════
# 离线锁补丁（代理环境必需）
# ══════════════════════════════════════════════════════════════════

_NETWORK_ERR_KEYWORDS = (
    "connection", "timeout", "proxy", "cannot connect",
    "network", "ssl", "certificate", "handshake", "refused",
)


_PROXY_ENV_KEYS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
    "NO_PROXY", "no_proxy",
)


def unset_proxy_env(verbose: bool = True) -> dict[str, str]:
    """
    清除当前进程的代理环境变量,避免后续阶段（量化前向 / 模型保存等）
    走代理影响内网通信。

    返回被清除的 {key: value} 字典,便于后续 restore_proxy_env 恢复。

    典型用法（量化主脚本）:
      prefetch_calib_datasets(specs)   # 下载校准集（用代理）
      unset_proxy_env()                # 下载完成后取消代理
      build_calib_dataset(...)         # 走本地缓存
      oneshot(...)                     # 量化阶段不走代理
    """
    saved: dict[str, str] = {}
    for key in _PROXY_ENV_KEYS:
        val = os.environ.pop(key, None)
        if val is not None:
            saved[key] = val
    if verbose and saved:
        cleared = ", ".join(sorted({k.upper() for k in saved}))
        print(f"[代理] 已取消: {cleared}", flush=True)
    elif verbose:
        print("[代理] 当前进程未设置代理环境变量,无需取消", flush=True)
    return saved


def restore_proxy_env(saved: dict[str, str], verbose: bool = True) -> None:
    """从 unset_proxy_env() 返回的 dict 中恢复代理环境变量。"""
    for key, val in saved.items():
        os.environ[key] = val
    if verbose and saved:
        print(f"[代理] 已恢复 {len(saved)} 个环境变量", flush=True)


def _offline_patch():
    """
    返回 (hc, dc, orig_hc, orig_dc) 并关闭 HuggingFace 离线锁。

    huggingface_hub / datasets 在模块导入时将 TRANSFORMERS_OFFLINE=1
    固化为模块级常量,改环境变量已无效,必须直接 patch:
      - huggingface_hub.constants.HF_HUB_OFFLINE
      - datasets.config.HF_HUB_OFFLINE / HF_DATASETS_OFFLINE
    模型从本地路径加载,不受这两处变量影响。
    """
    import huggingface_hub.constants as _hc
    import datasets.config as _dc
    _orig_hc = _hc.HF_HUB_OFFLINE
    _orig_dc = _dc.HF_HUB_OFFLINE
    _hc.HF_HUB_OFFLINE = False
    _dc.HF_HUB_OFFLINE = False
    _dc.HF_DATASETS_OFFLINE = False
    return _hc, _dc, _orig_hc, _orig_dc


def _offline_restore(hc, dc, orig_hc, orig_dc):
    """恢复 HuggingFace 离线锁。"""
    hc.HF_HUB_OFFLINE = orig_hc
    dc.HF_HUB_OFFLINE = orig_dc
    dc.HF_DATASETS_OFFLINE = orig_dc


# ══════════════════════════════════════════════════════════════════
# 多数据集规格解析
# ══════════════════════════════════════════════════════════════════

def parse_dataset_specs(
    dataset_str: str,
    samples_str: str,
    apply_aliases: bool = True,
) -> list[tuple[str, int]]:
    """
    将 --calib-dataset / --calib-samples 解析为 [(dataset_id, n_samples), ...]。

    支持格式:
      单集:   dataset_str="cyankiwi"                       samples_str="384"
              → [("cyankiwi/calibration", 384)]

      多集（样本数平均分配）:
              dataset_str="cyankiwi,ultrachat"            samples_str="512"
              → [("cyankiwi/calibration", 256), ("HuggingFaceH4/ultrachat_200k", 256)]

      多集（逐集指定样本数）:
              dataset_str="cyankiwi,ultrachat"            samples_str="256,256"
              → 同上

      整数样本数也接受（兼容旧调用）:
              dataset_str="cyankiwi"                      samples_int=384

    apply_aliases: True 时把短名解析为 HF dataset ID；False 时保留原样
    """
    ids = [s.strip() for s in dataset_str.split(",") if s.strip()]
    samples_str = str(samples_str)
    samples = [s.strip() for s in samples_str.split(",") if s.strip()]
    if not ids:
        raise ValueError("--calib-dataset 不能为空")

    if len(samples) == 1:
        total = int(samples[0])
        if total <= 0:
            raise ValueError("--calib-samples 必须为正整数")
        per = total // len(ids)
        # 最后一个补余数,确保总数精确
        counts = [per] * (len(ids) - 1) + [total - per * (len(ids) - 1)]
    else:
        if len(samples) != len(ids):
            raise ValueError(
                f"--calib-samples 指定了 {len(samples)} 个值，"
                f"但 --calib-dataset 有 {len(ids)} 个数据集，数量不匹配"
            )
        counts = [int(s) for s in samples]
        if any(n <= 0 for n in counts):
            raise ValueError("--calib-samples 中每个样本数都必须为正整数")

    if apply_aliases:
        ids = [resolve_dataset_id(x) for x in ids]
    return list(zip(ids, counts))


def _resolve_split(ds_id: str) -> str:
    """
    自动探测数据集的训练集 split 名称。

    优先 "train"；不存在则取第一个含 "train" 的（如 "train_sft"、"train_gen"）；
    再不行取第一个可用 split。
    """
    try:
        from datasets import get_dataset_split_names
        splits = get_dataset_split_names(ds_id)
    except Exception:
        return "train"

    if "train" in splits:
        return "train"
    for s in splits:
        if "train" in s:
            return s
    return splits[0] if splits else "train"


# ══════════════════════════════════════════════════════════════════
# 数据集 → 单 text 列统一格式
# ══════════════════════════════════════════════════════════════════

def _to_text_column(ds, ds_id: str, tokenizer):
    """
    将数据集统一转换为只含 'text' 列的格式,供 oneshot 消费。

    处理规则:
      1. 若已有 'text' 列 → 直接保留
      2. 若有 'messages' / 'conversations' 列 → 应用 chat template
         （自动识别 ShareGPT 格式 from/value 并转 OpenAI 规范 role/content）
      3. 兜底:从优选列表 (system/instruction/prompt/...) 中取字符串列拼接
    """
    cols = ds.column_names

    if "text" in cols:
        return ds.select_columns(["text"])

    # 多轮对话：messages 或 conversations 列
    for chat_col in ("messages", "conversations"):
        if chat_col in cols:
            return _chat_to_text(ds, cols, chat_col, tokenizer)

    return _stringify_columns_to_text(ds, cols)


def _chat_to_text(ds, cols, chat_col, tokenizer):
    """messages / conversations 列 → text 列（自动适配 OpenAI 与 ShareGPT 格式）。"""
    ROLE_MAP = {
        "human": "user", "gpt": "assistant", "tool": "tool", "system": "system",
        "user": "user", "assistant": "assistant",
    }

    def _normalize(messages):
        if not isinstance(messages, list):
            return []
        normalized = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            # OpenAI 格式 (role/content) 或 ShareGPT 格式 (from/value)
            role    = m.get("role") or m.get("from") or "user"
            content = m.get("content") or m.get("value") or ""
            normalized.append({
                "role": ROLE_MAP.get(role, role),
                "content": content if isinstance(content, str) else str(content),
            })
        return normalized

    def _apply(example):
        messages = _normalize(example.get(chat_col, []))
        if len(messages) < 2:
            return {"text": ""}
        try:
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False,
            )
        except Exception:
            text = "\n".join(m.get("content", "") for m in messages)
        return {"text": text}

    return ds.map(_apply, remove_columns=cols)


def _stringify_columns_to_text(ds, cols):
    """从字符串列拼接为 text 列（兜底，处理 SWE-bench / Open-Platypus 等无 messages 的数据集）。"""
    def _stringify(value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    parts.append(str(item.get("content") or item.get("text") or item))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        if isinstance(value, dict):
            return str(value.get("content") or value.get("text") or value)
        return str(value)

    sample = ds[0] if len(ds) else {}
    preferred = [
        c for c in (
            "problem_statement",        # SWE-bench
            "system", "instruction", "prompt", "question", "input",
            "response", "answer", "output", "completion", "content",
        )
        if c in cols
    ]
    candidate = [c for c in cols if isinstance(sample.get(c), (str, list, dict))]
    selected = preferred or candidate or [cols[0]]

    def _convert(example):
        parts = []
        for col in selected:
            text = _stringify(example.get(col)).strip()
            if text:
                parts.append(text)
        return {"text": "\n\n".join(parts)}

    return ds.map(_convert, remove_columns=cols)


# ══════════════════════════════════════════════════════════════════
# 预下载（快速失败）
# ══════════════════════════════════════════════════════════════════

def prefetch_calib_datasets(specs: list[tuple[str, int]]) -> None:
    """
    在模型加载前预先下载并缓存所有校准数据集（快速失败策略）。

    - 网络/代理异常时立即报错
    - 复用缓存，oneshot/build_calib_dataset 后续命中 HF_DATASETS_CACHE
    - 验证样本数,提前发现配置问题
    - 显式传 HF_TOKEN（如有）,避免 anonymous rate limit
    """
    from datasets import load_dataset

    cache_dir = os.environ.get("HF_DATASETS_CACHE")
    hf_token  = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    print(f"\n[校准数据集] 预下载（共 {len(specs)} 个数据集）")
    print(f"  缓存路径 : {cache_dir or '默认（容器内）'}")
    if hf_token:
        print(f"  HF Token : 已设置（{hf_token[:6]}…{hf_token[-4:]}, 长度 {len(hf_token)}）")
    else:
        print(f"  HF Token : 未设置（公开数据集可匿名下载,但有 rate limit）")

    hc, dc, orig_hc, orig_dc = _offline_patch()
    try:
        for ds_id, n in specs:
            print(f"  → {ds_id!r}（需要 {n} 条）", end=" ", flush=True)
            try:
                split = _resolve_split(ds_id)
                # 显式传 token,避免某些 huggingface_hub 内部路径未读环境变量
                load_kwargs = {"split": split}
                if hf_token:
                    load_kwargs["token"] = hf_token
                ds = load_dataset(ds_id, **load_kwargs)
                total = len(ds)
                if total < n:
                    raise RuntimeError(
                        f"数据集 {ds_id!r} 实际只有 {total} 条，"
                        f"少于所需 {n} 条，请减小样本数"
                    )
                print(f"✅ ({total} 条，split={split!r})")
            except Exception as e:
                err_lower = str(e).lower()
                if any(kw in err_lower for kw in _NETWORK_ERR_KEYWORDS):
                    raise RuntimeError(
                        f"数据集 {ds_id!r} 下载失败（网络错误）: {e}\n"
                        "请检查: ① 代理 HTTP_PROXY/HTTPS_PROXY 是否正确; "
                        "② 网络是否可达 HuggingFace Hub"
                    ) from e
                raise RuntimeError(
                    f"数据集 {ds_id!r} 预下载/校验失败: {type(e).__name__}: {e}"
                ) from e
    finally:
        _offline_restore(hc, dc, orig_hc, orig_dc)


# ══════════════════════════════════════════════════════════════════
# 加载 + 采样 + 混合
# ══════════════════════════════════════════════════════════════════

def build_calib_dataset(specs: list[tuple[str, int]], tokenizer):
    """
    加载、采样、统一格式后混合多个校准数据集，返回 (Dataset, total_samples)。

    返回的 Dataset 只含 'text' 列,已打乱顺序,可直接传入 oneshot(dataset=...)。
    """
    from datasets import load_dataset, concatenate_datasets

    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    print(f"\n[校准数据集] 加载并统一格式（{len(specs)} 个数据集）")

    hc, dc, orig_hc, orig_dc = _offline_patch()
    try:
        parts = []
        for ds_id, n in specs:
            split = _resolve_split(ds_id)
            print(f"  加载 {ds_id!r} (split={split!r})，取 {n} 条 ...", flush=True)
            load_kwargs = {"split": split}
            if hf_token:
                load_kwargs["token"] = hf_token
            ds = load_dataset(ds_id, **load_kwargs)
            ds = ds.shuffle(seed=42).select(range(min(n, len(ds))))
            ds = _to_text_column(ds, ds_id, tokenizer)
            # 过滤过短样本（旧 Qwen3.6 脚本经验:< 100 字符会被丢弃,
            # tokenize 后 < 64 tokens 对 AWQ 激活统计无显著贡献）
            ds = ds.filter(
                lambda x: isinstance(x.get("text"), str)
                          and len(x["text"].strip()) >= 100
            )
            if len(ds) == 0:
                raise RuntimeError(f"数据集 {ds_id!r} 转换为 text 后没有可用样本")
            parts.append(ds)
            print(f"    → {len(ds)} 条 ✅")
    finally:
        _offline_restore(hc, dc, orig_hc, orig_dc)

    total = sum(len(p) for p in parts)
    mixed = concatenate_datasets(parts).shuffle(seed=42) if len(parts) > 1 else parts[0]
    print(f"  数据集准备完成: {total} 条（{' + '.join(str(len(p)) for p in parts)}）")
    return mixed, total


def format_specs_summary(specs: list[tuple[str, int]]) -> str:
    """格式化 specs 为人类可读字符串，用于日志/打印。"""
    return " + ".join(f"{ds_id}({n}条)" for ds_id, n in specs)


# ══════════════════════════════════════════════════════════════════
# 一站式校准集准备（推荐量化主脚本调用）
# ══════════════════════════════════════════════════════════════════

def prepare_calib_dataset(
    specs: list[tuple[str, int]],
    tokenizer,
    skip_prefetch: bool = False,
    unset_proxy_after_prefetch: bool = True,
    print_summary: bool = True,
):
    """
    校准数据集准备的一站式入口,封装完整流水线:

      1. (可选) 打印数据集配方
      2. (可选) prefetch_calib_datasets    —— 预下载到 HF_DATASETS_CACHE,
                                             快速失败,网络异常立即报错
      3.        build_calib_dataset        —— 加载 + 统一 text 列 + 过滤短样本 +
                                             多集混合,返回单一 Dataset
      4. (可选) unset_proxy_env            —— 全部数据集就绪后清除代理,
                                             避免后续量化阶段误走代理

    注意: unset_proxy 必须在 build 完成后,而不是 prefetch 之后。
    因为 build_calib_dataset 内部 _resolve_split / load_dataset 仍可能
    查询 HF Hub 元数据（即使数据已缓存）—— 提前 unset 会导致 split 探测
    失败回退到 "train",对 ultrachat_200k 等用 "train_sft" 的数据集会
    错误地尝试加载不存在的 "train" split。

    参数:
      specs                       : parse_dataset_specs() 的输出
      tokenizer                   : transformers Tokenizer（用于 chat template）
      skip_prefetch               : True 时跳过预下载（不推荐,调试用）
      unset_proxy_after_prefetch  : True 时数据集全部就绪后清除代理
                                    （命名沿用,实际行为是 build 之后清除）
      print_summary               : True 时打印数据集配方表

    返回:
      (Dataset, total_samples)  —— dataset 只含 'text' 列,可直传 oneshot

    典型调用:
        specs = parse_dataset_specs(args.calib_dataset, args.calib_samples)
        dataset, total = prepare_calib_dataset(specs, tokenizer)
        oneshot(model=..., dataset=dataset, num_calibration_samples=total, ...)
    """
    if print_summary:
        print(f"\n[数据集配方]")
        for ds_id, n in specs:
            print(f"  {ds_id!r}  {n} 条")
        print(f"  合计 {sum(n for _, n in specs)} 条")

    if not skip_prefetch:
        prefetch_calib_datasets(specs)

    # 注意:build 在 unset_proxy 之前。
    # build 内部 _resolve_split 仍可能查 HF Hub（即使数据已缓存）。
    dataset, total = build_calib_dataset(specs, tokenizer)

    # 全部就绪后再清除代理,避免量化阶段误走代理
    if unset_proxy_after_prefetch:
        unset_proxy_env()

    return dataset, total

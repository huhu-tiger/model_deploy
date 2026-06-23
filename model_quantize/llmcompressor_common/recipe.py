"""
AWQ 量化 recipe 构造工具。

封装 llmcompressor 0.12.0 的两步骤 AWQ recipe:
    1. AWQModifier             —— per-channel 缩放因子（基于校准激活的 grid search）
    2. QuantizationModifier    —— 应用缩放后做 round-to-nearest 整数量化

关键点:
    - AWQModifier **不接受 ignore 参数**;ignore 列表只放在 QuantizationModifier 上
    - AWQModifier.duo_scaling 类型为 Union[bool, Literal['both']]
    - 0.12.0 之前的类名是 AWQTransformModifier,现在统一改为 AWQModifier
"""

from __future__ import annotations


# ══════════════════════════════════════════════════════════════════
# 预设 IGNORE 列表（按模型族）
# ══════════════════════════════════════════════════════════════════

MODEL_IGNORE_PRESETS: dict[str, list[str]] = {
    # Qwen3.6-35B-A3B（MoE + 线性注意力混合）
    "qwen3_5_moe": [
        "lm_head",
        "re:.*mlp\\.gate$",
        "re:.*shared_expert.*",
        "re:.*linear_attn.*",
        "re:.*self_attn.*",
        "re:.*layers\\.0\\..*",
        "re:.*mtp.*",
        "re:model\\.visual.*",
    ],

    # GLM-5.2 (GlmMoeDsaForCausalLM)
    "glm_moe_dsa": [
        "lm_head",
        "embed_tokens",
        "re:.*indexer.*",
        "re:.*mlp\\.gate$",
        "re:.*shared_expert.*",
        "re:.*layers\\.0\\..*",
    ],

    # 通用 MoE 兜底
    "generic_moe": [
        "lm_head",
        "embed_tokens",
        "re:.*mlp\\.gate$",
        "re:.*shared_expert.*",
        "re:.*layers\\.0\\..*",
    ],
}


def build_awq_recipe(
    ignore: list[str],
    scheme: str = "W4A16_ASYM",
    duo_scaling: bool | str = "both",
    targets: list[str] | None = None,
):
    """
    构造 [AWQModifier, QuantizationModifier] recipe。

    参数:
      ignore        : 不量化的层（仅作用于 QuantizationModifier）
      scheme        : 量化方案（W4A16_ASYM / W4A16 / W8A8_ASYM）
      duo_scaling   : True / False / "both"
                      - True : 同时使用激活和权重做缩放
                      - False: 仅用激活
                      - "both": 一半 grid search 用激活,另一半用激活+权重
      targets       : QuantizationModifier 目标层类型,默认 ["Linear"]

    返回:
      list[Modifier],可直接传给 llmcompressor.oneshot(recipe=...)
    """
    # 延迟 import,避免外层在不需要时也加载 llmcompressor
    from llmcompressor.modifiers.transform.awq import AWQModifier
    from llmcompressor.modifiers.quantization import QuantizationModifier

    return [
        AWQModifier(duo_scaling=duo_scaling),
        QuantizationModifier(
            ignore=list(ignore),
            scheme=scheme,
            targets=list(targets) if targets else ["Linear"],
        ),
    ]

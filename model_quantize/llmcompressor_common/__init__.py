"""
llmcompressor_common —— llmcompressor AWQ 量化的公共函数库。

用法:
    # 1. GPU 预选（必须在 import torch 之前）
    from llmcompressor_common.gpu_select import pre_select_gpus
    pre_select_gpus()

    import torch  # 之后才能 import torch

    # 2. 校准数据集
    from llmcompressor_common.calib_dataset import (
        parse_dataset_specs, prefetch_calib_datasets, build_calib_dataset,
    )
    specs = parse_dataset_specs("cyankiwi,ultrachat", "256,256")
    prefetch_calib_datasets(specs)
    dataset, total = build_calib_dataset(specs, tokenizer)

    # 3. AWQ recipe
    from llmcompressor_common.recipe import build_awq_recipe, MODEL_IGNORE_PRESETS
    recipe = build_awq_recipe(
        ignore=MODEL_IGNORE_PRESETS["qwen3_5_moe"],
        scheme="W4A16_ASYM",
    )

    # 4. 资源预检 / 日志（大模型可选）
    from llmcompressor_common.resource_check import check_resources
    from llmcompressor_common.logging_utils import setup_logging

详见: /media/source/model_deploy/model_quantize/llmcompressor_common/README.md
"""

# 重新导出核心 API（方便 `from llmcompressor_common import X`）
from .gpu_select import pre_select_gpus, get_gpu_info
from .calib_dataset import (
    DATASET_ALIASES,
    resolve_dataset_id,
    parse_dataset_specs,
    prefetch_calib_datasets,
    build_calib_dataset,
    prepare_calib_dataset,
    format_specs_summary,
    unset_proxy_env,
    restore_proxy_env,
)
from .recipe import build_awq_recipe, MODEL_IGNORE_PRESETS
from .memory import (
    parse_memory_gib,
    get_cpu_available_gib,
    resolve_cpu_memory_str,
    get_model_size_gib,
    get_model_layer_count,
    get_output_disk_free_gib,
)
from .resource_check import check_resources
from .logging_utils import setup_logging

__all__ = [
    # gpu_select
    "pre_select_gpus", "get_gpu_info",
    # calib_dataset
    "DATASET_ALIASES", "resolve_dataset_id",
    "parse_dataset_specs", "prefetch_calib_datasets", "build_calib_dataset",
    "prepare_calib_dataset",
    "format_specs_summary",
    "unset_proxy_env", "restore_proxy_env",
    # recipe
    "build_awq_recipe", "MODEL_IGNORE_PRESETS",
    # memory
    "parse_memory_gib", "get_cpu_available_gib", "resolve_cpu_memory_str",
    "get_model_size_gib", "get_model_layer_count", "get_output_disk_free_gib",
    # resource_check
    "check_resources",
    # logging
    "setup_logging",
]

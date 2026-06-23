"""数据集/子集/指标的查询接口。

所有描述文字维护在 eval_constants.py，本文件只负责查询逻辑。
"""

from __future__ import annotations

from typing import TypedDict

from eval_constants import (
    DATASET_DESCRIPTIONS,
    METRIC_DESCRIPTIONS,
    SUBSET_DESCRIPTIONS,
)


class DatasetInfo(TypedDict):
    dimension: str
    capability: str


def lookup_dataset(dataset: str) -> DatasetInfo:
    """按 dataset_name 查找；未知数据集返回通用占位。"""
    info = DATASET_DESCRIPTIONS.get(dataset)
    if info:
        return DatasetInfo(dimension=info["dimension"], capability=info["capability"])
    return DatasetInfo(
        dimension="其他",
        capability=f"数据集 {dataset}（未在注册表中，详见 reports/*.json）",
    )


def lookup_metric(metric: str) -> str:
    """返回 metric 衡量说明；未知指标返回占位文字。"""
    return METRIC_DESCRIPTIONS.get(metric, f"指标 {metric}（详见 evalscope 文档）")


def lookup_subset_capability(dataset: str, subset: str) -> str | None:
    """按 'dataset/subset' 查子集级说明，找不到返回 None。"""
    return SUBSET_DESCRIPTIONS.get(f"{dataset}/{subset}")


def format_capability_note(dataset: str, metric: str, subset: str = "") -> tuple[str, str]:
    """返回 (能力维度, 能力说明)。

    能力说明优先级：
      1. 子集级描述 SUBSET_DESCRIPTIONS[dataset/subset] + metric 说明
      2. 数据集级描述 DATASET_DESCRIPTIONS[dataset] + metric 说明
    """
    ds = lookup_dataset(dataset)
    metric_desc = lookup_metric(metric)
    subset_cap = lookup_subset_capability(dataset, subset) if subset else None
    capability = subset_cap if subset_cap is not None else ds["capability"]
    return ds["dimension"], f"{capability}；{metric_desc}"

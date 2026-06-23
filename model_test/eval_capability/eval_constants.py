"""
评测能力说明常量 —— 所有描述文字的唯一来源。

修改说明：
  - DATASET_DESCRIPTIONS  数据集级别的能力维度和整体说明
  - SUBSET_DESCRIPTIONS   子集级别的精细说明（优先于数据集级别）
  - METRIC_DESCRIPTIONS   指标含义说明

格式：
  DATASET_DESCRIPTIONS[dataset]           = {"dimension": ..., "capability": ...}
  SUBSET_DESCRIPTIONS["dataset/subset"]   = "说明文字"
  METRIC_DESCRIPTIONS[metric]             = "说明文字"
"""

from __future__ import annotations

# =============================================================================
# 数据集级别说明
# =============================================================================

DATASET_DESCRIPTIONS: dict[str, dict[str, str]] = {
    # ── 中文能力 ──────────────────────────────────────────────────────────────
    "ceval": {
        "dimension": "中文综合",
        "capability": "52 个中文学科选择题（人文/理工/社科），考察中文知识与常识推理",
    },
    "cmmlu": {
        "dimension": "中文综合",
        "capability": "67 个中文学科选择题，偏中国本土知识与语境理解",
    },
    # ── 英文知识 ──────────────────────────────────────────────────────────────
    "mmlu": {
        "dimension": "英文知识",
        "capability": "57 个英文学科选择题（5-shot），考察广域学科知识",
    },
    "mmlu_pro": {
        "dimension": "英文知识进阶",
        "capability": "10 选 1 高难 MCQ，干扰项更强，考察深度学科理解",
    },
    # ── 数学推理 ──────────────────────────────────────────────────────────────
    "gsm8k": {
        "dimension": "小学数学推理",
        "capability": "多步骤算术应用题，考察链式推理与数值计算（CoT 友好）",
    },
    "math_500": {
        "dimension": "高难数学",
        "capability": "MATH 子集 Level 1-5，考察竞赛级数学推导与证明",
    },
    "aime24": {
        "dimension": "竞赛数学",
        "capability": "AIME 2024 真题，考察高难度竞赛数学解题",
    },
    "aime25": {
        "dimension": "竞赛数学",
        "capability": "AIME 2025 真题，考察高难度竞赛数学解题",
    },
    # ── 科学推理 ──────────────────────────────────────────────────────────────
    "gpqa_diamond": {
        "dimension": "研究生级科学推理",
        "capability": "物理/化学/生物 PhD 级选择题，强干扰项，考察深度科学推理",
    },
    "bbh": {
        "dimension": "通用推理",
        "capability": "BigBench-Hard 23 子任务，考察多步逻辑、归纳与语言推理",
    },
    "drop": {
        "dimension": "阅读+数值推理",
        "capability": "段落阅读理解并结合文中数值进行计算与问答",
    },
    "arc": {
        "dimension": "科学常识",
        "capability": "小学科学选择题，考察基础科学常识与简单推理",
    },
    # ── 代码 ──────────────────────────────────────────────────────────────────
    "humaneval": {
        "dimension": "代码生成",
        "capability": "164 道 Python 函数补全，考察代码正确性与 pass@1",
    },
    "live_code_bench": {
        "dimension": "代码推理",
        "capability": "LeetCode 风格竞赛题，考察算法推理与可执行代码生成",
    },
    # ── 指令遵循 ──────────────────────────────────────────────────────────────
    "ifeval": {
        "dimension": "指令遵循",
        "capability": "可程序验证的格式/字数/关键词/结构约束，考察指令理解与遵从",
    },
    # ── 工具调用 ──────────────────────────────────────────────────────────────
    "bfcl_v3": {
        "dimension": "工具调用",
        "capability": "函数调用全场景：AST 格式校验（static）/ 真实执行（live）/ 多轮对话连续调用（multi_turn）",
    },
    "bfcl_v4": {
        "dimension": "工具调用+Agent",
        "capability": "v3 全部能力 + web_search / memory / 格式敏感性等 Agent 场景",
    },
}


# =============================================================================
# 子集级别说明（优先于 DATASET_DESCRIPTIONS）
# 格式：key = "dataset/subset"
# =============================================================================

SUBSET_DESCRIPTIONS: dict[str, str] = {
    # ── bfcl_v3 / AST_NON_LIVE ────────────────────────────────────────────────
    "bfcl_v3/simple":             "单函数调用格式校验（一个工具、明确参数）",
    "bfcl_v3/multiple":           "多函数选择：从多个候选中选出正确工具并给参数",
    "bfcl_v3/parallel":           "并行调用：同一轮同时调用多个独立工具",
    "bfcl_v3/parallel_multiple":  "并行 × 多选：同时调多个且每个均需从候选中选出",
    "bfcl_v3/java":               "Java 语言场景的单函数调用格式校验",
    "bfcl_v3/javascript":         "JavaScript 语言场景的单函数调用格式校验",
    # ── bfcl_v3 / AST_LIVE ────────────────────────────────────────────────────
    "bfcl_v3/live_simple":          "真实 API 单函数调用，参数需能实际执行通过",
    "bfcl_v3/live_multiple":        "真实 API 多函数选择 + 执行验证",
    "bfcl_v3/live_parallel":        "真实 API 并行调用 + 执行验证",
    "bfcl_v3/live_parallel_multiple": "真实 API 并行 × 多选 + 执行验证",
    # ── bfcl_v3 / RELEVANCE ───────────────────────────────────────────────────
    "bfcl_v3/irrelevance":      "无关请求拒绝：用户提问与工具无关时，模型应不调用工具",
    "bfcl_v3/live_irrelevance": "真实 API 场景下的无关请求拒绝",
    "bfcl_v3/live_relevance":   "真实 API 场景下的相关请求识别（应调工具时必须调）",
    # ── bfcl_v3 / MULTI_TURN ──────────────────────────────────────────────────
    "bfcl_v3/multi_turn_base":         "多轮对话基础：根据前几轮工具返回决定下一步调用",
    "bfcl_v3/multi_turn_miss_func":    "多轮对话中函数定义缺失时的容错与处理能力",
    "bfcl_v3/multi_turn_miss_param":   "多轮对话中参数定义缺失时的补全与应对能力",
    "bfcl_v3/multi_turn_long_context": "长上下文多轮对话中维持正确工具调用状态",
    # ── bfcl_v3 / 汇总行（自动生成，Num=0 表示无实际题目）─────────────────────
    "bfcl_v3/NON_LIVE":   "【汇总】AST_NON_LIVE 类所有子集的加权平均得分",
    "bfcl_v3/LIVE":       "【汇总】AST_LIVE 类所有子集的加权平均得分",
    "bfcl_v3/MULTI_TURN": "【汇总】MULTI_TURN 类所有子集的非加权平均得分",
    "bfcl_v3/OVERALL":    "【汇总】全部类别非加权平均（NON_LIVE + LIVE + MULTI_TURN）",
    # ── bfcl_v4 / 新增能力 ────────────────────────────────────────────────────
    "bfcl_v4/web_search_base":       "基础 Web 搜索工具调用（需 SerpAPI）",
    "bfcl_v4/web_search_no_snippet": "无摘要片段的 Web 搜索调用（考察无提示时的参数推断）",
    "bfcl_v4/memory_kv":             "KV 存储 Memory 工具调用（Agent 记忆场景）",
    "bfcl_v4/memory_vector":         "向量 Memory 工具调用（语义检索场景）",
    "bfcl_v4/memory_rec_sum":        "记忆摘要与召回工具调用",
    # ── ifeval ────────────────────────────────────────────────────────────────
    "ifeval/default": "~500 条含可程序验证约束的 prompt（格式/字数/关键词/结构）",
    # ── gsm8k ─────────────────────────────────────────────────────────────────
    "gsm8k/main": "多步骤小学数学应用题，考察链式推理与数值计算",
    # ── gpqa_diamond ──────────────────────────────────────────────────────────
    "gpqa_diamond/default": "物理/化学/生物 PhD 级选择题，强干扰项，考察深度科学推理",
    # ── math_500 ──────────────────────────────────────────────────────────────
    "math_500/Level 1": "MATH Level 1：入门难度数学题",
    "math_500/Level 2": "MATH Level 2：初级难度数学题",
    "math_500/Level 3": "MATH Level 3：中级难度数学题",
    "math_500/Level 4": "MATH Level 4：高级难度数学题",
    "math_500/Level 5": "MATH Level 5：竞赛级难度数学题",
    # ── humaneval ─────────────────────────────────────────────────────────────
    "humaneval/default": "164 道 Python 函数补全题，考察代码生成正确性（pass@1）",
}


# =============================================================================
# 指标说明
# =============================================================================

METRIC_DESCRIPTIONS: dict[str, str] = {
    # 通用准确率
    "mean_acc":  "准确率：模型输出与标准答案一致的比例",
    "acc":       "准确率：模型输出与标准答案一致的比例",
    # 代码/数学通过率
    "pass@1":    "单次生成通过全部测试用例的比例",
    "pass@k":    "k 次生成中至少一次通过测试的比例",
    # ifeval 四个子指标
    "mean_prompt_level_strict": "Prompt 级严格遵从：prompt 内全部可验证指令必须同时满足",
    "mean_prompt_level_loose":  "Prompt 级宽松遵从：允许轻微格式偏差仍计为遵从",
    "mean_inst_level_strict":   "指令级严格遵从：逐条指令单独计分后取平均（严格）",
    "mean_inst_level_loose":    "指令级宽松遵从：逐条指令单独计分后取平均（宽松）",
    # 阅读理解
    "f1": "F1：预测与参考答案的 token 重叠 F1 分数",
    "em": "Exact Match：预测与参考答案完全匹配的比例",
}

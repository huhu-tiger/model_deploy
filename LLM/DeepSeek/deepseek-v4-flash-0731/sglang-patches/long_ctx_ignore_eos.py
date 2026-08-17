"""Long-prompt EOS workaround for DeepSeek-V4 + DP attention.

Community has no root-cause fix yet (sglang#33397 / #33360). After long
prefill the EOS logit (token id 1) can beat newline; generation stops at
the first token. This hook sets ignore_eos when prompt_tokens >= threshold.

Short requests are unchanged. Long requests then stop on max_tokens
(default 128 if the client omits it). Disable with
SGLANG_LONG_CTX_IGNORE_EOS_TOKENS=0.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("sglang.long_ctx_ignore_eos")

_TARGET = "sglang.srt.managers.tokenizer_manager"


def _threshold() -> int:
    raw = os.environ.get("SGLANG_LONG_CTX_IGNORE_EOS_TOKENS", "32768")
    try:
        return int(raw)
    except ValueError:
        return 32768


def _prompt_len(input_ids) -> int:
    if not input_ids:
        return 0
    first = input_ids[0]
    if isinstance(first, (list, tuple)):
        return max((len(x) for x in input_ids), default=0)
    return len(input_ids)


def install(tm_mod) -> None:
    cls = getattr(tm_mod, "TokenizerManager", None)
    if cls is None:
        return
    orig = cls._create_tokenized_object
    if getattr(orig, "_long_ctx_ignore_eos", False):
        return
    thresh = _threshold()
    if thresh <= 0:
        return

    def wrapped(self, obj, input_text, input_ids, *args, **kwargs):
        result = orig(self, obj, input_text, input_ids, *args, **kwargs)
        n = _prompt_len(input_ids)
        if n < thresh:
            return result
        sp = getattr(result, "sampling_params", None)
        if sp is None or getattr(sp, "ignore_eos", False):
            return result
        sp.ignore_eos = True
        logger.warning(
            "long-ctx auto ignore_eos: prompt_tokens=%s >= %s "
            "(SGLANG_LONG_CTX_IGNORE_EOS_TOKENS=0 to disable)",
            n,
            thresh,
        )
        return result

    wrapped._long_ctx_ignore_eos = True
    cls._create_tokenized_object = wrapped
    logger.info("installed long-ctx ignore_eos hook (threshold=%s tokens)", thresh)


class _AfterImportHook:
    def find_spec(self, fullname, path, target=None):
        if fullname != _TARGET:
            return None
        for finder in sys.meta_path:
            if finder is self:
                continue
            find_spec = getattr(finder, "find_spec", None)
            if find_spec is None:
                continue
            spec = find_spec(fullname, path, target)
            if spec is None or spec.loader is None:
                continue
            loader = spec.loader
            orig_exec = loader.exec_module

            def exec_module(module, _orig=orig_exec):
                _orig(module)
                try:
                    install(module)
                except Exception:
                    logger.exception("failed to install long-ctx ignore_eos hook")

            loader.exec_module = exec_module
            return spec
        return None


def enable() -> None:
    if _threshold() <= 0:
        return
    if any(isinstance(x, _AfterImportHook) for x in sys.meta_path):
        return
    mod = sys.modules.get(_TARGET)
    if mod is not None:
        install(mod)
        return
    sys.meta_path.insert(0, _AfterImportHook())


enable()

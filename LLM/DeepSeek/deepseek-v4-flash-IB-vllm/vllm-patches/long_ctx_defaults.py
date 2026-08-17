"""vLLM request defaults + long-ctx min_tokens for DeepSeek-V4 premature EOS.

Official image is not rebuilt. sitecustomize imports this module.

When the client omits a field:
  temperature -> 0          (HF generation_config is 1.0)
  top_p -> 1.0
  thinking / enable_thinking -> false

max_tokens is not patched: 512 would truncate thinking / long answers;
runaway generation is the client's job.

When prompt_tokens >= threshold (default 32768) and min_tokens is 0:
  min_tokens -> 32, clamped to the request's resolved max_tokens.

Client-explicit values win. Disable with VLLM_LONG_CTX_DEFAULTS=0.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("vllm.long_ctx_defaults")

_ATTR = "_vllm_long_ctx_prompt_len"
_PROTOCOL = "vllm.entrypoints.openai.chat_completion.protocol"
_SERVING = "vllm.entrypoints.openai.chat_completion.serving"


def _enabled() -> bool:
    return os.environ.get("VLLM_LONG_CTX_DEFAULTS", "1") not in {"0", "false", "False"}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _threshold() -> int:
    return _int_env("VLLM_LONG_CTX_MIN_TOKENS_THRESHOLD", 32768)


def _min_tokens() -> int:
    return _int_env("VLLM_LONG_CTX_MIN_TOKENS", 32)


def _default_temperature() -> float:
    return _float_env("VLLM_DEFAULT_TEMPERATURE", 0.0)


def _default_top_p() -> float:
    return _float_env("VLLM_DEFAULT_TOP_P", 1.0)


def _prompt_len(request) -> int:
    return int(getattr(request, _ATTR, 0) or 0)


def _clamped_min_tokens(sp, want: int) -> int:
    cap = getattr(sp, "max_tokens", None)
    if cap is None:
        return want
    try:
        cap_i = int(cap)
    except (TypeError, ValueError):
        return want
    if cap_i <= 0:
        return 0
    return min(want, cap_i)


def _install_protocol(mod) -> None:
    cls = getattr(mod, "ChatCompletionRequest", None)
    if cls is None:
        return

    orig_sp = cls.to_sampling_params
    if not getattr(orig_sp, "_long_ctx_defaults", False):

        def to_sampling_params(self, max_tokens, default_sampling_params):
            defaults = dict(default_sampling_params or {})
            if self.temperature is None:
                defaults["temperature"] = _default_temperature()
            if self.top_p is None:
                defaults["top_p"] = _default_top_p()
            sp = orig_sp(self, max_tokens, defaults)
            n = _prompt_len(self)
            thresh = _threshold()
            min_n = _min_tokens()
            # Only fill in min_tokens when the client left it at the
            # field default (0). A client-supplied value -- including an
            # explicit 0 to allow immediate EOS -- always wins.
            client_min_tokens = getattr(self, "min_tokens", 0) or 0
            if (
                thresh > 0
                and min_n > 0
                and n >= thresh
                and not getattr(self, "ignore_eos", False)
                and client_min_tokens <= 0
            ):
                want = _clamped_min_tokens(sp, min_n)
                if want > 0:
                    sp.min_tokens = want
                    logger.warning(
                        "long-ctx auto min_tokens=%s: prompt_tokens=%s >= %s "
                        "(VLLM_LONG_CTX_DEFAULTS=0 to disable)",
                        want,
                        n,
                        thresh,
                    )
            return sp

        to_sampling_params._long_ctx_defaults = True
        cls.to_sampling_params = to_sampling_params

    orig_chat = cls.build_chat_params
    if getattr(orig_chat, "_long_ctx_defaults", False):
        return

    def build_chat_params(self, *args, **kwargs):
        user = dict(self.chat_template_kwargs or {})
        if (
            "thinking" not in user
            and "enable_thinking" not in user
            and getattr(self, "reasoning_effort", None) is None
        ):
            user["thinking"] = False
            user["enable_thinking"] = False
            old = self.chat_template_kwargs
            self.chat_template_kwargs = user
            try:
                return orig_chat(self, *args, **kwargs)
            finally:
                self.chat_template_kwargs = old
        return orig_chat(self, *args, **kwargs)

    build_chat_params._long_ctx_defaults = True
    cls.build_chat_params = build_chat_params
    logger.info(
        "installed chat defaults (T=%s top_p=%s; min_tokens=%s when prompt>=%s)",
        _default_temperature(),
        _default_top_p(),
        _min_tokens(),
        _threshold(),
    )


def _stamp_prompt_len(serving, request, engine_inputs) -> None:
    n = 0
    for engine_input in engine_inputs or []:
        try:
            n = max(n, int(serving._extract_prompt_len(engine_input) or 0))
        except Exception:
            comps = serving._extract_prompt_components(engine_input)
            ids = getattr(comps, "token_ids", None) or []
            n = max(n, len(ids))
    setattr(request, _ATTR, n)


def _install_serving(mod) -> None:
    cls = getattr(mod, "OpenAIServingChat", None)
    if cls is None:
        return
    orig = cls.render_chat_request
    if getattr(orig, "_long_ctx_defaults", False):
        return

    async def render_chat_request(self, request):
        result = await orig(self, request)
        if isinstance(result, tuple) and len(result) == 2:
            _conversation, engine_inputs = result
            try:
                _stamp_prompt_len(self, request, engine_inputs)
            except Exception:
                logger.exception("failed to stamp long-ctx prompt length")
        return result

    render_chat_request._long_ctx_defaults = True
    cls.render_chat_request = render_chat_request
    logger.info("installed render_chat_request prompt-len stamp")


_INSTALLERS = {
    _PROTOCOL: _install_protocol,
    _SERVING: _install_serving,
}


class _AfterImportHook:
    def find_spec(self, fullname, path, target=None):
        if fullname not in _INSTALLERS:
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

            def exec_module(module, _orig=orig_exec, _name=fullname):
                _orig(module)
                try:
                    _INSTALLERS[_name](module)
                except Exception:
                    logger.exception("failed to install %s hook", _name)

            loader.exec_module = exec_module
            return spec
        return None


def enable() -> None:
    if not _enabled():
        return
    if any(isinstance(x, _AfterImportHook) for x in sys.meta_path):
        return
    pending = False
    for name, install in _INSTALLERS.items():
        mod = sys.modules.get(name)
        if mod is not None:
            install(mod)
        else:
            pending = True
    if pending:
        sys.meta_path.insert(0, _AfterImportHook())
    print(
        "[vllm.long_ctx_defaults] enabled "
        f"(T={_default_temperature()} top_p={_default_top_p()} "
        f"min_tokens={_min_tokens()} when prompt>={_threshold()})",
        file=sys.stderr,
        flush=True,
    )


enable()

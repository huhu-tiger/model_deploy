# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
#
# Patched: vllm-project/vllm PR #46124
# Fix: Parse MiniMax M3 visible reasoning markers (<mm:think> / </mm:think>)
# When tokenizer splits special tokens, fall back to visible-text parsing
# so marker chunks populate delta.reasoning instead of leaking to delta.content.

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from vllm.entrypoints.openai.engine.protocol import DeltaMessage
from vllm.reasoning.basic_parsers import BaseThinkingReasoningParser

if TYPE_CHECKING:
    from vllm.entrypoints.openai.chat_completion.protocol import (
        ChatCompletionRequest,
    )
    from vllm.entrypoints.openai.responses.protocol import ResponsesRequest


class MiniMaxM3ReasoningParser(BaseThinkingReasoningParser):
    """Reasoning parser for MiniMax M3 explicit thinking blocks.

    MiniMax M3 emits reasoning as:

        <mm:think>reasoning text</mm:think>assistant content

    The M3 tokenizer exposes both markers as complete vocabulary tokens. The
    chat template may also prefill the start marker when
    ``thinking_mode="enabled"``, so generated text can begin directly inside a
    reasoning block without emitting ``<mm:think>`` again.
    """

    @property
    def start_token(self) -> str:
        return "<mm:think>"

    @property
    def end_token(self) -> str:
        return "</mm:think>"

    def __init__(self, tokenizer, *args, **kwargs):
        super().__init__(tokenizer, *args, **kwargs)
        chat_kwargs = kwargs.get("chat_template_kwargs", {}) or {}
        self._initial_in_reasoning = chat_kwargs.get("thinking_mode") == "enabled"
        self._at_response_start = True

    def extract_reasoning(
        self,
        model_output: str,
        request: "ChatCompletionRequest | ResponsesRequest",
    ) -> tuple[str | None, str | None]:
        # MiniMax M3 can start a response with a stray closer. Drop that first
        # token only; later unmatched closers stay visible as content.
        if not self._initial_in_reasoning and model_output.startswith(
            self.end_token
        ):
            content = model_output[len(self.end_token) :]
            return None, content or None

        if self._initial_in_reasoning and self.start_token not in model_output:
            reasoning, end, content = model_output.partition(self.end_token)
            if not end:
                return model_output, None
            return reasoning, content or None

        if self.start_token not in model_output:
            return None, model_output

        content_before, _, after_start = model_output.partition(self.start_token)
        reasoning, end, content_after = after_start.partition(self.end_token)
        if not end:
            return reasoning, content_before or None

        return reasoning, (content_before + content_after) or None

    def is_reasoning_end(self, input_ids: Sequence[int]) -> bool:
        # The MiniMax M3 chat template system prompt instruction text includes
        # literal <mm:think></mm:think> as a format example AND a standalone
        # </mm:think> in the phrase "after the </mm:think> prefix".
        # The base-class backward-scan hits this system-message </mm:think>
        # and incorrectly returns True, setting state.reasoning_ended=True
        # before the first generated token, so all output leaks into content.
        #
        # The generation prefix appended by the template is:
        #   disabled:  ...ai\n + </mm:think>  → input_ids[-1] == end_token_id
        #   enabled:   ...ai\n + <mm:think>   → input_ids[-1] == start_token_id
        #   default:   ...ai\n               → last token is neither marker
        #
        # Checking the last token avoids any confusion from marker examples
        # buried inside the system message.
        return bool(input_ids) and input_ids[-1] == self.end_token_id

    def is_reasoning_end_streaming(
        self, input_ids: Sequence[int], delta_ids: Iterable[int]
    ) -> bool:
        delta_ids = tuple(delta_ids)
        if self.end_token_id in delta_ids:
            return True
        if self.end_token_id in input_ids:
            return True
        if self._initial_in_reasoning:
            return False
        if self.start_token_id not in input_ids:
            return bool(input_ids)
        return False

    def extract_content_ids(self, input_ids: list[int]) -> list[int]:
        if self.end_token_id in input_ids:
            end_index = len(input_ids) - 1 - input_ids[::-1].index(
                self.end_token_id
            )
            return input_ids[end_index + 1 :]

        if self._initial_in_reasoning and self.start_token_id not in input_ids:
            return []

        if self.start_token_id not in input_ids:
            return input_ids
        return []

    def extract_reasoning_streaming(
        self,
        previous_text: str,
        current_text: str,
        delta_text: str,
        previous_token_ids: Sequence[int],
        current_token_ids: Sequence[int],
        delta_token_ids: Sequence[int],
    ) -> DeltaMessage | None:
        if not delta_text:
            return None

        # PR #46124: visible-text fallback —— when the cumulative stream
        # contains a visible marker, use text-based parsing regardless of
        # token IDs. This handles the case where the tokenizer splits
        # <mm:think> / </mm:think> into sub-tokens so the special token IDs
        # never appear in delta_token_ids.
        if self.start_token in current_text or self.end_token in current_text:
            previous_reasoning, previous_content = self.extract_reasoning(
                previous_text,
                request=None,  # type: ignore[arg-type]
            )
            current_reasoning, current_content = self.extract_reasoning(
                current_text,
                request=None,  # type: ignore[arg-type]
            )
            reasoning_delta = (current_reasoning or "")[
                len(previous_reasoning or "") :
            ]
            content_delta = (current_content or "")[
                len(previous_content or "") :
            ]
            if not reasoning_delta and not content_delta:
                return None
            return DeltaMessage(
                reasoning=reasoning_delta or None,
                content=content_delta or None,
            )

        if self._at_response_start and not self._initial_in_reasoning:
            # Apply the leading-closer tolerance once. Later unmatched closers
            # stay visible as content.
            self._at_response_start = False
            if delta_text.startswith(self.end_token):
                delta_text = delta_text[len(self.end_token) :]
                if not delta_text:
                    return None
                if delta_token_ids and delta_token_ids[0] == self.end_token_id:
                    delta_token_ids = delta_token_ids[1:]

        if self.end_token_id in previous_token_ids:
            return DeltaMessage(content=delta_text)

        if (
            self._initial_in_reasoning
            and self.start_token_id not in previous_token_ids
            and self.start_token_id not in delta_token_ids
        ):
            if self.end_token_id in delta_token_ids:
                reasoning, _, content = delta_text.partition(self.end_token)
                return DeltaMessage(
                    reasoning=reasoning or None,
                    content=content or None,
                )
            return DeltaMessage(reasoning=delta_text)

        if (
            self.start_token_id not in previous_token_ids
            and self.start_token_id not in delta_token_ids
        ):
            return DeltaMessage(content=delta_text)

        if self.end_token_id in delta_token_ids:
            reasoning_text, _, content = delta_text.partition(self.end_token)
            if self.start_token_id in delta_token_ids:
                _, _, reasoning_text = reasoning_text.partition(self.start_token)
            return DeltaMessage(
                reasoning=reasoning_text or None,
                content=content or None,
            )

        if self.start_token_id in delta_token_ids:
            _, _, reasoning = delta_text.partition(self.start_token)
            return DeltaMessage(reasoning=reasoning) if reasoning else None

        return DeltaMessage(reasoning=delta_text)

    def count_reasoning_tokens(self, token_ids: Sequence[int]) -> int:
        if not self._initial_in_reasoning:
            return super().count_reasoning_tokens(token_ids)

        count = 0
        depth = 1
        for token_id in token_ids:
            if token_id == self.start_token_id:
                depth += 1
                continue
            if token_id == self.end_token_id:
                if depth > 0:
                    depth -= 1
                continue
            if depth > 0:
                count += 1
        return count

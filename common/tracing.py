"""Tracing behind the `Tracer` Protocol. Off (no-op) unless Langfuse host and both keys are set.

Tracing is a debugging aid, not an audit log. Spans hold prompts and answers unless
LANGFUSE_CAPTURE_CONTENT=false, so keep the Langfuse server self-hosted and set a retention policy.
"""
from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from common.protocols import Span, Tracer
from common.settings import LangfuseSettings, langfuse_settings

logger = logging.getLogger("lcrag.tracing")

KINDS = {"span", "generation", "tool", "chain", "retriever", "guardrail", "agent"}


class _NoopSpan:
    def update(self, *, output: Any = None, level: str | None = None, message: str | None = None) -> None:
        return None


class NoopTracer:
    @contextmanager
    def span(self, name: str, *, kind: str = "span", input: Any = None,
             metadata: dict[str, Any] | None = None) -> Iterator[Span]:
        yield _NoopSpan()

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        return None


def _redact(value: Any) -> Any:
    """Keep only the shape of a value (sizes), never its text."""
    if value is None:
        return None
    if isinstance(value, str):
        return {"chars": len(value)}
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return {"items": len(value)}
    return value if isinstance(value, (bool, int, float)) else {"type": type(value).__name__}


class _LangfuseSpan:
    def __init__(self, obs: Any, mask: Any) -> None:
        self._obs, self._mask = obs, mask

    def update(self, *, output: Any = None, level: str | None = None, message: str | None = None) -> None:
        try:
            kwargs: dict[str, Any] = {}
            if output is not None:
                kwargs["output"] = self._mask(output)
            if level:
                kwargs["level"] = level
            if message:
                kwargs["status_message"] = message
            self._obs.update(**kwargs)
        except Exception as exc:  # noqa: BLE001 - tracing must never break a request
            logger.warning("trace update failed: %s", type(exc).__name__)


class LangfuseTracer:
    def __init__(self, client: Any, *, capture_content: bool = True) -> None:
        self._lf = client
        self._mask = (lambda v: v) if capture_content else _redact

    @contextmanager
    def span(self, name: str, *, kind: str = "span", input: Any = None,
             metadata: dict[str, Any] | None = None) -> Iterator[Span]:
        cm: Any = None
        try:
            cm = self._lf.start_as_current_observation(
                name=name, as_type=kind if kind in KINDS else "span",
                input=self._mask(input), metadata=metadata)
            obs = cm.__enter__()
        except Exception as exc:  # noqa: BLE001 - a broken tracer must not break the pipeline
            logger.warning("trace start failed: %s", type(exc).__name__)
            yield _NoopSpan()
            return
        handle = _LangfuseSpan(obs, self._mask)
        try:
            yield handle
        except BaseException as exc:
            handle.update(level="ERROR", message=type(exc).__name__)  # type only: messages may hold prompts
            self._close(cm, *sys.exc_info())
            raise
        else:
            self._close(cm, None, None, None)

    @staticmethod
    def _close(cm: Any, *exc_info: Any) -> None:
        try:
            cm.__exit__(*exc_info)
        except Exception as exc:  # noqa: BLE001
            logger.warning("trace end failed: %s", type(exc).__name__)

    def flush(self) -> None:
        try:
            self._lf.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning("trace flush failed: %s", type(exc).__name__)

    def shutdown(self) -> None:
        try:
            self._lf.shutdown()
        except Exception as exc:  # noqa: BLE001
            logger.warning("trace shutdown failed: %s", type(exc).__name__)


def build_tracer(settings: LangfuseSettings | None = None) -> Tracer:
    cfg = settings or langfuse_settings()
    if not cfg.enabled:
        return NoopTracer()
    try:
        from langfuse import Langfuse  # imported lazily: the SDK is optional when tracing is off

        client = Langfuse(host=cfg.host, public_key=cfg.public_key.get_secret_value(),
                          secret_key=cfg.secret_key.get_secret_value())
        return LangfuseTracer(client, capture_content=cfg.capture_content)
    except Exception as exc:  # noqa: BLE001 - tracing is optional; fall back to off
        logger.warning("tracing disabled, Langfuse init failed: %s", type(exc).__name__)
        return NoopTracer()

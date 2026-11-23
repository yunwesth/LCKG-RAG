"""Run the OpenAI-compatible API: `python -m scripts.serve` (settings: ORCH_HOST, ORCH_PORT, ORCH_API_KEY, ...)."""
from __future__ import annotations

import sys

import uvicorn

from common.settings import OrchestratorSettings, orchestrator_settings
from orchestrator.api import create_app
from orchestrator.wiring import build_pipeline

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def check_exposure(cfg: OrchestratorSettings) -> str | None:
    """An API reachable from other machines must ask for a key; returns the problem, or None."""
    if cfg.host not in LOOPBACK and not cfg.api_key.get_secret_value():
        return f"ORCH_HOST={cfg.host} is not loopback: set ORCH_API_KEY first (or bind to 127.0.0.1)."
    return None


def main() -> int:
    cfg = orchestrator_settings()
    problem = check_exposure(cfg)
    if problem:
        print(problem, file=sys.stderr)
        return 2
    pipeline = build_pipeline()
    try:
        uvicorn.run(create_app(pipeline, cfg), host=cfg.host, port=cfg.port)
    finally:
        pipeline.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

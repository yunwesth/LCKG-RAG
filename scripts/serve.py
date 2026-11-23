"""Run the OpenAI-compatible API: `python -m scripts.serve` (host/port from ORCH_HOST / ORCH_PORT)."""
from __future__ import annotations

import os

import uvicorn

from orchestrator.api import create_app
from orchestrator.wiring import build_pipeline


def main() -> None:
    uvicorn.run(create_app(build_pipeline()), host=os.getenv("ORCH_HOST", "127.0.0.1"),
                port=int(os.getenv("ORCH_PORT", "8000")))


if __name__ == "__main__":
    main()

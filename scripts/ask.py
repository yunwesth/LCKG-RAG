"""Ask one question from the terminal: `python -m scripts.ask "What comes before 8.EE.C.8?"`."""
from __future__ import annotations

import sys

from orchestrator.wiring import build_pipeline


def main() -> int:
    if len(sys.argv) < 2:
        print('usage: python -m scripts.ask "question" ["follow-up" ...]')
        return 2
    msgs: list[dict[str, str]] = []
    for i, text in enumerate(sys.argv[1:]):
        msgs.append({"role": "user", "content": text})
        state = build_pipeline().run(msgs)
        print(f"[{state.status.value if state.status else '?'}] {state.reply}")
        msgs.append({"role": "assistant", "content": state.reply or ""})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

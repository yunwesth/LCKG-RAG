# Progress

**Agents: append an entry here every time progress is made** (code or docs changed, decision made, bug found, command that mattered, task advanced). Add it before ending the turn. Newest first. Be concrete: paths, commands, results, why. Update "Current state" and the phase checklist too. Plan lives in `docs/masterplan.md`.

**Diagrams and status tracker:** [live tracker (published)](https://claude.ai/artifact/MBUMTrxa3x2vmpzg6BZsrN) · local source [`docs/tracker.html`](tracker.html). Keep it in sync with this file.

## Current state
Phase 0 done. Phase 1 (foundation) is complete except Ollama. Neo4j (`lcrag-neo4j`, bolt 7688) is up with the full KG; `scripts.healthcheck --deep` passes connection, read-only guard and schema (315,434 nodes / 551,058 rels). Ollama is not running and no models are pulled, so the two Ollama checks still fail. Docs only: `docs/pre-plan.md`, `docs/masterplan.md`, `docs/progress.md`. ECC plugin installed at project scope. No code yet.

## Phase checklist
- [ ] Phase 0: Decisions and discovery (Q1 to Q4, schema record). Schema record drafted, Q3 hardware known; all questions decided; exact Qwen chat tag pending
- [~] Phase 1: Foundation. Done and live-verified: skeleton, config, Compose, Neo4j + data, guarded read-only client, healthcheck, tests. Left: start Ollama, pull models, pass the 2 Ollama checks
- [ ] Phase 2: Ingest and indexes
- [ ] Phase 3: KG tool layer
- [ ] Phase 4: Orchestrator
- [ ] Phase 5: Eval and observability
- [ ] Phase 6: UI integration and hardening

## Next steps
- [ ] Start Ollama (`ollama serve`); `ollama pull qwen3-embedding:0.6b` (about 639 MB) and the chosen Qwen 3.6 8B-14B chat tag; put the verified tag in `.env` (`.env.example` has `qwen3.6:8b` as an UNVERIFIED placeholder); rerun `make health`
- [ ] Owner confirms masterplan section 9 schema (start Neo4j and run the 3 Cypher queries, or accept the discovered values) (Q2)
- [ ] Verify exact Qwen 3.6 small chat tag and embedding dimension with `ollama pull` (start Ollama first)

## Blockers and gotchas
- Do not fill TBD items without owner confirmation.
- ECC marketplace `ecc` is user-global and was repointed to the GitHub repo (previously a local dir in `~/LearningCommonsVisualization/ECC`).

## Log (newest first)

### 2026-11-15: Phase 1 live verification
- Started Docker Desktop. Port clash: KG project's `kg-neo4j` holds 7687/7474, so this project's host ports are 7688/7475 (compose env `NEO4J_BOLT_PORT`/`NEO4J_HTTP_PORT`, `.env` `NEO4J_URI`). Left `kg-neo4j` untouched.
- Created `.env` (git-ignored, mode 600) with a generated admin password; `make up` -> container `lcrag-neo4j` healthy.
- Loaded data per owner decision: ran `~/LearningCommonsVisualization/pocs/poc3/import_kg.py --data .../data/v1.17.0` against bolt 7688 (46.5 s; 551,058 rels in 21 s).
- **Bug found by the live run:** `Neo4jReader` passed a `neo4j.Query` to `tx.run`, unsupported in managed transactions (fake-driver tests could not catch it). Fixed with `@unit_of_work(timeout=...)` on the transaction function; test now asserts the timeout on the tx function.
- `python -m scripts.healthcheck --deep`: PASS connection, read-only guard, schema (all per-label counts match). Probe: server refuses `CREATE` inside `execute_read` (`Neo.ClientError.Statement.AccessMode`), probe node absent.
- Ollama: `ollama` installed, server not running, nothing pulled; 2 checks FAIL (expected). Did not pull models without approval (several GB).

### 2026-11-15: Phase 1 foundation built
- Added `pyproject.toml`, `.env.example`, `.gitignore`, `Makefile`, `docker-compose.yml` (neo4j `lcrag-neo4j`, optional `ui` profile with open-webui; Langfuse deferred to Phase 5).
- Modules: `common/{settings,errors,protocols,ollama_client}.py`; `kg_tools/{cypher_guard,neo4j_client,schema}.py`; package stubs for `orchestrator/`, `ingest/`, `evals/`; `scripts/healthcheck.py`.
- Tests (`tests/`, 39 passing, no Docker needed): guard, settings, Ollama client (mock transport, retry, 4xx no-retry), Neo4j reader (fake driver, cap, timeout), schema verifier, and `test_module_boundaries.py` enforcing the dependency direction and admin-credential isolation.
- Finding: Neo4j Community has no read-only users, so read-only is enforced in code (masterplan section 11). Python 3.12 venv at `.venv`. `ruff --fix` applied (import style only).
- Not done: any live check. `docker compose config` validates; daemon was down, Ollama not running.

### 2026-11-15: Models chosen
- Owner chose a lighter chat model (Qwen 3.6, 8B-14B, tag TBD) and `qwen3-embedding:0.6b`. Recorded in masterplan sections 7, 8, 10.

### 2026-11-15: Schema accepted, model candidates proposed
- Owner accepted the discovered schema (masterplan section 9, decisions log). Plan to sanity-check it against the live DB in Phase 1.
- Added masterplan section 10: Ollama candidates (chat: Qwen 3.6 27B / Gemma 4 26B; embeddings: nomic-embed-text / EmbeddingGemma). Not decided; web-sourced, must be verified with `ollama pull` and evals.

### 2026-11-15: Q1 and Q4 decided
- Owner: users = teachers/curriculum designers; first release = prerequisite lookup, then expand to standard-to-standard connections and supporting components; tool layer in-process first. Recorded in `docs/masterplan.md` sections 1, 7, 8.

### 2026-11-15: Phase 0 discovery
- Read-only review of `~/LearningCommonsVisualization` (README, docs/PROGRESS.md, pocs/poc3/import_kg.py). Recorded labels, relationship types, counts, load method and indexes in `docs/masterplan.md` section 9 (unconfirmed against live DB; Neo4j and Docker were not running).
- `sysctl`: Apple M5 Pro, 24 GB RAM. `ollama list` failed (server not running). Found no embeddings or vector index yet in the source loader.
- Key finding: prerequisites are `buildsTowards` (StandardsFrameworkItem) and `hasDependency` (LessonGrouping); existing Neo4j runs with `NEO4J_AUTH: none`, so a read-only user must be added.

### 2026-11-15: Removed MAT scope
- Owner said MAT is not related to this project. Removed all MAT references (question-type candidate, old Q4, Phase 0 item) from `docs/masterplan.md` and `docs/progress.md`; renumbered Q5 to Q4. Also removed MAT from `docs/pre-plan.md` (section 1 candidate, old open question 4; renumbered Q5 to Q4) at owner's request.

### 2026-11-15: Masterplan and progress files created
- Read `docs/pre-plan.md` (Graph RAG over Learning Commons KG in Neo4j, local Ollama LLM, LangGraph deterministic workflow with bounded agentic Retrieve, Open WebUI, Langfuse, eval-gated).
- Created `docs/masterplan.md` (goal, success criteria, architecture, hard rules, repo layout, phases 0 to 6, open questions, decisions log) and this file.

### 2026-11-15: ECC installed
- `claude plugin marketplace add https://github.com/affaan-m/ECC --scope project`, `claude plugin install ecc@ecc --scope project`. Wrote `.claude/settings.json`.

### 2026-11-16: Phase 1 closed
- Qwen 3.6 has no 8B-14B Ollama tag (27b ~17 GB, 35b-a3b ~23 GB). Owner chose smaller non-3.6 Qwen: pulled `qwen3:14b` and `qwen3-embedding:0.6b`; set `OLLAMA_CHAT_MODEL=qwen3:14b` in `.env`/`.env.example`. Embedding dimension = 1024.
- `python -m scripts.healthcheck --deep`: 5/5 PASS. `make test`: 39 passed. Phase 1 exit met. Next: Phase 2.

### 2026-11-16: Status tracker page
- Built a multi-representation tracker (infrastructure flowchart, roadmap, sequence, modules, data states, 33-item checklist; green=done, blue=partial, orange=next, gray=not started). Stored at `docs/tracker.html` (open in a browser); published copy: https://claude.ai/artifact/MBUMTrxa3x2vmpzg6BZsrN. Update the checklist and bars in it whenever a phase moves.

### 2026-11-16: Tracker redesigned with shapes
- `docs/tracker.html` now uses color = entity, shape = kind of thing (data store, config, script, channel, value, decision, event) and border style + marker = status. Added a Key card and a Data-and-types flowchart. Logged in `docs/MultiReps.md`; published copy updated at the same URL.

### 2026-11-16: Tracker diagram refactor
- Fixed flowchart color (Mermaid `classDef` rejects `var()`; classes now defined with a harmless property and colored by page CSS). Split the single infrastructure flowchart into two: 1) foundation and ingest, 2) answering path. Verified rendering locally in Chrome (0 syntax errors).

### 2026-11-16: Modularity rule
- Owner asked that everything stay modular so new features are easy to add. Added a standing 'Design rule: everything is modular' section to the top of `CLAUDE.md` (outside the progress markers). Add-not-edit for new question types; Protocols; config-only models; per-module tests.

### 2026-11-16: Phase 2 ingest built, small labels embedded
- Added `ingest/` (`targets.py` table of labels and text properties, `store.py` admin Neo4j store behind an `IngestStore` Protocol, `pipeline.py` idempotent keyset-paginated embed loop, `validate.py`), `scripts/ingest.py` CLI (`--label`, `--limit`, `--validate-only`), `common/constants.py`, `IngestSettings`. 10 new tests; 49 total pass.
- Bookkeeping: one `_IngestMeta` node stores embedding model and dimension (1024). `kg_tools/schema.py` excludes it from counts. A different model or dimension in config is refused until a full re-embed.
- Live: 11 labels embedded (37,194 nodes in 505.7 s, about 74 per second), cosine vector indexes `emb_<Label>` ONLINE, full-text `kg_search` and unique constraints confirmed, `VALIDATION PASS`. Re-run embedded 0 nodes and passed (idempotent).
- Owner scope question (all labels or standards only): embedded all labels since the extra cost was under 9 minutes.
- In progress: `StandardsFrameworkItem` (276,729 nodes with text of 276,818) running in the background, about 1 to 1.5 hours. Phase 2 exit needs `python -m scripts.ingest --validate-only` to pass for all 12 labels.
- Tracker updated (13 of 33 done, 2 partial).

### 2026-11-17: Phase 2 complete
- `StandardsFrameworkItem` embedding finished (276,729 nodes in 6,008 s, 46 per second). `--validate-only` passes for all 12 labels (VALIDATION PASS), so the Phase 2 exit condition is met; earlier reruns embedded 0 nodes.
- Tracker updated (15 of 33 done, Phase 2 5/5, Phase 3 next). Note: run Python as `.venv/bin/python` (system `python` is not on PATH).

### 2026-11-17: Phase 3 complete (KG tool layer)
- Added `kg_tools/queries.py`, six parameterized files in `kg_tools/cypher/` and `kg_tools/tools.py` with `KGTools`: `search_nodes` (vector per label plus full-text, rank fusion), `get_node`, `find_standard_by_code`, `get_neighbors`, `get_prerequisites`. All results carry node IDs, are capped, and fail closed on bad input. No existing module was edited (add, don't edit).
- Verified on the live data: `buildsTowards` runs prerequisite to later standard (source grade earlier in 354 edges, later in 16, equal in 387). Statement codes repeat across jurisdictions; many standards have no code.
- Tests: 73 unit (24 new, fakes) and 4 live pass; ruff clean. Exit criterion (tested on mocked and real Neo4j) met.
- Open for owner: direction of `hasDependency` on LessonGrouping (no tool yet) and how Resolve should pick a jurisdiction.

### 2026-11-21: Git, GitHub push, and Neo4j dump for the DGX Spark move
- Owner ran `git init`. `.gitignore` audited (the real admin password is in no trackable file) and extended (OS/editor files, tooling caches, `.env.*` except `.env.example`, `*.pem`, `*.key`). First commit `b9f4993` (51 files) via `ecc:prp-commit`, then `77056d6`. Pushed to https://github.com/yunwesth/LCKG_RAG (`master`). The first push got 403 because the stored credential was another account; fixed with `gh auth login` as `yunwesth` plus `gh auth setup-git`.
- Decision (owner): move to a DGX Spark (aarch64, 128 GB unified memory) and use vLLM instead of Ollama. Not started. Add a vLLM client behind the existing Protocols (config only). Embeddings: keep Ollama `qwen3-embedding:0.6b`, or re-embed everything (~100 min) if switching, because a different embedder may hurt search quality; `_IngestMeta` refuses a silent change.
- Neo4j dump made for the move: local `lcrag-neo4j` (Neo4j 5.26.33, arm64 image `neo4j:5-community`) was stopped, dumped with `neo4j-admin database dump neo4j` through a throwaway container, and restarted (healthy). File: `~/lcrag-dump/neo4j.dump` (2.9 GB, 539 files, 18 s), SHA-256 `b506afd605b4b5634b962774a0732b799a1fdb2f2e770b76a65ecf46bb848aed` (also in `~/lcrag-dump/neo4j.dump.sha256`). `kg-neo4j` (the other project) was not touched. The dump is NOT in git.
- To restore on the Spark: `scp` the dump, compare the SHA-256, `docker compose up -d neo4j` once to create the volume, stop it, then `docker run --rm -v <data>:/data -v <dump dir>:/dump neo4j:5-community neo4j-admin database load neo4j --from-path=/dump --overwrite-destination=true`, start it again, then run `make test`, `python -m scripts.healthcheck --deep` and `python -m scripts.ingest --validate-only` (expect 315,434 nodes, 551,058 rels, VALIDATION PASS). Create a new `.env` on the server (new admin password); `.env` is not in git.
- Note: `docker-compose.yml` uses the unpinned tag `neo4j:5-community`; consider pinning to 5.26.x so server and dump match.

### 2026-11-22: Decision, finish Phase 4 on the Mac and move to the Spark afterwards
- Owner preference: complete the build first, move later. Done on the Spark so far: repo cloned (renamed `LCKG-RAG`), Claude Code installed, `neo4j.dump` copied and verified (`neo4j.dump: OK`). Not done there: `.env`, Python env, restore. This Mac's `origin` now points to `https://github.com/yunwesth/LCKG-RAG.git`.
- Why it is safe to wait: the Phase 4 orchestrator only reads Neo4j, so the dump stays valid. Re-dump only if ingest writes again or the embedder changes.
- vLLM plan: a self-hosted vLLM server on the Spark exposes an OpenAI-compatible API. Add a client in `common/` behind the existing Protocol and change only `.env`. During Phase 4, run one vLLM smoke test (Qwen3 thinking mode, JSON output, streaming) on the Spark. Embedder stays Ollama `qwen3-embedding:0.6b` unless the owner chooses a full re-embed (~100 min).
- Next: investigate the `hasDependency` direction on the live data (read-only); the jurisdiction policy still needs the owner.

## 2026-11-22: Phase 4 orchestrator built (not yet committed)
- Jurisdiction policy decided by owner: ask the user. `hasDependency` direction confirmed (dependent -> prerequisite).
- Added `orchestrator/` pipeline (Understand, Resolve, Retrieve, Synthesize, Verify on LangGraph), OpenAI-compatible API (`orchestrator/api.py`, `scripts/serve.py`), CLI (`scripts/ask.py`), kg_tools `get_lesson_prerequisites` and `list_jurisdictions`, tests `tests/test_orchestrator.py` and `tests/test_orchestrator_api.py`.
- Live check on Ollama `qwen3:14b`: clarification turn works; `5.NF.B.5` (Multi-State) returns a cited prerequisite list. Lessons: a bare list of `[n]` citations came back until the prompt fixed a bullet format, so Verify now rejects replies with no real prose.
- Remaining: eval set and Langfuse (Phase 5), timeout enforcement, Open WebUI (Phase 6), vLLM smoke test on the Spark.
- Tracker (`docs/tracker.html`) updated: 24/33 done, 1 partly done (FastAPI endpoint verified with fakes only, not by live curl); Phase 4 bar 6/7.

## 2026-11-23: Phase 4 committed, API verified with curl
- Pushed `5b31e26` (orchestrator code) and `f8bb922` (docs). `make test`: 95 passed.
- Ran `python -m scripts.serve` and checked with curl: `/healthz`, `/v1/models`, non-stream answer (status answered, 7 citations), SSE stream (Korean clarify question reassembled into chunks), 422 for an empty messages list. Tracker updated to 25/33, Phase 4 7/7.
- Open: Synthesize prints the literal `CODE:` from its prompt template in bullets; `total_timeout_s` not enforced; `lookup` intent only lightly tested.

## 2026-11-23: Review fixes applied (not committed)
- Ran `ecc:python-reviewer` and `ecc:fastapi-reviewer`; owner chose to fix everything. Changes: stricter Verify (unclosed think, URLs, ungrounded codes, grouped citations), prompt hardening (defang, no forged assistant turns, last 2 user turns, no literal `CODE:`), Resolve requires the jurisdiction in the user's words, `Pipeline` timeout/closers/ready, API limits, error shape, concurrency gate, keepalive SSE, optional Bearer key, `/readyz`, `ORCH_*` settings.
- 123 tests pass, ruff clean, live `scripts.ask` verified. Next: re-run curl against `scripts.serve`, then commit.

## 2026-11-23: Phase 5 started (eval harness, uncommitted)
- Built the eval runner, scoring, gate and candidate builder; 38 candidate cases drafted from the graph, none reviewed yet, no baseline written (owner must review first).
- First live run with `OLLAMA_THINK=false`: all gated metrics 1.0, `cites_target_rate` 0.76, latency p50 7 s / p95 21 s. With thinking on, p50 was 28 s and some questions hit the 120 s total timeout.
- Open: owner review of candidates, baseline, Langfuse spans, prompt change so the answer always cites the target [1].
- Candidate set now 51 cases (concept, lesson, lookup, variant added). All gated metrics 1.0; `cites_target_rate` 0.65; latency p50 6.7 s. Still no baseline: waiting for owner review.
- Synthesize prompt fix: `cites_target_rate` 0.65 -> 1.0 on the 34 target cases (single run, `OLLAMA_THINK=false`). Added `scripts.run_evals --kinds`.
- Owner approved 51 cases; baseline saved (all gated metrics 1.0, p50 7.4 s); re-run identical. `cites_target_rate` added to the gate. Next: Langfuse spans.
- Journal sync before compaction: Phase 4 marked done; Phase 5 left = Langfuse tracing only.


## 2026-11-23 (evening) — Phase 5 Langfuse tracing
- Added `docker-compose.langfuse.yml` (self-hosted Langfuse v4, UI :3100, secrets from `.env`, project and keys auto-provisioned), `common/tracing.py`, `Tracer` Protocol, `LangfuseSettings`, `orchestrator/tracing.py`, `Pipeline(tracer=)`. One span per pipeline, node, LLM call and tool call; no-op without keys; `LANGFUSE_CAPTURE_CONTENT=false` for privacy. Verified live (parents correct) and with 17 unit tests. Phase 5 done; Phase 6 next.

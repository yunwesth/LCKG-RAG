# LearningCommonsRAG

Graph RAG over the Learning Commons Knowledge Graph (Neo4j) with a local Ollama LLM.
Read first: `docs/masterplan.md` (goal, phases, rules) and `docs/pre-plan.md` (source brief).
**Detailed progress is logged in `docs/progress.md`: append an entry there every time progress is made.** Never fill in a TBD without owner confirmation.

## Design rule: everything is modular (owner requirement, 2026-11-16)
Adding a new feature must be easy and must not mean rewriting existing code.
- Add, don't edit: a new question type is a new `kg_tools/cypher/*.cypher` file, a new typed tool, a new Understand intent and new eval cases. It must not change Retrieve, Synthesize, Verify, the Cypher guard or the other tools.
- Respect the dependency direction in masterplan section 11 (`tests/test_module_boundaries.py` enforces it). New code goes in the package that owns that job.
- Depend on the Protocols in `common/protocols.py`, never on another module's concrete class, so each module is testable with fakes and swappable.
- Model names, limits, URLs and credentials come from config (`.env`), never from code.
- Every new module or tool ships with its own unit test, and a new tool also updates the eval set (hard rule 4).
- Before building anything, ask: can this be added without touching existing modules? If not, redesign first and raise it with the owner.

<!-- PROGRESS:START -->
## Progress log

### Current state
Phase 0 done (schema accepted; chat = `qwen3:14b` (Qwen 3.6 has no small tag), embeddings = `qwen3-embedding:0.6b`). Phase 1 COMPLETE and fully live-verified (all 5 deep health checks pass, incl. Ollama): Neo4j `lcrag-neo4j` on bolt 7688 holds the full KG (315,434 nodes / 551,058 rels); `python -m scripts.healthcheck --deep` passes connection, read-only guard and schema. Modules: `common/` (settings, errors, protocols, ollama_client), `kg_tools/` (cypher_guard, neo4j_client, schema), stubs for `orchestrator/ ingest/ evals/`. 49 tests pass (`make test`). Phase 2 COMPLETE (2026-11-17): `ingest/` (targets, store, pipeline, validate) + `python -m scripts.ingest`; all 12 labels embedded (dim 1024, cosine vector indexes `emb_<Label>` ONLINE), `python -m scripts.ingest --validate-only` = VALIDATION PASS (standards 276,729/276,729). Phase 3 COMPLETE (2026-11-17): `kg_tools/queries.py` + 6 files in `kg_tools/cypher/` + `kg_tools/tools.py` (`KGTools`: `search_nodes` hybrid vector+full-text, `get_node`, `find_standard_by_code`, `get_neighbors`, `get_prerequisites`); 73 unit tests + 4 live tests (`pytest -m live`) pass. Phase 4 BUILT (2026-11-22, uncommitted until the owner says so): `orchestrator/` LangGraph pipeline (Understand, Resolve, Retrieve, Synthesize, Verify), CLI `scripts/ask.py`, API `scripts/serve.py`, 2 new kg_tools (`get_lesson_prerequisites`, `list_jurisdictions`); live-verified on Ollama; tracker 24/33. Phase 5 (evals, Langfuse) is next. ECC plugin (`ecc@ecc` v2.2.3) installed at project scope. Details in `docs/progress.md`.

### Next steps
- [x] Ollama up; pulled `qwen3-embedding:0.6b` (dim 1024) and `qwen3:14b` (chat). `.env` and `.env.example` updated.
- [x] Phase 2: all 12 labels embedded, validation PASS, tracker updated (15/33 done).
- [x] Phase 3: KG tool layer done and tested (tracker 18/33).
- [~] Phase 4: orchestrator BUILT and live-verified on Ollama (2026-11-22): `orchestrator/{state,understand,resolve,retrieve,synthesize,verify,graph,api,wiring,messages,ports}.py`, `scripts/ask.py` (CLI), `scripts/serve.py` (FastAPI `/v1/chat/completions`, SSE). Jurisdiction policy DECIDED (owner): ask the user. Left: fuller eval of answer quality (Phase 5), Langfuse spans, total-timeout enforcement, Open WebUI wiring (Phase 6), hard test of `lookup` intent.
- [ ] DGX Spark move is DEFERRED until after Phase 4 (owner preference, 2026-11-22): build Phase 4 on the Mac against Ollama; the orchestrator must reach the LLM only through the `common/protocols.py` Protocols. On the Spark later: `.env` with a new password, restore the dump, venv + `make test`, live tests, start a self-hosted vLLM server and switch the base URL. Do one vLLM smoke test (Qwen3 thinking mode, JSON output, streaming) during Phase 4. Embedder: keep Ollama `qwen3-embedding:0.6b` (simplest) or re-embed everything (~100 min)..
- [ ] View the published tracker artifact to confirm colors; keep `docs/tracker.html` in sync with `docs/progress.md`
- [ ] Restart Claude Code; verify `/plugin list`; optionally `/plugin configure ecc@ecc`

### Gotchas / blockers
- Never fill a TBD without owner confirmation.
- Marketplace `ecc` is user-global; adding it repointed it from `~/LearningCommonsVisualization/ECC` to the git URL. Don't also run ECC `install.sh --profile full`.
- Port clash: the KG project's `kg-neo4j` holds 7687/7474, so this project uses 7688/7475. Leave `kg-neo4j` untouched.
- Neo4j Community has no read-only users, so read-only is enforced in code (`execute_read` plus the Cypher guard). `Neo4jReader` must use `@unit_of_work(timeout=...)`, not `neo4j.Query`, in managed transactions (fake-driver tests can't catch this).
- `.env` is git-ignored and holds the generated admin password. `tests/test_module_boundaries.py` enforces dependency direction and admin-credential isolation.
- `buildsTowards` direction CONFIRMED: `(prerequisite)-[:buildsTowards]->(later)` (source grade earlier in 354 edges, later in 16, equal in 387). `hasDependency` direction CONFIRMED 2026-11-22 (read-only check on live data): `(dependent/later)-[:hasDependency]->(prerequisite)`, the OPPOSITE of `buildsTowards` (269 LessonGrouping->LessonGrouping edges; target in an earlier grade in 46, later in 0, same grade in 44; Course-[:hasPart]->LessonGrouping). Statement codes repeat across jurisdictions (e.g. `HSS-ID.C.7` matches >10 nodes), so Resolve needs a jurisdiction. `find_standard_by_code` takes one. Many standards have no `statementCode`.
- Tests that read env: run `make test` without sourcing `.env` (sourcing it breaks `test_settings`); live tests need `set -a; . ./.env; set +a`.
- KG prerequisites are `buildsTowards` (StandardsFrameworkItem) and `hasDependency` (LessonGrouping). MAT is out of scope.

### Session history (newest first)
#### 2026-11-23 (later) — Multirep page recolored by shape kind, split per phase
- `docs/phases-1-to-4.html` (artifact https://claude.ai/artifact/Xx19Yv5qW5kCdZtKTWNC9z) is now at v4. Owner feedback: all-grey diagrams hurt readability. Cause: colors injected by script did not apply because the published page renders Mermaid itself; fix = `classDef`/style written directly in each flowchart. v2 colored by phase; owner clarified (rolled back) they wanted color by SHAPE KIND: component=rect blue, data store=cylinder green, config=hexagon orange, channel/API=parallelogram teal, script/function=double box purple, value/message=stadium grey, decision=diamond rose, state/event=circle/flag amber. Phase boxes are neutral grey. v4 adds four separate per-phase diagrams (P1 foundation, P2 ingest, P3 tools + cypher files, P4 orchestrator) after the big map; the map and roadmap stay as overview. The local HTML omits the Mermaid script, so it shows code if opened locally. Rendered page still NOT visually checked.
- Q&A only: explained `.cypher` = text file holding a Neo4j Cypher query (e.g. `kg_tools/cypher/get_lesson_prerequisites.cypher`). No code changes; Phase 4 (about 23 files) is still uncommitted, waiting for the owner to say commit.
#### 2026-11-23 — Phases 1-4 multirep page
- Added `docs/phases-1-to-4.html` (9 views: shape key, dependency map, roadmap, data/types, Resolve decisions, sequence, inventory, analogy, worked example) and logged it in `docs/MultiReps.md`. Published: https://claude.ai/artifact/Xx19Yv5qW5kCdZtKTWNC9z (rendered page not visually checked). Phase 4 is still uncommitted.
#### 2026-11-23 — Phase 4 recap, tracker sync, compaction (no new code)
- Explained Phase 4 to the owner (Korean). Clarified: the LLM stays on Ollama `qwen3:14b`; `orchestrator/api.py` is only the entry point for Open WebUI/curl; vLLM later means swapping only the `common/` client.
- `docs/tracker.html` is at 24/33 done, 1 partial (Phase 4 is 6/7; the FastAPI endpoint is partial because it was tested with fakes only, not curl against a running `scripts.serve`).
- `/ecc:strategic-compact` advised committing before compacting. Phase 4 (about 23 files) is STILL UNCOMMITTED; commit only when the owner asks. Not done: curl test of `scripts.serve`, total-timeout enforcement, a hard test of the `lookup` intent.
#### 2026-11-22 (night 2) — Phase 4 orchestrator built
- Owner chose jurisdiction policy 1: when a code exists in several jurisdictions and the user named none, Resolve asks which (Korean/English by conversation). Stated jurisdiction is validated against `KGTools.list_jurisdictions()`; an explicit code is never replaced by a topic search (found live: Texas has no `8.EE.C.8`).
- New kg_tools: `get_lesson_prerequisites` (+ `get_lesson_prerequisites.cypher`, direction dependent->prerequisite), `list_jurisdictions`. Pipeline: Understand (LLM, JSON schema) -> Resolve -> Retrieve (depth 3, 15 items) -> Synthesize (LLM sees numbered evidence, cites [n]) -> Verify (fail-closed: needs citations that exist and real prose). Streaming only chunks the verified reply.
- Live: `python -m scripts.ask "5.NF.B.5 를 배우기 전에 뭘 알아야 해?" "Multi-State"` gives a cited answer. Needs `ollama serve` running (it was off; pipeline refused safely). `make test` 100+ pass, ruff clean. Not committed yet.
#### 2026-11-22 (night) — hasDependency direction confirmed
- Read-only Cypher on `lcrag-neo4j`: `hasDependency` points from the dependent (later) LessonGrouping to its prerequisite, opposite of `buildsTowards`. Tools must flip direction per relationship type. Remaining Phase 4 blocker: jurisdiction policy (owner).
#### 2026-11-22 (late) — Journal sync, decision commit pushed
- Session was mostly discussion; no code changes. Facts: Neo4j data dir 5.8 GB, dump 2.9 GB (Spark needs ~3 GB file + ~6 GB restored DB); dump + sha256 copied to the Spark by scp and verified (`neo4j.dump: OK`). Step A on the Spark (`.env` with new password, restore dump) was given to the owner but not confirmed done; owner then chose to finish Phase 4 on the Mac first.
- Decision commit `1b8e6f3` (CLAUDE.md, docs/progress.md, AGENTS.md) is pushed to `origin/master` (github.com/yunwesth/LCKG-RAG); working tree clean. Gotcha: `scp` target must have no space (`user@host:~/`).
- Next: read-only investigation of `hasDependency` direction on the live Neo4j, then Phase 4.
#### 2026-11-22 — Decision: finish Phase 4 on the Mac, move to the Spark afterwards
- Owner prefers to complete the build first and move later. Agreed: the Phase 4 orchestrator only reads Neo4j, so the dump already on the Spark (`~/neo4j.dump`, checksum OK, repo cloned as `LCKG-RAG`, Claude Code installed) stays valid; re-dump only if ingest writes again. This Mac's `origin` now points to `https://github.com/yunwesth/LCKG-RAG.git`.
- vLLM plan: self-hosted vLLM on the Spark serves an OpenAI-compatible API; add a client in `common/` behind the existing Protocol and change only `.env`. Test thinking mode, JSON output and streaming once on the Spark during Phase 4. Not committed yet: this CLAUDE.md edit.
- Immediate next step: investigate the `hasDependency` direction on the live Neo4j data (read-only); the jurisdiction policy still needs the owner.
#### 2026-11-21 (evening) — DGX Spark move in progress
- Move to DGX Spark is underway (step by step). Repo cloned on the Spark and renamed `LCKG-RAG`; Claude Code installed there. Local Neo4j dump created, copied to the Spark and verified (`neo4j.dump: OK`, checksum). `.gitignore` and `docs/progress.md` edited; logged in commit `58cb19f` "docs: log neo4j dump and dgx spark move plan".
- Next on the Spark: (A) create `.env` with a NEW password, restore the dump with `neo4j-admin database load`, set up the Python env, run `make test`, then the live tests. Then decide the vLLM client and embedder question (see the entry below) before Phase 4.
#### 2026-11-21 — First git commit, .gitignore audit, move-to-server plan
- Owner ran `git init`; I audited `.gitignore` (core entries fine; real admin password appears in no trackable file) and added: `.DS_Store`, `.idea/`, `.vscode/`, `.mypy_cache/`, `.coverage`, `htmlcov/`, `dist/`, `build/`, `.env.*` with `!.env.example`, `*.pem`, `*.key`.
- Committed via `ecc:prp-commit`: `b9f4993` "feat: add graph rag foundation, embedding ingest and kg tool layer" (51 files, branch `master`, no remote yet).
- Plan discussed (not started): move to an SSH server and use vLLM instead of Ollama. Add a vLLM client behind the existing Protocols (config only). Keep embeddings on Ollama `qwen3-embedding:0.6b` or fully re-embed (~100 min): vectors from a different embedder may hurt search quality. Move Neo4j with `neo4j-admin database dump/restore`, never through git. Decide before Phase 4.
#### 2026-11-17 22:13 — Diagram links, vector count, Phase 3 wrap-up, status summary
- Session (09:02-22:13): checked embedding status; linked the tracker diagram from `docs/masterplan.md` and `docs/progress.md`; answered the vector-store question (the DB is Neo4j; vectors live in the 12 `emb_<Label>` cosine indexes, dim 1024); built Phase 3; gave an "everything done" summary.
- Only file edited in the final stretch: `tests/test_kg_tools_live.py` (1-line fix to a live test). No new decisions. Phase 4 is still blocked on the two owner questions in Gotchas (`hasDependency` direction, jurisdiction policy).
#### 2026-11-17 — Phase 3 KG tool layer
- New: `kg_tools/queries.py` (`load_query`), `kg_tools/cypher/{get_node,find_by_code,search_fulltext,search_vector,get_neighbors,get_prerequisites}.cypher`, `kg_tools/tools.py` (pydantic results, every item has `id`; limits fetch limit+1 to report `truncated`; depth 1..6; rel type and direction validated; Lucene text escaped; search fuses ranks (RRF) because index scores are not comparable). Tools depend on `GraphReader`/`Embedder` Protocols only.
- Tests: `tests/test_kg_tools.py` (24, fakes; also checks every .cypher passes the guard and `SEARCHABLE_LABELS` == `ingest.targets`), `tests/test_kg_tools_live.py` (4, real Neo4j + Ollama). Live search ~0.13 s; ruff clean.
- Tracker 18/33, republished; `AGENTS.md` and `docs/progress.md` synced.
#### 2026-11-17 — Phase 2 closed
- Standards embedding finished in background: 276,729 nodes in 6,008 s (46/s). `set -a; . ./.env; set +a; .venv/bin/python -m scripts.ingest --validate-only` → VALIDATION PASS for all 12 labels (system `python` is not on PATH; use `.venv/bin/python`).
- `docs/tracker.html` updated: Phase 2 5/5, 15/33 done, 0 partial, Phase 3 marked next. `docs/progress.md` and `AGENTS.md` synced. Published tracker copy not yet republished.
#### 2026-11-16 21:00 — Docs/tracker sync, embedding status check
- Owner asked to update all md files and the tracker, and whether embedding is done. Answer: NO. 11 small labels done and validated; `StandardsFrameworkItem` was at ~11,328 / 276,729 (~4%) at 20:58, still RUNNING in background (log: session scratchpad `ingest-standards.log`), ETA ~1-1.5 h at 40-70 nodes/s. If interrupted, rerun `python -m scripts.ingest --label StandardsFrameworkItem` (resumable), then `--validate-only`.
- Tracker artifact watch connection dropped (MBUMTrxa3x2vmpzg6BZsrN); no code changes in this entry.
#### 2026-11-16 17:00 — Phase 2 ingest built
- New: `common/constants.py` (`_IngestMeta` label, `embedding` prop), `IngestSettings` in `common/settings.py` (`INGEST_BATCH_SIZE`, `INGEST_MAX_CHARS`), `ingest/{targets,store,pipeline,validate}.py`, `scripts/ingest.py`, `tests/test_ingest.py` (10 tests, fakes). `kg_tools/schema.py` now ignores the `_IngestMeta` node so the 315,434-node check still holds.
- Adding a label to embed = one row in `ingest/targets.py`. Model + dim recorded once in `_IngestMeta`; a config change is refused (needs full re-embed).
- Owner scope question answered by doing all labels (small ones took 8.4 min at ~74/s). Standards run started in background (log in scratchpad); sample rate 40-70/s.
- Gotchas fixed: `SHOW CONSTRAINTS` cannot be followed by `UNWIND`; Neo4j reports similarity as `COSINE`; driver `notifications_min_severity="OFF"` silences first-run warnings.
- `docs/tracker.html` updated (Phase 2 3/5 done); `AGENTS.md` re-synced from this file.
#### 2026-11-16 15:35 — Journal sync (no code changes)
- Session transcript held no new work beyond the 15:30 entry below (tracker colors, flowchart split, modularity rule). State unchanged: Phase 1 done, Phase 2 (ingest and indexes) is next. Published tracker still not visually checked.
#### 2026-11-16 15:30 — Tracker colors/flowchart split, modularity rule
- `docs/tracker.html`: fixed Mermaid "Syntax error" (`classDef` can't take `var(--…)`; colors now written per node, pastel fill + stronger outline, dark text in both themes). Split the infra flowchart into two (Foundation and ingest; answering path), no crossing lines. Published copy v5: https://claude.ai/artifact/MBUMTrxa3x2vmpzg6BZsrN (local verified in Chrome; published page NOT visually checked).
- Added the "Design rule: everything is modular" section to this file (above the markers) and logged it in `docs/progress.md`.
- Scope answer: first release = prerequisite lookup (`buildsTowards` 757 edges, `hasDependency` 269 edges).
#### 2026-11-16 — Status tracker
- Added `docs/tracker.html` (v2: color = entity, shape = kind, border = status; logged in `docs/MultiReps.md`): diagrams + 33-item checklist (10 done). Keep it in sync when a phase moves; published copy https://claude.ai/artifact/MBUMTrxa3x2vmpzg6BZsrN.
#### 2026-11-16 — Phase 1 closed
- Qwen 3.6 has NO 8B-14B tag on Ollama (only 27b/35b-a3b; verified on ollama.com/library/qwen3.6/tags). Owner chose a smaller non-3.6 Qwen: `qwen3:14b` (9.3 GB). Embedding dim verified 1024. Started `ollama serve`; `make health` deep all PASS; 39 tests pass.
#### 2026-11-15 — Masterplan, Phase 0, Phase 1 build and live verify
- Created `docs/masterplan.md` and `docs/progress.md`; removed MAT from them and from `docs/pre-plan.md`. Decided Q1 and Q4 (teachers and curriculum designers; first release is prerequisite lookup).
- Phase 0 discovery from `~/LearningCommonsVisualization`; owner accepted the schema; chose the lighter Qwen chat model and the Qwen embedding model.
- Phase 1: pyproject, `.env.example`, Makefile, docker-compose, `common/`, `kg_tools/`, `scripts/healthcheck.py`, 6 test files. Live: started Docker, ran `import_kg.py` against bolt 7688 (46.5 s), fixed the `Neo4jReader` managed-transaction bug; deep healthcheck passed except Ollama.
#### 2026-11-15 — Install ECC
- `claude plugin marketplace add https://github.com/affaan-m/ECC --scope project`; `claude plugin install ecc@ecc --scope project` → wrote `.claude/settings.json`.
<!-- PROGRESS:END -->

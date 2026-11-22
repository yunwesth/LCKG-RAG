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
Phase 0 done (schema accepted; chat = `qwen3:14b` (Qwen 3.6 has no small tag), embeddings = `qwen3-embedding:0.6b`). Phase 1 COMPLETE and fully live-verified (all 5 deep health checks pass, incl. Ollama): Neo4j `lcrag-neo4j` on bolt 7688 holds the full KG (315,434 nodes / 551,058 rels); `python -m scripts.healthcheck --deep` passes connection, read-only guard and schema. Modules: `common/` (settings, errors, protocols, ollama_client), `kg_tools/` (cypher_guard, neo4j_client, schema), stubs for `orchestrator/ ingest/ evals/`. 49 tests pass (`make test`). Phase 2 COMPLETE (2026-11-17): `ingest/` (targets, store, pipeline, validate) + `python -m scripts.ingest`; all 12 labels embedded (dim 1024, cosine vector indexes `emb_<Label>` ONLINE), `python -m scripts.ingest --validate-only` = VALIDATION PASS (standards 276,729/276,729). Phase 3 COMPLETE (2026-11-17): `kg_tools/queries.py` + 6 files in `kg_tools/cypher/` + `kg_tools/tools.py` (`KGTools`: `search_nodes` hybrid vector+full-text, `get_node`, `find_standard_by_code`, `get_neighbors`, `get_prerequisites`); 73 unit tests + 4 live tests (`pytest -m live`) pass. Phase 4 (orchestrator) is next. ECC plugin (`ecc@ecc` v2.2.3) installed at project scope. Details in `docs/progress.md`.

### Next steps
- [x] Ollama up; pulled `qwen3-embedding:0.6b` (dim 1024) and `qwen3:14b` (chat). `.env` and `.env.example` updated.
- [x] Phase 2: all 12 labels embedded, validation PASS, tracker updated (15/33 done).
- [x] Phase 3: KG tool layer done and tested (tracker 18/33).
- [ ] Phase 4: orchestrator (LangGraph Understand, Resolve, Retrieve, Synthesize, Verify; FastAPI `/v1/chat/completions` with SSE). Needs owner answers: `hasDependency` direction on LessonGrouping and a jurisdiction policy (see Gotchas).
- [ ] DGX Spark move is DEFERRED until after Phase 4 (owner preference, 2026-11-22): build Phase 4 on the Mac against Ollama; the orchestrator must reach the LLM only through the `common/protocols.py` Protocols. On the Spark later: `.env` with a new password, restore the dump, venv + `make test`, live tests, start a self-hosted vLLM server and switch the base URL. Do one vLLM smoke test (Qwen3 thinking mode, JSON output, streaming) during Phase 4. Embedder: keep Ollama `qwen3-embedding:0.6b` (simplest) or re-embed everything (~100 min)..
- [ ] View the published tracker artifact to confirm colors; keep `docs/tracker.html` in sync with `docs/progress.md`
- [ ] Restart Claude Code; verify `/plugin list`; optionally `/plugin configure ecc@ecc`

### Gotchas / blockers
- Never fill a TBD without owner confirmation.
- Marketplace `ecc` is user-global; adding it repointed it from `~/LearningCommonsVisualization/ECC` to the git URL. Don't also run ECC `install.sh --profile full`.
- Port clash: the KG project's `kg-neo4j` holds 7687/7474, so this project uses 7688/7475. Leave `kg-neo4j` untouched.
- Neo4j Community has no read-only users, so read-only is enforced in code (`execute_read` plus the Cypher guard). `Neo4jReader` must use `@unit_of_work(timeout=...)`, not `neo4j.Query`, in managed transactions (fake-driver tests can't catch this).
- `.env` is git-ignored and holds the generated admin password. `tests/test_module_boundaries.py` enforces dependency direction and admin-credential isolation.
- `buildsTowards` direction CONFIRMED: `(prerequisite)-[:buildsTowards]->(later)` (source grade earlier in 354 edges, later in 16, equal in 387). `hasDependency` (LessonGrouping) direction NOT yet checked, so it has no tool; ask owner. Statement codes repeat across jurisdictions (e.g. `HSS-ID.C.7` matches >10 nodes), so Resolve needs a jurisdiction. `find_standard_by_code` takes one. Many standards have no `statementCode`.
- Tests that read env: run `make test` without sourcing `.env` (sourcing it breaks `test_settings`); live tests need `set -a; . ./.env; set +a`.
- KG prerequisites are `buildsTowards` (StandardsFrameworkItem) and `hasDependency` (LessonGrouping). MAT is out of scope.

### Session history (newest first)
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

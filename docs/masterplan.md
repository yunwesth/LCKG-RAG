# Masterplan: Learning Commons Graph RAG

Source: `docs/pre-plan.md` (architecture brief v0.1). This is the single source of truth for goal, scope, phases and decisions. Progress is logged in `docs/progress.md`.
Rule: items marked **TBD** are undecided. Do not invent them. Ask the owner or leave a marked stub. Resolve a TBD only with owner confirmation, then record it in section 8.

## 1. Target goal

A production-grade RAG system whose primary knowledge source is the **Learning Commons Knowledge Graph (KG)** in **Neo4j**. A **local LLM (Ollama)** answers natural-language questions by retrieving evidence from the KG through typed, read-only tools. **Every answer is grounded in retrieved nodes and cites node IDs.** If the KG has no support, the system says so (fail closed).

Primary users: **teachers and curriculum designers** (decided 2026-11-15). First-release question type: **prerequisite lookup**. Planned expansion, in later releases: standard-to-standard connections, then supporting components (learning components, activities, misconceptions). Tools, eval set and UI are scoped to prerequisite lookup first, with the tool and eval design kept extensible.

## 2. Success criteria

- Answers cite node IDs; every claim maps to a retrieved node (grounding rate tracked).
- Streams to Open WebUI via an OpenAI-compatible `/v1/chat/completions`.
- Eval set (about 20 to 50 questions per question type) with a regression gate: no change to model, prompt or retrieval may drop below the previous baseline.
- Every request produces a Langfuse trace (one span per LangGraph node and per tool call).
- Local-first: no external LLM API calls by default. Reproducible via Docker Compose (Ollama stays on the host).

## 3. Architecture summary

```
User -> Open WebUI -> Orchestrator (FastAPI + LangGraph)
  Understand -> Resolve -> Retrieve -> Synthesize(+Verify)
     |  Ollama /api/chat        |  KG tool layer (typed, read-only)
     v                          v
   Ollama (host)            Neo4j (vector + full-text indexes) <-- Ingest <-- KG source files
Orchestrator --traces--> Langfuse      Eval runner --> Orchestrator (eval_set.jsonl)
```

Orchestration is a **deterministic workflow with a bounded agentic step**, not a free agent:

| Node | Style |
|---|---|
| Understand | Deterministic: one LLM call, JSON-schema output (intent, entities) |
| Resolve | Deterministic: entity text to KG node IDs (vector + full-text) |
| Retrieve | Fixed tool plan per intent by default. Optional agentic loop capped by `MAX_TOOL_STEPS` (default 4) and a timeout, enabled only if evals show multi-step failures |
| Synthesize | Deterministic: answer only from retrieved context, cite node IDs, stream |
| Verify | Deterministic: claims must map to retrieved nodes. Regenerate once, then fall back to "not found in the KG" |

Retrieval is hybrid: vector search finds entry points, full-text handles exact names and codes, graph traversal does relational reasoning. The LLM never writes Cypher in the default path.

## 4. Hard rules (from the brief)

1. No LLM-generated Cypher by default. All Cypher is parameterized and lives in `kg_tools/cypher/`.
2. Every LangGraph node has typed Pydantic input/output state and a unit test with mocked LLM and Neo4j.
3. Any LLM decision that gates control flow uses JSON-schema-constrained output.
4. Keep 3 to 5 tools with short, precise docstrings. Adding a tool requires updating the eval set.
5. Never hardcode the embedding model: read from config and record model name and dimension in Neo4j metadata.
6. Fail closed on empty retrieval or failed verification.
7. Do not fill in any TBD without confirmation.
8. Security: read-only Neo4j access (enforced in code, see section 11), parameterized queries, KG content and user input treated as data (prompt-injection defense), no secrets in code, config via env vars.
9. Hard caps and resilience: `MAX_TOOL_STEPS`, per-step and total timeouts, per-query timeout and result-size cap, retry with backoff for Ollama/Neo4j.

## 5. Components and target repo layout

```
.
├── docker-compose.yml      # orchestrator, Neo4j, Langfuse, Open WebUI
├── .env.example
├── orchestrator/           # app.py, graph.py, nodes/{understand,resolve,retrieve,synthesize,verify}.py, llm.py, tracing.py
├── kg_tools/               # tools.py, cypher/*.cypher, neo4j_client.py
├── ingest/ingest.py        # idempotent (MERGE), embeddings, indexes, validation
├── evals/                  # eval_set.jsonl, run_evals.py
└── docs/                   # pre-plan.md, masterplan.md, progress.md, architecture.md
```

Provisional tools (finalize after question types are chosen): `search_nodes`, `get_node`, `get_neighbors`, `get_prerequisites` (the last depends on real relationship types, **TBD**).

## 6. Phases

Each phase ends with its exit criteria met and a `docs/progress.md` entry.

**Phase 0: Decisions and discovery (blocks everything else)**
- Owner picks the first-release users and 1 to 2 question types (Q1).
- Run in Neo4j Browser and record output in section 8: `MATCH (n) RETURN count(n); CALL db.labels(); CALL db.relationshipTypes();` plus properties per label (Q2).
- Confirm how the existing data was loaded (embed-in-place vs reload).
- Confirm Mac chip and RAM, then choose Ollama chat and embedding models (Q3).
- Decide tool layer in-process vs HTTP (Q4).
- Exit: all four open questions answered and recorded.

**Phase 1: Foundation**
- Repo skeleton per section 5, `.env.example`, config module, Docker Compose with Neo4j (and Langfuse, Open WebUI stubs).
- Read-only Neo4j access (in-code, see section 11). `neo4j_client.py` with timeouts.
- Exit: `docker compose up` brings up services. Neo4j reachable from Python.

**Phase 2: Ingest and indexes**
- Idempotent ingest: add embeddings to existing data first. Normalize, embed in batches via Ollama, write, create vector, full-text and unique-ID indexes and constraints, validate counts and no missing embeddings.
- Embedding model name and dimension stored in DB metadata.
- Exit: validation passes. Re-running ingest changes nothing.

**Phase 3: KG tool layer**
- Parameterized Cypher in `kg_tools/cypher/`, typed tools in `tools.py`, query embedding via Ollama.
- Read-only, timeouts, result caps, node IDs in every result.
- Exit: tools unit-tested against mocked and real Neo4j.

**Phase 4: Orchestrator**
- LangGraph state machine with Pydantic state per node, mocked-LLM and mocked-Neo4j tests per node.
- FastAPI `/v1/chat/completions` with SSE streaming. Fail-closed paths implemented.
- Exit: end-to-end question answered with node-ID citations from the CLI/curl.

**Phase 5: Eval and observability**
- `eval_set.jsonl` (20 to 50 per question type), `run_evals.py` metrics: tool/plan correctness, entity resolution accuracy, grounding rate, latency. Baseline recorded.
- Langfuse tracing with a span per node and per tool call.
- Regression gate in CI.
- Exit: baseline committed, gate runs in CI.

**Phase 6: UI integration and hardening**
- Open WebUI wired to the orchestrator as an OpenAI-compatible connection.
- Prompt-injection review, timeouts and retry verification, secrets audit.
- Decide whether to enable the agentic Retrieve loop, based only on eval results.
- Exit: full flow works through Open WebUI. Eval gate green.

## 7. Open questions (from the brief)

| # | Question | Status |
|---|---|---|
| Q1 | Primary users and 1 to 2 first-release question types | DECIDED (see section 8) |
| Q2 | Real Neo4j schema and how data was originally loaded | ACCEPTED by owner 2026-11-15 (see section 9) |
| Q3 | Mac chip and RAM, therefore Ollama chat and embedding models | Hardware known (M5 Pro, 24 GB). DECIDED 2026-11-15 (section 10): Qwen 3.6 small (8B-14B, exact tag TBD) for chat, qwen3-embedding:0.6b for embeddings. Chat model validated by eval set |
| Q4 | Tool layer in-process or separate HTTP service | DECIDED: in-process first (see section 8) |

## 8. Decisions log

Record confirmed answers here with date and who decided.

| Date | Decision | Notes |
|---|---|---|
| 2026-11-15 | Primary users: teachers / curriculum designers | Owner |
| 2026-11-15 | First release: prerequisite lookup only; later expand to standard-to-standard connections and supporting components | Owner. Keep tool set and eval set extensible |
| 2026-11-15 | Neo4j schema accepted as discovered (section 9) | Owner. Verify against live DB in Phase 1 |
| 2026-11-16 | Chat model: `qwen3:14b` (Qwen 3.6 has no 8B-14B Ollama tag; only 27b and 35b-a3b) | Owner chose a smaller non-3.6 Qwen. Eval set can swap it |
| 2026-11-15 | Embedding model: `qwen3-embedding:0.6b` (verify dimension after pull and store in DB metadata) | Owner |
| 2026-11-15 | Neo4j data: reload KG v1.17.0 into this project's own volume via the KG project's importer | Owner. Done: 315,434 nodes, 551,058 relationships, verified |
| 2026-11-16 | Phase 2 embeds every text-bearing label (12 labels, `ingest/targets.py`), not only standards | Small labels cost under 9 minutes. Bookkeeping node `_IngestMeta` holds model and dimension; schema checks ignore it |
| 2026-11-15 | Tool layer runs in-process first, HTTP split later if needed | Owner |

## 9. Schema record (Phase 0 discovery)

Source: `~/LearningCommonsVisualization` (README, `docs/PROGRESS.md`, `pocs/poc3/import_kg.py`), read-only. **Accepted by owner on 2026-11-15** without a live-DB check (Neo4j was not running during discovery). Re-run the three Cypher queries from `pre-plan.md` section 6 in Phase 1 as a sanity check and correct this section if they differ.

- **Dataset:** Learning Commons KG v1.17.0 open export (`nodes.jsonl`, `relationships.jsonl`, about 1 GB, in `~/LearningCommonsVisualization/data/v1.17.0/`). Expected totals: 315,434 nodes, 551,058 relationships, 13 labels, 12 relationship types.
- **Node labels (count):** StandardsFrameworkItem 276,818; LearningComponent 10,731; Activity 8,173; Misconception 8,117; Assessment 4,516; Lesson 2,550; Construct 2,258; MasteryThreshold 1,022; LessonGrouping 764; StandardsFramework 266; GuidanceFrameworkItem 198; Course 18; GuidanceFramework 3.
- **Relationship types (count):** hasChild 277,622; supports 154,124; hasEducationalAlignment 52,807; hasStandardAlignment 28,271; hinders 19,294; hasPart 15,944; hasMasteryThreshold 1,022; buildsTowards 757; hasReference 472; relatesTo 284; hasDependency 269; mutuallyExclusiveWith 192.
- **Prerequisite/progression data:** `(StandardsFrameworkItem)-[:buildsTowards]->(StandardsFrameworkItem)` (757 edges, cross-grade and cross-framework) and `hasDependency` between LessonGrouping (269). Backward chains from a standard run much deeper than forward ones.
- **How it was loaded:** `pocs/poc3/import_kg.py`, idempotent. Nodes MERGE on `identifier`, relationships MERGE on their own `identifier`. 13 unique constraints, 3 range indexes (`idx_framework_jur_subj`, `idx_item_jurisdiction`, `idx_item_code`) and a full-text index `kg_search`. Relationships keep only identifier/dateCreated/dateModified/author. Array-like string props converted to lists (for example `gradeLevel`). Verified by `verify_counts.py` (PASS).
- **Not in the DB yet:** embeddings and a vector index. Ingest mode "add embeddings to existing data" fits (Q2 default, accepted).
- **Existing Neo4j setup (visualization project):** `neo4j:5-community` with APOC in Docker, container `kg-neo4j`, Bolt on `127.0.0.1:7687`, `NEO4J_AUTH: none` (dev only). This project needs a read-only user (hard rule 8), so auth must change.
- **Host:** Apple M5 Pro, 24 GB RAM. Ollama installed but not running, no models listed at discovery time. Docker daemon not running.

## 10. Ollama models (owner decision 2026-11-15)

**Chosen:** chat = Qwen 3.6 small variant (about 8B-14B, exact Ollama tag to be verified), embeddings = `qwen3-embedding:0.6b` (about 639 MB, 32K context; confirm vector dimension after pulling). The table below is the earlier proposal, kept for fallbacks.

Hardware: M5 Pro, 24 GB. Ollama's MLX backend needs 32 GB, so expect the Metal path. Sources are web guides of mixed quality, so verify tags with `ollama pull` and test on our own JSON schemas. Models are read from config (hard rule 5), so swapping is cheap; the eval set decides the final pick.

| Role | Primary candidate | Alternates |
|---|---|---|
| Chat (Understand, Synthesize; JSON-schema output) | Qwen 3.6 27B (about 17 GB at Q4, tight on 24 GB) | Gemma 4 26B (about 18 GB); a 14B-class model if memory is tight; Granite 4.2 8B as a fast fallback |
| Embeddings | nomic-embed-text (768 dim, 274 MB, fast on CPU) | EmbeddingGemma (768 dim, Matryoshka); qwen3-embedding:0.6b |

Selection test (Phase 2/5): JSON-schema validity rate on the Understand step, prerequisite-lookup eval scores, latency, and memory headroom while Neo4j runs in Docker (about 3 GB). Changing the embedding model requires re-embedding all nodes.

## 11. Phase 1 design notes (modularity and read-only)

**Read-only deviation (needs owner awareness).** The brief asks for a read-only Neo4j *user*. Neo4j **Community** (the image the KG project uses) has no RBAC, so a read-only user cannot exist. Read-only is therefore enforced in code, in two layers: `kg_tools/cypher_guard.py` rejects any write clause, multi-statement query, subquery `CALL` or non-allowlisted procedure before the query leaves the process, and `Neo4jReader` only opens read transactions (`execute_read`). Admin credentials (`NEO4J_ADMIN_*`) are used only by ingest; a test fails if any other module references them. A true DB-level read-only user would need Neo4j Enterprise. Verified live 2026-11-15: bypassing the guard, a `CREATE` inside `execute_read` is refused by the server (`Neo.ClientError.Statement.AccessMode`: Writing in read access mode not allowed), so the two layers are independent.

**Module map and allowed dependency direction** (enforced by `tests/test_module_boundaries.py`):

| Package | Role | May import |
|---|---|---|
| `common` | settings, typed errors, Protocols (`Embedder`, `ChatModel`, `GraphReader`), `OllamaClient` | nothing in the project |
| `kg_tools` | `cypher_guard`, `Neo4jReader`, `schema` (accepted schema + verifier), later tools and `cypher/*.cypher` | `common` |
| `ingest` | Phase 2, the only writer | `common` |
| `orchestrator` | Phase 4 state machine and API | `common`, `kg_tools` |
| `evals` | Phase 5, talks to the orchestrator over HTTP | `common` |
| `scripts` | thin operational wrappers (`healthcheck`) | all |

Modules depend on Protocols in `common/protocols.py`, never on each other's concrete classes, so every module is unit-testable with fakes and backends are swappable. Deviation from the brief's layout: the Ollama client lives in `common/ollama_client.py` (not `orchestrator/llm.py`) because `kg_tools` (query embeddings) and `ingest` (node embeddings) also need it and must not import the orchestrator. `orchestrator/llm.py` can re-export it in Phase 4.

Config: one `.env` (template `.env.example`), per-module settings classes in `common/settings.py`. No model names in code; the chat and embedding model tags come from config.

Neo4j data: `docker-compose.yml` uses its own container (`lcrag-neo4j`) on host ports 7688 (Bolt) and 7475 (Browser), configurable via `NEO4J_BOLT_PORT`/`NEO4J_HTTP_PORT`, because the KG project's `kg-neo4j` holds 7687/7474. Data volume: `NEO4J_DATA_DIR` (default `./neo4j/data`). The KG project's database is not touched. Decision 2026-11-15 (owner): reload into this project's own volume using the KG project's `pocs/poc3/import_kg.py` (read-only use of its code and JSONL).

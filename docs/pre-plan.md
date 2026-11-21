# Graph RAG System: Architecture Brief (for coding agents)

Status: draft v0.1. Items marked **TBD** are undecided; do not invent them. Ask the owner or leave a clearly marked stub.

## 1. Goal

Build a production-grade RAG system whose primary knowledge source is the **Learning Commons Knowledge Graph (KG)**, stored in **Neo4j**. A local LLM answers natural-language questions by retrieving evidence from the KG through typed tools, and every answer must be grounded in retrieved nodes (cited by node ID).

Target users and question types: **TBD** (candidates: prerequisite lookup, standard-to-standard connections). Tools, eval set and UI details depend on this decision.

## 2. Orchestration style: deterministic workflow with a bounded agentic step

The orchestrator is **not** a free-roaming agent. It is a LangGraph state machine with a fixed skeleton:

| Node | Style | Notes |
|---|---|---|
| Understand | Deterministic | One LLM call with JSON-schema output (intent, entities). No tool choice. |
| Resolve | Deterministic | Maps entity text to real KG node IDs via tool layer (vector + full-text). |
| Retrieve | **Bounded agentic** | Default: intent maps to a fixed tool plan (deterministic). Optional: for open-ended intents the LLM picks tools in a loop, capped at `MAX_TOOL_STEPS` (default 4) and a wall-clock timeout. |
| Synthesize | Deterministic | Answer only from retrieved context; cite node IDs; stream tokens. |
| Verify | Deterministic | Every claim must map to a retrieved node. On failure: regenerate once, then fall back to "not found in the KG". |

Rationale: the LLM is a small local model (Ollama). Free-form tool use is unreliable at this size, so control flow lives in code and the model is used for narrow, schema-constrained decisions. Start fully deterministic in Retrieve; enable the agentic loop only if the eval set shows multi-step questions failing.

## 3. Architecture

```
User -> Open WebUI
          | HTTP POST /v1/chat/completions (OpenAI-compatible, SSE stream back)
          v
Orchestrator (FastAPI + LangGraph)
  Understand -> Resolve -> Retrieve -> Synthesize(+Verify)
     |  Ollama /api/chat           |  KG tool layer (typed, read-only)
     v                             v
   Ollama (host)               Neo4j (Bolt 7687)  <-- Ingest script <-- KG source files (CSV/JSON)
   (LLM + embeddings)             ^ vector + full-text indexes
                                  |
Orchestrator --traces--> Langfuse        Eval runner --HTTP--> Orchestrator  (reads Eval set JSONL)
```

### Components

| Component | Tech | Responsibility |
|---|---|---|
| Open WebUI | Docker | Chat frontend. Configured with the orchestrator as an OpenAI-compatible connection ("model"). |
| Orchestrator | Python, FastAPI, LangGraph | Exposes `/v1/chat/completions` (streaming). Runs the state machine. Emits traces. |
| Ollama | Runs on the Mac host (not in Docker) | Chat model with JSON-schema output + embedding model. Reached from containers at `host.docker.internal:11434`. |
| KG tool layer | Python module (in-process first; HTTP service later) | Typed, parameterized tools over Neo4j. Also performs query embedding via Ollama. |
| Neo4j | Docker (or Aura) | Graph store + vector index + full-text index. App uses a **read-only** DB user. |
| Ingest script | Python, batch, idempotent | Loads KG source files, creates embeddings, writes nodes/relationships/indexes. |
| Langfuse | Docker, self-hosted | Per-request traces and eval scores. |
| Eval runner | Python (pytest-style) | Sends eval questions to the orchestrator, scores results, reports regressions. |

## 4. Data flows (arrow reference)

| # | From -> To | Protocol | Payload |
|---|---|---|---|
| 1 | User <-> Open WebUI | HTTPS | question text, answer |
| 2 | Open WebUI <-> Orchestrator | HTTP `POST /v1/chat/completions` | messages JSON; SSE token stream back |
| 3 | Orchestrator <-> Ollama | HTTP `/api/chat` | prompt + JSON schema; intent JSON or token stream |
| 4 | Orchestrator <-> Tool layer | Python call (HTTP if split out later) | tool name + args JSON; subgraph + node IDs |
| 5 | Tool layer <-> Neo4j | Bolt | parameterized Cypher, vector/full-text queries; node/relationship rows |
| 6 | Tool layer -> Ollama | HTTP `/api/embed` | query text -> float vector |
| 7 | Orchestrator -> Langfuse | HTTP (SDK/OTLP) | trace spans (inputs, outputs, latency) |
| 8 | Ingest -> Neo4j | Bolt batch writes | nodes, relationships, embedding vectors |
| 9 | Ingest <-> Ollama | HTTP `/api/embed` | node text -> vectors |
| 10 | KG source files -> Ingest | file read | CSV/JSON export |
| 11 | Eval set -> Eval runner | file read | questions + gold answers (JSONL) |
| 12 | Eval runner -> Orchestrator | same endpoint as #2 | test questions; score report |

## 5. Retrieval design (hybrid GraphRAG)

- **Vector search finds entry points.** Natural-language text is embedded and matched to node descriptions via the Neo4j vector index. Full-text index handles exact names and standard codes.
- **Graph traversal does relational reasoning.** From the resolved nodes, tools expand along relationships (for example prerequisites, related standards) with bounded depth.
- The LLM never writes Cypher in the default path. All Cypher lives in the tool layer as parameterized queries.

### Tool layer (provisional; finalize after question types are chosen)

Keep the set small (3 to 5 tools) with precise docstrings, because small models mis-select among many tools.

| Tool | Input | Output |
|---|---|---|
| `search_nodes` | `text`, optional `node_type`, `k` | ranked node candidates (id, label, score) via vector + full-text |
| `get_node` | `node_id` | node properties |
| `get_neighbors` | `node_id`, `relationship_type`, `depth` (max 3), `direction` | subgraph (nodes + edges) |
| `get_prerequisites` | `node_id`, `depth` | ordered prerequisite chain (**TBD**: depends on actual relationship types) |

Tool rules: read-only, parameterized Cypher only, per-query timeout, result-size cap, and every result carries node IDs for citation.

## 6. Data model (Neo4j)

**TBD: confirm against the real database.** Run these in Neo4j Browser and record the output here:

```cypher
MATCH (n) RETURN count(n);
CALL db.labels();
CALL db.relationshipTypes();
```

Required indexes (created by ingest):
- Vector index on node text embedding (record embedding model name + dimension in DB metadata; changing the model requires re-embedding everything).
- Full-text index on names/codes.
- Unique constraint on node ID.

Context: the KG was already loaded into Neo4j and visualized. The first ingest mode should be **add embeddings to existing data**, not reload from scratch (**TBD**: confirm how the existing data was loaded).

## 7. Ingest script

Offline, run on demand. Must be **idempotent** (use `MERGE`, safe to re-run).

1. Read KG source files (CSV/JSON).
2. Normalize: unify IDs, drop duplicates and dangling relationships.
3. Embed node text through Ollama `/api/embed` (batched).
4. Write nodes, relationships, vectors to Neo4j in batches; create indexes and constraints.
5. Validate: node/relationship counts, no nodes missing embeddings.

## 8. Evaluation and observability (required, not optional)

- **Eval set**: JSONL of questions with gold answers (for example expected node IDs, expected tool). Start with about 20 to 50 questions per question type.
- **Metrics**: tool/plan correctness, entity resolution accuracy, answer grounding rate (claims supported by retrieved nodes), latency.
- **Regression gate**: any change to model, prompt, or retrieval must not drop scores below the previous baseline; run the eval runner in CI.
- **Tracing**: every request produces a Langfuse trace with one span per LangGraph node and per tool call.
- Switch Retrieve to the agentic loop only if multi-step questions fail the eval threshold.

## 9. Non-functional requirements

- Streaming responses to Open WebUI.
- Hard caps: `MAX_TOOL_STEPS`, per-step and total timeouts, retry with backoff on Ollama/Neo4j errors.
- Security: Neo4j read-only credentials; treat KG content and user input strictly as data (prompt-injection defense); no secrets in code; configuration via environment variables.
- Local-first: no external LLM API calls by default.
- Reproducible deployment with Docker Compose (orchestrator, Neo4j, Langfuse, Open WebUI). Ollama stays on the host.

## 10. Suggested repository layout

```
.
├── docker-compose.yml
├── .env.example
├── orchestrator/
│   ├── app.py              # FastAPI, /v1/chat/completions (SSE)
│   ├── graph.py            # LangGraph state machine
│   ├── nodes/              # understand.py, resolve.py, retrieve.py, synthesize.py, verify.py
│   ├── llm.py              # Ollama client (chat, JSON schema, embed)
│   └── tracing.py          # Langfuse integration
├── kg_tools/
│   ├── tools.py            # typed tool functions
│   ├── cypher/             # parameterized .cypher files
│   └── neo4j_client.py
├── ingest/
│   └── ingest.py
├── evals/
│   ├── eval_set.jsonl
│   └── run_evals.py
└── docs/
    └── architecture.md     # this file
```

## 11. Rules for the coding agent

1. Do not let the LLM generate Cypher in the default path; add parameterized queries to `kg_tools/cypher/`.
2. Every LangGraph node has a typed input/output state (Pydantic) and a unit test with a mocked LLM and mocked Neo4j.
3. All LLM decisions that gate control flow use JSON-schema-constrained output.
4. Keep tool descriptions short and unambiguous; do not add tools without updating the eval set.
5. Never hardcode the embedding model; read it from config and record it in Neo4j metadata.
6. Fail closed: if retrieval returns nothing or verification fails, answer that the KG has no supporting information.
7. Do not fill in any **TBD** item without confirmation.

## 12. Open questions

1. Primary users and the 1 to 2 question types for the first release (drives tools and eval set).
2. Real Neo4j schema (labels, relationship types, properties) and how the data was originally loaded.
3. Mac chip and RAM, which fixes the Ollama model choice (chat and embedding), validated against the eval set.
4. Whether the tool layer stays in-process or becomes a separate HTTP service.
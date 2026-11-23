# 진행 상황 (Progress)

> 이 문서는 `docs/progress.md`의 한국어 번역본입니다. 원본은 영어이며, 기록은 원본에 계속 추가합니다. 번역본은 필요할 때 다시 생성합니다.

**에이전트 안내: 진행이 있을 때마다(코드나 문서 변경, 결정, 버그 발견, 중요한 명령, 작업 진전) 이 파일에 항목을 추가하세요.** 턴을 끝내기 전에 추가합니다. 최신 항목이 위로 갑니다. 구체적으로 쓰세요: 경로, 명령, 결과, 이유. "현재 상태"와 단계(Phase) 체크리스트도 함께 갱신합니다. 계획은 `docs/masterplan.md`에 있습니다.

**다이어그램과 상태 트래커:** [라이브 트래커 (게시됨)](https://claude.ai/artifact/MBUMTrxa3x2vmpzg6BZsrN) · 로컬 원본 [`docs/tracker.html`](tracker.html). 이 파일과 항상 동기화하세요.

## 현재 상태
Phase 0 완료. Phase 1(기반)은 Ollama를 제외하고 완료. Neo4j(`lcrag-neo4j`, bolt 7688)가 전체 KG와 함께 실행 중이며, `scripts.healthcheck --deep`가 연결, 읽기 전용 가드, 스키마(315,434 노드 / 551,058 관계)를 통과합니다. Ollama는 실행 중이 아니고 모델도 받지 않아서 Ollama 검사 2개는 아직 실패합니다. 문서만 있음: `docs/pre-plan.md`, `docs/masterplan.md`, `docs/progress.md`. ECC 플러그인이 프로젝트 범위로 설치됨. 아직 코드 없음.

> 참고: 이 "현재 상태" 단락은 원본에서도 오래된 내용입니다(Phase 4까지 진행된 최신 상태는 아래 로그와 `CLAUDE.md`를 보세요).

## 단계(Phase) 체크리스트
- [ ] Phase 0: 결정과 탐색 (Q1~Q4, 스키마 기록). 스키마 기록 초안 완료, Q3 하드웨어 파악, 모든 질문 결정됨; 정확한 Qwen 채팅 태그는 보류
- [~] Phase 1: 기반. 완료 및 실환경 검증: 골격, 설정, Compose, Neo4j + 데이터, 가드가 있는 읽기 전용 클라이언트, 헬스체크, 테스트. 남음: Ollama 시작, 모델 받기, Ollama 검사 2개 통과
- [ ] Phase 2: 인제스트와 인덱스
- [ ] Phase 3: KG 도구 계층
- [ ] Phase 4: 오케스트레이터
- [ ] Phase 5: 평가와 관측성
- [ ] Phase 6: UI 통합과 안정화

## 다음 단계
- [ ] Ollama 시작(`ollama serve`); `ollama pull qwen3-embedding:0.6b`(약 639 MB)와 선택한 Qwen 3.6 8B-14B 채팅 태그; 검증된 태그를 `.env`에 넣기(`.env.example`의 `qwen3.6:8b`는 검증되지 않은 임시값); `make health` 다시 실행
- [ ] 오너가 masterplan 9절 스키마를 확인(Neo4j를 시작해 Cypher 쿼리 3개를 실행하거나, 발견된 값을 수락) (Q2)
- [ ] `ollama pull`로 정확한 Qwen 3.6 소형 채팅 태그와 임베딩 차원을 검증(먼저 Ollama 시작)

## 막힌 점과 주의사항
- 오너 확인 없이 TBD 항목을 채우지 않습니다.
- ECC 마켓플레이스 `ecc`는 사용자 전역이며 GitHub 저장소로 다시 지정되었습니다(이전에는 `~/LearningCommonsVisualization/ECC`의 로컬 디렉터리).

## 로그 (최신순)

### 2026-11-15: Phase 1 실환경 검증
- Docker Desktop 시작. 포트 충돌: KG 프로젝트의 `kg-neo4j`가 7687/7474를 사용하므로, 이 프로젝트의 호스트 포트는 7688/7475입니다(compose 환경변수 `NEO4J_BOLT_PORT`/`NEO4J_HTTP_PORT`, `.env`의 `NEO4J_URI`). `kg-neo4j`는 건드리지 않았습니다.
- 생성한 비밀번호가 담긴 `.env`(git 무시, 권한 600) 생성; `make up` -> 컨테이너 `lcrag-neo4j` healthy.
- 오너 결정에 따라 데이터 로드: `~/LearningCommonsVisualization/pocs/poc3/import_kg.py --data .../data/v1.17.0`를 bolt 7688에 대해 실행(46.5초; 관계 551,058개는 21초).
- **실환경 실행으로 발견한 버그:** `Neo4jReader`가 `neo4j.Query`를 `tx.run`에 넘겼는데, 관리형 트랜잭션에서는 지원되지 않습니다(가짜 드라이버 테스트로는 잡을 수 없었음). 트랜잭션 함수에 `@unit_of_work(timeout=...)`를 써서 수정; 테스트는 이제 트랜잭션 함수의 타임아웃을 검증합니다.
- `python -m scripts.healthcheck --deep`: 연결, 읽기 전용 가드, 스키마 PASS(레이블별 개수 모두 일치). 확인: 서버가 `execute_read` 안의 `CREATE`를 거부함(`Neo.ClientError.Statement.AccessMode`), 프로브 노드 없음.
- Ollama: `ollama`는 설치되어 있으나 서버가 실행 중이 아니고 받은 모델 없음; 검사 2개 FAIL(예상된 결과). 수 GB라서 승인 없이는 모델을 받지 않았습니다.

### 2026-11-15: Phase 1 기반 구축
- `pyproject.toml`, `.env.example`, `.gitignore`, `Makefile`, `docker-compose.yml` 추가(neo4j `lcrag-neo4j`, open-webui가 있는 선택적 `ui` 프로필; Langfuse는 Phase 5로 연기).
- 모듈: `common/{settings,errors,protocols,ollama_client}.py`; `kg_tools/{cypher_guard,neo4j_client,schema}.py`; `orchestrator/`, `ingest/`, `evals/`의 패키지 스텁; `scripts/healthcheck.py`.
- 테스트(`tests/`, 39개 통과, Docker 불필요): 가드, 설정, Ollama 클라이언트(모의 전송, 재시도, 4xx는 재시도 없음), Neo4j 리더(가짜 드라이버, 상한, 타임아웃), 스키마 검증기, 그리고 의존 방향과 관리자 자격 증명 격리를 강제하는 `test_module_boundaries.py`.
- 발견: Neo4j Community에는 읽기 전용 사용자가 없어서, 읽기 전용은 코드에서 강제합니다(masterplan 11절). Python 3.12 venv는 `.venv`. `ruff --fix` 적용(import 스타일만).
- 하지 않은 것: 실환경 검사 전부. `docker compose config`는 유효; 데몬은 꺼져 있었고 Ollama는 실행 중이 아니었음.

### 2026-11-15: 모델 선택
- 오너가 더 가벼운 채팅 모델(Qwen 3.6, 8B-14B, 태그 미정)과 `qwen3-embedding:0.6b`를 선택. masterplan 7, 8, 10절에 기록.

### 2026-11-15: 스키마 수락, 모델 후보 제안
- 오너가 발견된 스키마를 수락(masterplan 9절, 결정 로그). Phase 1에서 실제 DB와 대조해 점검할 계획.
- masterplan 10절 추가: Ollama 후보(채팅: Qwen 3.6 27B / Gemma 4 26B; 임베딩: nomic-embed-text / EmbeddingGemma). 미결정; 웹에서 얻은 정보이므로 `ollama pull`과 평가로 검증해야 함.

### 2026-11-15: Q1과 Q4 결정
- 오너: 사용자 = 교사/교육과정 설계자; 첫 릴리스 = 선수 지식(prerequisite) 조회, 이후 표준 간 연결과 지원 구성요소로 확장; 도구 계층은 우선 프로세스 내부. `docs/masterplan.md` 1, 7, 8절에 기록.

### 2026-11-15: Phase 0 탐색
- `~/LearningCommonsVisualization`을 읽기 전용으로 검토(README, docs/PROGRESS.md, pocs/poc3/import_kg.py). 레이블, 관계 유형, 개수, 로드 방법, 인덱스를 `docs/masterplan.md` 9절에 기록(실제 DB와는 미확인; Neo4j와 Docker가 실행 중이 아니었음).
- `sysctl`: Apple M5 Pro, RAM 24 GB. `ollama list` 실패(서버 미실행). 원본 로더에서 임베딩이나 벡터 인덱스는 찾지 못함.
- 핵심 발견: 선수 지식은 `buildsTowards`(StandardsFrameworkItem)와 `hasDependency`(LessonGrouping)입니다. 기존 Neo4j는 `NEO4J_AUTH: none`으로 실행되므로 읽기 전용 사용자를 추가해야 합니다.

### 2026-11-15: MAT 범위 제거
- 오너가 MAT는 이 프로젝트와 무관하다고 말함. `docs/masterplan.md`와 `docs/progress.md`에서 MAT 관련 내용(질문 유형 후보, 예전 Q4, Phase 0 항목)을 모두 제거하고 Q5를 Q4로 번호 조정. 오너 요청에 따라 `docs/pre-plan.md`에서도 MAT 제거(1절 후보, 예전 열린 질문 4; Q5를 Q4로 번호 조정).

### 2026-11-15: Masterplan과 progress 파일 생성
- `docs/pre-plan.md`를 읽음(Neo4j의 Learning Commons KG 위의 Graph RAG, 로컬 Ollama LLM, 제한된 에이전트형 Retrieve가 있는 결정적 LangGraph 워크플로, Open WebUI, Langfuse, 평가 게이트).
- `docs/masterplan.md`(목표, 성공 기준, 아키텍처, 필수 규칙, 저장소 구조, Phase 0~6, 열린 질문, 결정 로그)와 이 파일을 생성.

### 2026-11-15: ECC 설치
- `claude plugin marketplace add https://github.com/affaan-m/ECC --scope project`, `claude plugin install ecc@ecc --scope project`. `.claude/settings.json` 작성.

### 2026-11-16: Phase 1 종료
- Qwen 3.6에는 8B-14B Ollama 태그가 없음(27b 약 17 GB, 35b-a3b 약 23 GB). 오너가 더 작은 비-3.6 Qwen을 선택: `qwen3:14b`와 `qwen3-embedding:0.6b`를 받고 `.env`/`.env.example`에 `OLLAMA_CHAT_MODEL=qwen3:14b` 설정. 임베딩 차원 = 1024.
- `python -m scripts.healthcheck --deep`: 5/5 PASS. `make test`: 39개 통과. Phase 1 종료 조건 충족. 다음: Phase 2.

### 2026-11-16: 상태 트래커 페이지
- 다중 표현 트래커 제작(인프라 순서도, 로드맵, 시퀀스, 모듈, 데이터 상태, 33개 항목 체크리스트; 초록=완료, 파랑=부분, 주황=다음, 회색=시작 전). `docs/tracker.html`에 저장(브라우저로 열기); 게시본: https://claude.ai/artifact/MBUMTrxa3x2vmpzg6BZsrN. Phase가 진행될 때마다 체크리스트와 막대를 갱신하세요.

### 2026-11-16: 트래커를 도형으로 재설계
- `docs/tracker.html`은 이제 색 = 개체, 도형 = 사물의 종류(데이터 저장소, 설정, 스크립트, 채널, 값, 결정, 이벤트), 테두리 스타일 + 마커 = 상태를 사용합니다. 범례 카드와 데이터·타입 순서도를 추가. `docs/MultiReps.md`에 기록; 게시본은 같은 URL에서 갱신.

### 2026-11-16: 트래커 다이어그램 리팩터링
- 순서도 색 문제 수정(Mermaid `classDef`가 `var()`를 거부함; 이제 클래스는 무해한 속성으로 정의하고 페이지 CSS로 색을 입힘). 단일 인프라 순서도를 둘로 분리: 1) 기반과 인제스트, 2) 응답 경로. Chrome에서 로컬 렌더링 확인(문법 오류 0).

### 2026-11-16: 모듈성 규칙
- 오너가 새 기능을 쉽게 추가할 수 있도록 모든 것을 모듈식으로 유지해 달라고 요청. `CLAUDE.md` 상단(진행 마커 바깥)에 상시 규칙 '설계 규칙: 모든 것은 모듈식'을 추가. 새 질문 유형은 수정이 아닌 추가; Protocol 사용; 모델은 설정으로만; 모듈별 테스트.

### 2026-11-16: Phase 2 인제스트 구축, 작은 레이블 임베딩 완료
- `ingest/` 추가(`targets.py`: 레이블과 텍스트 속성 표, `store.py`: `IngestStore` Protocol 뒤의 관리자 Neo4j 저장소, `pipeline.py`: 멱등적 키셋 페이지네이션 임베딩 루프, `validate.py`), `scripts/ingest.py` CLI(`--label`, `--limit`, `--validate-only`), `common/constants.py`, `IngestSettings`. 새 테스트 10개; 총 49개 통과.
- 기록 관리: `_IngestMeta` 노드 하나에 임베딩 모델과 차원(1024)을 저장. `kg_tools/schema.py`는 개수 계산에서 이를 제외. 설정의 모델이나 차원이 다르면 전체 재임베딩 전까지 거부됩니다.
- 실환경: 레이블 11개 임베딩(노드 37,194개, 505.7초, 초당 약 74개), 코사인 벡터 인덱스 `emb_<Label>` ONLINE, 전문 검색 `kg_search`와 유니크 제약 확인, `VALIDATION PASS`. 재실행 시 0개 노드를 임베딩하고 통과(멱등).
- 오너의 범위 질문(전체 레이블 vs 표준만): 추가 비용이 9분 미만이라 전체 레이블을 임베딩.
- 진행 중: `StandardsFrameworkItem`(텍스트가 있는 276,818개 중 276,729개 노드)을 백그라운드에서 실행, 약 1~1.5시간. Phase 2 종료에는 12개 레이블 전부에 대해 `python -m scripts.ingest --validate-only`가 통과해야 함.
- 트래커 갱신(33개 중 13개 완료, 2개 부분).

### 2026-11-17: Phase 2 완료
- `StandardsFrameworkItem` 임베딩 완료(노드 276,729개, 6,008초, 초당 46개). `--validate-only`가 12개 레이블 전부 통과(VALIDATION PASS)하여 Phase 2 종료 조건 충족; 이전 재실행은 0개 임베딩.
- 트래커 갱신(33개 중 15개 완료, Phase 2 5/5, 다음은 Phase 3). 참고: Python은 `.venv/bin/python`으로 실행(시스템 `python`은 PATH에 없음).

### 2026-11-17: Phase 3 완료 (KG 도구 계층)
- `kg_tools/queries.py`, `kg_tools/cypher/`의 매개변수화된 파일 6개, `KGTools`가 있는 `kg_tools/tools.py` 추가: `search_nodes`(레이블별 벡터 + 전문 검색, 순위 융합), `get_node`, `find_standard_by_code`, `get_neighbors`, `get_prerequisites`. 모든 결과에 노드 ID가 있고, 상한이 있으며, 잘못된 입력에는 닫힌 채로 실패(fail closed)합니다. 기존 모듈은 수정하지 않았습니다(추가하되 수정하지 않기).
- 실제 데이터로 검증: `buildsTowards`는 선수 표준에서 이후 표준으로 향함(출발 학년이 더 이른 경우 354개 간선, 더 늦은 경우 16개, 같은 경우 387개). 표준 코드는 관할 구역(jurisdiction)마다 반복되고, 코드가 없는 표준도 많음.
- 테스트: 단위 73개(신규 24개, 가짜 사용)와 라이브 4개 통과; ruff 깨끗. 종료 기준(모의 및 실제 Neo4j에서 테스트) 충족.
- 오너에게 남은 질문: LessonGrouping의 `hasDependency` 방향(아직 도구 없음)과 Resolve가 관할 구역을 고르는 방법.

### 2026-11-21: Git, GitHub 푸시, DGX Spark 이전용 Neo4j 덤프
- 오너가 `git init` 실행. `.gitignore`를 점검(실제 관리자 비밀번호는 추적 가능한 파일에 없음)하고 확장(OS/에디터 파일, 도구 캐시, `.env.example`을 제외한 `.env.*`, `*.pem`, `*.key`). 첫 커밋 `b9f4993`(51개 파일)을 `ecc:prp-commit`으로 만들고, 이어서 `77056d6`. https://github.com/yunwesth/LCKG_RAG(`master`)에 푸시. 첫 푸시는 저장된 자격 증명이 다른 계정이라 403이 났고, `yunwesth`로 `gh auth login`과 `gh auth setup-git`을 실행해 해결.
- 결정(오너): DGX Spark(aarch64, 128 GB 통합 메모리)로 옮기고 Ollama 대신 vLLM 사용. 아직 시작 안 함. 기존 Protocol 뒤에 vLLM 클라이언트를 추가(설정만 변경). 임베딩: Ollama `qwen3-embedding:0.6b`를 유지하거나, 바꾼다면 전체 재임베딩(약 100분). 다른 임베더는 검색 품질을 해칠 수 있고 `_IngestMeta`가 조용한 변경을 거부하기 때문.
- 이전용 Neo4j 덤프: 로컬 `lcrag-neo4j`(Neo4j 5.26.33, arm64 이미지 `neo4j:5-community`)를 중지하고, 일회용 컨테이너로 `neo4j-admin database dump neo4j`를 실행한 뒤 재시작(healthy). 파일: `~/lcrag-dump/neo4j.dump`(2.9 GB, 539개 파일, 18초), SHA-256 `b506afd605b4b5634b962774a0732b799a1fdb2f2e770b76a65ecf46bb848aed`(`~/lcrag-dump/neo4j.dump.sha256`에도 있음). `kg-neo4j`(다른 프로젝트)는 건드리지 않았습니다. 덤프는 git에 들어 있지 않습니다.
- Spark에서 복원하는 방법: 덤프를 `scp`로 전송, SHA-256 비교, `docker compose up -d neo4j`를 한 번 실행해 볼륨을 만들고 중지, 그다음 `docker run --rm -v <data>:/data -v <dump dir>:/dump neo4j:5-community neo4j-admin database load neo4j --from-path=/dump --overwrite-destination=true`, 다시 시작, 이후 `make test`, `python -m scripts.healthcheck --deep`, `python -m scripts.ingest --validate-only` 실행(315,434 노드, 551,058 관계, VALIDATION PASS가 기대값). 서버에서 새 `.env`를 만듭니다(새 관리자 비밀번호); `.env`는 git에 없습니다.
- 참고: `docker-compose.yml`은 고정되지 않은 태그 `neo4j:5-community`를 사용하므로, 서버와 덤프가 맞도록 5.26.x로 고정하는 것을 고려하세요.

### 2026-11-22: 결정, Phase 4는 Mac에서 끝내고 이후 Spark로 이전
- 오너 선호: 먼저 구축을 끝내고 나중에 이전. Spark에서 지금까지 한 것: 저장소 클론(`LCKG-RAG`로 이름 변경), Claude Code 설치, `neo4j.dump` 복사 및 검증(`neo4j.dump: OK`). 거기서 아직 안 한 것: `.env`, Python 환경, 복원. 이 Mac의 `origin`은 이제 `https://github.com/yunwesth/LCKG-RAG.git`을 가리킵니다.
- 기다려도 안전한 이유: Phase 4 오케스트레이터는 Neo4j를 읽기만 하므로 덤프가 계속 유효합니다. 인제스트가 다시 쓰기를 하거나 임베더가 바뀔 때만 다시 덤프합니다.
- vLLM 계획: Spark의 자체 호스팅 vLLM 서버가 OpenAI 호환 API를 제공. `common/`의 기존 Protocol 뒤에 클라이언트를 추가하고 `.env`만 변경. Phase 4 동안 Spark에서 vLLM 스모크 테스트 1회(Qwen3 사고 모드, JSON 출력, 스트리밍). 오너가 전체 재임베딩(약 100분)을 택하지 않는 한 임베더는 Ollama `qwen3-embedding:0.6b` 유지.
- 다음: 실제 데이터에서 `hasDependency` 방향 조사(읽기 전용); 관할 구역 정책은 아직 오너 결정이 필요.

## 2026-11-22: Phase 4 오케스트레이터 구축 (아직 커밋 안 함)
- 관할 구역 정책은 오너가 결정: 사용자에게 묻는다. `hasDependency` 방향 확인(의존하는 쪽 -> 선수 지식).
- `orchestrator/` 파이프라인(LangGraph 기반 Understand, Resolve, Retrieve, Synthesize, Verify), OpenAI 호환 API(`orchestrator/api.py`, `scripts/serve.py`), CLI(`scripts/ask.py`), kg_tools `get_lesson_prerequisites`와 `list_jurisdictions`, 테스트 `tests/test_orchestrator.py`와 `tests/test_orchestrator_api.py` 추가.
- Ollama `qwen3:14b` 실환경 확인: 되묻기 턴이 동작; `5.NF.B.5`(Multi-State)는 출처가 달린 선수 지식 목록을 반환. 교훈: 프롬프트에서 글머리표 형식을 고정하기 전까지는 `[n]` 인용만 나열된 응답이 나왔으므로, 이제 Verify는 실제 문장이 없는 응답을 거부합니다.
- 남은 일: 평가 세트와 Langfuse(Phase 5), 타임아웃 강제, Open WebUI(Phase 6), Spark에서 vLLM 스모크 테스트.
- 트래커(`docs/tracker.html`) 갱신: 33개 중 24개 완료, 1개 부분 완료(FastAPI 엔드포인트는 가짜로만 검증했고 실제 curl 검증은 안 함); Phase 4 막대 6/7.

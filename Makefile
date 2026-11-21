PY = .venv/bin/python

.PHONY: setup up down test health lint
setup:
	python3.12 -m venv .venv
	$(PY) -m pip install -q -e ".[dev]"
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example; edit passwords")

up:
	docker compose up -d neo4j

down:
	docker compose down

test:
	$(PY) -m pytest -m "not live"

health:
	set -a; . ./.env; set +a; $(PY) -m scripts.healthcheck

lint:
	.venv/bin/ruff check .

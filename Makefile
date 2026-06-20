# Developer task runner for the RAG Refinement System.

.PHONY: install lint type test up down

install:
	pip install ".[dev]"

lint:
	ruff check backend ingestion tests

type:
	mypy backend ingestion

test:
	pytest -q

up:
	docker compose up -d --build

down:
	docker compose down

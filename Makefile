.PHONY: install test lint format eval eval-full index serve docker clean

PORT ?= 8080

install:
	pip install -e ".[dev,api]"

test:
	pytest

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .
	ruff check --fix .

eval:
	python evals/run_eval.py --mode offline

eval-full:
	python evals/run_eval.py --mode full --out artifacts/eval_report.json --markdown artifacts/eval_report.md

index:
	python scripts/build_index.py

serve:
	uvicorn support_agent.api:app --port $(PORT) --reload

docker:
	mkdir -p artifacts/index
	docker build -t support-agent:local .

clean:
	rm -rf artifacts .pytest_cache .ruff_cache .coverage
	find . -name __pycache__ -type d -exec rm -rf {} +

.PHONY: help up down logs ps seed test lint format clean pull-models

help:
	@echo "Social Support Workflow Automation"
	@echo "  make up         - start all services (auto-detect profile)"
	@echo "  make down       - stop all services"
	@echo "  make logs       - tail logs for all services"
	@echo "  make ps         - show running services"
	@echo "  make seed       - run the seeder (synthetic data + KB + classifier)"
	@echo "  make test       - run tests"
	@echo "  make eval       - run the evaluation harness (metrics + LLM-as-judge report)"
	@echo "  make lint       - ruff lint"
	@echo "  make format     - ruff format"
	@echo "  make pull-models - pull Ollama models"
	@echo "  make clean      - remove volumes + artifacts (DESTRUCTIVE)"

PROFILE ?= local

up:
	bash setup.sh

down:
	docker compose --profile $(PROFILE) down

logs:
	docker compose --profile $(PROFILE) logs -f --tail=100

ps:
	docker compose --profile $(PROFILE) ps

seed:
	docker compose --profile $(PROFILE) run --rm seeder python -m seeder.main

test:
	pytest -v

eval:
	docker compose exec api python -m tests.evals

lint:
	ruff check src tests seeder

format:
	ruff format src tests seeder

pull-models:
	ollama pull qwen3.5:9b-mlx
	ollama pull minicpm-v:8b
	ollama pull bge-m3

clean:
	docker compose --profile $(PROFILE) down -v
	rm -rf models/*.joblib docs/bias_report.json docs/cv_metrics.json

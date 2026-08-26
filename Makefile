.PHONY: dev test lint report

dev:
	docker-compose up -d

test:
	pytest

lint:
	ruff check src tests
	ruff format --check src tests
	mypy

report:
	python -m handover.report --fixtures tests/fixtures --out out/report.html

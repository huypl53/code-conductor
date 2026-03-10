.PHONY: lint test build format

lint:
	cd packages/conductor-core && uv run ruff check . && uv run ruff format --check . && uv run pyright
	pnpm --filter conductor-dashboard exec biome check ./src

test:
	cd packages/conductor-core && uv run pytest

build:
	pnpm --filter conductor-dashboard build

format:
	cd packages/conductor-core && uv run ruff format .
	pnpm --filter conductor-dashboard exec biome format --write ./src

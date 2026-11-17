default: test

# Install dependencies, pre-commit hooks, and the playwright chromium browser.
setup:
    uv sync
    uv run pre-commit install
    uv run playwright install chromium

# Run the app locally on http://localhost:8080 (auto-reloads on change), with a scratch db under ./.local.
run:
    mkdir -p .local
    BOTTLE_SQLITE_MAIN=.local/dev.db SRS_ASSUME_OWNER=1 uv run hypercorn 'srs.app:app()' --bind 0.0.0.0:8080 --reload

# Fast tests: the app in-process, plus the browser scheduler checked against the server's (needs node).
test-unit:
    uv run pytest -x tests/unit

# Everything, including the container + openhost router tests (needs podman).
test:
    env $(env | grep -oE '^(OPENHOST|BOTTLE)_[A-Z_]+' | sed 's/^/-u /') uv run pytest -x

# Lint, format, and typecheck (same checks as the pre-commit hooks).
check:
    uv run ruff check --fix .
    uv run ruff format .
    uv run mypy

# Build the container image.
build:
    podman build -t srs .

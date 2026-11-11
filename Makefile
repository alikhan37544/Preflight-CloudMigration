PY := .venv/bin/python
UVICORN := $(PY) -m uvicorn

.PHONY: install fixtures seed test e2e lint claims freeze verify demo demo-fg stop clean codebase

install:
	uv venv .venv --python 3.12
	uv pip install --python $(PY) -e '.[dev]'
	$(PY) -m playwright install chromium

fixtures:
	$(PY) scripts/generate_fixture.py

seed: fixtures
	$(PY) -m scripts.seed_demo --force

test: fixtures
	$(PY) -m pytest

e2e:
	$(PY) -m pytest tests/test_e2e.py -m e2e -s

lint:
	$(PY) -m compileall -q app scripts
	$(PY) scripts/claims_lint.py

claims:
	$(PY) scripts/claims_lint.py

freeze: fixtures
	$(PY) scripts/freeze.py

verify:
	$(PY) -m app.cli verify-audit

demo: fixtures
	$(PY) -m scripts.seed_demo --force
	-@tmux kill-session -t preflight 2>/dev/null || true
	tmux new-session -d -s preflight '$(CURDIR)/scripts/run_demo_server.sh'
	@echo "PreFlight demo started in tmux session 'preflight'."
	@echo "Open http://127.0.0.1:8000/?run=R-DEMO-001"
	@echo "Attach with: tmux attach -t preflight"

demo-fg: fixtures
	$(PY) -m scripts.seed_demo --force
	$(UVICORN) app.main:app --host 127.0.0.1 --port 8000

codebase:
	$(PY) -m app.cli codebase cascade-mutual --out codebase/cascade

stop:
	-@tmux kill-session -t preflight 2>/dev/null || true
	@echo "PreFlight demo session stopped."

clean:
	rm -rf data/runs .pytest_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

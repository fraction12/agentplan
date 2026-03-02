.PHONY: test build publish install release clean

# Run full test suite
test:
	AGENTPLAN_DB=/tmp/test_agentplan.db python3 -m pytest test_agentplan.py -v

# Remove old build artifacts
clean:
	rm -rf dist/ build/ *.egg-info/

# Build wheel and tarball
build: clean
	python3 -m build

# Upload to PyPI (requires token)
publish: build
	twine upload dist/* -u __token__ -p "$$(cat ~/Documents/SECURE/PyPi\ API\ Token.rtf | strings | grep -o 'pypi-[A-Za-z0-9_-]*')"

# Update global install from freshly built wheel
install:
	pip3 install --break-system-packages --no-cache-dir $$(ls dist/agentplan-*-py3-none-any.whl | tail -1) --force-reinstall

# Full release pipeline: test → build → upload → install → tag → push
# Usage: make release V=0.4.1
release:
ifndef V
	$(error Usage: make release V=0.4.1)
endif
	@# ── Preflight checks ──
	@echo "🔍 Preflight checks..."
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "❌ Dirty working tree. Commit or stash changes first."; \
		exit 1; \
	fi
	@if ! echo "$(V)" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$$'; then \
		echo "❌ Invalid version '$(V)'. Use semver (e.g., 0.4.1)"; \
		exit 1; \
	fi
	@if git tag | grep -q "^v$(V)$$"; then \
		echo "❌ Tag v$(V) already exists."; \
		exit 1; \
	fi
	@if ! grep -q "## v$(V)" CHANGELOG.md 2>/dev/null; then \
		echo "❌ No '## v$(V)' entry in CHANGELOG.md. Update it first."; \
		exit 1; \
	fi
	@echo "✅ All checks passed"
	@# ── Bump version ──
	@echo "📝 Bumping to v$(V)..."
	@if [ "$$(uname)" = "Darwin" ]; then \
		sed -i '' 's/version = ".*"/version = "$(V)"/' pyproject.toml; \
		sed -i '' 's/__version__ = ".*"/__version__ = "$(V)"/' agentplan/cli.py; \
	else \
		sed -i 's/version = ".*"/version = "$(V)"/' pyproject.toml; \
		sed -i 's/__version__ = ".*"/__version__ = "$(V)"/' agentplan/cli.py; \
	fi
	@# ── Test ──
	@echo "🧪 Running tests..."
	$(MAKE) test
	@# ── Build + Publish ──
	@echo "📦 Building and publishing..."
	$(MAKE) publish
	@# ── Install ──
	@echo "⬇️  Updating global install..."
	$(MAKE) install
	@# ── Git: commit, tag, push ──
	@echo "🏷️  Committing and tagging..."
	git add -A
	git diff --cached --quiet || git commit -m "release: v$(V)"
	git tag -a "v$(V)" -m "Release v$(V)"
	git push origin main --tags
	@echo ""
	@echo "✅ v$(V) is live!"
	@echo "   PyPI: https://pypi.org/project/agentplan/$(V)/"
	@echo "   Tag:  https://github.com/fraction12/agentplan/releases/tag/v$(V)"

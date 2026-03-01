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

# Full release pipeline: test → build → upload → install
# Usage: make release V=0.4.1
release:
ifndef V
	$(error Usage: make release V=0.4.1)
endif
	@echo "🚀 Releasing agentplan v$(V)..."
	sed -i '' 's/version = ".*"/version = "$(V)"/' pyproject.toml
	sed -i '' 's/__version__ = ".*"/__version__ = "$(V)"/' agentplan/cli.py
	$(MAKE) test
	$(MAKE) publish
	$(MAKE) install
	git add -A
	git commit -m "release: v$(V)"
	git push origin main
	@echo "✅ v$(V) live on PyPI + GitHub"

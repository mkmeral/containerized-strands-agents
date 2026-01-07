.PHONY: install dev test build clean publish publish-test

# Install the package
install:
	pip install -e .

# Install with all dev dependencies
dev:
	pip install -e ".[dev,webui]"

# Run tests (unit tests only, no Docker required)
test:
	pytest tests/ -v --ignore=tests/test_e2e.py --ignore=tests/test_integration.py --ignore=tests/test_custom_system_prompt_integration.py

# Run all tests (requires Docker)
test-all:
	pytest tests/ -v

# Build the package
build: clean
	pip install hatch
	hatch build
	twine check dist/*

# Clean build artifacts
clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Publish to TestPyPI (for testing)
publish-test: build
	twine upload --repository testpypi dist/*

# Publish to PyPI
publish: build
	twine upload dist/*

# Build Docker image
docker:
	./scripts/build_docker.sh

# Run the MCP server
server:
	containerized-strands-agents-server

# Run the web UI
webui:
	containerized-strands-agents-webui

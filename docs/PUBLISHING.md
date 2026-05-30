# Publishing

This package uses standard PyPA build artifacts.

## Build

```bash
uv run --extra dev python -m pytest tests/unit
uv build
uv run --extra dev python -m twine check dist/*
```

## GitHub Trusted Publishing

The repository includes `.github/workflows/publish.yml`, configured for PyPI
Trusted Publishing.

Create a PyPI pending publisher with:

- Owner: `manishdighore`
- Repository: `adk-deep-agent`
- Workflow: `publish.yml`
- Environment: `pypi`

Then publish a GitHub release or run the workflow manually.

## Manual TestPyPI

```bash
uv run --extra dev python -m twine upload --repository testpypi dist/*
```

Install from TestPyPI in a clean environment:

```bash
uv pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ adk-deep-agent
```

## Manual PyPI

```bash
uv run --extra dev python -m twine upload dist/*
```

Before publishing, update `version` in `pyproject.toml` and `__version__` in
`adk_deep_agent/__init__.py`, then add a matching section to `CHANGELOG.md`.

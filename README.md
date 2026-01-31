# Vartalaap

Voice bot platform for local businesses.

## Quick start

1) Install uv
2) Install deps

```bash
uv sync --all-extras
```

3) Generate schemas (optional)

```bash
./scripts/generate.sh
```

4) Run API

```bash
uv run uvicorn src.main:app --reload
```

5) Run Admin

```bash
uv run streamlit run admin/app.py
```

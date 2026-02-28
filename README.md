# az-scout-plugin-latency-stats

Inter-region latency statistics plugin for [az-scout](https://github.com/lrivallain/az-scout).

## Features

- **Latency dataset** — static latency matrix based on [Microsoft published statistics](https://learn.microsoft.com/en-us/azure/networking/azure-network-latency)
- **API endpoints** — `POST /plugins/latency-stats/matrix` for pairwise latency matrices, `GET /plugins/latency-stats/pairs` to list all known pairs
- **MCP tool** — `region_latency(source_region, target_region)` returns indicative RTT between two Azure regions
- **UI tab** — interactive D3.js force-directed graph where regions are nodes and edges show latency in ms
- **URL hash routing** — `#latency` selects the plugin tab

## Setup

```bash
pip install az-scout-plugin-latency-stats
az-scout  # plugin is auto-discovered
```

For development:

```bash
git clone https://github.com/lrivallain/az-scout-plugin-latency-stats
cd az-scout-plugin-latency-stats
uv sync --group dev
uv pip install -e .
az-scout  # plugin is auto-discovered
```

## Structure

```
az-scout-plugin-latency-stats/
├── .github/
│   ├── copilot-instructions.md  # Copilot context for this plugin
│   └── workflows/
│       ├── ci.yml               # CI pipeline (lint + test, Python 3.11–3.13)
│       └── publish.yml          # Publish to PyPI on version tags
├── pyproject.toml
├── README.md
└── src/
    └── az_scout_latency_stats/
        ├── __init__.py          # Plugin class + module-level `plugin` instance
        ├── latency.py           # Static latency dataset + public API
        ├── routes.py            # FastAPI APIRouter (optional)
        ├── tools.py             # MCP tool functions (optional)
        └── static/
            ├── css/
            │   └── latency.css      # Plugin styles (auto-loaded via css_entry)
            ├── html/
            │   └── latency-tab.html # HTML fragment (fetched by JS at runtime)
            └── js/
                └── latency-tab.js   # Tab UI logic (auto-loaded via js_entry)
```

## How it works

1. The plugin JS loads the HTML fragment into `#plugin-tab-latency`.
2. Regions are populated from the main app's `regions` global.
3. The user selects 2+ regions and clicks **Show Latency Graph**.
4. The plugin calls `POST /plugins/latency-stats/matrix` with the selected regions.
5. A D3.js force-directed graph renders regions as nodes with RTT-labelled edges.

### API

```bash
# Pairwise matrix
curl -X POST http://localhost:8080/plugins/latency-stats/matrix \
  -H "Content-Type: application/json" \
  -d '{"regions": ["francecentral", "westeurope", "eastus"]}'

# All known pairs
curl http://localhost:8080/plugins/latency-stats/pairs
```

### MCP tool

```
region_latency(source_region="francecentral", target_region="westeurope")
```

## Quality checks

The scaffold includes GitHub Actions workflows in `.github/workflows/`:

- **`ci.yml`** — Runs lint (ruff + mypy) and tests (pytest) on Python 3.11–3.13, triggered on push/PR to `main`.
- **`publish.yml`** — Builds, creates a GitHub Release, and publishes to PyPI via trusted publishing (OIDC). Triggered on version tags (`v*`). Requires a `pypi` environment configured in your repo settings with OIDC trusted publishing.

Run the same checks locally:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
uv run pytest
```

To publish a release:

```bash
git tag v2026.2.0
git push origin v2026.2.0
```

## Copilot support

The `.github/copilot-instructions.md` file provides context to GitHub Copilot about
the plugin structure, conventions, and az-scout plugin API. It helps Copilot generate
code that follows the project patterns.

## Data source

Latency values are approximate median round-trip times from the [Azure Network Latency](https://learn.microsoft.com/en-us/azure/networking/azure-network-latency) page. Always validate with in-tenant measurements.

## License

[MIT](LICENSE.txt)

## Disclaimer

> **This tool is not affiliated with Microsoft.** All capacity, pricing, and latency information are indicative and not a guarantee of deployment success. Spot placement scores are probabilistic. Quota values and pricing are dynamic and may change between planning and actual deployment. Latency values are based on [Microsoft published statistics](https://learn.microsoft.com/en-us/azure/networking/azure-network-latency) and must be validated with in-tenant measurements.

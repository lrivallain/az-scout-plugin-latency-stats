# az-scout-plugin-latency-stats

[az-scout](https://az-scout.com) plugin for inter-region and inter-zone (Availability Zone) latency statistics.

<img width="1088" height="1361" alt="Screnshot of latency plugin" src="https://github.com/user-attachments/assets/53b51880-c2c4-4381-89eb-e5adda78de1a" />

## Features

- **Latency dataset** — static latency matrix based on [Microsoft published statistics](https://learn.microsoft.com/en-us/azure/networking/azure-network-latency)
- **Cloud63 dataset support** — optional inter-region crowd-sourced measurements via `mode="cloud63"`
- **Inter-zone dataset support** — benchmark-based AZ latency matrix from Cloud63 benchmark API
- **API endpoints** — inter-region and inter-zone endpoints for matrix and available regions
- **MCP tools** — `inter_region_latency(...)` for inter-region RTT and `inter_zone_latency(...)` for inter-zone P50 RTT latency in µs
- **UI tab** — interactive D3.js views with inter-region/inter-zone scope switch, map/table synchronization, and bidirectional hover highlighting
- **URL hash routing** — `#latency-stats` selects the plugin tab

## Setup

```bash
uv pip install az-scout-plugin-latency-stats
az-scout  # plugin is auto-discovered
```

For development:

```bash
git clone https://github.com/az-scout/az-scout-plugin-latency-stats
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
        ├── cloud63.py           # Cloud63 data fetch/cache + inter-region matrix API
        ├── inter_zone.py        # Inter-zone benchmark fetch/cache + AZ matrix API
        ├── latency.py           # Static latency dataset + public API
        ├── metadata.py          # Shared source/disclaimer/methodology constants
        ├── routes.py            # FastAPI APIRouter (optional)
        ├── tools.py             # MCP tool functions (optional)
        └── static/
            ├── css/
            │   └── latency.css      # Plugin styles (auto-loaded via css_entry)
            ├── data/
            │   └── region-coordinates.json
            ├── html/
            │   └── latency-tab.html # HTML fragment (fetched by JS at runtime)
            └── js/
                ├── latency-tab.js           # Main tab bootstrap + inter-region UI logic
                └── latency-tab-interzone.js # Inter-zone graph/table rendering + sync
```

## How it works

1. The plugin loads the HTML fragment into `#plugin-tab-latency-stats`.
2. The user selects a scope:
   - **Inter-region**: select regions and choose source mode (`azuredocs` or `cloud63`).
   - **Inter-zone (AZ)**: uses the main app region selector (`#region-select`).
3. Inter-region calls `POST /plugins/latency-stats/inter-region/matrix` and renders world map + matrix table.
4. Inter-zone calls `POST /plugins/latency-stats/inter-zone/matrix` and renders AZ graph + pair table.
5. Hover interactions are synchronized between graph links and table values in both directions.

### API

```bash
# Pairwise matrix
curl -X POST http://localhost:8080/plugins/latency-stats/inter-region/matrix \
  -H "Content-Type: application/json" \
  -d '{"regions": ["francecentral", "westeurope", "eastus"], "mode": "azuredocs"}'

# All known pairs
curl http://localhost:8080/plugins/latency-stats/inter-region/pairs

# Cloud63 available regions
curl http://localhost:8080/plugins/latency-stats/inter-region/cloud63-regions

# Inter-zone available regions
curl http://localhost:8080/plugins/latency-stats/inter-zone/regions

# Inter-zone AZ matrix
curl -X POST http://localhost:8080/plugins/latency-stats/inter-zone/matrix \
  -H "Content-Type: application/json" \
  -d '{"region": "westeurope"}'
```

### MCP tool

```
inter_region_latency(source_region="francecentral", target_region="westeurope")
inter_region_latency(source_region="francecentral", target_region="westeurope", mode="cloud63")
inter_zone_latency(region="westeurope", source_zone="az1", target_zone="az2")
```

## Quality checks

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
uv run pytest
```

## Copilot support

The `.github/copilot-instructions.md` file provides context to GitHub Copilot about
the plugin structure, conventions, and az-scout plugin API.

## Data sources

- **Azure Docs** (inter-region): [Azure Network Latency](https://learn.microsoft.com/en-us/azure/networking/azure-network-latency)
- **Cloud63** (inter-region optional mode): [Azure Latency Test](https://latency.azure.cloud63.fr/)
- **Cloud63 benchmark API** (inter-zone AZ): `https://fa-azure-network-benchmark.azurewebsites.net/api/data`

Inter-zone outputs are exposed in **microseconds** (`latencyUsP50`). Always validate with in-tenant measurements.

## License

[MIT](LICENSE.txt)

## Disclaimer

> **This tool is not affiliated with Microsoft.** All capacity, pricing, and availability information is indicative and not a guarantee of deployment success. Values are dynamic and may change between planning and actual deployment. Always validate in official Microsoft sources and in your target tenant/subscription.

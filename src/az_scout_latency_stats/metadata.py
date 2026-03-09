"""Shared metadata constants for latency API routes and MCP tools."""

AZUREDOCS_SOURCE = "https://learn.microsoft.com/en-us/azure/networking/azure-network-latency"
CLOUD63_SOURCE = "https://latency.azure.cloud63.fr/"
INTRA_ZONE_SOURCE = "https://fa-azure-network-benchmark.azurewebsites.net/api/data"

AZUREDOCS_DISCLAIMER = (
    "Latency values are indicative and must be validated with in-tenant measurements."
)

CLOUD63_DISCLAIMER = (
    "Cloud63 latency values are crowd-sourced measurements. Validate with in-tenant measurements."
)

INTRA_ZONE_DISCLAIMER = (
    "Intra-zone latency values are indicative benchmark data based on physical AZ identifiers. "
    "Do NOT remap through logical-to-physical zone mappings. "
    "Validate with in-tenant measurements."
)

INTRA_ZONE_METHODOLOGY = "P50 RTT (sum of directional medians, microseconds) between physical AZs"

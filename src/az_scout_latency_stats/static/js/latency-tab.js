// Latency Stats plugin — D3.js force-directed graph
// Renders an interactive graph: regions = nodes, edges = pairwise RTT (ms).
// Uses the same colour palette as the core AZ topology graph.
(function () {
    const PLUGIN_NAME = "latency-stats";
    const container = document.getElementById("plugin-tab-" + PLUGIN_NAME);
    if (!container) return;

    // Colour palette matching the core AZ topology graph
    const REGION_COLORS = [
        "#0078d4", "#107c10", "#d83b01", "#8764b8",
        "#008272", "#b4009e", "#ca5010", "#0063b1",
        "#498205", "#c239b3",
    ];

    // -----------------------------------------------------------------------
    // 1. Load HTML fragment
    // -----------------------------------------------------------------------
    fetch(`/plugins/${PLUGIN_NAME}/static/html/latency-tab.html`)
        .then(resp => resp.text())
        .then(html => {
            container.innerHTML = html;
            initLatencyPlugin();
        })
        .catch(err => {
            container.innerHTML = `<div class="alert alert-danger">Failed to load plugin UI: ${err.message}</div>`;
        });

    // -----------------------------------------------------------------------
    // 2. Plugin initialisation
    // -----------------------------------------------------------------------
    function initLatencyPlugin() {
        const regionSelect = document.getElementById("latency-region-select");
        const btn          = document.getElementById("latency-btn");
        const graphEl      = document.getElementById("latency-graph-container");
        const legendEl     = document.getElementById("latency-legend");

        // Populate region select from the main app's regions global
        function populateRegions() {
            const regionList = (typeof regions !== "undefined" ? regions : []);
            regionSelect.innerHTML = "";
            if (!regionList.length) {
                regionSelect.innerHTML = '<option value="" disabled>No regions available</option>';
                return;
            }
            regionList.forEach(r => {
                const opt = document.createElement("option");
                opt.value = r.name;
                opt.textContent = r.displayName || r.name;
                regionSelect.appendChild(opt);
            });
        }

        // Enable button when >= 2 regions selected
        regionSelect.addEventListener("change", () => {
            const selected = Array.from(regionSelect.selectedOptions).map(o => o.value);
            btn.disabled = selected.length < 2;
        });

        // React to tenant changes (regions list refreshes)
        const tenantEl = document.getElementById("tenant-select");
        if (tenantEl) {
            tenantEl.addEventListener("change", () => {
                // Wait a tick for regions to update
                setTimeout(populateRegions, 500);
            });
        }

        // React to region selector updates via MutationObserver
        const regionEl = document.getElementById("region-select");
        if (regionEl) {
            const obs = new MutationObserver(() => populateRegions());
            obs.observe(regionEl, { attributes: true, attributeFilter: ["value"] });
        }

        // -----------------------------------------------------------------
        // Fetch matrix & render
        // -----------------------------------------------------------------
        btn.addEventListener("click", async () => {
            const selected = Array.from(regionSelect.selectedOptions).map(o => o.value);
            if (selected.length < 2) return;

            graphEl.innerHTML = '<p class="text-body-secondary text-center py-3">Loading…</p>';
            legendEl.innerHTML = "";

            try {
                const data = await apiPost(`/plugins/${PLUGIN_NAME}/matrix`, { regions: selected });
                renderLatencyGraph(data, graphEl, legendEl);
            } catch (e) {
                graphEl.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
            }
        });

        // Initial population
        populateRegions();
    }

    // -----------------------------------------------------------------------
    // 3. D3.js force-directed graph renderer
    // -----------------------------------------------------------------------
    function renderLatencyGraph(data, graphEl, legendEl) {
        graphEl.innerHTML = "";
        legendEl.innerHTML = "";

        const regionNames = data.regions || [];
        const matrix = data.matrix || [];
        if (regionNames.length < 2) {
            graphEl.innerHTML = '<p class="text-body-secondary text-center">Select at least 2 regions.</p>';
            return;
        }

        // Build nodes & links
        const colorScale = d3.scaleOrdinal(REGION_COLORS).domain(regionNames);
        const nodes = regionNames.map((name, i) => ({ id: name, index: i }));
        const links = [];
        for (let i = 0; i < regionNames.length; i++) {
            for (let j = i + 1; j < regionNames.length; j++) {
                const rtt = matrix[i][j];
                if (rtt !== null && rtt !== undefined) {
                    links.push({
                        source: regionNames[i],
                        target: regionNames[j],
                        rtt: rtt,
                    });
                }
            }
        }

        if (!links.length) {
            graphEl.innerHTML = '<p class="text-body-secondary text-center py-3">No known latency data between selected regions.</p>';
            return;
        }

        // RTT range for visual scaling
        const rttValues = links.map(l => l.rtt).filter(v => v > 0);
        const minRtt = Math.min(...rttValues, 1);
        const maxRtt = Math.max(...rttValues, 1);
        const rttColorScale = d3.scaleSequential(d3.interpolateRdYlGn)
            .domain([maxRtt, minRtt]); // reversed: low latency = green

        // SVG dimensions
        const width = 800;
        const height = Math.max(450, regionNames.length * 50);
        const nodeRadius = 22;

        const svg = d3.select(graphEl).append("svg")
            .attr("viewBox", `0 0 ${width} ${height}`)
            .attr("preserveAspectRatio", "xMidYMid meet");

        // Force simulation
        const simulation = d3.forceSimulation(nodes)
            .force("link", d3.forceLink(links).id(d => d.id)
                .distance(d => 60 + d.rtt * 1.5)
                .strength(0.4))
            .force("charge", d3.forceManyBody().strength(-400))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collision", d3.forceCollide(nodeRadius + 10));

        // Links
        const linkGroup = svg.append("g").attr("class", "latency-links");
        const linkElements = linkGroup.selectAll("line")
            .data(links).enter().append("line")
            .attr("class", "latency-link")
            .attr("stroke", d => rttColorScale(d.rtt))
            .attr("stroke-width", d => {
                // Thicker line = lower latency (better)
                const norm = 1 - (d.rtt - minRtt) / (maxRtt - minRtt || 1);
                return 1.5 + norm * 3;
            });

        // Edge label backgrounds & labels
        const edgeLabelGroup = svg.append("g").attr("class", "latency-edge-labels");
        const edgeLabelBgs = edgeLabelGroup.selectAll("rect")
            .data(links).enter().append("rect")
            .attr("class", "latency-edge-bg")
            .attr("width", d => String(d.rtt + " ms").length * 7 + 6)
            .attr("height", 14);
        const edgeLabels = edgeLabelGroup.selectAll("text")
            .data(links).enter().append("text")
            .attr("class", "latency-edge-label")
            .text(d => d.rtt + " ms");

        // Nodes
        const nodeGroup = svg.append("g").attr("class", "latency-nodes");
        const nodeElements = nodeGroup.selectAll("g")
            .data(nodes).enter().append("g")
            .attr("class", "latency-node")
            .style("cursor", "pointer")
            .call(d3.drag()
                .on("start", dragStarted)
                .on("drag", dragged)
                .on("end", dragEnded));

        nodeElements.append("circle")
            .attr("r", nodeRadius)
            .attr("class", "latency-node-circle")
            .attr("fill", d => colorScale(d.id) + "30")
            .attr("stroke", d => colorScale(d.id));

        nodeElements.append("text")
            .attr("class", "latency-node-label")
            .attr("text-anchor", "middle")
            .attr("dy", "0.35em")
            .text(d => d.id.length > 14 ? d.id.slice(0, 12) + "…" : d.id);

        // Tooltip (full name)
        nodeElements.append("title").text(d => d.id);

        // Hover highlighting
        nodeElements.on("mouseenter", function (event, d) {
            const connectedLinks = links.filter(l =>
                l.source.id === d.id || l.target.id === d.id
            );
            const connectedNodes = new Set();
            connectedNodes.add(d.id);
            connectedLinks.forEach(l => {
                connectedNodes.add(l.source.id);
                connectedNodes.add(l.target.id);
            });

            linkElements
                .classed("highlighted", l => l.source.id === d.id || l.target.id === d.id)
                .classed("dimmed", l => l.source.id !== d.id && l.target.id !== d.id);
            edgeLabels
                .classed("highlighted", l => l.source.id === d.id || l.target.id === d.id)
                .classed("dimmed", l => l.source.id !== d.id && l.target.id !== d.id);
            edgeLabelBgs
                .classed("dimmed", l => l.source.id !== d.id && l.target.id !== d.id);
            nodeElements.style("opacity", n => connectedNodes.has(n.id) ? 1 : 0.2);
        });

        nodeElements.on("mouseleave", function () {
            linkElements.classed("highlighted", false).classed("dimmed", false);
            edgeLabels.classed("highlighted", false).classed("dimmed", false);
            edgeLabelBgs.classed("dimmed", false);
            nodeElements.style("opacity", 1);
        });

        // Simulation tick
        simulation.on("tick", () => {
            // Constrain nodes within SVG bounds
            nodes.forEach(d => {
                d.x = Math.max(nodeRadius, Math.min(width - nodeRadius, d.x));
                d.y = Math.max(nodeRadius, Math.min(height - nodeRadius, d.y));
            });

            linkElements
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            const labelW = d => String(d.rtt + " ms").length * 7 + 6;
            edgeLabelBgs
                .attr("x", d => (d.source.x + d.target.x) / 2 - labelW(d) / 2)
                .attr("y", d => (d.source.y + d.target.y) / 2 - 7);
            edgeLabels
                .attr("x", d => (d.source.x + d.target.x) / 2)
                .attr("y", d => (d.source.y + d.target.y) / 2 + 4);

            nodeElements.attr("transform", d => `translate(${d.x},${d.y})`);
        });

        // Drag handlers
        function dragStarted(event, d) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }
        function dragged(event, d) {
            d.fx = event.x;
            d.fy = event.y;
        }
        function dragEnded(event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }

        // Legend
        const knownCount = links.length;
        const totalPossible = regionNames.length * (regionNames.length - 1) / 2;
        const unknownCount = totalPossible - knownCount;
        legendEl.innerHTML = `
            <span>${regionNames.length} regions</span> ·
            <span>${knownCount} known pairs</span>
            ${unknownCount > 0 ? `· <span class="text-warning">${unknownCount} unknown</span>` : ""} ·
            <span style="color:${rttColorScale(minRtt)}">●</span> ${minRtt} ms (min) –
            <span style="color:${rttColorScale(maxRtt)}">●</span> ${maxRtt} ms (max)
        `;
    }
})();

// Latency Stats plugin — D3.js geo map
// Renders an interactive world map: regions = dots, edges = great-circle arcs
// coloured by pairwise RTT (ms).
(function () {
    const PLUGIN_NAME = "latency-stats";
    const TAB_ID = "latency";
    const container = document.getElementById("plugin-tab-" + TAB_ID);
    if (!container) return;

    const WORLD_TOPO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";
    const TOPOJSON_CDN = "https://cdn.jsdelivr.net/npm/topojson-client@3/dist/topojson-client.min.js";
    const COORDS_URL = `/plugins/${PLUGIN_NAME}/static/data/region-coordinates.json`;

    // Dynamically load topojson-client if not already available
    function ensureTopojson() {
        if (typeof topojson !== "undefined") return Promise.resolve();
        return new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = TOPOJSON_CDN;
            script.onload = resolve;
            script.onerror = () => reject(new Error("Failed to load topojson-client library"));
            document.head.appendChild(script);
        });
    }

    // Colour palette for region dots
    const REGION_COLORS = [
        "#0078d4", "#107c10", "#d83b01", "#8764b8",
        "#008272", "#b4009e", "#ca5010", "#0063b1",
        "#498205", "#c239b3",
    ];

    // Cache for loaded data
    let regionCoords = null;
    let worldTopo = null;

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
        const regionSelect  = document.getElementById("latency-region-select");
        const filterInput   = document.getElementById("latency-region-filter");
        const btn           = document.getElementById("latency-btn");
        const mapEl         = document.getElementById("latency-map-container");
        const legendEl      = document.getElementById("latency-legend");
        const tableEl       = document.getElementById("latency-table-container");
        const toggleBtn     = document.getElementById("latency-selector-toggle");
        const popover       = document.getElementById("latency-selector-popover");
        const selBadge      = document.getElementById("latency-selection-badge");

        // Start with popover open (no regions selected yet)
        popover.classList.add("open");

        // Toggle region picker popover
        toggleBtn.addEventListener("click", () => {
            popover.classList.toggle("open");
            if (popover.classList.contains("open")) filterInput.focus();
        });

        // Close popover on outside click — only if at least one region is selected
        document.addEventListener("click", (e) => {
            const selected = Array.from(regionSelect.selectedOptions);
            if (selected.length === 0) return; // keep open until something is selected
            if (!popover.contains(e.target) && e.target !== toggleBtn && !toggleBtn.contains(e.target)) {
                popover.classList.remove("open");
            }
        });

        // Pre-load topojson lib, coordinates, and world topology in parallel
        ensureTopojson().then(() => Promise.all([
            fetch(COORDS_URL).then(r => r.json()),
            fetch(WORLD_TOPO_URL).then(r => r.json()),
        ])).then(([coords, topo]) => {
            regionCoords = coords;
            worldTopo = topo;
            populateRegions();
            renderEmptyMap(mapEl);
        }).catch(err => {
            console.warn("Failed to preload map data:", err);
        });

        // Sorted region list cache for filtering
        let allRegionEntries = [];

        // Populate region select from the plugin's own coordinates data
        function populateRegions(filter) {
            const previousSelection = new Set(
                Array.from(regionSelect.selectedOptions).map(o => o.value)
            );
            regionSelect.innerHTML = "";
            if (!regionCoords || !Object.keys(regionCoords).length) {
                regionSelect.innerHTML = '<option value="" disabled>Loading regions…</option>';
                return;
            }
            if (!allRegionEntries.length) {
                allRegionEntries = Object.entries(regionCoords)
                    .sort((a, b) => a[1].displayName.localeCompare(b[1].displayName));
            }
            const q = (filter || "").toLowerCase();
            allRegionEntries.forEach(([name, info]) => {
                const display = info.displayName || name;
                if (q && !display.toLowerCase().includes(q) && !name.toLowerCase().includes(q)) return;
                const opt = document.createElement("option");
                opt.value = name;
                opt.textContent = display;
                if (previousSelection.has(name)) opt.selected = true;
                regionSelect.appendChild(opt);
            });
        }

        // Filter input handler
        filterInput.addEventListener("input", () => {
            populateRegions(filterInput.value);
        });

        // Enable button when >= 2 regions selected, update badge
        regionSelect.addEventListener("change", () => {
            const selected = Array.from(regionSelect.selectedOptions).map(o => o.value);
            btn.disabled = selected.length < 2;
            selBadge.textContent = selected.length
                ? `${selected.length} region${selected.length > 1 ? "s" : ""} selected`
                : "";
        });

        // -----------------------------------------------------------------
        // Fetch matrix & render
        // -----------------------------------------------------------------
        btn.addEventListener("click", async () => {
            const selected = Array.from(regionSelect.selectedOptions).map(o => o.value);
            if (selected.length < 2) return;

            mapEl.innerHTML = '<p class="text-body-secondary text-center py-3">Loading…</p>';
            legendEl.innerHTML = "";
            tableEl.innerHTML = "";

            try {
                // Ensure topojson lib and map data are loaded
                await ensureTopojson();
                if (!regionCoords || !worldTopo) {
                    const [coords, topo] = await Promise.all([
                        fetch(COORDS_URL).then(r => r.json()),
                        fetch(WORLD_TOPO_URL).then(r => r.json()),
                    ]);
                    regionCoords = coords;
                    worldTopo = topo;
                }

                const data = await apiPost(`/plugins/${PLUGIN_NAME}/matrix`, { regions: selected });
                renderLatencyMap(data, mapEl, legendEl);
                renderLatencyTable(data, tableEl);
            } catch (e) {
                mapEl.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
            }
        });
    }

    // -----------------------------------------------------------------------
    // 2b. Empty world map (shown before any region is selected)
    // -----------------------------------------------------------------------
    function renderEmptyMap(mapEl) {
        mapEl.innerHTML = "";
        if (!worldTopo) return;

        const width = 960;
        const height = 500;

        const projection = d3.geoNaturalEarth1()
            .translate([width / 2, height / 2])
            .scale(153);

        const pathGen = d3.geoPath().projection(projection);

        const svg = d3.select(mapEl).append("svg")
            .attr("viewBox", `0 0 ${width} ${height}`)
            .attr("preserveAspectRatio", "xMidYMid meet")
            .attr("class", "latency-map-svg");

        const countries = topojson.feature(worldTopo, worldTopo.objects.countries);
        svg.append("g")
            .attr("class", "latency-map-land")
            .selectAll("path")
            .data(countries.features)
            .enter().append("path")
            .attr("d", pathGen);

        const borders = topojson.mesh(worldTopo, worldTopo.objects.countries, (a, b) => a !== b);
        svg.append("path")
            .datum(borders)
            .attr("class", "latency-map-borders")
            .attr("d", pathGen);
    }

    // -----------------------------------------------------------------------
    // 3. D3.js geo map renderer
    // -----------------------------------------------------------------------
    function renderLatencyMap(data, mapEl, legendEl) {
        mapEl.innerHTML = "";
        legendEl.innerHTML = "";

        const regionNames = data.regions || [];
        const matrix = data.matrix || [];
        if (regionNames.length < 2) {
            mapEl.innerHTML = '<p class="text-body-secondary text-center">Select at least 2 regions.</p>';
            return;
        }

        // Build nodes with geo coordinates
        const colorScale = d3.scaleOrdinal(REGION_COLORS).domain(regionNames);
        const nodes = [];
        const missingCoords = [];
        for (const name of regionNames) {
            const coord = regionCoords[name];
            if (coord) {
                nodes.push({ id: name, lon: coord.lon, lat: coord.lat, displayName: coord.displayName });
            } else {
                missingCoords.push(name);
            }
        }

        if (missingCoords.length) {
            console.warn("Missing coordinates for regions:", missingCoords);
        }

        // Build links
        const links = [];
        for (let i = 0; i < regionNames.length; i++) {
            for (let j = i + 1; j < regionNames.length; j++) {
                const rtt = matrix[i][j];
                if (rtt !== null && rtt !== undefined) {
                    const srcCoord = regionCoords[regionNames[i]];
                    const tgtCoord = regionCoords[regionNames[j]];
                    if (srcCoord && tgtCoord) {
                        links.push({
                            source: regionNames[i],
                            target: regionNames[j],
                            rtt,
                            srcLon: srcCoord.lon, srcLat: srcCoord.lat,
                            tgtLon: tgtCoord.lon, tgtLat: tgtCoord.lat,
                        });
                    }
                }
            }
        }

        if (!nodes.length) {
            mapEl.innerHTML = '<p class="text-body-secondary text-center py-3">No coordinate data for selected regions.</p>';
            return;
        }

        // RTT colour scale
        const rttValues = links.map(l => l.rtt).filter(v => v > 0);
        const minRtt = Math.min(...rttValues, 1);
        const maxRtt = Math.max(...rttValues, 1);
        const rttColorScale = d3.scaleSequential(d3.interpolateRdYlGn)
            .domain([maxRtt, minRtt]); // low latency → green

        // SVG dimensions
        const width = 960;
        const height = 500;

        // Find the optimal centre longitude that minimises the angular span
        // of all selected regions — handles the antimeridian (e.g. US West + Japan).
        const lons = nodes.map(n => n.lon);
        const lats = nodes.map(n => n.lat);

        function bestCenterLon(longitudes) {
            // Sort longitudes, find the largest gap, and centre opposite to it.
            const sorted = [...longitudes].sort((a, b) => a - b);
            if (sorted.length === 1) return sorted[0];
            let maxGap = 0;
            let gapAfterIdx = 0;
            for (let i = 0; i < sorted.length; i++) {
                const next = (i + 1) % sorted.length;
                let gap = sorted[next] - sorted[i];
                if (next === 0) gap += 360; // wrap around
                if (gap > maxGap) {
                    maxGap = gap;
                    gapAfterIdx = i;
                }
            }
            // Centre is opposite the midpoint of the largest gap
            const gapMid = sorted[gapAfterIdx] + maxGap / 2;
            let center = gapMid + 180;
            if (center > 180) center -= 360;
            return center;
        }

        const centLon = bestCenterLon(lons);
        const centLat = (Math.min(...lats) + Math.max(...lats)) / 2;

        const projection = d3.geoNaturalEarth1()
            .rotate([-centLon, 0])
            .center([0, centLat])
            .translate([width / 2, height / 2]);

        // Auto-fit: scale to encompass all nodes with padding
        const padding = 80;
        const testPoints = nodes.map(n => projection([n.lon, n.lat]));
        const xExtent = d3.extent(testPoints, p => p[0]);
        const yExtent = d3.extent(testPoints, p => p[1]);
        const dataW = (xExtent[1] - xExtent[0]) || 1;
        const dataH = (yExtent[1] - yExtent[0]) || 1;
        const scaleFactor = Math.min(
            (width - 2 * padding) / dataW,
            (height - 2 * padding) / dataH
        );
        const currentScale = projection.scale();
        projection.scale(currentScale * scaleFactor);

        // Recenter after rescaling
        const afterPoints = nodes.map(n => projection([n.lon, n.lat]));
        const cx = d3.mean(afterPoints, p => p[0]);
        const cy = d3.mean(afterPoints, p => p[1]);
        const [tx, ty] = projection.translate();
        projection.translate([tx + (width / 2 - cx), ty + (height / 2 - cy)]);

        const pathGen = d3.geoPath().projection(projection);

        const svg = d3.select(mapEl).append("svg")
            .attr("viewBox", `0 0 ${width} ${height}`)
            .attr("preserveAspectRatio", "xMidYMid meet")
            .attr("class", "latency-map-svg");

        // World basemap
        const countries = topojson.feature(worldTopo, worldTopo.objects.countries);
        svg.append("g")
            .attr("class", "latency-map-land")
            .selectAll("path")
            .data(countries.features)
            .enter().append("path")
            .attr("d", pathGen);

        // Country borders
        const borders = topojson.mesh(worldTopo, worldTopo.objects.countries, (a, b) => a !== b);
        svg.append("path")
            .datum(borders)
            .attr("class", "latency-map-borders")
            .attr("d", pathGen);

        // Latency arcs (great-circle lines)
        const arcGroup = svg.append("g").attr("class", "latency-arcs");
        const arcElements = arcGroup.selectAll("path")
            .data(links).enter().append("path")
            .attr("class", "latency-arc")
            .attr("d", d => {
                const lineGeo = {
                    type: "LineString",
                    coordinates: [[d.srcLon, d.srcLat], [d.tgtLon, d.tgtLat]],
                };
                return pathGen(lineGeo);
            })
            .attr("stroke", d => rttColorScale(d.rtt))
            .attr("stroke-width", d => {
                const norm = 1 - (d.rtt - minRtt) / (maxRtt - minRtt || 1);
                return 1.5 + norm * 2.5;
            });

        // Arc labels (RTT values at midpoint)
        const labelGroup = svg.append("g").attr("class", "latency-arc-labels");
        const labelBgs = labelGroup.selectAll("rect")
            .data(links).enter().append("rect")
            .attr("class", "latency-arc-label-bg");
        const labelTexts = labelGroup.selectAll("text")
            .data(links).enter().append("text")
            .attr("class", "latency-arc-label")
            .text(d => d.rtt + " ms");

        // Position arc labels on the rendered SVG path.
        // Preferred: path geometric midpoint. If that point is off-screen
        // (arc wraps around the map edge), walk along the path to find the
        // best visible point that is still ON the arc.
        arcElements.each(function (d, i) {
            const pathNode = this;
            const totalLen = pathNode.getTotalLength();
            const text = d.rtt + " ms";
            const textW = text.length * 7 + 6;
            const margin = 10;

            function isVisible(x, y) {
                return x >= -textW && x <= width + textW &&
                       y >= -14 && y <= height + 14;
            }

            const mid = pathNode.getPointAtLength(totalLen / 2);
            let lx = mid.x;
            let ly = mid.y;

            if (!isVisible(lx, ly)) {
                // Walk along the path in small steps and collect all visible
                // points. Among them pick the one closest to the 50 % mark.
                const samples = 100;
                let bestDist = Infinity;
                let bestPt = null;
                for (let s = 0; s <= samples; s++) {
                    const pt = pathNode.getPointAtLength((s / samples) * totalLen);
                    if (isVisible(pt.x, pt.y)) {
                        const dist = Math.abs(s / samples - 0.5);
                        if (dist < bestDist) {
                            bestDist = dist;
                            bestPt = pt;
                        }
                    }
                }
                if (bestPt) {
                    lx = bestPt.x;
                    ly = bestPt.y;
                }
                // else keep original (clamped below)
            }

            // Clamp within SVG bounds
            lx = Math.max(margin + textW / 2, Math.min(width - margin - textW / 2, lx));
            ly = Math.max(margin + 7, Math.min(height - margin - 7, ly));

            d3.select(labelBgs.nodes()[i])
                .attr("x", lx - textW / 2)
                .attr("y", ly - 7)
                .attr("width", textW)
                .attr("height", 14);
            d3.select(labelTexts.nodes()[i])
                .attr("x", lx)
                .attr("y", ly + 4);
        });

        // Region dots
        const dotGroup = svg.append("g").attr("class", "latency-dots");
        const dotElements = dotGroup.selectAll("g")
            .data(nodes).enter().append("g")
            .attr("class", "latency-dot")
            .attr("transform", d => {
                const p = projection([d.lon, d.lat]);
                return `translate(${p[0]},${p[1]})`;
            })
            .style("cursor", "pointer");

        dotElements.append("circle")
            .attr("r", 7)
            .attr("class", "latency-dot-circle")
            .attr("fill", d => colorScale(d.id))
            .attr("stroke", d => colorScale(d.id));

        dotElements.append("text")
            .attr("class", "latency-dot-label")
            .attr("dx", 10)
            .attr("dy", 4)
            .text(d => d.displayName || d.id);

        // Tooltip
        dotElements.append("title").text(d => d.displayName || d.id);

        // Hover highlighting
        dotElements.on("mouseenter", function (event, d) {
            const connectedLinks = links.filter(l =>
                l.source === d.id || l.target === d.id
            );
            const connectedNodes = new Set([d.id]);
            connectedLinks.forEach(l => {
                connectedNodes.add(l.source);
                connectedNodes.add(l.target);
            });

            arcElements
                .classed("highlighted", l => l.source === d.id || l.target === d.id)
                .classed("dimmed", l => l.source !== d.id && l.target !== d.id);
            labelTexts
                .classed("highlighted", l => l.source === d.id || l.target === d.id)
                .classed("dimmed", l => l.source !== d.id && l.target !== d.id);
            labelBgs
                .classed("dimmed", l => l.source !== d.id && l.target !== d.id);
            dotElements.style("opacity", n => connectedNodes.has(n.id) ? 1 : 0.25);
        });

        dotElements.on("mouseleave", function () {
            arcElements.classed("highlighted", false).classed("dimmed", false);
            labelTexts.classed("highlighted", false).classed("dimmed", false);
            labelBgs.classed("dimmed", false);
            dotElements.style("opacity", 1);
        });

        // Legend
        const knownCount = links.length;
        const totalPossible = regionNames.length * (regionNames.length - 1) / 2;
        const unknownCount = totalPossible - knownCount;
        // Build gradient stops for the legend bar
        const gradStops = [];
        for (let p = 0; p <= 100; p += 5) {
            const rttVal = minRtt + (p / 100) * (maxRtt - minRtt);
            gradStops.push(`${rttColorScale(rttVal)} ${p}%`);
        }
        legendEl.innerHTML = `
            <span>${regionNames.length} regions</span> ·
            <span>${knownCount} known pairs</span>
            ${unknownCount > 0 ? `· <span class="text-warning">${unknownCount} unknown</span>` : ""}
            ${missingCoords.length ? `· <span class="text-warning">${missingCoords.length} region(s) not on map</span>` : ""}
            <div class="latency-legend-bar">
                <div>
                    <div class="latency-legend-gradient" style="background: linear-gradient(to right, ${gradStops.join(", ")})"></div>
                    <div class="latency-legend-labels"><span>${minRtt} ms</span><span>${maxRtt} ms</span></div>
                </div>
            </div>
        `;
    }
    // -----------------------------------------------------------------------
    // 4. Latency table renderer
    // -----------------------------------------------------------------------
    function renderLatencyTable(data, tableEl) {
        tableEl.innerHTML = "";

        const regionNames = data.regions || [];
        const matrix = data.matrix || [];
        if (regionNames.length < 2) return;

        // Get display names from coordinates
        const displayName = (name) => {
            if (regionCoords && regionCoords[name]) return regionCoords[name].displayName;
            return name;
        };

        // RTT colour scale for cell backgrounds
        const allRtt = [];
        for (let i = 0; i < regionNames.length; i++) {
            for (let j = 0; j < regionNames.length; j++) {
                if (i !== j && matrix[i][j] !== null && matrix[i][j] !== undefined) {
                    allRtt.push(matrix[i][j]);
                }
            }
        }
        const minRtt = Math.min(...allRtt, 1);
        const maxRtt = Math.max(...allRtt, 1);
        const rttColorScale = d3.scaleSequential(d3.interpolateRdYlGn)
            .domain([maxRtt, minRtt]);

        const table = document.createElement("table");
        table.className = "latency-table";

        // Header row
        const thead = document.createElement("thead");
        const headerRow = document.createElement("tr");
        headerRow.appendChild(document.createElement("th")); // empty corner
        regionNames.forEach(name => {
            const th = document.createElement("th");
            th.textContent = displayName(name);
            th.title = name;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        // Body rows
        const tbody = document.createElement("tbody");
        regionNames.forEach((rowName, i) => {
            const tr = document.createElement("tr");
            const rowHeader = document.createElement("th");
            rowHeader.textContent = displayName(rowName);
            rowHeader.title = rowName;
            tr.appendChild(rowHeader);

            regionNames.forEach((colName, j) => {
                const td = document.createElement("td");
                if (i === j) {
                    td.textContent = "—";
                    td.className = "latency-cell-self";
                } else {
                    const rtt = matrix[i][j];
                    if (rtt !== null && rtt !== undefined) {
                        const span = document.createElement("span");
                        span.textContent = rtt + " ms";
                        td.appendChild(span);

                        const copyBtn = document.createElement("button");
                        copyBtn.className = "latency-copy-btn";
                        copyBtn.setAttribute("data-bs-toggle", "tooltip");
                        copyBtn.setAttribute("data-bs-placement", "top");
                        copyBtn.setAttribute("data-bs-title", "Copy to clipboard");
                        copyBtn.innerHTML = '<i class="bi bi-clipboard"></i>';
                        const clipText = `${displayName(rowName)} \u2192 ${displayName(colName)}: ${rtt}ms`;
                        copyBtn.addEventListener("click", (e) => {
                            e.stopPropagation();
                            navigator.clipboard.writeText(clipText).then(() => {
                                copyBtn.innerHTML = '<i class="bi bi-check2"></i>';
                                const tip = bootstrap.Tooltip.getInstance(copyBtn);
                                if (tip) { tip.setContent({ ".tooltip-inner": "Copied!" }); }
                                setTimeout(() => {
                                    copyBtn.innerHTML = '<i class="bi bi-clipboard"></i>';
                                    if (tip) { tip.setContent({ ".tooltip-inner": "Copy to clipboard" }); }
                                }, 1200);
                            });
                        });
                        td.appendChild(copyBtn);

                        td.style.backgroundColor = rttColorScale(rtt) + "55";
                        td.style.color = "inherit";
                    } else {
                        td.textContent = "—";
                        td.className = "latency-cell-unknown";
                    }
                }
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);

        tableEl.appendChild(table);

        // Initialize Bootstrap tooltips on copy buttons
        tableEl.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
            new bootstrap.Tooltip(el, { trigger: "hover" });
        });

        // Cross-hair highlight: hovered cell + its row header and column header
        const headerCells = thead.querySelectorAll("th");

        tbody.addEventListener("mouseover", (e) => {
            const td = e.target.closest("td");
            if (!td) return;
            const tr = td.parentElement;
            const colIdx = Array.from(tr.children).indexOf(td);

            // Highlight the hovered cell
            td.classList.add("latency-cell-active");
            // Highlight the row header (first child = th)
            const rowTh = tr.querySelector("th");
            if (rowTh) rowTh.classList.add("latency-header-highlight");
            // Highlight the column header
            if (headerCells[colIdx]) headerCells[colIdx].classList.add("latency-header-highlight");
        });

        tbody.addEventListener("mouseout", (e) => {
            const td = e.target.closest("td");
            if (!td) return;
            const tr = td.parentElement;
            const colIdx = Array.from(tr.children).indexOf(td);

            td.classList.remove("latency-cell-active");
            const rowTh = tr.querySelector("th");
            if (rowTh) rowTh.classList.remove("latency-header-highlight");
            if (headerCells[colIdx]) headerCells[colIdx].classList.remove("latency-header-highlight");
        });
    }
})();

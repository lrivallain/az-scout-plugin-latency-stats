// Latency Stats plugin — D3.js geo map
// Renders an interactive world map: regions = dots, edges = great-circle arcs
// coloured by pairwise RTT (ms).
(function () {
    const PLUGIN_NAME = "latency-stats";
    const TAB_ID = "latency-stats";
    const container = document.getElementById("plugin-tab-" + TAB_ID);
    if (!container) return;

    const WORLD_TOPO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";
    const TOPOJSON_CDN = "https://cdn.jsdelivr.net/npm/topojson-client@3/dist/topojson-client.min.js";
    const COORDS_URL = `/plugins/${PLUGIN_NAME}/static/data/region-coordinates.json`;
    const INTERZONE_MODULE_URL = `/plugins/${PLUGIN_NAME}/static/js/latency-tab-interzone.js`;

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

    function ensureScript(url, globalSymbol) {
        if (globalSymbol && typeof window[globalSymbol] !== "undefined") return Promise.resolve();
        return new Promise((resolve, reject) => {
            const existing = document.querySelector(`script[src="${url}"]`);
            if (existing) {
                existing.addEventListener("load", () => resolve());
                existing.addEventListener("error", () => reject(new Error(`Failed to load ${url}`)));
                return;
            }
            const script = document.createElement("script");
            script.src = url;
            script.onload = resolve;
            script.onerror = () => reject(new Error(`Failed to load ${url}`));
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

    // Shared state for cross-highlighting between map and table
    let _mapSelections = null;   // { arcElements, flowDots, labelTexts, labelBgs, dotElements, links }
    let _tableEl = null;         // <div> that contains the rendered table

    // -----------------------------------------------------------------------
    // 1. Load HTML fragment
    // -----------------------------------------------------------------------
    fetch(`/plugins/${PLUGIN_NAME}/static/html/latency-tab.html`)
        .then(resp => resp.text())
        .then(async html => {
            container.innerHTML = html;
            await ensureScript(INTERZONE_MODULE_URL, "LatencyStatsIntra");
            initLatencyPlugin();
        })
        .catch(err => {
            container.innerHTML = `<div class="alert alert-danger">Failed to load plugin UI: ${err.message}</div>`;
        });

    // -----------------------------------------------------------------------
    // 2. Plugin initialisation
    // -----------------------------------------------------------------------
    function initLatencyPlugin() {
        const regionList     = document.getElementById("latency-region-list");
        const filterInput   = document.getElementById("latency-region-filter");
        const selectAllBtn  = document.getElementById("latency-select-all-btn");
        const deselectAllBtn = document.getElementById("latency-deselect-all-btn");
        const mapEl         = document.getElementById("latency-map-container");
        const legendEl      = document.getElementById("latency-legend");
        const tableEl       = document.getElementById("latency-table-container");
        const toggleBtn     = document.getElementById("latency-selector-toggle");
        const popover       = document.getElementById("latency-selector-popover");
        const selBadge      = document.getElementById("latency-selection-badge");
        const sourceText    = document.getElementById("latency-source-text");
        const interModeEl   = document.getElementById("latency-inter-mode");
        const interzoneModeEl   = document.getElementById("latency-interzone-mode");
        const interzoneGraphEl  = document.getElementById("latency-interzone-graph-container");
        const interzoneTableEl  = document.getElementById("latency-interzone-table-container");
        const interzoneRegionEl = document.getElementById("latency-interzone-region-current");
        const interzoneStatusEl = document.getElementById("latency-interzone-status");
        const coreRegionSelect = document.getElementById("region-select");
        const scopeRadios = document.querySelectorAll('input[name="latency-scope"]');
        const selectedRegions = new Set(); // persists across filter rebuilds

        // Mode toggle (azuredocs / cloud63)
        const modeRadios = document.querySelectorAll('input[name="latency-mode"]');

        function getScope() {
            const checked = document.querySelector('input[name="latency-scope"]:checked');
            return checked ? checked.value : "inter";
        }

        function getMode() {
            const checked = document.querySelector('input[name="latency-mode"]:checked');
            return checked ? checked.value : "azuredocs";
        }

        function updateSourceText(scope, mode) {
            const variant = scope === "interzone" ? "interzone"
                : mode === "cloud63" ? "inter-cloud63"
                : "inter-azuredocs";
            sourceText.querySelectorAll(".latency-source-text-variant").forEach(el => {
                el.classList.toggle("d-none", el.dataset.sourceVariant !== variant);
            });
        }

        modeRadios.forEach(r => r.addEventListener("change", async () => {
            if (getScope() !== "inter") return;
            const mode = getMode();
            updateSourceText("inter", mode);
            if (mode === "cloud63") {
                await mergeCloud63Regions();
            }
            fetchAndRender();
        }));

        scopeRadios.forEach(r => r.addEventListener("change", () => {
            switchScope();
        }));

        function getCoreSelectedRegion() {
            if (!coreRegionSelect) return "";
            return (coreRegionSelect.value || "").toLowerCase().trim();
        }

        function switchScope() {
            const scope = getScope();
            const mode = getMode();
            updateSourceText(scope, mode);

            if (scope === "interzone") {
                interModeEl.classList.add("d-none");
                interzoneModeEl.classList.remove("d-none");
                fetchAndRenderInterzone();
                return;
            }

            interModeEl.classList.remove("d-none");
            interzoneModeEl.classList.add("d-none");
            fetchAndRender();
        }

        if (coreRegionSelect) {
            coreRegionSelect.addEventListener("change", () => {
                if (getScope() === "interzone") fetchAndRenderInterzone();
            });
            const regionObserver = new MutationObserver(() => {
                if (getScope() === "interzone") fetchAndRenderInterzone();
            });
            regionObserver.observe(coreRegionSelect, {
                childList: true,
                subtree: true,
                attributes: true,
            });
        }

        // Start with popover open (no regions selected yet)
        popover.classList.add("open");

        // Toggle region picker popover
        toggleBtn.addEventListener("click", () => {
            popover.classList.toggle("open");
            if (popover.classList.contains("open")) filterInput.focus();
        });

        // Close popover on outside click — only if at least one region is selected
        document.addEventListener("click", (e) => {
            if (selectedRegions.size === 0) return; // keep open until something is selected
            if (!popover.contains(e.target) && e.target !== toggleBtn && !toggleBtn.contains(e.target)) {
                popover.classList.remove("open");
            }
        });

        // Pre-load topojson lib, coordinates, and world topology ALL in parallel
        Promise.all([
            ensureTopojson(),
            fetch(COORDS_URL).then(r => r.json()),
            fetch(WORLD_TOPO_URL).then(r => r.json()),
        ]).then(([_, coords, topo]) => {
            regionCoords = coords;
            worldTopo = topo;
            populateRegions();
            renderEmptyMap(mapEl);
        }).catch(err => {
            console.warn("Failed to preload map data:", err);
        });

        // Sorted region list cache for filtering
        let allRegionEntries = [];
        let cloud63RegionsMerged = false;

        // Convert a region slug like "southcentralus" to "South Central US"
        function slugToDisplayName(slug) {
            return slug
                .replace(/([a-z])([A-Z])/g, "$1 $2")
                .replace(/([a-z])(\d)/g, "$1 $2")
                .replace(/\b\w/g, c => c.toUpperCase());
        }

        // Fetch Cloud63 regions and merge any new ones into regionCoords
        async function mergeCloud63Regions() {
            if (cloud63RegionsMerged) return;
            try {
                const resp = await fetch(`/plugins/${PLUGIN_NAME}/inter-region/cloud63-regions`);
                if (!resp.ok) return;
                const data = await resp.json();
                const cloud63List = data.regions || [];
                let added = 0;
                for (const name of cloud63List) {
                    if (!regionCoords[name]) {
                        regionCoords[name] = { lat: 0, lon: 0, displayName: slugToDisplayName(name) };
                        added++;
                    }
                }
                if (added > 0) {
                    // Invalidate sorted cache so populateRegions rebuilds it
                    allRegionEntries = [];
                    populateRegions(filterInput.value);
                }
                cloud63RegionsMerged = true;
            } catch (err) {
                console.warn("Failed to fetch Cloud63 regions:", err);
            }
        }

        // Populate region checklist from the plugin's own coordinates data
        function populateRegions(filter) {
            regionList.innerHTML = "";
            if (!regionCoords || !Object.keys(regionCoords).length) {
                regionList.innerHTML = '<span class="text-body-secondary small">Loading regions…</span>';
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
                const label = document.createElement("label");
                label.title = display;
                const cb = document.createElement("input");
                cb.type = "checkbox";
                cb.className = "form-check-input me-1";
                cb.value = name;
                cb.checked = selectedRegions.has(name);
                cb.addEventListener("change", () => {
                    if (cb.checked) selectedRegions.add(name);
                    else selectedRegions.delete(name);
                    updateBadge();
                    fetchAndRender();
                });
                label.appendChild(cb);
                label.appendChild(document.createTextNode(display));
                regionList.appendChild(label);
            });
        }

        function updateBadge() {
            selBadge.textContent = selectedRegions.size
                ? `${selectedRegions.size} region${selectedRegions.size > 1 ? "s" : ""} selected`
                : "";
        }

        // Filter input handler
        filterInput.addEventListener("input", () => {
            populateRegions(filterInput.value);
        });

        // Select all visible regions
        selectAllBtn.addEventListener("click", () => {
            regionList.querySelectorAll("input[type=checkbox]").forEach(cb => {
                cb.checked = true;
                selectedRegions.add(cb.value);
            });
            updateBadge();
            fetchAndRender();
        });

        // Deselect all regions
        deselectAllBtn.addEventListener("click", () => {
            selectedRegions.clear();
            regionList.querySelectorAll("input[type=checkbox]").forEach(cb => {
                cb.checked = false;
            });
            updateBadge();
            fetchAndRender();
        });

        // -----------------------------------------------------------------
        // Fetch matrix & render (triggered by mode or region change)
        // -----------------------------------------------------------------
        async function fetchAndRender() {
            if (getScope() !== "inter") return;
            const selected = Array.from(selectedRegions);
            if (selected.length < 2) {
                renderEmptyMap(mapEl);
                legendEl.innerHTML = "";
                tableEl.innerHTML = "";
                return;
            }

            mapEl.innerHTML = '<p class="text-body-secondary text-center py-3">Loading…</p>';
            legendEl.innerHTML = "";
            tableEl.innerHTML = "";

            try {
                await ensureTopojson();
                if (!regionCoords || !worldTopo) {
                    const [coords, topo] = await Promise.all([
                        fetch(COORDS_URL).then(r => r.json()),
                        fetch(WORLD_TOPO_URL).then(r => r.json()),
                    ]);
                    regionCoords = coords;
                    worldTopo = topo;
                }

                const mode = getMode();
                const data = await apiPost(`/plugins/${PLUGIN_NAME}/inter-region/matrix`, { regions: selected, mode });
                renderLatencyMap(data, mapEl, legendEl);
                renderLatencyTable(data, tableEl);
            } catch (e) {
                mapEl.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
            }
        }

        async function fetchAndRenderInterzone() {
            const region = getCoreSelectedRegion();
            interzoneRegionEl.textContent = region || "—";

            if (!coreRegionSelect) {
                interzoneStatusEl.textContent = "Main app region selector not found.";
                interzoneGraphEl.innerHTML = '<p class="text-body-secondary text-center py-3">Region selector unavailable.</p>';
                interzoneTableEl.innerHTML = "";
                return;
            }

            if (!region) {
                interzoneStatusEl.textContent = "Select a region in the main app to view AZ latency.";
                interzoneGraphEl.innerHTML = '<p class="text-body-secondary text-center py-3">Select a region to display inter-zone latency.</p>';
                interzoneTableEl.innerHTML = "";
                return;
            }

            interzoneStatusEl.textContent = "Loading inter-zone latency data…";
            interzoneGraphEl.innerHTML = '<p class="text-body-secondary text-center py-3">Loading…</p>';
            interzoneTableEl.innerHTML = "";

            try {
                const data = await apiPost(`/plugins/${PLUGIN_NAME}/inter-zone/matrix`, { region });
                if (!window.LatencyStatsIntra || !window.LatencyStatsIntra.render) {
                    throw new Error("Inter-zone module failed to load");
                }
                window.LatencyStatsIntra.render(data, interzoneGraphEl, interzoneTableEl);
                interzoneStatusEl.textContent = `Showing ${data.zones.length} Availability Zones (P50 RTT).`;
            } catch (e) {
                interzoneStatusEl.textContent = `Error: ${e.message}`;
                interzoneGraphEl.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
                interzoneTableEl.innerHTML = "";
            }
        }

        switchScope();
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

        // Traveling dots — two per arc, moving in opposite directions
        const dotFlowGroup = svg.append("g").attr("class", "latency-flow-dots");
        arcElements.each(function (d) {
            const pathD = this.getAttribute("d");
            if (!pathD) return;
            const color = rttColorScale(d.rtt);
            // Duration scales with RTT: low RTT = fast dot, high RTT = slow
            const duration = 1 + (d.rtt - minRtt) / (maxRtt - minRtt || 1) * 3; // 1s–4s

            // Forward dot (source → target)
            const fwd = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            fwd.setAttribute("r", "3.5");
            fwd.setAttribute("fill", color);
            fwd.setAttribute("class", "latency-flow-dot");
            fwd.dataset.source = d.source;
            fwd.dataset.target = d.target;
            const animFwd = document.createElementNS("http://www.w3.org/2000/svg", "animateMotion");
            animFwd.setAttribute("dur", duration + "s");
            animFwd.setAttribute("repeatCount", "indefinite");
            animFwd.setAttribute("path", pathD);
            fwd.appendChild(animFwd);
            dotFlowGroup.node().appendChild(fwd);

            // Reverse dot (target → source)
            const rev = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            rev.setAttribute("r", "3.5");
            rev.setAttribute("fill", color);
            rev.setAttribute("class", "latency-flow-dot");
            rev.dataset.source = d.source;
            rev.dataset.target = d.target;
            const animRev = document.createElementNS("http://www.w3.org/2000/svg", "animateMotion");
            animRev.setAttribute("dur", duration + "s");
            animRev.setAttribute("repeatCount", "indefinite");
            animRev.setAttribute("path", pathD);
            animRev.setAttribute("keyPoints", "1;0");
            animRev.setAttribute("keyTimes", "0;1");
            animRev.setAttribute("calcMode", "linear");
            rev.appendChild(animRev);
            dotFlowGroup.node().appendChild(rev);
        });

        const flowDots = dotFlowGroup.selectAll(".latency-flow-dot");

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

        // ---- Shared map selections for cross-highlighting ----
        _mapSelections = { arcElements, flowDots, labelTexts, labelBgs, dotElements, links };

        // ---- Hover highlighting: region dots ----
        dotElements.on("mouseenter", function (event, d) {
            highlightMapByNode(d.id);
            highlightTablePairs(links.filter(l => l.source === d.id || l.target === d.id));
        });

        dotElements.on("mouseleave", function () {
            clearMapHighlight();
            clearTableHighlight();
        });

        // ---- Hover highlighting: arcs ----
        arcElements
            .style("cursor", "pointer")
            .on("mouseenter", function (event, d) {
                highlightMapByLink(d.source, d.target);
                highlightTablePairs([d]);
            })
            .on("mouseleave", function () {
                clearMapHighlight();
                clearTableHighlight();
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
    // -----------------------------------------------------------------------
    // Cross-highlighting helpers (map side)
    // -----------------------------------------------------------------------
    function highlightMapByNode(nodeId) {
        if (!_mapSelections) return;
        const { arcElements, flowDots, labelTexts, labelBgs, dotElements, links } = _mapSelections;
        const connectedLinks = links.filter(l => l.source === nodeId || l.target === nodeId);
        const connectedNodes = new Set([nodeId]);
        connectedLinks.forEach(l => { connectedNodes.add(l.source); connectedNodes.add(l.target); });

        arcElements
            .classed("highlighted", l => l.source === nodeId || l.target === nodeId)
            .classed("dimmed", l => l.source !== nodeId && l.target !== nodeId);
        labelTexts
            .classed("highlighted", l => l.source === nodeId || l.target === nodeId)
            .classed("dimmed", l => l.source !== nodeId && l.target !== nodeId);
        labelBgs
            .classed("dimmed", l => l.source !== nodeId && l.target !== nodeId);
        dotElements.style("opacity", n => connectedNodes.has(n.id) ? 1 : 0.25);
        flowDots
            .classed("active", function () {
                return this.dataset.source === nodeId || this.dataset.target === nodeId;
            })
            .classed("dimmed", function () {
                return this.dataset.source !== nodeId && this.dataset.target !== nodeId;
            });
    }

    function highlightMapByLink(source, target) {
        if (!_mapSelections) return;
        const { arcElements, flowDots, labelTexts, labelBgs, dotElements } = _mapSelections;

        const isMatch = l => (l.source === source && l.target === target) ||
                             (l.source === target && l.target === source);
        arcElements
            .classed("highlighted", isMatch)
            .classed("dimmed", l => !isMatch(l));
        labelTexts
            .classed("highlighted", isMatch)
            .classed("dimmed", l => !isMatch(l));
        labelBgs
            .classed("dimmed", l => !isMatch(l));
        dotElements.style("opacity", n => n.id === source || n.id === target ? 1 : 0.25);
        flowDots
            .classed("active", function () {
                return (this.dataset.source === source && this.dataset.target === target) ||
                       (this.dataset.source === target && this.dataset.target === source);
            })
            .classed("dimmed", function () {
                return !((this.dataset.source === source && this.dataset.target === target) ||
                         (this.dataset.source === target && this.dataset.target === source));
            });
    }

    function clearMapHighlight() {
        if (!_mapSelections) return;
        const { arcElements, flowDots, labelTexts, labelBgs, dotElements } = _mapSelections;
        arcElements.classed("highlighted", false).classed("dimmed", false);
        labelTexts.classed("highlighted", false).classed("dimmed", false);
        labelBgs.classed("dimmed", false);
        dotElements.style("opacity", 1);
        flowDots.classed("active", false).classed("dimmed", false);
    }

    // -----------------------------------------------------------------------
    // Cross-highlighting helpers (table side)
    // -----------------------------------------------------------------------
    function highlightTablePairs(pairs) {
        if (!_tableEl) return;
        pairs.forEach(p => {
            // Highlight both directions (row=source,col=target and row=target,col=source)
            const cells = _tableEl.querySelectorAll(
                `td[data-source="${p.source}"][data-target="${p.target}"],` +
                `td[data-source="${p.target}"][data-target="${p.source}"]`
            );
            cells.forEach(td => td.classList.add("latency-cell-active"));
        });
    }

    function clearTableHighlight() {
        if (!_tableEl) return;
        _tableEl.querySelectorAll(".latency-cell-active").forEach(td => {
            td.classList.remove("latency-cell-active");
        });
        _tableEl.querySelectorAll(".latency-header-highlight").forEach(el => {
            el.classList.remove("latency-header-highlight");
        });
    }

    function renderLatencyTable(data, tableEl) {
        _tableEl = tableEl;
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
                // Data attributes for cross-highlighting with the map
                if (i !== j) {
                    td.dataset.source = rowName;
                    td.dataset.target = colName;
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

            // Cross-hair highlight on the table
            td.classList.add("latency-cell-active");
            const rowTh = tr.querySelector("th");
            if (rowTh) rowTh.classList.add("latency-header-highlight");
            if (headerCells[colIdx]) headerCells[colIdx].classList.add("latency-header-highlight");

            // Cross-highlight the matching arc + flow dots on the map
            const source = td.dataset.source;
            const target = td.dataset.target;
            if (source && target) {
                highlightMapByLink(source, target);
            }
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

            clearMapHighlight();
        });
    }

})();

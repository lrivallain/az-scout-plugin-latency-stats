// Latency Stats plugin — intra-zone graph + table renderer
(function () {
    function render(data, graphContainerEl, tableContainerEl) {
        renderIntraZoneGraph(data, graphContainerEl);
        renderIntraZoneTable(data, tableContainerEl);
    }

    let intraSelections = null;
    let intraTableEl = null;

    function renderIntraZoneGraph(data, containerEl) {
        containerEl.innerHTML = "";
        intraSelections = null;

        const zones = data.zones || [];
        const pairs = data.pairs || [];
        if (zones.length < 2) {
            containerEl.innerHTML = '<p class="text-body-secondary text-center py-3">No intra-zone data available for this region.</p>';
            return;
        }

        const width = 960;
        const height = 500;
        const centerX = width / 2;
        const centerY = height / 2 + 10;
        const radiusX = Math.min(300, width * 0.34);
        const radiusY = Math.min(160, height * 0.28);
        const nodeW = 210;
        const nodeH = 52;

        const svg = d3.select(containerEl).append("svg")
            .attr("viewBox", `0 0 ${width} ${height}`)
            .attr("preserveAspectRatio", "xMidYMid meet")
            .attr("class", "latency-map-svg");

        svg.append("text")
            .attr("x", 20)
            .attr("y", 30)
            .attr("class", "latency-zone-map-title")
            .text("Zone Mapping Graph");

        svg.append("text")
            .attr("x", centerX)
            .attr("y", 62)
            .attr("text-anchor", "middle")
            .attr("class", "latency-zone-map-card-title")
            .text("Physical Zones");

        const zonePoints = new Map();
        zones.forEach((zone, idx) => {
            const angle = -Math.PI / 2 + (2 * Math.PI * idx) / zones.length;
            const pointX = centerX + Math.cos(angle) * radiusX;
            const pointY = centerY + Math.sin(angle) * radiusY;
            zonePoints.set(zone, { x: pointX, y: pointY });

            svg.append("rect")
                .attr("x", pointX - nodeW / 2)
                .attr("y", pointY - nodeH / 2)
                .attr("width", nodeW)
                .attr("height", nodeH)
                .attr("rx", 12)
                .attr("class", "latency-zone-map-node");

            svg.append("text")
                .attr("x", pointX)
                .attr("y", pointY + 6)
                .attr("text-anchor", "middle")
                .attr("class", "latency-zone-map-row-label")
                .text(zone);
        });

        function pointOnRectEdge(centerX, centerY, targetX, targetY, boxWidth, boxHeight) {
            const halfW = boxWidth / 2;
            const halfH = boxHeight / 2;
            const vectorX = targetX - centerX;
            const vectorY = targetY - centerY;

            if (vectorX === 0 && vectorY === 0) {
                return { x: centerX, y: centerY };
            }

            const scaleX = vectorX === 0 ? Number.POSITIVE_INFINITY : halfW / Math.abs(vectorX);
            const scaleY = vectorY === 0 ? Number.POSITIVE_INFINITY : halfH / Math.abs(vectorY);
            const scale = Math.min(scaleX, scaleY);

            return {
                x: centerX + vectorX * scale,
                y: centerY + vectorY * scale,
            };
        }

        function quadPoint(x0, y0, cx, cy, x1, y1, t) {
            const inv = 1 - t;
            const x = inv * inv * x0 + 2 * inv * t * cx + t * t * x1;
            const y = inv * inv * y0 + 2 * inv * t * cy + t * t * y1;
            return { x, y };
        }

        function getLatencyUs(pair) {
            if (pair.latencyUsP50 !== undefined && pair.latencyUsP50 !== null) {
                return pair.latencyUsP50;
            }
            return null;
        }

        function formatLatencyUs(valueUs) {
            if (valueUs === null || valueUs === undefined) return "—";
            return `${valueUs} µs`;
        }

        const allRtt = pairs.map(getLatencyUs).filter(v => v !== null && v !== undefined);
        const minRtt = Math.min(...allRtt, 0.1);
        const maxRtt = Math.max(...allRtt, 0.1);
        const colorScale = d3.scaleSequential(d3.interpolateRdYlGn).domain([maxRtt, minRtt]);

        const latencyGroup = svg.append("g").attr("class", "latency-intra-links");
        pairs.forEach(pair => {
            const src = zonePoints.get(pair.zoneA);
            const dst = zonePoints.get(pair.zoneB);
            if (!src || !dst) return;

            const srcCenterX = src.x;
            const srcCenterY = src.y;
            const dstCenterX = dst.x;
            const dstCenterY = dst.y;
            const midX = (srcCenterX + dstCenterX) / 2;
            const midY = (srcCenterY + dstCenterY) / 2;
            const curveLift = 45 + Math.min(
                55,
                Math.abs(srcCenterY - dstCenterY) * 0.3 + Math.abs(srcCenterX - dstCenterX) * 0.08
            );
            const cx = midX;
            const cy = midY - curveLift;

            const srcEdge = pointOnRectEdge(srcCenterX, srcCenterY, cx, cy, nodeW, nodeH);
            const dstEdge = pointOnRectEdge(dstCenterX, dstCenterY, cx, cy, nodeW, nodeH);

            const xA = srcEdge.x;
            const yA = srcEdge.y;
            const xB = dstEdge.x;
            const yB = dstEdge.y;
            const latencyUs = getLatencyUs(pair);
            if (latencyUs === null) return;
            const pairKey = [pair.zoneA, pair.zoneB].sort().join("|");

            const path = latencyGroup.append("path")
                .attr("d", `M ${xA} ${yA} Q ${cx} ${cy}, ${xB} ${yB}`)
                .attr("stroke", colorScale(latencyUs))
                .attr("stroke-width", 3)
                .attr("stroke-opacity", 0.9)
                .attr("fill", "none")
                .attr("data-pair-key", pairKey)
                .attr("class", "latency-zone-map-latency-link");

            path
                .style("cursor", "pointer")
                .on("mouseenter", () => {
                    highlightIntraMapByPair(pair.zoneA, pair.zoneB);
                    highlightIntraTablePair(pair.zoneA, pair.zoneB);
                })
                .on("mouseleave", () => {
                    clearIntraMapHighlight();
                    clearIntraTableHighlight();
                });

            const label = formatLatencyUs(latencyUs);
            const labelPoint = quadPoint(xA, yA, cx, cy, xB, yB, 0.5);
            const labelX = labelPoint.x;
            const labelY = labelPoint.y;

            latencyGroup.append("rect")
                .attr("x", labelX - (label.length * 3.3))
                .attr("y", labelY - 11)
                .attr("width", label.length * 6.6)
                .attr("height", 18)
                .attr("rx", 4)
                .attr("data-pair-key", pairKey)
                .attr("class", "latency-zone-map-latency-bg");

            latencyGroup.append("text")
                .attr("x", labelX)
                .attr("y", labelY + 2)
                .attr("text-anchor", "middle")
                .attr("data-pair-key", pairKey)
                .attr("class", "latency-zone-map-latency-label")
                .text(label);
        });

        intraSelections = {
            linkElements: latencyGroup.selectAll(".latency-zone-map-latency-link"),
            labelTexts: latencyGroup.selectAll(".latency-zone-map-latency-label"),
            labelBgs: latencyGroup.selectAll(".latency-zone-map-latency-bg"),
        };
    }

    function highlightIntraMapByPair(zoneA, zoneB) {
        if (!intraSelections || !zoneA || !zoneB) return;
        const pairKey = [zoneA, zoneB].sort().join("|");
        const { linkElements, labelTexts, labelBgs } = intraSelections;

        linkElements
            .classed("highlighted", function () {
                return this.dataset.pairKey === pairKey;
            })
            .classed("dimmed", function () {
                return this.dataset.pairKey !== pairKey;
            });

        labelTexts
            .classed("highlighted", function () {
                return this.dataset.pairKey === pairKey;
            })
            .classed("dimmed", function () {
                return this.dataset.pairKey !== pairKey;
            });

        labelBgs
            .classed("dimmed", function () {
                return this.dataset.pairKey !== pairKey;
            });
    }

    function clearIntraMapHighlight() {
        if (!intraSelections) return;
        const { linkElements, labelTexts, labelBgs } = intraSelections;
        linkElements.classed("highlighted", false).classed("dimmed", false);
        labelTexts.classed("highlighted", false).classed("dimmed", false);
        labelBgs.classed("dimmed", false);
    }

    function highlightIntraTablePair(zoneA, zoneB) {
        if (!intraTableEl || !zoneA || !zoneB) return;
        const [z1, z2] = [zoneA, zoneB].sort();
        clearIntraTableHighlight();
        const cells = intraTableEl.querySelectorAll(
            `td[data-zone-a="${z1}"][data-zone-b="${z2}"]`
        );
        cells.forEach(td => {
            td.classList.add("latency-cell-active");

            const row = td.parentElement;
            if (row) {
                row.querySelectorAll("td:nth-child(1), td:nth-child(2)").forEach(el => {
                    el.classList.add("latency-header-highlight");
                });
            }

            const table = td.closest("table");
            if (table) {
                const headers = table.querySelectorAll("thead th");
                if (headers[2]) headers[2].classList.add("latency-header-highlight");
            }
        });
    }

    function clearIntraTableHighlight() {
        if (!intraTableEl) return;
        intraTableEl.querySelectorAll(".latency-cell-active").forEach(td => {
            td.classList.remove("latency-cell-active");
        });
        intraTableEl.querySelectorAll(".latency-header-highlight").forEach(el => {
            el.classList.remove("latency-header-highlight");
        });
    }

    function renderIntraZoneTable(data, containerEl) {
        intraTableEl = containerEl;
        containerEl.innerHTML = "";

        const region = data.region || "";
        const pairs = data.pairs || [];
        if (!pairs.length) {
            containerEl.innerHTML = '<p class="text-body-secondary text-center py-3">No intra-zone pair data available.</p>';
            return;
        }

        const table = document.createElement("table");
        table.className = "latency-table";
        table.innerHTML = `
            <thead>
                <tr>
                    <th>Between…</th>
                    <th>And…</th>
                    <th>P50 RTT (µs)</th>
                </tr>
            </thead>
            <tbody></tbody>
        `;

        const body = table.querySelector("tbody");
        pairs.forEach(pair => {
            const latencyUs = pair.latencyUsP50 !== undefined && pair.latencyUsP50 !== null
                ? pair.latencyUsP50
                : null;
            const zoneAName = pair.zoneA;
            const zoneBName = pair.zoneB;
            const [zoneA, zoneB] = [pair.zoneA, pair.zoneB].sort();
            const row = document.createElement("tr");
            row.innerHTML = `
                <td>${zoneAName}</td>
                <td>${zoneBName}</td>
                <td>${latencyUs === null ? "—" : `${latencyUs} µs`}</td>
            `;
            const latencyCell = row.querySelector("td:last-child");
            if (latencyCell) {
                latencyCell.dataset.zoneA = zoneA;
                latencyCell.dataset.zoneB = zoneB;
            }
            body.appendChild(row);
        });

        containerEl.appendChild(table);

        body.addEventListener("mouseover", (e) => {
            const td = e.target.closest("td");
            if (!td || !td.dataset.zoneA || !td.dataset.zoneB) return;
            highlightIntraTablePair(td.dataset.zoneA, td.dataset.zoneB);
            highlightIntraMapByPair(td.dataset.zoneA, td.dataset.zoneB);
        });

        body.addEventListener("mouseout", (e) => {
            const td = e.target.closest("td");
            if (!td || !td.dataset.zoneA || !td.dataset.zoneB) return;
            clearIntraTableHighlight();
            clearIntraMapHighlight();
        });
    }

    window.LatencyStatsIntra = {
        render,
    };
})();

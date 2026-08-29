/**
 * Usage page — request volume, latency, errors, cache hits
 */
window.MarkomPage_usage = {
    async render(container, days) {
        days = days || 7;
        container.innerHTML = `
            <div class="stat-grid">
                <div class="stat-card"><div class="stat-label">Total Requests</div><div class="stat-value" id="usage-total">-</div></div>
                <div class="stat-card"><div class="stat-label">Avg Latency</div><div class="stat-value" id="usage-latency">-</div></div>
                <div class="stat-card"><div class="stat-label">Error Rate</div><div class="stat-value" id="usage-errors">-</div></div>
                <div class="stat-card"><div class="stat-label">Cache Hit Rate</div><div class="stat-value" id="usage-cache">-</div></div>
            </div>
            <div class="chart-row">
                <div class="card">
                    <div class="card-header"><span class="card-title">Request Volume</span></div>
                    <div class="chart-container"><canvas id="usage-requests-chart"></canvas></div>
                </div>
                <div class="card">
                    <div class="card-header"><span class="card-title">Errors Over Time</span></div>
                    <div class="chart-container"><canvas id="usage-errors-chart"></canvas></div>
                </div>
            </div>
            <div class="card" style="margin-top:16px;">
                <div class="card-header"><span class="card-title">Latency by Model</span></div>
                <div id="usage-latency-table"></div>
            </div>
        `;
        this.refresh(days);
    },
    async refresh(days) {
        days = days || 7;
        try {
            const [reqs, latency, errors, cache] = await Promise.all([
                API.usageRequests(days),
                API.usageLatency(days),
                API.usageErrors(days),
                API.usageCacheHits(days),
            ]);
            const reqDates = Object.keys(reqs.by_date || {});
            const reqVals = Object.values(reqs.by_date || {});
            document.getElementById('usage-total').textContent = reqVals.reduce((a, b) => a + b, 0).toLocaleString();

            const latencies = Object.values(latency.by_model || {});
            const avgLat = latencies.length ? (latencies.reduce((a, b) => a + b.avg, 0) / latencies.length).toFixed(0) : 0;
            document.getElementById('usage-latency').textContent = `${avgLat}ms`;

            const errVals = Object.values(errors.by_date || {});
            const errTotal = errVals.reduce((a, b) => a + b, 0);
            document.getElementById('usage-errors').textContent = `${errTotal}`;

            document.getElementById('usage-cache').textContent = `${((cache.hit_rate || 0) * 100).toFixed(1)}%`;

            createChart('usage-requests-chart', 'bar', reqDates, [{ label: 'Requests', data: reqVals }]);
            const errDates = Object.keys(errors.by_date || {});
            createChart('usage-errors-chart', 'line', errDates, [{ label: 'Errors', data: Object.values(errors.by_date || {}) }]);

            let tableHtml = '<table class="data-table"><thead><tr><th>Model</th><th>Count</th><th>Avg</th><th>P50</th><th>P95</th><th>P99</th></tr></thead><tbody>';
            for (const [model, info] of Object.entries(latency.by_model || {})) {
                tableHtml += `<tr><td>${model}</td><td>${info.count}</td><td>${info.avg}ms</td><td>${info.p50}ms</td><td>${info.p95}ms</td><td>${info.p99}ms</td></tr>`;
            }
            tableHtml += '</tbody></table>';
            document.getElementById('usage-latency-table').innerHTML = tableHtml || '<div class="empty-state">No latency data</div>';
        } catch (e) {
            console.error('Usage load failed:', e);
        }
    }
};

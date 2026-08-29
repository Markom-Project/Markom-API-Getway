/**
 * Cost page — spend charts, breakdown tables, export
 */
window.MarkomPage_cost = {
    async render(container, days) {
        days = days || 30;
        container.innerHTML = `
            <div class="stat-grid">
                <div class="stat-card"><div class="stat-label">Total Spend (${days}d)</div><div class="stat-value" id="cost-total">-</div></div>
                <div class="stat-card"><div class="stat-label">Daily Avg</div><div class="stat-value" id="cost-daily">-</div></div>
                <div class="stat-card"><div class="stat-label">Models Used</div><div class="stat-value" id="cost-models">-</div></div>
                <div class="stat-card" style="display:flex;align-items:center;justify-content:center;">
                    <a href="/api/cost/export?days=${days}" class="btn btn-secondary" target="_blank">Export CSV</a>
                </div>
            </div>
            <div class="chart-row">
                <div class="card">
                    <div class="card-header"><span class="card-title">Spend Trend</span></div>
                    <div class="chart-container"><canvas id="cost-trend-chart"></canvas></div>
                </div>
                <div class="card">
                    <div class="card-header"><span class="card-title">By Model</span></div>
                    <div class="chart-container"><canvas id="cost-model-chart"></canvas></div>
                </div>
            </div>
            <div class="card" style="margin-top:16px;">
                <div class="card-header"><span class="card-title">By Team</span></div>
                <div id="cost-team-table"></div>
            </div>
        `;
        this.refresh(days);
    },
    async refresh(days) {
        days = days || 30;
        try {
            const [summary, byModel, byTeam] = await Promise.all([
                API.costSummary(days),
                API.costByModel(days),
                API.costByTeam(days),
            ]);
            document.getElementById('cost-total').textContent = `$${summary.total_spend}`;
            const dates = Object.keys(summary.by_date);
            const vals = Object.values(summary.by_date);
            document.getElementById('cost-daily').textContent = dates.length ? `$${(summary.total_spend / dates.length).toFixed(2)}` : '$0';
            document.getElementById('cost-models').textContent = Object.keys(byModel.models || {}).length;

            createChart('cost-trend-chart', 'line', dates, [{ label: 'Spend ($)', data: vals }]);
            const modelLabels = Object.keys(byModel.models || {});
            const modelVals = Object.values(byModel.models || {}).map(v => typeof v === 'number' ? v : v.total_cost || 0);
            createChart('cost-model-chart', 'doughnut', modelLabels, [{ data: modelVals }], { plugins: { legend: { display: true, position: 'right' } }, scales: {} });

            const teams = byTeam.teams || {};
            let tableHtml = '<table class="data-table"><thead><tr><th>Team</th><th>Spend</th></tr></thead><tbody>';
            for (const [team, cost] of Object.entries(teams)) {
                tableHtml += `<tr><td>${team}</td><td>$${typeof cost === 'number' ? cost.toFixed(2) : cost}</td></tr>`;
            }
            tableHtml += '</tbody></table>';
            document.getElementById('cost-team-table').innerHTML = tableHtml || '<div class="empty-state">No team data</div>';
        } catch (e) {
            console.error('Cost load failed:', e);
        }
    }
};

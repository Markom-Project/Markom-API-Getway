/**
 * Providers page — health scores, routing log, toggle
 */
window.MarkomPage_providers = {
    async render(container) {
        container.innerHTML = `
            <div class="card">
                <div class="card-header"><span class="card-title">Provider Health</span></div>
                <div id="providers-health-table"></div>
            </div>
            <div class="card" style="margin-top:16px;">
                <div class="card-header"><span class="card-title">Recent Routing Decisions</span></div>
                <div id="providers-routing-table"></div>
            </div>
        `;
        this.refresh();
    },
    async refresh() {
        try {
            const [health, routing] = await Promise.all([
                API.providersHealth(),
                API.providersRoutingLog(50),
            ]);
            const providers = health.providers || [];
            let html = '<table class="data-table"><thead><tr><th>Model</th><th>Provider</th><th>Status</th><th>Latency</th></tr></thead><tbody>';
            providers.forEach(p => {
                const badge = p.status === 'healthy' ? 'badge-green' : 'badge-red';
                html += `<tr><td>${p.model}</td><td>${p.provider}</td><td><span class="badge ${badge}">${p.status}</span></td><td>${p.latency || '-'}ms</td></tr>`;
            });
            html += '</tbody></table>';
            document.getElementById('providers-health-table').innerHTML = html || '<div class="empty-state">No provider data</div>';

            const logs = routing.routing_decisions || [];
            let rhtml = '<table class="data-table"><thead><tr><th>Time</th><th>Model</th><th>Selected</th><th>Reason</th></tr></thead><tbody>';
            logs.forEach(l => {
                rhtml += `<tr><td>${l.timestamp || ''}</td><td>${l.model || ''}</td><td>${l.selected_provider || ''}</td><td>${l.reason || ''}</td></tr>`;
            });
            rhtml += '</tbody></table>';
            document.getElementById('providers-routing-table').innerHTML = rhtml || '<div class="empty-state">No routing decisions</div>';
        } catch (e) {
            console.error('Providers load failed:', e);
        }
    }
};

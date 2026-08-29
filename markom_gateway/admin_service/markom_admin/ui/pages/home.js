/**
 * Home page — summary cards, health, activity
 */
window.MarkomPage_home = {
    async render(container) {
        container.innerHTML = `
            <div class="stat-grid">
                <div class="stat-card"><div class="stat-label">Today's Spend</div><div class="stat-value" id="home-today-spend">-</div></div>
                <div class="stat-card"><div class="stat-label">7-Day Spend</div><div class="stat-value" id="home-total-spend">-</div></div>
                <div class="stat-card"><div class="stat-label">Requests (7d)</div><div class="stat-value" id="home-requests">-</div></div>
                <div class="stat-card"><div class="stat-label">Providers Up</div><div class="stat-value" id="home-providers">-</div></div>
            </div>
            <div class="chart-row">
                <div class="card">
                    <div class="card-header"><span class="card-title">Cache Hit Rate</span></div>
                    <div style="font-size:36px;font-weight:700;color:var(--brand);text-align:center;padding:20px;" id="home-cache-rate">-</div>
                </div>
                <div class="card">
                    <div class="card-header"><span class="card-title">System Health</span></div>
                    <div id="home-health" style="padding:10px;"></div>
                </div>
            </div>
        `;
        try {
            const data = await API.homeSummary();
            document.getElementById('home-today-spend').textContent = `$${data.today_spend}`;
            document.getElementById('home-total-spend').textContent = `$${data.total_spend_7d}`;
            document.getElementById('home-requests').textContent = data.total_requests_7d.toLocaleString();
            document.getElementById('home-providers').textContent = data.providers_up;
            document.getElementById('home-cache-rate').textContent = `${(data.cache_hit_rate * 100).toFixed(1)}%`;
            document.getElementById('home-health').innerHTML = `
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                    <span class="badge badge-green">Core: Running</span>
                    <span class="badge badge-green">Cache: Active</span>
                    <span class="badge badge-green">Audit: Writing</span>
                </div>
            `;
        } catch (e) {
            console.error('Home load failed:', e);
        }
    }
};

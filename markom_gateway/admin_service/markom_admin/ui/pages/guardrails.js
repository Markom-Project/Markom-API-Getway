/**
 * Guardrails page — trigger log, audit trail viewer
 */
window.MarkomPage_guardrails = {
    async render(container) {
        container.innerHTML = `
            <div class="stat-grid">
                <div class="stat-card"><div class="stat-label">Total Triggers</div><div class="stat-value" id="guard-total">-</div></div>
                <div class="stat-card"><div class="stat-label">PII Detections</div><div class="stat-value" id="guard-pii">-</div></div>
                <div class="stat-card"><div class="stat-label">Audit Records</div><div class="stat-value" id="guard-audit-count">-</div></div>
                <div class="stat-card" style="display:flex;align-items:center;justify-content:center;">
                    <a href="/api/guardrails/audit/export?days=30" class="btn btn-secondary" target="_blank">Export Audit</a>
                </div>
            </div>
            <div class="card">
                <div class="card-header"><span class="card-title">Guardrail Triggers</span></div>
                <div id="guard-triggers-table"></div>
            </div>
            <div class="card" style="margin-top:16px;">
                <div class="card-header">
                    <span class="card-title">Audit Trail</span>
                    <select id="guard-audit-status" class="form-select" style="width:140px;" onchange="MarkomPage_guardrails._filterAudit()">
                        <option value="">All</option>
                        <option value="success">Success</option>
                        <option value="failure">Failure</option>
                    </select>
                </div>
                <div id="guard-audit-table"></div>
            </div>
        `;
        this.refresh();
    },
    async refresh() {
        try {
            const [triggers, audit] = await Promise.all([
                API.guardrailTriggers(7),
                API.guardrailAudit(7),
            ]);
            document.getElementById('guard-total').textContent = triggers.total || 0;
            document.getElementById('guard-audit-count').textContent = audit.total || 0;

            let piiCount = 0;
            (triggers.triggers || []).forEach(t => {
                const gr = t.guardrail_results || {};
                piiCount += gr.pii_detected ? 1 : 0;
            });
            document.getElementById('guard-pii').textContent = piiCount;

            let thtml = '<table class="data-table"><thead><tr><th>Time</th><th>User</th><th>Model</th><th>Details</th></tr></thead><tbody>';
            (triggers.triggers || []).forEach(t => {
                thtml += `<tr><td>${t.timestamp}</td><td>${t.user_id}</td><td>${t.model}</td><td><pre style="margin:0;font-size:11px;">${JSON.stringify(t.guardrail_results)}</pre></td></tr>`;
            });
            thtml += '</tbody></table>';
            document.getElementById('guard-triggers-table').innerHTML = thtml || '<div class="empty-state">No triggers</div>';

            this._renderAuditTable(audit.records || []);
        } catch (e) {
            console.error('Guardrails load failed:', e);
        }
    },
    _renderAuditTable(records) {
        let html = '<table class="data-table"><thead><tr><th>Time</th><th>User</th><th>Model</th><th>Status</th><th>Latency</th><th>Cost</th></tr></thead><tbody>';
        records.forEach(r => {
            const badge = r.status === 'success' ? 'badge-green' : 'badge-red';
            html += `<tr><td>${r.timestamp || ''}</td><td>${r.user_id || ''}</td><td>${r.model || ''}</td><td><span class="badge ${badge}">${r.status}</span></td><td>${r.latency_ms || '-'}ms</td><td>$${r.cost_usd || 0}</td></tr>`;
        });
        html += '</tbody></table>';
        document.getElementById('guard-audit-table').innerHTML = html || '<div class="empty-state">No records</div>';
    },
    async _filterAudit() {
        const status = document.getElementById('guard-audit-status').value;
        try {
            const audit = await API.guardrailAudit(7, status);
            this._renderAuditTable(audit.records || []);
        } catch (e) {
            console.error('Audit filter failed:', e);
        }
    }
};

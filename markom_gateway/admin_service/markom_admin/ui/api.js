/**
 * MarKom API Client — wraps all dashboard backend calls.
 */
const API = {
    _token: null,

    setToken(token) {
        this._token = token;
    },

    _headers() {
        const h = { 'Content-Type': 'application/json' };
        if (this._token) h['Authorization'] = `Bearer ${this._token}`;
        return h;
    },

    async get(url) {
        const resp = await fetch(url, { headers: this._headers() });
        if (resp.status === 401) { window.__logout && window.__logout(); throw new Error('Unauthorized'); }
        if (!resp.ok) throw new Error(`GET ${url}: ${resp.status}`);
        return resp.json();
    },

    async post(url, body) {
        const resp = await fetch(url, { method: 'POST', headers: this._headers(), body: JSON.stringify(body) });
        if (resp.status === 401) { window.__logout && window.__logout(); throw new Error('Unauthorized'); }
        if (!resp.ok) throw new Error(`POST ${url}: ${resp.status}`);
        return resp.json();
    },

    async put(url, body) {
        const resp = await fetch(url, { method: 'PUT', headers: this._headers(), body: JSON.stringify(body) });
        if (resp.status === 401) { window.__logout && window.__logout(); throw new Error('Unauthorized'); }
        if (!resp.ok) throw new Error(`PUT ${url}: ${resp.status}`);
        return resp.json();
    },

    async del(url) {
        const resp = await fetch(url, { method: 'DELETE', headers: this._headers() });
        if (resp.status === 401) { window.__logout && window.__logout(); throw new Error('Unauthorized'); }
        if (!resp.ok) throw new Error(`DELETE ${url}: ${resp.status}`);
        return resp.json();
    },

    // Auth
    me() { return this.get('/api/auth/me'); },

    // Home
    homeSummary() { return this.get('/api/home/summary'); },

    // Cost
    costSummary(days) { return this.get(`/api/cost/summary?days=${days}`); },
    costByModel(days) { return this.get(`/api/cost/by-model?days=${days}`); },
    costByTeam(days) { return this.get(`/api/cost/by-team?days=${days}`); },
    costByKey(days) { return this.get(`/api/cost/by-key?days=${days}`); },
    costTrend(days) { return this.get(`/api/cost/trend?days=${days}`); },

    // Usage
    usageRequests(days) { return this.get(`/api/usage/requests?days=${days}`); },
    usageLatency(days) { return this.get(`/api/usage/latency?days=${days}`); },
    usageErrors(days) { return this.get(`/api/usage/errors?days=${days}`); },
    usageCacheHits(days) { return this.get(`/api/usage/cache-hits?days=${days}`); },

    // Providers
    providersHealth() { return this.get('/api/providers/health'); },
    providersRoutingLog(limit) { return this.get(`/api/providers/routing-log?limit=${limit || 50}`); },
    providersToggle(model, enable) { return this.post(`/api/providers/${model}/toggle?enable=${enable}`); },

    // Guardrails
    guardrailTriggers(days) { return this.get(`/api/guardrails/triggers?days=${days}`); },
    guardrailAudit(days, status) { return this.get(`/api/guardrails/audit?days=${days}${status ? '&status=' + status : ''}`); },

    // Accounts
    listAccounts() { return this.get('/api/accounts'); },
    createAccount(data) { return this.post('/api/accounts', data); },
    updateAccount(id, data) { return this.put(`/api/accounts/${id}`, data); },
    disableAccount(id) { return this.post(`/api/accounts/${id}/disable`); },
    removeAccount(id) { return this.post(`/api/accounts/${id}/remove`); },

    // Settings
    listRoles() { return this.get('/api/settings/roles'); },
    getRole(slug) { return this.get(`/api/settings/roles/${slug}`); },
    createRole(data) { return this.post('/api/settings/roles', data); },
    updateRole(slug, data) { return this.put(`/api/settings/roles/${slug}`, data); },
    deleteRole(slug) { return this.del(`/api/settings/roles/${slug}`); },
};

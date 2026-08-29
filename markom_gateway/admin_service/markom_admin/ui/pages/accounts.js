/**
 * Accounts page — user table, create/edit/disable/remove
 */
window.MarkomPage_accounts = {
    async render(container) {
        container.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <h3 style="font-size:16px;font-weight:600;">User Accounts</h3>
                <button class="btn btn-primary" onclick="MarkomPage_accounts._showCreate()">+ Add User</button>
            </div>
            <div class="card"><div id="accounts-table"></div></div>
        `;
        this.refresh();
    },
    async refresh() {
        try {
            const data = await API.listAccounts();
            const accounts = data.accounts || [];
            let html = '<table class="data-table"><thead><tr><th>User</th><th>Email</th><th>Role</th><th>Tabs</th><th>Actions</th></tr></thead><tbody>';
            accounts.forEach(a => {
                const tabs = (a.tabs || []).map(t => `<span class="badge badge-gray" style="margin:1px;">${t.slug || t}</span>`).join(' ');
                html += `<tr>
                    <td><strong>${a.display_name || a.external_id}</strong></td>
                    <td>${a.email || '-'}</td>
                    <td><span class="badge badge-green">${a.role}</span></td>
                    <td>${tabs}</td>
                    <td>
                        <button class="btn btn-secondary btn-sm" onclick="MarkomPage_accounts._showEdit('${a.external_id}')">Edit</button>
                        <button class="btn btn-secondary btn-sm" onclick="MarkomPage_accounts._disable('${a.external_id}')" style="color:var(--yellow);">Disable</button>
                        <button class="btn btn-secondary btn-sm" onclick="MarkomPage_accounts._remove('${a.external_id}')" style="color:var(--red);">Remove</button>
                    </td>
                </tr>`;
            });
            html += '</tbody></table>';
            document.getElementById('accounts-table').innerHTML = html || '<div class="empty-state">No accounts</div>';
        } catch (e) {
            console.error('Accounts load failed:', e);
        }
    },
    _showCreate() {
        window.__openModal('Create Account', `
            <div class="form-group"><label class="form-label">External ID</label><input class="form-input" id="acc-ext-id" placeholder="user-id"></div>
            <div class="form-group"><label class="form-label">Email</label><input class="form-input" id="acc-email" type="email"></div>
            <div class="form-group"><label class="form-label">Display Name</label><input class="form-input" id="acc-name"></div>
            <div class="form-group"><label class="form-label">Role</label>
                <select class="form-select" id="acc-role">
                    <option value="viewer">Viewer</option>
                    <option value="developer">Developer</option>
                    <option value="team_lead">Team Lead</option>
                    <option value="admin">Admin</option>
                </select>
            </div>
            <div class="form-group"><label class="form-label">Tab Overrides (comma-separated)</label><input class="form-input" id="acc-tabs" placeholder="cost,usage"></div>
        `, `
            <button class="btn btn-secondary" onclick="window.__closeModal()">Cancel</button>
            <button class="btn btn-primary" onclick="MarkomPage_accounts._doCreate()">Create</button>
        `);
    },
    async _doCreate() {
        const data = {
            external_id: document.getElementById('acc-ext-id').value,
            email: document.getElementById('acc-email').value || null,
            display_name: document.getElementById('acc-name').value || null,
            role: document.getElementById('acc-role').value,
            tab_overrides: document.getElementById('acc-tabs').value.split(',').map(s => s.trim()).filter(Boolean),
        };
        try {
            await API.createAccount(data);
            window.__closeModal();
            window.__showToast('Account created');
            this.refresh();
        } catch (e) {
            window.__showToast('Failed: ' + e.message, 'error');
        }
    },
    _showEdit(extId) {
        window.__openModal('Edit Account', `
            <div class="form-group"><label class="form-label">Email</label><input class="form-input" id="acc-edit-email"></div>
            <div class="form-group"><label class="form-label">Display Name</label><input class="form-input" id="acc-edit-name"></div>
            <div class="form-group"><label class="form-label">Role</label>
                <select class="form-select" id="acc-edit-role">
                    <option value="viewer">Viewer</option>
                    <option value="developer">Developer</option>
                    <option value="team_lead">Team Lead</option>
                    <option value="admin">Admin</option>
                </select>
            </div>
            <div class="form-group"><label class="form-label">Tab Overrides (comma-separated)</label><input class="form-input" id="acc-edit-tabs" placeholder="cost,usage"></div>
        `, `
            <button class="btn btn-secondary" onclick="window.__closeModal()">Cancel</button>
            <button class="btn btn-primary" onclick="MarkomPage_accounts._doEdit('${extId}')">Save</button>
        `);
    },
    async _doEdit(extId) {
        const data = {
            email: document.getElementById('acc-edit-email').value || null,
            display_name: document.getElementById('acc-edit-name').value || null,
            role: document.getElementById('acc-edit-role').value,
            tab_overrides: document.getElementById('acc-edit-tabs').value.split(',').map(s => s.trim()).filter(Boolean),
        };
        try {
            await API.updateAccount(extId, data);
            window.__closeModal();
            window.__showToast('Account updated');
            this.refresh();
        } catch (e) {
            window.__showToast('Failed: ' + e.message, 'error');
        }
    },
    async _disable(extId) {
        if (!confirm(`Disable ${extId}?`)) return;
        try {
            await API.disableAccount(extId);
            window.__showToast('Account disabled');
            this.refresh();
        } catch (e) {
            window.__showToast('Failed: ' + e.message, 'error');
        }
    },
    async _remove(extId) {
        if (!confirm(`Permanently remove ${extId}?`)) return;
        try {
            await API.removeAccount(extId);
            window.__showToast('Account removed');
            this.refresh();
        } catch (e) {
            window.__showToast('Failed: ' + e.message, 'error');
        }
    }
};

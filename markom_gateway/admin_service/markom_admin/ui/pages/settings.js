/**
 * Settings page — role template manager
 */
window.MarkomPage_settings = {
    _roles: [],
    _allTabs: [],
    _allPerms: [],

    async render(container) {
        container.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <h3 style="font-size:16px;font-weight:600;">Role Templates</h3>
                <button class="btn btn-primary" onclick="MarkomPage_settings._showCreate()">+ New Role</button>
            </div>
            <div class="card"><div id="settings-roles-table"></div></div>
        `;
        this.refresh();
    },
    async refresh() {
        try {
            const data = await API.listRoles();
            this._roles = data.roles || [];
            this._allTabs = data.all_tabs || [];
            this._allPerms = data.all_permissions || [];
            this._renderTable();
        } catch (e) {
            console.error('Settings load failed:', e);
        }
    },
    _renderTable() {
        let html = '<table class="data-table"><thead><tr><th>Role</th><th>Description</th><th>System</th><th>Tabs</th><th>Permissions</th><th>Actions</th></tr></thead><tbody>';
        this._roles.forEach(r => {
            const tabs = (r.tabs || []).map(t => `<span class="badge badge-gray" style="margin:1px;">${t}</span>`).join(' ');
            const perms = (r.permissions || []).length;
            html += `<tr>
                <td><strong>${r.display_name}</strong><br><span style="font-size:11px;color:var(--gray400);">${r.slug}</span></td>
                <td>${r.description || '-'}</td>
                <td>${r.is_system ? '<span class="badge badge-yellow">System</span>' : '<span class="badge badge-gray">Custom</span>'}</td>
                <td>${tabs}</td>
                <td>${perms} permissions</td>
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="MarkomPage_settings._showEdit('${r.slug}')">Edit</button>
                    ${!r.is_system ? `<button class="btn btn-secondary btn-sm" onclick="MarkomPage_settings._delete('${r.slug}')" style="color:var(--red);">Delete</button>` : ''}
                </td>
            </tr>`;
        });
        html += '</tbody></table>';
        document.getElementById('settings-roles-table').innerHTML = html;
    },
    _checkboxGrid(items, selected, prefix) {
        return `<div class="checkbox-grid">${items.map(item => `
            <label class="checkbox-item">
                <input type="checkbox" name="${prefix}" value="${item}" ${selected.includes(item) ? 'checked' : ''}>
                ${item}
            </label>
        `).join('')}</div>`;
    },
    _showCreate() {
        window.__openModal('Create Custom Role', `
            <div class="form-group"><label class="form-label">Slug (unique)</label><input class="form-input" id="role-slug" placeholder="billing_auditor"></div>
            <div class="form-group"><label class="form-label">Display Name</label><input class="form-input" id="role-name" placeholder="Billing Auditor"></div>
            <div class="form-group"><label class="form-label">Description</label><input class="form-input" id="role-desc"></div>
            <div class="form-group"><label class="form-label">Tabs</label>${this._checkboxGrid(this._allTabs, [], 'role-tab')}</div>
            <div class="form-group"><label class="form-label">Permissions</label>${this._checkboxGrid(this._allPerms, [], 'role-perm')}</div>
        `, `
            <button class="btn btn-secondary" onclick="window.__closeModal()">Cancel</button>
            <button class="btn btn-primary" onclick="MarkomPage_settings._doCreate()">Create</button>
        `);
    },
    async _doCreate() {
        const tabs = [...document.querySelectorAll('input[name="role-tab"]:checked')].map(el => el.value);
        const perms = [...document.querySelectorAll('input[name="role-perm"]:checked')].map(el => el.value);
        const data = {
            slug: document.getElementById('role-slug').value,
            display_name: document.getElementById('role-name').value,
            description: document.getElementById('role-desc').value,
            tabs,
            permissions: perms,
        };
        try {
            await API.createRole(data);
            window.__closeModal();
            window.__showToast('Role created');
            this.refresh();
        } catch (e) {
            window.__showToast('Failed: ' + e.message, 'error');
        }
    },
    _showEdit(slug) {
        const role = this._roles.find(r => r.slug === slug);
        if (!role) return;
        window.__openModal(`Edit: ${role.display_name}`, `
            <div class="form-group"><label class="form-label">Display Name</label><input class="form-input" id="role-edit-name" value="${role.display_name}"></div>
            <div class="form-group"><label class="form-label">Description</label><input class="form-input" id="role-edit-desc" value="${role.description || ''}"></div>
            <div class="form-group"><label class="form-label">Tabs</label>${this._checkboxGrid(this._allTabs, role.tabs || [], 'role-edit-tab')}</div>
            <div class="form-group"><label class="form-label">Permissions</label>${this._checkboxGrid(this._allPerms, role.permissions || [], 'role-edit-perm')}</div>
        `, `
            <button class="btn btn-secondary" onclick="window.__closeModal()">Cancel</button>
            <button class="btn btn-primary" onclick="MarkomPage_settings._doEdit('${slug}')">Save</button>
        `);
    },
    async _doEdit(slug) {
        const tabs = [...document.querySelectorAll('input[name="role-edit-tab"]:checked')].map(el => el.value);
        const perms = [...document.querySelectorAll('input[name="role-edit-perm"]:checked')].map(el => el.value);
        const data = {
            display_name: document.getElementById('role-edit-name').value,
            description: document.getElementById('role-edit-desc').value,
            tabs,
            permissions: perms,
        };
        try {
            await API.updateRole(slug, data);
            window.__closeModal();
            window.__showToast('Role updated');
            this.refresh();
        } catch (e) {
            window.__showToast('Failed: ' + e.message, 'error');
        }
    },
    async _delete(slug) {
        if (!confirm(`Delete role "${slug}"?`)) return;
        try {
            await API.deleteRole(slug);
            window.__showToast('Role deleted');
            this.refresh();
        } catch (e) {
            window.__showToast('Failed: ' + e.message, 'error');
        }
    }
};

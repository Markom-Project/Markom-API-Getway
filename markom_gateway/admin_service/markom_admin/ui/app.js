/**
 * MarKom App — SPA router, auth flow, tab switching, keyboard navigation
 */
(function() {
    const STORAGE_KEY = 'markom_api_key';
    let currentUser = null;
    let currentPage = null;

    const ICONS = {
        home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
        dollar: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
        chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
        server: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>',
        shield: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
        users: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
        cog: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
    };

    const pageModules = {};
    const loadedScripts = new Set();

    async function loadPageModule(slug) {
        if (pageModules[slug]) return pageModules[slug];
        try {
            await new Promise((resolve, reject) => {
                if (loadedScripts.has(slug)) { resolve(); return; }
                const s = document.createElement('script');
                s.src = `/static/pages/${slug}.js`;
                s.onload = () => { loadedScripts.add(slug); resolve(); };
                s.onerror = reject;
                document.head.appendChild(s);
            });
            const modName = `MarkomPage_${slug.replace('-', '_')}`;
            if (window[modName]) {
                pageModules[slug] = window[modName];
                return pageModules[slug];
            }
        } catch (e) {
            console.warn(`Failed to load page module: ${slug}`, e);
        }
        return null;
    }

    function getToken() {
        return localStorage.getItem(STORAGE_KEY);
    }

    function setToken(token) {
        localStorage.setItem(STORAGE_KEY, token);
        API.setToken(token);
    }

    window.__logout = function() {
        localStorage.removeItem(STORAGE_KEY);
        currentUser = null;
        window.location.hash = '#/login';
        render();
    };

    function showToast(message, type = 'success') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        toast.setAttribute('role', 'status');
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    window.__showToast = showToast;

    window.__closeModal = function() {
        const overlay = document.getElementById('modal-overlay');
        overlay.style.display = 'none';
        overlay.removeAttribute('aria-hidden');
        const modal = document.querySelector('.modal');
        if (modal) modal.remove();
        document.body.focus();
    };

    window.__openModal = function(title, bodyHtml, footerHtml) {
        const overlay = document.getElementById('modal-overlay');
        overlay.style.display = 'block';
        const existing = document.querySelector('.modal');
        if (existing) existing.remove();
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-label', title);
        modal.innerHTML = `
            <div class="modal-header">${title}</div>
            <div class="modal-body">${bodyHtml}</div>
            ${footerHtml ? `<div class="modal-footer">${footerHtml}</div>` : ''}
        `;
        document.body.appendChild(modal);

        // Focus first input in modal
        const firstInput = modal.querySelector('input, select, textarea');
        if (firstInput) setTimeout(() => firstInput.focus(), 50);

        // Trap focus in modal
        modal.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                window.__closeModal();
                return;
            }
            if (e.key !== 'Tab') return;
            const focusable = modal.querySelectorAll('input, select, textarea, button, [tabindex]:not([tabindex="-1"])');
            if (focusable.length === 0) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        });
    };

    function renderSidebar() {
        const nav = document.getElementById('sidebar-nav');
        nav.innerHTML = '';
        if (!currentUser || !currentUser.tabs) return;

        currentUser.tabs.forEach(tab => {
            const item = document.createElement('button');
            item.className = `nav-item${currentPage === tab.slug ? ' active' : ''}`;
            item.setAttribute('aria-label', `${tab.label} tab`);
            item.setAttribute('aria-current', currentPage === tab.slug ? 'page' : 'false');
            item.innerHTML = `${ICONS[tab.icon] || ''}<span>${tab.label}</span>`;
            item.onclick = () => {
                window.location.hash = `#/${tab.slug}`;
                document.getElementById('sidebar').classList.remove('open');
            };
            nav.appendChild(item);
        });
    }

    function renderUserInfo() {
        if (!currentUser) return;
        const nameEl = document.querySelector('.user-name');
        const roleEl = document.querySelector('.user-role');
        const avatarEl = document.querySelector('.user-avatar');
        nameEl.textContent = currentUser.display_name || currentUser.email || currentUser.user_id;
        roleEl.textContent = currentUser.role;
        avatarEl.textContent = (currentUser.display_name || currentUser.user_id || 'U')[0].toUpperCase();
    }

    async function render() {
        const token = getToken();
        if (!token) {
            window.location.hash = '#/login';
            renderLogin();
            return;
        }

        API.setToken(token);

        if (!currentUser) {
            try {
                currentUser = await API.me();
            } catch {
                localStorage.removeItem(STORAGE_KEY);
                window.location.hash = '#/login';
                renderLogin();
                return;
            }
        }

        const hash = window.location.hash || '#/home';
        const path = hash.replace('#/', '').split('/')[0] || 'home';

        if (path === 'login') {
            renderLogin();
            return;
        }

        const allowedSlugs = (currentUser.tabs || []).map(t => t.slug);
        if (!allowedSlugs.includes(path)) {
            window.location.hash = '#/home';
            currentPage = 'home';
            renderSidebar();
            renderUserInfo();
            await loadAndRenderPage('home');
            return;
        }

        currentPage = path;
        document.getElementById('page-title').textContent =
            currentUser.tabs.find(t => t.slug === path)?.label || path;

        const showTimeRange = ['cost', 'usage'].includes(path);
        document.getElementById('time-range-selector').style.display = showTimeRange ? 'block' : 'none';

        renderSidebar();
        renderUserInfo();
        await loadAndRenderPage(path);
    }

    async function loadAndRenderPage(slug) {
        const content = document.getElementById('page-content');
        content.innerHTML = '<div class="empty-state"><p>Loading...</p></div>';

        const mod = await loadPageModule(slug);
        if (mod && typeof mod.render === 'function') {
            content.innerHTML = '';
            try { await mod.render(content); } catch (e) {
                console.error(`Page render error (${slug}):`, e);
                content.innerHTML = `<div class="empty-state"><p>Failed to load page</p></div>`;
            }
        } else {
            content.innerHTML = `<div class="empty-state"><p>Page "${slug}" not available</p></div>`;
        }

        // Move focus to page content for screen readers
        content.focus();
    }

    function renderLogin() {
        document.getElementById('sidebar').style.display = 'none';
        document.getElementById('page-title').textContent = '';
        document.getElementById('top-bar').querySelector('.top-bar-actions').innerHTML = '';
        const content = document.getElementById('page-content');
        content.innerHTML = `
            <div style="display:flex;align-items:center;justify-content:center;min-height:80vh;">
                <div class="card" style="width:400px;text-align:center;">
                    <div style="font-size:36px;font-weight:700;color:var(--text-brand);margin-bottom:8px;">MarKom Gateway</div>
                    <div style="color:var(--text-tertiary);margin-bottom:24px;">Enter your API key to sign in</div>
                    <form onsubmit="event.preventDefault(); window.__doLogin();" aria-label="Login form">
                        <div class="form-group" style="text-align:left;">
                            <label class="form-label" for="login-key">API Key</label>
                            <input type="password" id="login-key" class="form-input" placeholder="sk-..." autocomplete="off" required aria-required="true">
                        </div>
                        <button type="submit" class="btn btn-primary" style="width:100%;">Sign In</button>
                    </form>
                </div>
            </div>
        `;
        document.getElementById('sidebar').style.display = '';
        setTimeout(() => {
            const input = document.getElementById('login-key');
            if (input) input.focus();
        }, 100);
    }

    window.__doLogin = async function() {
        const key = document.getElementById('login-key')?.value?.trim();
        if (!key) { showToast('Enter an API key', 'error'); return; }
        setToken(key);
        try {
            currentUser = await API.me();
            window.location.hash = '#/home';
            render();
        } catch {
            localStorage.removeItem(STORAGE_KEY);
            currentUser = null;
            showToast('Invalid API key', 'error');
        }
    };

    window.__onTimeRangeChange = function(days) {
        if (currentPage && pageModules[currentPage] && typeof pageModules[currentPage].refresh === 'function') {
            pageModules[currentPage].refresh(parseInt(days));
        }
    };

    // Keyboard navigation: arrow keys in sidebar
    document.addEventListener('keydown', (e) => {
        const sidebar = document.getElementById('sidebar-nav');
        if (!sidebar || document.activeElement?.closest('#sidebar-nav') !== sidebar) return;
        const items = [...sidebar.querySelectorAll('.nav-item')];
        const idx = items.indexOf(document.activeElement);
        if (idx === -1) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            items[Math.min(idx + 1, items.length - 1)].focus();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            items[Math.max(idx - 1, 0)].focus();
        }
    });

    window.addEventListener('hashchange', render);
    window.addEventListener('DOMContentLoaded', () => {
        const token = getToken();
        if (token) API.setToken(token);
        render();
    });
})();

/**
 * Chart.js setup — reads brand colors from design tokens.
 */
document.addEventListener('DOMContentLoaded', () => {
    if (typeof Chart === 'undefined') return;

    Chart.defaults.font.family = getComputedStyle(document.documentElement)
        .getPropertyValue('--font-family').trim() ||
        "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    Chart.defaults.color = getComputedStyle(document.documentElement)
        .getPropertyValue('--text-tertiary').trim() || '#6b7280';
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.padding = 16;

    const cs = getComputedStyle(document.documentElement);
    const brand = cs.getPropertyValue('--brand').trim() || '#120505';
    const brandAlpha = `rgba(18,5,5,0.15)`;
    const palette = [brand, '#6366f1', '#059669', '#d97706', '#dc2626', '#7c3aed', '#2563eb'];

    window.__chartColors = { brand, brandAlpha, palette };
});

function createChart(canvasId, type, labels, datasets, options = {}) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return null;

    const colors = window.__chartColors || {
        brand: '#120505',
        brandAlpha: 'rgba(18,5,5,0.15)',
        palette: ['#120505'],
    };

    datasets = datasets.map((ds, i) => ({
        label: ds.label || '',
        data: ds.data || [],
        borderColor: ds.borderColor || colors.palette[i % colors.palette.length],
        backgroundColor: ds.backgroundColor ||
            (type === 'line' ? colors.brandAlpha : colors.palette[i % colors.palette.length]),
        borderWidth: ds.borderWidth || 2,
        tension: ds.tension ?? 0.3,
        fill: ds.fill ?? (type === 'line'),
        pointRadius: ds.pointRadius ?? 2,
        ...ds,
    }));

    const gridColor = getComputedStyle(document.documentElement)
        .getPropertyValue('--surface-100').trim() || '#f3f4f6';

    return new Chart(ctx, {
        type,
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: datasets.length > 1 } },
            scales: {
                x: { grid: { display: false } },
                y: { beginAtZero: true, grid: { color: gridColor } },
            },
            ...options,
        },
    });
}

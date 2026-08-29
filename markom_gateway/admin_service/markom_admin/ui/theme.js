/**
 * MarKom Theme — reads design tokens from CSS variables.
 * Never hardcode hex values here; always derive from theme.css.
 */
const MARCOM = (() => {
    const cs = getComputedStyle(document.documentElement);
    const v = (name, fallback) => cs.getPropertyValue(name).trim() || fallback;
    return {
        brand:          v('--brand', '#120505'),
        brandHover:     v('--brand-hover', '#2a0b0b'),
        brandLight:     v('--brand-light', '#5a1a1a'),
        brandBg:        v('--brand-bg', '#fef2f2'),
        textPrimary:    v('--text-primary', '#111827'),
        textSecondary:  v('--text-secondary', '#4b5563'),
        textTertiary:   v('--text-tertiary', '#6b7280'),
        textInverse:    v('--text-inverse', '#ffffff'),
        textBrand:      v('--text-brand', '#120505'),
        green:          v('--green', '#059669'),
        greenBg:        v('--green-bg', '#d1fae5'),
        red:            v('--red', '#dc2626'),
        redBg:          v('--red-bg', '#fee2e2'),
        yellow:         v('--yellow', '#d97706'),
        yellowBg:       v('--yellow-bg', '#fef3c7'),
        blue:           v('--blue', '#2563eb'),
        blueBg:         v('--blue-bg', '#dbeafe'),
        surface0:       v('--surface-0', '#ffffff'),
        surface50:      v('--surface-50', '#f9fafb'),
        surface100:     v('--surface-100', '#f3f4f6'),
        surface200:     v('--surface-200', '#e5e7eb'),
        surface300:     v('--surface-300', '#d1d5db'),
        surface400:     v('--surface-400', '#9ca3af'),
        surface500:     v('--surface-500', '#6b7280'),
        surface600:     v('--surface-600', '#4b5563'),
        surface700:     v('--surface-700', '#374151'),
        surface800:     v('--surface-800', '#1f2937'),
        surface900:     v(--'--surface-900', '#111827'),
    };
})();

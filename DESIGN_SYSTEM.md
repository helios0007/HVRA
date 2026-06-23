# OASIS — UI / UX & Style Guide

A self-contained design-system reference for the **OASIS** dashboard
(*Overheating Assessment System for Intervention Strategies*). Copy the tokens and
component recipes below into any project (plain HTML/CSS, React, Vue…) to get the
same look and feel. Every value here is taken from the live app — not invented.

> **TL;DR for your friend:** paste the [`:root` token block](#1-design-tokens-paste-this-first)
> into your global CSS, add the [Inter font link](#0-fonts), then use the
> [component recipes](#5-components-copy-paste). The signature look = **dark, near-black
> UI + one warm coral accent (`#ef6a4d`) + a thermal heat-map data palette (yellow→deep-red)
> + a monospace font for labels/eyebrows**.

---

## Design principles
1. **Dark, low-glare canvas.** Near-black blues (`#0a0e14` → `#202938`), never pure black. Content floats on subtly lighter elevated surfaces.
2. **One warm brand accent.** Coral-orange `#ef6a4d` is the *only* brand color — used for the logo, active tab, primary buttons, focus. Everything else is neutral.
3. **Thermal data palette is sacred.** Heat / vulnerability data uses a ColorBrewer **YlOrRd** scale (pale yellow → deep red). Never recolor data with the brand accent.
4. **Mono for metadata.** A monospace font marks "system" text: eyebrows, section numbers, chips, code, labels. Body copy is Inter.
5. **Pills & soft cards.** Status/tags are `99px` pills with a *tinted* background + a same-hue border at ~0.4 alpha. Cards use `10px` radius and a deep soft shadow.
6. **Calm motion.** Transitions `0.12–0.2s`. One "ping" pulse on a live-status dot. Respect `prefers-reduced-motion`.

---

## 0. Fonts
The UI font is **Inter** with a system fallback; labels use a monospace stack. Add this to your `<head>`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
```

> Note: in the OASIS repo the Inter `<link>` isn't actually included, so it currently
> falls back to `system-ui`. Add the link above to get the *intended* Inter look.

---

## 1. Design tokens (paste this first)

```css
:root {
  /* ---- Surfaces (dark, near-black blue) ---- */
  --bg-primary:   #0a0e14;   /* app background */
  --bg-secondary: #11161f;   /* header, side panels, tab bar */
  --bg-tertiary:  #1a212c;   /* chips, inputs */
  --bg-elevated:  #202938;   /* raised cards / popovers */

  /* ---- Text ---- */
  --text-primary:   #e8edf4;
  --text-secondary: #94a3b8;
  --text-muted:     #64748b;

  /* ---- Lines ---- */
  --border-color:  #283242;
  --border-subtle: #1e2734;
  --line:          #1e2734;

  /* ---- Status / chart accents ---- */
  --accent-green:  #34d399;
  --accent-yellow: #fbbf24;
  --accent-orange: #fb923c;
  --accent-red:    #f87171;
  --accent-blue:   #60a5fa;
  --accent-violet: #a78bfa;

  /* ---- Brand accent (the ONE) — landing + dashboard chrome ---- */
  --accent: #ef6a4d;

  /* ---- Shape & depth ---- */
  --radius:    10px;
  --radius-sm: 6px;
  --shadow:    0 8px 28px rgba(0, 0, 0, 0.45);

  /* ---- Type ---- */
  --font:      'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  --font-mono: ui-monospace, 'SF Mono', Consolas, monospace;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: var(--font);
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
}
```

---

## 2. Thermal / HVI data palette
Use this **only** for heat-vulnerability or temperature data (maps, gauges, bars, legends).
It's a ColorBrewer **YlOrRd** ramp on a 0–10 index.

| Score | Hex | Meaning |
|------:|-----|---------|
| 0   | `#ffffcc` | pale yellow (near-white) |
| 3   | `#ffeda0` | low |
| 4   | `#feb24c` | orange |
| 5   | `#fd8d3c` | |
| 6   | `#fc4e2a` | orange-red |
| 7   | `#e31a1c` | red |
| 8.5 | `#b10026` | |
| 10  | `#800026` | deep red |

```css
/* Legend / heat bar — matches the data ramp exactly */
.hvi-gradient {
  background: linear-gradient(90deg,
    #ffffcc 0%, #ffeda0 30%, #feb24c 40%, #fd8d3c 50%,
    #fc4e2a 60%, #e31a1c 70%, #b10026 85%, #800026 100%);
}
```

**Risk tiers** (decision thresholds used across the app):

| Tier | Range | Color | Action |
|------|-------|-------|--------|
| Low | 0–4.0 | `#feb24c` | No intervention needed |
| Moderate | 4.0–5.5 | `#fd8d3c` | Street-level measures recommended |
| High | 5.5–7.0 | `#fc4e2a` | Priority — urban + building measures |
| Critical | 7.0–10 | `#b10026` | Immediate full retrofit pathway |

---

## 3. The signature landing background (page-wide thermal field)
This is the most recognizable OASIS visual — a fixed, warm "heat field" behind the
whole page. Apply to your scroll container.

```css
.landing {
  /* alias the dashboard tokens so landing + app feel like one product */
  --lp-bg: var(--bg-primary);
  --lp-fg: var(--text-primary);
  --lp-mut: var(--text-secondary);
  --lp-line: var(--border-subtle);
  --lp-accent: var(--accent);

  min-height: 100vh;
  overflow-y: auto;
  scroll-behavior: smooth;
  color: var(--lp-fg);
  font-family: var(--font);

  background-color: var(--lp-bg);
  background-image:
    radial-gradient(900px 620px at 12% 3%,  rgba(96,120,170,.08), transparent 60%),
    radial-gradient(820px 560px at 88% 14%, rgba(251,146,60,.10), transparent 60%),
    radial-gradient(1000px 720px at 50% 50%, rgba(239,68,68,.06), transparent 62%),
    radial-gradient(900px 720px at 10% 84%, rgba(251,191,36,.07), transparent 60%),
    radial-gradient(1000px 780px at 94% 98%, rgba(217,30,24,.10), transparent 60%),
    linear-gradient(180deg, #090a0e 0%, #0b0a0d 55%, #130b0d 100%);
  background-attachment: fixed;   /* content glides over a constant field */
  background-repeat: no-repeat;
}
```

---

## 4. Layout conventions
- **App shell:** flex column, `height: 100vh`, `background: var(--bg-primary)`.
- **Header:** `56px` tall, `background: linear-gradient(180deg, var(--bg-secondary), var(--bg-primary))`, bottom border `--border-color`. Brand text in `--accent`, 700 weight.
- **Tab bar:** `44px` tall, `--bg-secondary`, `4px` gap. Active tab = accent text + accent bottom-border.
- **Side panel:** `360px` wide, `--bg-secondary`, left border `--border-color`. Main area flexes.
- **Spacing rhythm:** 4 / 8 / 12 / 18 / 20 / 24 px. Panel padding `20px`.
- **Radii:** pills `99px`, cards `10px` (`--radius`), small controls `6px` (`--radius-sm`), bento/landing cards `14px`.

---

## 5. Components (copy-paste)

```css
/* ---------- Header + brand ---------- */
.app-header {
  display: flex; justify-content: space-between; align-items: center;
  height: 56px; padding: 0 20px; flex-shrink: 0;
  background: linear-gradient(180deg, var(--bg-secondary), var(--bg-primary));
  border-bottom: 1px solid var(--border-color);
}
.app-logo {
  font-size: 17px; font-weight: 700; letter-spacing: 0.2px; color: var(--accent);
  display: inline-flex; align-items: center; gap: 7px;
}
.app-subtitle { font-size: 12px; color: var(--text-muted); font-weight: 500; }

/* ---------- Chips & status pills ---------- */
.chip {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 5px 12px; border-radius: 99px;
  background-color: var(--bg-tertiary); border: 1px solid var(--border-color);
  font-size: 12px; font-weight: 600; color: var(--text-primary);
}
.chip i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }

.status-badge { padding: 5px 12px; border-radius: 99px; font-size: 12px; font-weight: 600; }
.status-badge.success { background: rgba(52,211,153,.12);  color: var(--accent-green); border: 1px solid rgba(52,211,153,.4); }
.status-badge.error   { background: rgba(248,113,113,.12); color: var(--accent-red);   border: 1px solid rgba(248,113,113,.4); }
.status-badge.loading { background: rgba(96,165,250,.12);  color: var(--accent-blue);  border: 1px solid rgba(96,165,250,.4);
  animation: pulse 1.5s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .55; } }

/* ---------- Tabs ---------- */
.tab-bar {
  display: flex; height: 44px; padding: 0 12px; gap: 4px; flex-shrink: 0;
  background-color: var(--bg-secondary); border-bottom: 1px solid var(--border-color);
}
.tab {
  padding: 0 18px; border: none; background: transparent; cursor: pointer;
  color: var(--text-secondary); font-family: var(--font); font-size: 13px; font-weight: 600;
  border-bottom: 2px solid transparent; transition: all .18s ease;
  display: inline-flex; align-items: center; gap: 7px;
}
.tab:hover:not(:disabled) { color: var(--text-primary); background: rgba(255,255,255,.04); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab:disabled { opacity: .4; cursor: not-allowed; }

/* ---------- Buttons ---------- */
.btn {
  font-size: .95rem; font-weight: 700; padding: 13px 24px; border-radius: 9px;
  cursor: pointer; border: 1px solid transparent; transition: transform .12s, border-color .2s;
}
.btn.primary { background: var(--accent); color: #fff; box-shadow: 0 12px 30px -12px var(--accent); }
.btn.primary:hover { transform: translateY(-2px); }
.btn.secondary { background: var(--bg-tertiary); color: var(--text-primary); border-color: var(--border-color); }

/* ---------- Card / panel ---------- */
.card {
  background: var(--bg-secondary); border: 1px solid var(--border-color);
  border-radius: var(--radius); box-shadow: var(--shadow); padding: 20px;
}
.card h3 { font-size: 16px; font-weight: 700; margin-bottom: 12px; }
.card p  { color: var(--text-secondary); line-height: 1.6; }

/* ---------- Live badge with pinging dot (landing hero) ---------- */
.badge {
  display: inline-flex; align-items: center; gap: 9px; padding: 7px 15px;
  border: 1px solid var(--border-subtle); border-radius: 30px;
  background: color-mix(in srgb, var(--accent) 9%, transparent);
  font-family: var(--font-mono); font-size: .74rem; letter-spacing: .08em;
  text-transform: uppercase; color: var(--text-secondary);
}
.badge-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); animation: ping 2.2s ease-out infinite; }
@keyframes ping {
  0%   { box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent) 60%, transparent); }
  70%,100% { box-shadow: 0 0 0 9px transparent; }
}

/* ---------- Bento grid (landing feature cards) ---------- */
.bento { display: grid; grid-template-columns: repeat(3, 1fr); grid-auto-rows: 1fr; gap: 18px; }
.bento-item {
  border: 1px solid var(--line); border-radius: 14px; padding: 24px;
  background: var(--bg-secondary); transition: transform .15s, border-color .2s, box-shadow .2s;
}
.bento-item:hover {
  transform: translateY(-4px);
  border-color: color-mix(in srgb, var(--accent) 50%, var(--line));
  box-shadow: 0 14px 34px -16px rgba(239,68,68,.4);
}
.bento-lg { grid-column: span 2; grid-row: span 2; }

/* ---------- Big hero title ---------- */
.hero-title { font-size: clamp(2.6rem, 6.4vw, 5.2rem); line-height: 1.02; letter-spacing: -.03em; font-weight: 800; }
.hero-sub   { font-size: clamp(1rem, 1.5vw, 1.2rem); line-height: 1.65; color: var(--text-secondary); max-width: 640px; }
.eyebrow    { font-family: var(--font-mono); text-transform: uppercase; letter-spacing: .08em; color: var(--text-muted); font-size: .74rem; }
```

---

## 6. Floating map/overlay panels
Overlays on maps/3D use a **light glass** card (the one place we go light, for legibility over imagery):

```css
.overlay-card {
  position: absolute; z-index: 10; padding: 1rem; min-width: 200px;
  background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(8px);
  border: 1px solid #E2E8F0; border-radius: 12px;
  box-shadow: 0 10px 25px rgba(15, 23, 42, 0.1);
  font-size: 0.85rem; color: #0F172A;
}
```

---

## 7. Accessibility / motion
```css
@media (prefers-reduced-motion: reduce) {
  .badge-dot, .status-badge.loading { animation: none !important; }
}
```

---

## Quick checklist to match OASIS
- [ ] Add the **Inter** font link.
- [ ] Paste the **`:root` tokens**; set `body` to `--bg-primary` + `--text-primary`.
- [ ] Use **`#ef6a4d`** as the only brand accent (logo, active tab, primary button).
- [ ] Use the **YlOrRd ramp** for any heat/vulnerability data — never the brand accent.
- [ ] Pills = `99px` + tinted bg + same-hue 0.4-alpha border.
- [ ] Cards = `10px` radius + `--shadow`; landing cards = `14px` + hover lift.
- [ ] Monospace for eyebrows, chips, section numbers, labels.
- [ ] For a landing page, apply the **fixed thermal background**.

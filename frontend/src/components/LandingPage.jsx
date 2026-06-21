// Landing page — the framing screen before the live tool, and the opener for
// the jury. Workspace-product feel (dark, precise, kinetic) inspired by the
// cryptowl.io class of sites, grounded in OASIS's heat language: a single
// flowing daylight field, a framed dashboard mockup, a "replay the heat across
// time" motif, bento features, count-up metrics and a data ticker. No libs.

import { useState, useRef, useEffect } from 'react';

// ── Motion primitives ─────────────────────────────────────────────────────
function useInView(options = { threshold: 0.18, rootMargin: '0px 0px -8% 0px' }) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') { setInView(true); return; }
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { setInView(true); obs.disconnect(); }
    }, options);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);
  return [ref, inView];
}

// Fade-up wrapper; `delay` (ms) staggers grid children.
function Reveal({ children, className = '', delay = 0, as: Tag = 'div', ...rest }) {
  const [ref, inView] = useInView();
  return (
    <Tag
      ref={ref}
      className={`reveal ${inView ? 'in' : ''} ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

function useCountUp(target, inView, duration = 1300) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!inView) return;
    // Respect reduced-motion: jump straight to the final value.
    if (typeof window !== 'undefined' &&
        window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setVal(target);
      return;
    }
    let raf;
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      setVal(target * eased);
      if (t < 1) raf = requestAnimationFrame(step);
      else setVal(target);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [inView, target, duration]);
  return val;
}

function Stat({ value, label, count = true, suffix = '' }) {
  const [ref, inView] = useInView();
  const n = useCountUp(value, inView && count);
  return (
    <div ref={ref} className={`lp-stat reveal ${inView ? 'in' : ''}`}>
      <dt>{count ? Math.round(n) : value}{suffix}</dt>
      <dd>{label}</dd>
    </div>
  );
}

// One HVI-coloured 3D building, drawn in cabinet projection (front + top + side).
function IsoBlock({ x, y, w, h, dep = 20, color }) {
  const dy = dep * 0.55;
  const front = `${x},${y} ${x + w},${y} ${x + w},${y - h} ${x},${y - h}`;
  const top = `${x},${y - h} ${x + w},${y - h} ${x + w + dep},${y - h - dy} ${x + dep},${y - h - dy}`;
  const side = `${x + w},${y} ${x + w},${y - h} ${x + w + dep},${y - h - dy} ${x + w + dep},${y - dy}`;
  return (
    <g stroke="rgba(0,0,0,.4)" strokeWidth="0.5">
      <polygon points={front} fill={color} />
      <polygon points={side} fill={color} />
      <polygon points={side} fill="#000" opacity="0.32" stroke="none" />
      <polygon points={top} fill={color} />
      <polygon points={top} fill="#fff" opacity="0.22" stroke="none" />
    </g>
  );
}

// ── Hero dashboard mockup — a faithful framing of the real OASIS 3D Explore tab
function DashboardMock() {
  // back-to-front so nearer towers overlap the ones behind
  const blocks = [
    { x: 108, y: 432, w: 44, h: 50, color: '#ffeda0' },
    { x: 234, y: 434, w: 46, h: 58, color: '#feb24c' },
    { x: 360, y: 432, w: 44, h: 52, color: '#fd8d3c' },
    { x: 470, y: 434, w: 42, h: 64, color: '#fc4e2a' },
    { x: 70, y: 482, w: 54, h: 60, color: '#feb24c' },
    { x: 142, y: 502, w: 50, h: 92, color: '#fd8d3c' },
    { x: 206, y: 488, w: 58, h: 74, color: '#fc4e2a' },
    { x: 280, y: 508, w: 52, h: 122, color: '#e31a1c' },
    { x: 352, y: 492, w: 56, h: 66, color: '#feb24c' },
    { x: 422, y: 510, w: 54, h: 98, color: '#fc4e2a' },
    { x: 488, y: 494, w: 50, h: 80, color: '#b10026' },
    { x: 548, y: 514, w: 46, h: 62, color: '#fd8d3c' },
  ];
  const tabs = [
    ['Draw & Analyze', 74], ['3D Explore', 196], ['HVI Map', 296],
    ['Heatmap & Drivers', 410], ['Interventions', 545], ['Building', 660],
  ];
  const tiers = [
    ['0–4.0', 'Low', '#feb24c'], ['4.0–5.5', 'Moderate', '#fd8d3c'],
    ['5.5–7.0', 'High', '#fc4e2a'], ['7.0–10', 'Critical', '#b10026'],
  ];
  const MONO = 'ui-monospace, Consolas, monospace';
  const SANS = 'system-ui, -apple-system, Segoe UI, sans-serif';
  return (
    <svg className="lp-mock" viewBox="0 0 960 600" role="img"
      aria-label="OASIS dashboard: the 3D Explore tab showing a neighbourhood of buildings coloured by Heat Vulnerability Index, with a score gauge, statistics and legend">
      <defs>
        <clipPath id="lpwin"><rect x="0" y="0" width="960" height="600" rx="16" /></clipPath>
        <clipPath id="lpmap"><rect x="16" y="98" width="624" height="486" rx="10" /></clipPath>
        <radialGradient id="lpHeat" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#fc4e2a" stopOpacity="0.42" />
          <stop offset="60%" stopColor="#feb24c" stopOpacity="0.16" />
          <stop offset="100%" stopColor="#feb24c" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="lpWord" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#fbbf24" /><stop offset="55%" stopColor="#fb923c" /><stop offset="100%" stopColor="#ef4444" />
        </linearGradient>
        <linearGradient id="lpScale" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#ffffcc" /><stop offset="40%" stopColor="#feb24c" />
          <stop offset="70%" stopColor="#fc4e2a" /><stop offset="100%" stopColor="#800026" />
        </linearGradient>
      </defs>

      <g clipPath="url(#lpwin)">
        <rect x="0" y="0" width="960" height="600" fill="#0a0c11" />

        {/* ── app header ── */}
        <rect x="0" y="0" width="960" height="50" fill="#0e1119" />
        <circle cx="20" cy="25" r="5" fill="#ef4444" /><circle cx="38" cy="25" r="5" fill="#fbbf24" /><circle cx="56" cy="25" r="5" fill="#34d399" />
        <text x="82" y="31" fontSize="17" fontWeight="800" fill="url(#lpWord)" fontFamily={SANS} letterSpacing="0.5">OASIS</text>
        <text x="150" y="31" fontSize="11.5" fill="#7c828f" fontFamily={SANS}>Heat Vulnerability · Barcelona</text>
        <rect x="690" y="14" width="158" height="22" rx="11" fill="#15181f" stroke="#252a34" />
        <circle cx="706" cy="25" r="4" fill="#e31a1c" />
        <text x="716" y="29" fontSize="11" fill="#c4cad6" fontFamily={MONO}>Zone HVI 7.4 · 128</text>
        <rect x="856" y="14" width="86" height="22" rx="11" fill="rgba(52,211,153,.12)" stroke="rgba(52,211,153,.45)" />
        <text x="872" y="29" fontSize="11" fill="#34d399" fontFamily={MONO}>✓ Ready</text>

        {/* ── tab bar ── */}
        <rect x="0" y="50" width="960" height="42" fill="#0c0e15" />
        <line x1="0" y1="92" x2="960" y2="92" stroke="#1b1f29" />
        {tabs.map(([label, cx]) => {
          const active = label === '3D Explore';
          return (
            <g key={label}>
              <text x={cx} y="76" fontSize="11.5" textAnchor="middle" fontFamily={SANS}
                fill={active ? '#fb923c' : '#8a8f9a'} fontWeight={active ? 700 : 400}>{label}</text>
              {active && <rect x={cx - 36} y="89" width="72" height="3" rx="1.5" fill="#fb923c" />}
            </g>
          );
        })}

        {/* ── map panel (3D Explore) ── */}
        <rect x="16" y="98" width="624" height="486" rx="10" fill="#06080c" stroke="#1b1f29" />
        <g clipPath="url(#lpmap)">
          {/* street grid */}
          <g stroke="#11151d" strokeWidth="1">
            {[...Array(9)].map((_, i) => <line key={'v' + i} x1={16 + i * 70} y1="98" x2={16 + i * 70} y2="584" />)}
            {[...Array(7)].map((_, i) => <line key={'h' + i} x1="16" y1={120 + i * 66} x2="640" y2={120 + i * 66} />)}
          </g>
          {/* UTCI heat underlay */}
          <ellipse cx="300" cy="500" rx="240" ry="150" fill="url(#lpHeat)" />
          <ellipse cx="470" cy="470" rx="150" ry="110" fill="url(#lpHeat)" />
          {/* drawn-zone boundary */}
          <polygon points="58,470 360,452 600,486 560,576 96,560" fill="rgba(251,146,60,.05)"
            stroke="rgba(251,146,60,.55)" strokeWidth="1.5" strokeDasharray="6 5" />
          {/* HVI-coloured 3D buildings */}
          {blocks.map((b, i) => <IsoBlock key={i} {...b} />)}
        </g>
        {/* map legend */}
        <text x="34" y="566" fontSize="10" fill="#8a8f9a" fontFamily={MONO}>HVI</text>
        <rect x="60" y="558" width="120" height="9" rx="2" fill="url(#lpScale)" />
        <text x="186" y="566" fontSize="10" fill="#8a8f9a" fontFamily={MONO}>low → high</text>

        {/* ── sidebar ── */}
        <rect x="652" y="98" width="292" height="486" rx="10" fill="#0e1119" stroke="#1b1f29" />
        <text x="798" y="124" fontSize="10.5" letterSpacing="2" fill="#7c828f" fontFamily={MONO} textAnchor="middle">ZONE VULNERABILITY</text>
        {/* HVI gauge ring */}
        <circle cx="798" cy="184" r="44" fill="none" stroke="#1b1f29" strokeWidth="11" />
        <circle cx="798" cy="184" r="44" fill="none" stroke="#e31a1c" strokeWidth="11" strokeLinecap="round"
          strokeDasharray="205 277" transform="rotate(-90 798 184)" />
        <text x="798" y="186" fontSize="34" fontWeight="800" fill="#f4f6fa" fontFamily={SANS} textAnchor="middle">7.4</text>
        <text x="798" y="204" fontSize="11" fill="#7c828f" fontFamily={MONO} textAnchor="middle">/ 10</text>
        <text x="798" y="250" fontSize="12.5" fontWeight="700" fill="#e31a1c" fontFamily={SANS} textAnchor="middle">Critical vulnerability</text>

        {/* stat grid 2×2 */}
        <g fontFamily={SANS}>
          <text x="688" y="294" fontSize="20" fontWeight="800" fill="#f4f6fa">128</text>
          <text x="688" y="310" fontSize="10" fill="#7c828f">Buildings</text>
          <text x="820" y="294" fontSize="20" fontWeight="800" fill="#f4f6fa">6.1</text>
          <text x="820" y="310" fontSize="10" fill="#7c828f">Median HVI</text>
          <text x="688" y="344" fontSize="20" fontWeight="800" fill="#e31a1c">8.3</text>
          <text x="688" y="360" fontSize="10" fill="#7c828f">Max HVI</text>
          <text x="820" y="344" fontSize="20" fontWeight="800" fill="#feb24c">3.9</text>
          <text x="820" y="360" fontSize="10" fill="#7c828f">Min HVI</text>
        </g>
        <line x1="676" y1="380" x2="920" y2="380" stroke="#1b1f29" />

        {/* HVI tier legend */}
        <text x="676" y="402" fontSize="10.5" letterSpacing="1.5" fill="#7c828f" fontFamily={MONO}>HVI RISK TIERS</text>
        {tiers.map(([range, label, color], i) => {
          const y = 414 + i * 27; const active = label === 'Critical';
          return (
            <g key={label} fontFamily={SANS}>
              {active && <rect x="672" y={y} width="252" height="23" rx="5" fill="rgba(177,0,38,.14)" />}
              <rect x="680" y={y + 5} width="13" height="13" rx="2" fill={color} />
              <text x="702" y={y + 16} fontSize="11" fill="#9aa0ac" fontFamily={MONO}>{range}</text>
              <text x="752" y={y + 16} fontSize="11.5" fill={active ? '#f4f6fa' : '#c4cad6'} fontWeight={active ? 700 : 400}>{label}</text>
            </g>
          );
        })}

        {/* risk distribution */}
        <text x="676" y="544" fontSize="10.5" letterSpacing="1.5" fill="#7c828f" fontFamily={MONO}>RISK DISTRIBUTION</text>
        <g>
          <rect x="676" y="554" width="68" height="12" rx="2" fill="#90EE90" />
          <rect x="746" y="554" width="104" height="12" rx="2" fill="#FFA500" />
          <rect x="852" y="554" width="68" height="12" rx="2" fill="#FF4500" />
        </g>
      </g>
      <rect x="0.5" y="0.5" width="959" height="599" rx="16" fill="none" stroke="#262b36" />
    </svg>
  );
}

// Schematic persona apartment — a tiny static version of the coupled section
function PersonaThumb() {
  return (
    <svg viewBox="0 0 320 230" width="100%" style={{ background: '#fbfbf9', borderRadius: 8 }}
      fontFamily="ui-monospace, Consolas, monospace">
      <g stroke="#e8842a" fill="none" strokeWidth="1">
        <circle cx="34" cy="38" r="8" fill="#fff" />
        {[...Array(8)].map((_, i) => {
          const a = (i * Math.PI) / 4;
          return <line key={i} x1={34 + Math.cos(a) * 11} y1={38 + Math.sin(a) * 11} x2={34 + Math.cos(a) * 15} y2={38 + Math.sin(a) * 15} />;
        })}
        {[0, 1, 2].map((k) => <line key={k} x1={42} y1={46 + k * 7} x2={86} y2={88 + k * 14} strokeDasharray="3 3" opacity="0.7" />)}
      </g>
      <rect x="80" y="54" width="200" height="15" fill="#2e2e2a" />
      <rect x="80" y="69" width="13" height="126" fill="#2e2e2a" />
      <rect x="267" y="69" width="13" height="126" fill="#2e2e2a" />
      <rect x="93" y="69" width="174" height="8" fill="#2e2e2a" />
      <rect x="93" y="187" width="174" height="8" fill="#2e2e2a" />
      <rect x="80" y="96" width="13" height="80" fill="#dde6ef" stroke="#1a1a1a" strokeWidth="0.8" />
      <g stroke="#d43d2a" fill="#d43d2a">
        <line x1="150" y1="82" x2="150" y2="104" strokeWidth="5" />
        <polygon points="150,108 146,100 154,100" />
      </g>
      <g stroke="#e8842a" fill="#e8842a">
        <line x1="95" y1="134" x2="133" y2="146" strokeWidth="4" />
        <polygon points="137,148 128,144 131,138" />
      </g>
      <g>
        <ellipse cx="133" cy="166" rx="25" ry="30" fill="#d43d2a" opacity="0.15" />
        <rect x="119" y="164" width="29" height="30" rx="3" fill="#f3f3ee" stroke="#1a1a1a" strokeWidth="1" />
        <g stroke="#1a1a1a" fill="none" strokeWidth="1.4">
          <circle cx="131" cy="146" r="6" fill="#fff" />
          <line x1="131" y1="152" x2="133" y2="166" />
          <line x1="133" y1="166" x2="145" y2="166" />
        </g>
      </g>
      <text x="198" y="116" fontSize="11" fontWeight="700" fill="#d43d2a">36°C</text>
      <text x="198" y="129" fontSize="7.5" fill="#8a8a82">indoor · unsafe</text>
    </svg>
  );
}

function Section({ n, label, title, children }) {
  return (
    <section className="lp-section" id={label.toLowerCase().replace(/\s+/g, '-')}>
      <Reveal className="lp-section-head">
        <span className="lp-section-n">{n}</span>
        <span className="lp-section-label">{label}</span>
      </Reveal>
      {title && <Reveal as="h2" className="lp-h2" delay={60}>{title}</Reveal>}
      {children}
    </section>
  );
}

const STEPS = [
  { n: '01', title: 'Diagnose', text: 'A building-level Heat Vulnerability Index from live satellite, cadastral and census data — shown in 3D over a street-level heat field.' },
  { n: '02', title: 'Decide', text: 'The decision gate: apply urban-scale measures first, then a verdict on whether building-level retrofit is needed at all.' },
  { n: '03', title: 'Design', text: 'Evidence-based interventions with a live what-if, and auto-generated climatic drawings — down to the resident’s apartment section.' },
];

const PILLARS = [
  { name: 'Building exposure', weight: 35, color: '#a78bfa', factors: ['Construction era', 'Roof type', 'Street canyon H/W', 'Green-space proximity'] },
  { name: 'Social vulnerability', weight: 40, color: '#34d399', factors: ['Population 65+', 'Household income', 'Social isolation', 'No air-conditioning', 'Disability'] },
  { name: 'Thermal context', weight: 25, color: '#fb923c', factors: ['Land surface temp.', 'Urban heat island', 'NDVI / vegetation'] },
];

const DIFFERENTIATORS = [
  { k: 'Health capital, not degrees', v: 'Headline output is harm avoided — heat deaths and illness averted, sleep recovered.' },
  { k: 'Regenerative give-back', v: 'Counts what each measure does beyond the window: albedo, avoided A/C heat, grid load.' },
  { k: 'Future-climate layer', v: 'Assess present-day and ~2050 — see whose vulnerability grows fastest.' },
  { k: 'Evidence-based', v: 'Every cooling coefficient cited to peer-reviewed literature. No black box.' },
];

const SOURCES = ['Landsat 8/9', 'Sentinel-2', 'Catastro', 'Idescat', 'OpenStreetMap', 'Infrared SDK', 'Renda atlas'];

// Building-scale capabilities — rendered as an asymmetric bento.
const BUILDING = [
  { title: 'Room-by-room HVI', text: 'Upload a building’s IFC model and every room is scored and ranked by heat risk — solar gain, ventilation, envelope, occupant vulnerability and overnight recovery.', big: true },
  { title: 'Interactive 3D model', text: 'The building itself, rooms coloured by risk, with a before / after-retrofit toggle, section cuts and click-to-inspect.' },
  { title: 'Diagnosis & retrofits', text: 'A plain-language diagnosis per room plus a ranked retrofit shortlist — each with expected ΔT, €/m² and embodied carbon.' },
  { title: 'Grounded in the zone', text: 'The urban heat measured for that street (its UHI delta) is fed into the building model, so the indoor diagnosis reflects where it actually stands.' },
];

const FAQS = [
  {
    q: 'How is the Heat Vulnerability Index computed?',
    a: 'Twelve factors across exposure, sensitivity and adaptive capacity are normalised 0–1 and weighted (35% building exposure, 40% social vulnerability, 25% thermal context) into a 0–10 index — reported in index points, not degrees, so the social dimension is never lost in a temperature reading.',
  },
  {
    q: 'What does “grounded” building analysis mean?',
    a: 'When you select a building, the urban-scale heat the tool measured for that zone (UHI delta from the heat-stress and peak-UTCI field) is passed into the building-level pipeline — so the room-by-room diagnosis reflects the street it actually sits on, not a city average.',
  },
  {
    q: 'Why “health capital” instead of degrees?',
    a: 'A 2 °C drop means little on its own. OASIS reports the harm avoided — heat deaths and illness averted, nights of sleep recovered — and the regenerative give-back of each measure: albedo gained, A/C heat avoided, grid load shed.',
  },
  {
    q: 'Can it run for a city other than Barcelona?',
    a: 'Yes. Satellite and street-morphology inputs are already worldwide; each new city needs only a swappable cadastre, census and income adapter. Barcelona is the demonstrator.',
  },
  {
    q: 'How do the interventions get costed?',
    a: 'Quantities come from real geometry — roof, façade and floor areas, dwelling counts, street area and tree counts — multiplied by evidence-based unit rates, so the programme cost reflects the actual zone rather than a flat per-m² guess.',
  },
];

// Interactive accordion (chevron-expand) — single panel open at a time.
function Accordion({ items }) {
  const [open, setOpen] = useState(0);
  return (
    <div className="lp-acc">
      {items.map((f, i) => {
        const isOpen = open === i;
        return (
          <div className={`lp-acc-item ${isOpen ? 'open' : ''}`} key={i}>
            <button className="lp-acc-q" onClick={() => setOpen(isOpen ? -1 : i)} aria-expanded={isOpen}>
              <span>{f.q}</span>
              <svg className="lp-acc-chev" width="18" height="18" viewBox="0 0 24 24" fill="none"
                stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>
            <div className="lp-acc-panel"><div className="lp-acc-inner"><p>{f.a}</p></div></div>
          </div>
        );
      })}
    </div>
  );
}

// Process rail — a connecting line that fills + lights its nodes when in view.
function ProcessRail({ labels }) {
  const [ref, inView] = useInView();
  const n = labels.length;
  const edge = (0.5 / n) * 100;       // % inset of the first/last node
  const span = ((n - 1) / n) * 100;   // % distance the fill travels
  return (
    <div ref={ref} className={`lp-rail ${inView ? 'in' : ''}`}>
      <span className="lp-rail-track" style={{ left: `${edge}%`, right: `${edge}%` }} />
      <span className="lp-rail-fill" style={{ left: `${edge}%`, width: inView ? `${span}%` : '0%' }} />
      {labels.map((l, i) => (
        <span className="lp-rail-node" key={l}
          style={{ left: `${((i + 0.5) / n) * 100}%`, transitionDelay: `${i * 240}ms` }}>
          <i /><em>{l}</em>
        </span>
      ))}
    </div>
  );
}

// Through-time — "replay the heat" present → ~2050 (cryptowl temporal motif).
function TimeReplay() {
  const [ref, inView] = useInView();
  return (
    <div ref={ref} className={`lp-time ${inView ? 'in' : ''}`}>
      <div className="lp-time-card now">
        <span className="lp-time-tag">Today</span>
        <span className="lp-time-big">41°C</span>
        <span className="lp-time-sub">peak UTCI · risk <b className="hot">High</b></span>
      </div>
      <div className="lp-time-track" aria-hidden="true">
        <span className="lp-time-line" />
        <span className="lp-time-fill" />
        <span className="lp-time-dot a" />
        <span className="lp-time-dot b" />
        <em className="lp-time-cap">replay vulnerability across the century</em>
      </div>
      <div className="lp-time-card future">
        <span className="lp-time-tag">~2050</span>
        <span className="lp-time-big">46°C</span>
        <span className="lp-time-sub">peak UTCI · risk <b className="sev">Severe</b></span>
      </div>
    </div>
  );
}

export default function LandingPage({ onLaunch }) {
  const [progress, setProgress] = useState(0);
  const [activeSec, setActiveSec] = useState('the-subject');
  const landingRef = useRef(null);

  const onScroll = (e) => {
    const el = e.currentTarget;
    const max = el.scrollHeight - el.clientHeight;
    setProgress(max > 0 ? (el.scrollTop / max) * 100 : 0);
  };

  // Scroll-spy: highlight the nav link for the section currently in view.
  useEffect(() => {
    const root = landingRef.current;
    if (!root || typeof IntersectionObserver === 'undefined') return;
    const ids = ['the-subject', 'method', 'approach', 'building-scale', 'through-time', 'faq'];
    const secs = ids.map((id) => document.getElementById(id)).filter(Boolean);
    const obs = new IntersectionObserver(
      (entries) => entries.forEach((e) => { if (e.isIntersecting) setActiveSec(e.target.id); }),
      { root, rootMargin: '-45% 0px -50% 0px', threshold: 0 },
    );
    secs.forEach((s) => obs.observe(s));
    return () => obs.disconnect();
  }, []);

  const navLink = (id, text) => (
    <a href={`#${id}`} className={activeSec === id ? 'active' : ''}>{text}</a>
  );

  return (
    <div className="landing" ref={landingRef} onScroll={onScroll}>
      {/* scroll progress */}
      <div className="lp-progress" style={{ transform: `scaleX(${progress / 100})` }} />

      {/* nav */}
      <nav className="lp-nav">
        <span className="lp-nav-brand"><img className="lp-nav-logo" src="/oasis-logo.png" alt="OASIS" /></span>
        <div className="lp-nav-links">
          {navLink('the-subject', 'Subject')}
          {navLink('method', 'Method')}
          {navLink('approach', 'Approach')}
          {navLink('building-scale', 'Building')}
          {navLink('through-time', 'Future')}
          {navLink('faq', 'FAQ')}
          <button className="lp-nav-btn" onClick={onLaunch}>Launch ↗</button>
        </div>
      </nav>

      {/* hero — clean dark with a soft warm glow behind the mockup */}
      <div className="lp-hero-wrap">
        <div className="lp-hero-glow" aria-hidden="true" />
        <header className="lp-hero">
          <Reveal className="lp-hero-brand"><img className="lp-hero-logo" src="/oasis-logo.png" alt="PROJECT OASIS" /></Reveal>
          <Reveal className="lp-badge" delay={40}>
            <span className="lp-badge-dot" />demo city Barcelona · IAAC Research Studio Term III
          </Reveal>
          <Reveal as="h1" className="lp-title" delay={100}>
            Who gets protected<br /><span className="lp-title-hot">from the heat first?</span>
          </Reveal>
          <Reveal as="p" className="lp-sub" delay={150}>
            A human-centred instrument that finds the most heat-vulnerable buildings, decides whether
            neighbourhood measures are enough, and designs the retrofit that protects the people inside —
            from satellite data down to the resident&rsquo;s apartment.
          </Reveal>
          <Reveal className="lp-cta" delay={210}>
            <button className="lp-btn primary" onClick={onLaunch}>Launch the tool →</button>
            <a className="lp-btn ghost" href="#method">See the method</a>
          </Reveal>
          <Reveal className="lp-hero-mock" delay={280}>
            <DashboardMock />
          </Reveal>
          <dl className="lp-stats">
            <Stat value={12} label="vulnerability factors" />
            <Stat value={7} label="live data sources" />
            <Stat value={10} label="interventions" />
            <Stat value={2050} label="climate scenario" count={false} />
          </dl>
        </header>
      </div>

      {/* trust strip — data sources as social proof */}
      <div className="lp-trust">
        <span className="lp-trust-label">Built on live, open data</span>
        <div className="lp-marquee" aria-hidden="true">
          <div className="lp-marquee-track">
            {[...SOURCES, ...SOURCES].map((s, i) => <span className="lp-chip" key={i}>{s}</span>)}
          </div>
        </div>
      </div>

      {/* 01 — the subject */}
      <Section n="01" label="The Subject" title="The subject of the project is a person.">
        <Reveal className="lp-persona" delay={80}>
          <div className="lp-persona-text">
            <p>
              An over-75 resident of a top-floor, southwest-facing flat in Barceloneta — pre-1980,
              no air-conditioning. The tool draws their apartment, the heat paths into it, and the
              retrofit that brings it back to safe.
            </p>
            <div className="lp-metric">
              <span className="lp-before">36°C</span>
              <span className="lp-arrow">→</span>
              <span className="lp-after">30°C</span>
              <span className="lp-metric-label">modelled indoor, after retrofit</span>
            </div>
          </div>
          <div className="lp-persona-thumb"><PersonaThumb /></div>
        </Reveal>
      </Section>

      {/* 02 — method */}
      <Section n="02" label="Method" title="A 12-factor Heat Vulnerability Index.">
        <Reveal as="p" className="lp-lead">
          Exposure · sensitivity · adaptive capacity (Reid et al. 2009), normalised 0–1 and weighted
          to a 0–10 index — reported in index points, not degrees.
        </Reveal>
        <div className="lp-pillars">
          {PILLARS.map((p, i) => (
            <Reveal className="lp-pillar lp-glass" key={p.name} delay={i * 110}>
              <div className="lp-pillar-head">
                <span className="lp-pillar-dot" style={{ background: p.color, boxShadow: `0 0 10px ${p.color}` }} />
                <span className="lp-pillar-name">{p.name}</span>
                <span className="lp-pillar-weight">{p.weight}%</span>
              </div>
              <div className="lp-weight">
                <span className="lp-weight-fill" style={{ '--w': `${p.weight}%`, background: p.color }} />
              </div>
              <ul>{p.factors.map((f) => <li key={f}>{f}</li>)}</ul>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* 03 — approach */}
      <Section n="03" label="Approach" title="Diagnose · Decide · Design">
        <Reveal as="p" className="lp-rail-hint">Scroll to follow the process ↓</Reveal>
        <ProcessRail labels={['Diagnose', 'Decide', 'Design']} />
        <div className="lp-steps">
          {STEPS.map((s, i) => (
            <Reveal className="lp-step lp-glass" key={s.n} delay={i * 110}>
              <span className="lp-step-n">{s.n}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* 04 — building scale (bento) */}
      <Section n="04" label="Building scale" title="From the street into the apartment.">
        <Reveal as="p" className="lp-lead">
          The same diagnosis continues indoors. Upload a building’s IFC model and OASIS analyses it room
          by room, renders it in 3D, and proposes retrofits — grounded in the urban heat measured outside
          its walls.
        </Reveal>
        <div className="lp-bento">
          {BUILDING.map((b, i) => (
            <Reveal className={`lp-bento-item lp-glass ${b.big ? 'lp-bento-lg' : ''}`} key={b.title} delay={i * 90}>
              <h3>{b.title}</h3>
              <p>{b.text}</p>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* 05 — through time */}
      <Section n="05" label="Through time" title="Replay the heat across the century.">
        <Reveal as="p" className="lp-lead">
          Every zone is assessed today and against a ~2050 climate scenario — so you can see whose
          vulnerability grows fastest and design for the city that is coming, not just the one that is here.
        </Reveal>
        <Reveal delay={80}><TimeReplay /></Reveal>
      </Section>

      {/* 06 — why it's different */}
      <Section n="06" label="Why it differs" title="A regenerative instrument, not a comfort calculator.">
        <div className="lp-diff">
          {DIFFERENTIATORS.map((d, i) => (
            <Reveal className="lp-diff-row" key={d.k} delay={i * 80}>
              <span className="lp-diff-k">{d.k}</span>
              <span className="lp-diff-v">{d.v}</span>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* 07 — FAQ */}
      <Section n="07" label="FAQ" title="Questions, answered.">
        <Accordion items={FAQS} />
      </Section>

      {/* final CTA */}
      <section className="lp-final">
        <div className="lp-thermal lp-thermal--final" aria-hidden="true" />
        <Reveal as="h2">Draw a zone. Find who&rsquo;s most at risk. Design the give-back.</Reveal>
        <Reveal delay={120}>
          <button className="lp-btn primary big" onClick={onLaunch}>Launch the tool →</button>
        </Reveal>
      </section>

      {/* structured footer */}
      <footer className="lp-foot">
        <div className="lp-foot-brand">
          <img className="lp-foot-logo" src="/oasis-logo.png" alt="OASIS" />
          <p>Overheating Assessment System for Intervention Strategies — a human-centred heat-resilience instrument from satellite scale to the resident’s apartment.</p>
        </div>
        <div className="lp-foot-cols">
          <div className="lp-foot-col">
            <h4>Tool</h4>
            <a href="#method">Method</a>
            <a href="#approach">Approach</a>
            <a href="#building-scale">Building scale</a>
            <a href="#through-time">Future climate</a>
          </div>
          <div className="lp-foot-col">
            <h4>Project</h4>
            <a href="#the-subject">The subject</a>
            <a href="#faq">FAQ</a>
            <a href="https://github.com/helios0007/HVRA" target="_blank" rel="noreferrer">GitHub ↗</a>
          </div>
          <div className="lp-foot-col">
            <h4>Studio</h4>
            <span>IAAC · Research Studio</span>
            <span>Term III · Barcelona</span>
            <button className="lp-foot-cta" onClick={onLaunch}>Launch the tool →</button>
          </div>
        </div>
        <div className="lp-foot-base">
          <span>© {new Date().getFullYear()} OASIS — IAAC Research Studio</span>
          <span>Demonstrator city · Barcelona</span>
        </div>
      </footer>
    </div>
  );
}

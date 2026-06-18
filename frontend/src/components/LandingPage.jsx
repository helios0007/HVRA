// Landing page — the framing screen before the live tool, and the opener for
// the jury. Minimal but structured: a thin nav, numbered sections, and the
// methodology surfaced. Self-contained (no live data), renders instantly.

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
      <div className="lp-section-head">
        <span className="lp-section-n">{n}</span>
        <span className="lp-section-label">{label}</span>
      </div>
      {title && <h2 className="lp-h2">{title}</h2>}
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
  { name: 'Building exposure', weight: '35%', color: '#a78bfa', factors: ['Construction era', 'Roof type', 'Street canyon H/W', 'Green-space proximity'] },
  { name: 'Social vulnerability', weight: '40%', color: '#34d399', factors: ['Population 65+', 'Household income', 'Social isolation', 'No air-conditioning', 'Disability'] },
  { name: 'Thermal context', weight: '25%', color: '#fb923c', factors: ['Land surface temp.', 'Urban heat island', 'NDVI / vegetation'] },
];

const DIFFERENTIATORS = [
  { k: 'Health capital, not degrees', v: 'Headline output is harm avoided — heat deaths and illness averted, sleep recovered.' },
  { k: 'Regenerative give-back', v: 'Counts what each measure does beyond the window: albedo, avoided A/C heat, grid load.' },
  { k: 'Future-climate layer', v: 'Assess present-day and ~2050 — see whose vulnerability grows fastest.' },
  { k: 'Evidence-based', v: 'Every cooling coefficient cited to peer-reviewed literature. No black box.' },
];

const SOURCES = ['Landsat 8/9', 'Sentinel-2', 'Catastro', 'Idescat', 'OpenStreetMap', 'Infrared SDK', 'Renda atlas'];

export default function LandingPage({ onLaunch }) {
  return (
    <div className="landing">
      {/* nav */}
      <nav className="lp-nav">
        <span className="lp-nav-brand">▦ HVRA</span>
        <div className="lp-nav-links">
          <a href="#the-subject">Subject</a>
          <a href="#method">Method</a>
          <a href="#approach">Approach</a>
          <button className="lp-nav-btn" onClick={onLaunch}>Launch ↗</button>
        </div>
      </nav>

      {/* hero */}
      <header className="lp-hero">
        <span className="lp-eyebrow">Urban Heat Triage · demo city Barcelona</span>
        <h1 className="lp-title">Who gets protected<br />from the heat first?</h1>
        <p className="lp-sub">
          A human-centred instrument that finds the most heat-vulnerable buildings, decides whether
          neighbourhood measures are enough, and designs the retrofit that protects the people inside —
          from satellite data down to the resident&rsquo;s apartment.
        </p>
        <div className="lp-cta">
          <button className="lp-btn primary" onClick={onLaunch}>Launch the tool →</button>
          <a className="lp-btn ghost" href="#method">See the method</a>
        </div>
        <dl className="lp-stats">
          <div><dt>12</dt><dd>vulnerability factors</dd></div>
          <div><dt>7</dt><dd>live data sources</dd></div>
          <div><dt>10</dt><dd>interventions</dd></div>
          <div><dt>2050</dt><dd>climate scenario</dd></div>
        </dl>
      </header>

      {/* 01 — the subject */}
      <Section n="01" label="The Subject" title="The subject of the project is a person.">
        <div className="lp-persona">
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
        </div>
      </Section>

      {/* 02 — method */}
      <Section n="02" label="Method" title="A 12-factor Heat Vulnerability Index.">
        <p className="lp-lead">
          Exposure · sensitivity · adaptive capacity (Reid et al. 2009), normalised 0–1 and weighted
          to a 0–10 index — reported in index points, not degrees.
        </p>
        <div className="lp-pillars">
          {PILLARS.map((p) => (
            <div className="lp-pillar" key={p.name}>
              <div className="lp-pillar-head">
                <span className="lp-pillar-dot" style={{ background: p.color }} />
                <span className="lp-pillar-name">{p.name}</span>
                <span className="lp-pillar-weight">{p.weight}</span>
              </div>
              <ul>{p.factors.map((f) => <li key={f}>{f}</li>)}</ul>
            </div>
          ))}
        </div>
      </Section>

      {/* 03 — approach */}
      <Section n="03" label="Approach" title="Diagnose · Decide · Design">
        <div className="lp-steps">
          {STEPS.map((s) => (
            <div className="lp-step" key={s.n}>
              <span className="lp-step-n">{s.n}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* 04 — why it's different */}
      <Section n="04" label="Why it differs" title="A regenerative instrument, not a comfort calculator.">
        <div className="lp-diff">
          {DIFFERENTIATORS.map((d) => (
            <div className="lp-diff-row" key={d.k}>
              <span className="lp-diff-k">{d.k}</span>
              <span className="lp-diff-v">{d.v}</span>
            </div>
          ))}
        </div>
      </Section>

      {/* 05 — data */}
      <Section n="05" label="Data" title="Built on live, open data.">
        <div className="lp-chips">{SOURCES.map((s) => <span className="lp-chip" key={s}>{s}</span>)}</div>
        <p className="lp-note">
          Globally applicable — each city needs only a swappable cadastre, census and income adapter.
          Satellite and street-morphology inputs are already worldwide.
        </p>
      </Section>

      {/* final CTA */}
      <section className="lp-final">
        <h2>Draw a zone. Find who&rsquo;s most at risk. Design the give-back.</h2>
        <button className="lp-btn primary big" onClick={onLaunch}>Launch the tool →</button>
      </section>

      <footer className="lp-footer">
        <span>HVRA — Heat Vulnerability Risk Analyzer</span>
        <span>IAAC Research Studio · Term III</span>
        <a href="https://github.com/helios0007/HVRA" target="_blank" rel="noreferrer">GitHub ↗</a>
      </footer>
    </div>
  );
}

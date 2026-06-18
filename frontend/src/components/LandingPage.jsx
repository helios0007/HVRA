// Landing page — the framing screen before the live tool, and the opener for
// the jury. Leads with the question and the resident, then Diagnose → Decide →
// Design, the differentiators, and the live data sources. Self-contained (no
// live data), so it renders instantly.

// Schematic persona apartment — a tiny static version of the coupled section
function PersonaThumb() {
  return (
    <svg viewBox="0 0 320 240" width="100%" style={{ background: '#fcfcfa', borderRadius: 10 }}
      fontFamily="ui-monospace, Consolas, monospace">
      {/* sun + rays */}
      <g stroke="#e8842a" fill="none" strokeWidth="1">
        <circle cx="34" cy="40" r="9" fill="#fff" />
        {[...Array(8)].map((_, i) => {
          const a = (i * Math.PI) / 4;
          return <line key={i} x1={34 + Math.cos(a) * 12} y1={40 + Math.sin(a) * 12} x2={34 + Math.cos(a) * 16} y2={40 + Math.sin(a) * 16} />;
        })}
        {[0, 1, 2].map((k) => <line key={k} x1={42} y1={48 + k * 7} x2={86} y2={92 + k * 14} strokeDasharray="3 3" opacity="0.7" />)}
      </g>
      {/* roof */}
      <rect x="80" y="58" width="200" height="16" fill="#2e2e2a" />
      {/* walls */}
      <rect x="80" y="74" width="13" height="130" fill="#2e2e2a" />
      <rect x="267" y="74" width="13" height="130" fill="#2e2e2a" />
      <rect x="93" y="74" width="174" height="8" fill="#2e2e2a" />
      <rect x="93" y="196" width="174" height="8" fill="#2e2e2a" />
      {/* SW window */}
      <rect x="80" y="100" width="13" height="84" fill="#dde6ef" stroke="#1a1a1a" strokeWidth="0.8" />
      {/* heat arrows */}
      <g stroke="#d43d2a" fill="#d43d2a">
        <line x1="150" y1="86" x2="150" y2="108" strokeWidth="5" />
        <polygon points="150,112 146,104 154,104" />
      </g>
      <g stroke="#e8842a" fill="#e8842a">
        <line x1="95" y1="140" x2="135" y2="152" strokeWidth="4" />
        <polygon points="139,154 130,150 133,144" />
      </g>
      {/* resident */}
      <g>
        <ellipse cx="135" cy="172" rx="26" ry="32" fill="#d43d2a" opacity="0.15" />
        <rect x="120" y="170" width="30" height="30" rx="3" fill="#f3f3ee" stroke="#1a1a1a" strokeWidth="1" />
        <g stroke="#1a1a1a" fill="none" strokeWidth="1.4">
          <circle cx="132" cy="150" r="6" fill="#fff" />
          <line x1="132" y1="156" x2="134" y2="172" />
          <line x1="134" y1="172" x2="146" y2="172" />
        </g>
      </g>
      <text x="200" y="120" fontSize="11" fontWeight="700" fill="#d43d2a">36°C</text>
      <text x="200" y="134" fontSize="7.5" fill="#8a8a82">indoor · unsafe</text>
    </svg>
  );
}

const STEPS = [
  { n: '01', icon: '🛰️', title: 'Diagnose', text: 'A building-level Heat Vulnerability Index from live satellite, cadastral and census data — visualised in 3D over a street-level heat field.' },
  { n: '02', icon: '⚖️', title: 'Decide', text: 'The decision gate: apply urban-scale measures first, then a verdict on whether building-level retrofit is needed at all.' },
  { n: '03', icon: '📐', title: 'Design', text: 'Evidence-based interventions with a live what-if, and auto-generated climatic drawings — down to the resident\'s apartment section.' },
];

const DIFFERENTIATORS = [
  { icon: '❤️', title: 'Health capital, not degrees', text: 'Headline output is harm avoided — heat deaths and illness averted, sleep recovered.' },
  { icon: '🌱', title: 'Regenerative give-back', text: 'Counts what each measure does beyond the window: albedo, avoided A/C heat, grid load.' },
  { icon: '📈', title: 'Future-climate layer', text: 'Assess present-day and ~2050 — see whose vulnerability grows fastest.' },
  { icon: '📚', title: 'Evidence-based', text: 'Every cooling coefficient cited to peer-reviewed literature. No black box.' },
];

const SOURCES = ['Landsat 8/9', 'Sentinel-2', 'Catastro', 'Idescat', 'OpenStreetMap', 'Infrared SDK'];

export default function LandingPage({ onLaunch }) {
  return (
    <div className="landing">
      {/* hero */}
      <section className="landing-hero">
        <div className="landing-hero-inner">
          <span className="landing-eyebrow">Urban Heat Triage · demo city: Barcelona</span>
          <h1 className="landing-title">Who gets protected<br />from the heat first?</h1>
          <p className="landing-sub">
            From satellite data to the resident's apartment — a human-centred instrument that
            finds the most heat-vulnerable buildings, decides whether neighbourhood measures are
            enough, and designs the retrofit that protects the people inside.
          </p>
          <div className="landing-cta">
            <button className="landing-btn primary" onClick={onLaunch}>Launch the tool →</button>
            <a className="landing-btn ghost" href="#how">See how it works</a>
          </div>
          <div className="landing-statstrip">
            <span><strong>12</strong> vulnerability factors</span>
            <span><strong>7</strong> live data sources</span>
            <span><strong>10</strong> interventions</span>
            <span><strong>2050</strong> climate scenario</span>
          </div>
        </div>
      </section>

      {/* the resident */}
      <section className="landing-persona">
        <div className="landing-persona-text">
          <h2>The subject of the project is a person.</h2>
          <p>
            An over-75 resident of a top-floor, southwest-facing flat in Barceloneta — pre-1980,
            no air-conditioning. The tool draws their apartment, the heat paths into it, and the
            retrofit that brings it back to safe.
          </p>
          <div className="landing-persona-metric">
            <span className="lp-before">36°C</span>
            <span className="lp-arrow">→</span>
            <span className="lp-after">30°C</span>
            <span className="lp-label">modelled indoor, after retrofit</span>
          </div>
        </div>
        <div className="landing-persona-thumb"><PersonaThumb /></div>
      </section>

      {/* how it works */}
      <section className="landing-how" id="how">
        <h2 className="landing-h2">Diagnose · Decide · Design</h2>
        <div className="landing-steps">
          {STEPS.map((s) => (
            <div className="landing-step" key={s.n}>
              <div className="landing-step-head">
                <span className="landing-step-n">{s.n}</span>
                <span className="landing-step-icon">{s.icon}</span>
              </div>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* differentiators */}
      <section className="landing-diff">
        <h2 className="landing-h2">A regenerative instrument, not a comfort calculator</h2>
        <div className="landing-diff-grid">
          {DIFFERENTIATORS.map((d) => (
            <div className="landing-diff-card" key={d.title}>
              <span className="landing-diff-icon">{d.icon}</span>
              <h3>{d.title}</h3>
              <p>{d.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* data sources */}
      <section className="landing-data">
        <span className="landing-data-label">Built on live, open data</span>
        <div className="landing-data-chips">
          {SOURCES.map((s) => <span className="landing-chip" key={s}>{s}</span>)}
        </div>
        <p className="landing-data-note">
          Globally applicable — each city needs only a swappable cadastre, census and income adapter.
          Satellite and street-morphology inputs are already worldwide.
        </p>
      </section>

      {/* final CTA */}
      <section className="landing-final">
        <h2>Draw a zone. Find who's most at risk. Design the give-back.</h2>
        <button className="landing-btn primary big" onClick={onLaunch}>Launch the tool →</button>
      </section>

      <footer className="landing-footer">
        <span>HVRA — Heat Vulnerability Risk Analyzer</span>
        <span>IAAC Research Studio · Term III</span>
        <a href="https://github.com/helios0007/HVRA" target="_blank" rel="noreferrer">GitHub ↗</a>
      </footer>
    </div>
  );
}

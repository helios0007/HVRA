// 12-factor HVI breakdown grouped by bucket, with weight chips and score bars.
// Accepts the `hvi_factors` property of a building feature.

const BUCKETS = [
  {
    key: 'building',
    icon: '🏢',
    label: 'Building exposure',
    weight: '35%',
    color: '#a78bfa',
    factors: [
      { key: 'construction_era', label: 'Construction era', source: 'Catastro · pre-1980 = highest risk', weight: 15 },
      { key: 'roof_type', label: 'Roof type', source: 'Catastro/OSM · flat roof = higher risk', weight: 10 },
      { key: 'street_canyon', label: 'Street canyon H/W', source: 'OSM · narrow = less ventilation', weight: 5 },
      { key: 'green_space', label: 'Green space within 50m', source: 'OSM · absence = higher exposure', weight: 5 },
    ],
  },
  {
    key: 'social',
    icon: '👥',
    label: 'Social vulnerability',
    weight: '40%',
    color: '#34d399',
    factors: [
      { key: 'elderly_population', label: '% population 65+', source: 'Idescat census sections', weight: 15 },
      { key: 'household_income', label: 'Household income', source: 'BCN income atlas · inverse', weight: 10 },
      { key: 'social_isolation', label: '% single-person households', source: 'Census 2021 · isolation proxy', weight: 7 },
      { key: 'no_ac', label: '% households without AC', source: 'Census 2021 cooling systems', weight: 5 },
      { key: 'disability', label: '% population with disability', source: 'INE · mobility limitations', weight: 3 },
    ],
  },
  {
    key: 'thermal',
    icon: '🌡️',
    label: 'Thermal context',
    weight: '25%',
    color: '#fb923c',
    factors: [
      { key: 'lst', label: 'Land surface temperature', source: 'Landsat C2 L2 · 30m', weight: 15 },
      { key: 'uhi_delta', label: 'UHI delta vs city mean', source: 'Landsat · same scene', weight: 5 },
      { key: 'ndvi', label: 'NDVI / vegetation cover', source: 'Sentinel-2 · 10m · inverse', weight: 5 },
    ],
  },
];

export default function FactorBreakdown({ factors, compact = false }) {
  if (!factors) return null;

  return (
    <div className={`factor-breakdown ${compact ? 'compact' : ''}`}>
      {BUCKETS.map((bucket) => (
        <div className="fb-bucket" key={bucket.key}>
          <div className="fb-bucket-header">
            <span className="fb-bucket-title">
              <span className="fb-bucket-icon">{bucket.icon}</span>
              {bucket.label}
            </span>
            <span className="fb-bucket-chip" style={{ borderColor: bucket.color, color: bucket.color }}>
              {bucket.weight}
            </span>
          </div>
          {bucket.factors.map((f) => {
            const data = factors[f.key];
            const score = data?.score ?? null;
            return (
              <div className="fb-factor" key={f.key}>
                <div className="fb-factor-row">
                  <span className="fb-factor-label" title={f.source}>{f.label}</span>
                  <span className="fb-factor-meta">
                    <span className="fb-factor-weight">{f.weight}%</span>
                    <span className="fb-factor-score">{score !== null ? score.toFixed(2) : '—'}</span>
                  </span>
                </div>
                <div className="fb-bar">
                  <div
                    className="fb-bar-fill"
                    style={{
                      width: `${score !== null ? Math.min(score * 100, 100) : 0}%`,
                      backgroundColor: bucket.color,
                    }}
                  />
                </div>
                {!compact && <div className="fb-factor-source">{f.source}</div>}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

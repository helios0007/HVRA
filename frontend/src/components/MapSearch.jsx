import React, { useState, useRef, useEffect } from 'react';

// Lightweight, dependency-free location search for the draw-zone map.
// Calls the Mapbox Geocoding API (same token the map already uses) and flies
// the map to the chosen result so users can navigate to a place before drawing
// their zone, instead of panning the basemap manually.
const TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

export default function MapSearch({ mapRef }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(-1);
  const debounceRef = useRef(null);
  const boxRef = useRef(null);

  // Close the dropdown when clicking outside the search box.
  useEffect(() => {
    const onDoc = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const search = async (q) => {
    if (!TOKEN || !q || q.trim().length < 3) { setResults([]); setOpen(false); return; }
    setLoading(true);
    try {
      const map = mapRef?.current;
      let prox = '';
      if (map) { const c = map.getCenter(); prox = `&proximity=${c.lng},${c.lat}`; }
      const url =
        `https://api.mapbox.com/geocoding/v5/mapbox.places/${encodeURIComponent(q.trim())}.json` +
        `?access_token=${TOKEN}&limit=5&language=en` +
        `&types=place,locality,neighborhood,address,poi${prox}`;
      const res = await fetch(url);
      const data = await res.json();
      setResults(Array.isArray(data.features) ? data.features : []);
      setActive(-1);
      setOpen(true);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const onChange = (e) => {
    const v = e.target.value;
    setQuery(v);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(v), 350);
  };

  const goTo = (f) => {
    const map = mapRef?.current;
    if (map && f) {
      if (Array.isArray(f.bbox) && f.bbox.length === 4) {
        map.fitBounds([[f.bbox[0], f.bbox[1]], [f.bbox[2], f.bbox[3]]],
          { padding: 60, duration: 1200, maxZoom: 16 });
      } else if (Array.isArray(f.center)) {
        map.flyTo({ center: f.center, zoom: 15, duration: 1200 });
      }
    }
    setQuery(f?.place_name || '');
    setResults([]);
    setOpen(false);
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && (!open || results.length === 0)) {
      clearTimeout(debounceRef.current);
      search(query);
      return;
    }
    if (!open || results.length === 0) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); goTo(results[active >= 0 ? active : 0]); }
    else if (e.key === 'Escape') { setOpen(false); }
  };

  const clear = () => { setQuery(''); setResults([]); setOpen(false); };

  if (!TOKEN) return null;

  return (
    <div
      ref={boxRef}
      style={{
        position: 'absolute', top: '1.5rem', left: '1.5rem', zIndex: 11, width: '300px',
        fontSize: '0.9rem',
      }}
    >
      <div
        style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          background: 'rgba(255, 255, 255, 0.97)', border: '1px solid #E2E8F0',
          borderRadius: open && results.length ? '12px 12px 0 0' : '12px',
          boxShadow: '0 10px 25px rgba(15, 23, 42, 0.12)', padding: '0.55rem 0.75rem',
          backdropFilter: 'blur(8px)',
        }}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748B" strokeWidth="2" style={{ flexShrink: 0 }}>
          <circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input
          value={query}
          onChange={onChange}
          onKeyDown={onKeyDown}
          onFocus={() => { if (results.length) setOpen(true); }}
          placeholder="Search a location…"
          aria-label="Search a location"
          style={{
            flex: 1, border: 'none', outline: 'none', background: 'transparent',
            fontSize: '0.9rem', color: '#0F172A',
          }}
        />
        {loading && (
          <span style={{ fontSize: '0.7rem', color: '#94A3B8', flexShrink: 0 }}>…</span>
        )}
        {!loading && query && (
          <button
            onClick={clear}
            aria-label="Clear search"
            style={{
              border: 'none', background: 'transparent', cursor: 'pointer',
              color: '#94A3B8', fontSize: '1.1rem', lineHeight: 1, padding: 0, flexShrink: 0,
            }}
          >×</button>
        )}
      </div>

      {open && results.length > 0 && (
        <ul
          style={{
            listStyle: 'none', margin: 0, padding: 0,
            background: 'rgba(255, 255, 255, 0.99)', border: '1px solid #E2E8F0', borderTop: 'none',
            borderRadius: '0 0 12px 12px', boxShadow: '0 12px 25px rgba(15, 23, 42, 0.12)',
            overflow: 'hidden', maxHeight: '260px', overflowY: 'auto',
          }}
        >
          {results.map((f, i) => (
            <li
              key={f.id || i}
              onMouseDown={(e) => { e.preventDefault(); goTo(f); }}
              onMouseEnter={() => setActive(i)}
              style={{
                padding: '0.55rem 0.85rem', cursor: 'pointer',
                background: i === active ? '#EFF6FF' : 'transparent',
                borderTop: i === 0 ? 'none' : '1px solid #F1F5F9',
              }}
            >
              <div style={{ fontWeight: 600, color: '#0F172A', fontSize: '0.85rem' }}>
                {f.text || f.place_name}
              </div>
              {f.place_name && f.place_name !== f.text && (
                <div style={{ fontSize: '0.75rem', color: '#64748B', marginTop: '1px' }}>
                  {f.place_name}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

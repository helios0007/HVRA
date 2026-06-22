import React, { useEffect, useRef, useState } from 'react'
import './RenderView.css'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/**
 * Full-screen "after retrofit" AI render view — replaces the room-detail
 * sidebar while open so the generated image has room to breathe. Supports
 * back/forward navigation across every render requested this session
 * (a simple array + index, like browser history).
 *
 * history: [{ jobId, room, strategyId, strategyName, viewType, orientation,
 *             status, imageUrl, error, sourceUrl, sourceType,
 *             heading, pitch, fov }]
 *
 * status: 'framing' (exterior strategies only — adjust the Street View
 * camera before rendering) → 'idle' → 'loading' → 'done' | 'error'.
 *
 * sourceUrl points at the real photo (Street View or 3D viewport screenshot)
 * the render was generated from — shown alongside the result so the user
 * can self-check Street View actually captured the correct building/facade
 * before trusting the AI render.
 */
const ORIENTATION_HEADING = { N: 0, NE: 45, E: 90, SE: 135, S: 180, SW: 225, W: 270, NW: 315 }

export default function RenderView({ history, index, onNavigate, onClose, onResolve, onCaptureScreenshot }) {
  const entry = history[index]
  const requestedRef = useRef(new Set())
  const [lightbox, setLightbox] = useState(null)   // { src, alt } | null
  const [showPromptBox, setShowPromptBox] = useState(false)
  const [customPrompt, setCustomPrompt] = useState('')

  // ── Frame adjustment (Street View only) — heading/pitch/fov sliders with
  // a live preview, shown before the paid AI render fires, so the user can
  // pan/tilt/zoom until the whole building is actually in frame. Defaults
  // to the orientation-derived heading; the user can nudge from there.
  const [frame, setFrame] = useState(null)         // { heading, pitch, fov } | null
  const [previewUrl, setPreviewUrl] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState(null)

  useEffect(() => {
    if (!entry || entry.status !== 'framing') {
      setFrame(null)
      return
    }
    setFrame({
      heading: ORIENTATION_HEADING[entry.orientation?.toUpperCase()] ?? 180,
      pitch: 0,
      fov: 80,
    })
  }, [entry?.jobId, entry?.room?.room_id, entry?.strategyId, entry?.status])

  // Fetch a live preview whenever the frame changes, debounced so dragging
  // a slider doesn't fire a request per pixel.
  useEffect(() => {
    if (!entry || entry.status !== 'framing' || !frame) return
    setPreviewLoading(true)
    setPreviewError(null)
    const t = setTimeout(() => {
      const params = new URLSearchParams({
        heading: frame.heading, pitch: frame.pitch, fov: frame.fov,
      })
      fetch(`${API_URL}/jobs/${entry.jobId}/street_view_preview?${params}`)
        .then(res => {
          if (!res.ok) throw new Error('No Street View coverage at this location/angle')
          return res.blob()
        })
        .then(blob => {
          setPreviewUrl(prev => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(blob) })
          setPreviewLoading(false)
        })
        .catch(err => {
          setPreviewError(err.message)
          setPreviewLoading(false)
        })
    }, 350)
    return () => clearTimeout(t)
  }, [frame, entry?.jobId, entry?.status])

  // Kick off the request the first time a fresh (idle) entry is shown.
  useEffect(() => {
    if (!entry || entry.status !== 'idle') return
    const key = `${entry.jobId}__${entry.room.room_id}__${entry.strategyId}__${entry.customPrompt || ''}__${entry.heading ?? ''}_${entry.pitch ?? ''}_${entry.fov ?? ''}`
    if (requestedRef.current.has(key)) return
    requestedRef.current.add(key)
    runRender(entry, index, onResolve, onCaptureScreenshot)
  }, [entry, index])

  useEffect(() => {
    setShowPromptBox(false)
    setCustomPrompt('')
  }, [index])

  if (!entry) return null

  const canBack = index > 0
  const canForward = index < history.length - 1

  if (entry.status === 'framing') {
    return (
      <div className="render-view">
        <div className="render-view-toolbar">
          <button className="rv-nav-btn" disabled={!canBack} onClick={() => onNavigate(index - 1)} title="Previous render">
            ← Back
          </button>
          <div className="rv-title">
            <span className="rv-room">{entry.room.room_name}</span>
            <span className="rv-strategy">{entry.strategyName}</span>
          </div>
          <button className="rv-close-btn" onClick={onClose} title="Close render view">✕</button>
        </div>

        <div className="render-view-body">
          <div className="rv-frame-pane">
            <div className="rv-frame-preview">
              {previewUrl && (
                <img src={previewUrl} alt="Street View preview" className="rv-image" />
              )}
              {previewLoading && <div className="rv-frame-loading">Loading preview…</div>}
              {previewError && !previewLoading && (
                <div className="rv-frame-error">
                  {previewError} — you can still continue; the render will fall back to a 3D viewport screenshot.
                </div>
              )}
            </div>

            <div className="rv-frame-controls">
              <p className="rv-frame-hint">
                Adjust the camera until the whole building is in frame, then continue.
              </p>
              <label className="rv-frame-slider">
                <span>Heading (pan) — {Math.round(frame?.heading ?? 0)}°</span>
                <input
                  type="range" min="0" max="359" step="1"
                  value={frame?.heading ?? 0}
                  onChange={e => setFrame(f => ({ ...f, heading: Number(e.target.value) }))}
                />
              </label>
              <label className="rv-frame-slider">
                <span>Pitch (tilt) — {frame?.pitch ?? 0}°</span>
                <input
                  type="range" min="-30" max="30" step="1"
                  value={frame?.pitch ?? 0}
                  onChange={e => setFrame(f => ({ ...f, pitch: Number(e.target.value) }))}
                />
              </label>
              <label className="rv-frame-slider">
                <span>Field of view (zoom out) — {frame?.fov ?? 80}°</span>
                <input
                  type="range" min="40" max="120" step="5"
                  value={frame?.fov ?? 80}
                  onChange={e => setFrame(f => ({ ...f, fov: Number(e.target.value) }))}
                />
              </label>
              <div className="rv-frame-actions">
                <button
                  className="rv-modify-cancel"
                  onClick={() => onResolve(index, { status: 'idle' })}
                  title="Skip adjusting and use the default frame"
                >
                  Use default frame
                </button>
                <button
                  className="rv-modify-submit"
                  disabled={!previewUrl}
                  onClick={() => onResolve(index, {
                    status: 'idle', heading: frame.heading, pitch: frame.pitch, fov: frame.fov,
                  })}
                >
                  Use this frame →
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="render-view">
      <div className="render-view-toolbar">
        <button className="rv-nav-btn" disabled={!canBack} onClick={() => onNavigate(index - 1)} title="Previous render">
          ← Back
        </button>
        <div className="rv-title">
          <span className="rv-room">{entry.room.room_name}</span>
          <span className="rv-strategy">{entry.strategyName}</span>
        </div>
        <button className="rv-nav-btn" disabled={!canForward} onClick={() => onNavigate(index + 1)} title="Next render">
          Forward →
        </button>
        <button className="rv-close-btn" onClick={onClose} title="Close render view">✕</button>
      </div>

      <div className="render-view-body">
        {entry.status === 'idle' || entry.status === 'loading' ? (
          <div className="rv-loading">
            <span className="rv-spinner" />
            Generating photorealistic render of {entry.strategyName.toLowerCase()}…
          </div>
        ) : entry.status === 'error' ? (
          <div className="rv-error">
            <p>{entry.error}</p>
            <button
              className="rv-retry-btn"
              onClick={() => runRender(entry, index, onResolve, onCaptureScreenshot, true)}
            >
              Try again
            </button>
          </div>
        ) : (
          <div className="rv-compare">
            {entry.sourceUrl && (
              <div className="rv-compare-pane">
                <span className="rv-compare-label">
                  Source photo
                  {entry.sourceType && (
                    <span className="rv-source-tag">
                      {entry.sourceType === 'street_view' ? 'Google Street View' : '3D viewport'}
                    </span>
                  )}
                </span>
                <img
                  src={entry.sourceUrl}
                  alt="Source photo this render is based on"
                  className="rv-image rv-image--clickable"
                  onClick={() => setLightbox({ src: entry.sourceUrl, alt: 'Source photo' })}
                />
              </div>
            )}
            <div className="rv-compare-pane">
              <span className="rv-compare-label">After retrofit (AI render)</span>
              <img
                src={entry.imageUrl}
                alt={`${entry.strategyName} applied`}
                className="rv-image rv-image--clickable"
                onClick={() => setLightbox({ src: entry.imageUrl, alt: `${entry.strategyName} applied` })}
              />
            </div>
          </div>
        )}
      </div>

      {(entry.status === 'done' || entry.status === 'error') && (
        <div className="rv-modify">
          {!showPromptBox ? (
            <button className="rv-modify-toggle" onClick={() => setShowPromptBox(true)}>
              ✎ Not quite right? Describe what to change
            </button>
          ) : (
            <div className="rv-modify-box">
              <textarea
                className="rv-modify-input"
                placeholder='e.g. "Make the louvers dark bronze metal, angled steeper, with wider gaps between slats"'
                value={customPrompt}
                onChange={e => setCustomPrompt(e.target.value)}
                rows={2}
              />
              <div className="rv-modify-actions">
                <button
                  className="rv-modify-cancel"
                  onClick={() => { setShowPromptBox(false); setCustomPrompt('') }}
                >
                  Cancel
                </button>
                <button
                  className="rv-modify-submit"
                  disabled={!customPrompt.trim()}
                  onClick={() => {
                    const trimmed = customPrompt.trim()
                    onResolve(index, { customPrompt: trimmed })
                    runRender({ ...entry, customPrompt: trimmed }, index, onResolve, onCaptureScreenshot)
                    setShowPromptBox(false)
                  }}
                >
                  Regenerate with this change
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {lightbox && (
        <div className="rv-lightbox" onClick={() => setLightbox(null)}>
          <img src={lightbox.src} alt={lightbox.alt} className="rv-lightbox-img" />
          <button className="rv-lightbox-close" onClick={() => setLightbox(null)}>✕</button>
        </div>
      )}

      {history.length > 1 && (
        <div className="rv-history-strip">
          {history.map((h, i) => (
            <button
              key={i}
              className={`rv-thumb ${i === index ? 'rv-thumb--active' : ''}`}
              onClick={() => onNavigate(i)}
              title={`${h.room.room_name} — ${h.strategyName}`}
            >
              {h.status === 'done' && h.imageUrl
                ? <img src={h.imageUrl} alt="" />
                : <span className="rv-thumb-placeholder">{h.status === 'error' ? '!' : '…'}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

async function runRender(entry, index, onResolve, onCaptureScreenshot, isRetry = false) {
  onResolve(index, { status: 'loading' })
  try {
    const customPrompt = entry.customPrompt || ''
    const hasCustomFrame = entry.heading != null

    const appendFrame = (form) => {
      if (hasCustomFrame) {
        form.append('heading', entry.heading)
        form.append('pitch', entry.pitch ?? 0)
        form.append('fov', entry.fov ?? 80)
      }
    }

    const form = new FormData()
    form.append('room_id', entry.room.room_id)
    form.append('strategy_id', entry.strategyId)
    form.append('orientation', entry.orientation || '')
    form.append('room_name', entry.room.room_name || '')
    form.append('custom_prompt', customPrompt)
    appendFrame(form)

    let res = await fetch(`${API_URL}/jobs/${entry.jobId}/render`, { method: 'POST', body: form })

    // 422 with no fallback sent yet → Street View had no coverage (or this
    // is an interior strategy) — capture the viewport and retry once.
    if (res.status === 422 && onCaptureScreenshot) {
      const blob = await onCaptureScreenshot()
      if (!blob) throw new Error('Could not capture a fallback viewport screenshot')
      const retryForm = new FormData()
      retryForm.append('room_id', entry.room.room_id)
      retryForm.append('strategy_id', entry.strategyId)
      retryForm.append('orientation', entry.orientation || '')
      retryForm.append('room_name', entry.room.room_name || '')
      retryForm.append('custom_prompt', customPrompt)
      appendFrame(retryForm)
      retryForm.append('fallback_screenshot', blob, 'viewport.jpg')
      res = await fetch(`${API_URL}/jobs/${entry.jobId}/render`, { method: 'POST', body: retryForm })
    }

    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error(detail.detail || `Render failed (HTTP ${res.status})`)
    }

    const sourceType = res.headers.get('X-Render-Source') || null
    const blob = await res.blob()

    // Fetch the saved source photo for self-check display alongside the
    // result — failure here shouldn't block showing the actual render.
    let sourceUrl = null
    try {
      const srcParams = new URLSearchParams({
        room_id: entry.room.room_id,
        strategy_id: entry.strategyId,
        custom_prompt: customPrompt,
        orientation: entry.orientation || '',
      })
      if (hasCustomFrame) {
        srcParams.set('heading', entry.heading)
        srcParams.set('pitch', entry.pitch ?? 0)
        srcParams.set('fov', entry.fov ?? 80)
      }
      const srcRes = await fetch(`${API_URL}/jobs/${entry.jobId}/render_source?${srcParams}`)
      if (srcRes.ok) sourceUrl = URL.createObjectURL(await srcRes.blob())
    } catch { /* non-fatal — render still shown without the source preview */ }

    onResolve(index, {
      status: 'done',
      imageUrl: URL.createObjectURL(blob),
      sourceUrl,
      sourceType,
    })
  } catch (err) {
    onResolve(index, { status: 'error', error: err.message || 'Render failed' })
  }
}

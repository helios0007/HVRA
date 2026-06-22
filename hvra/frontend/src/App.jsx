import React, { useState, useRef, useCallback, useEffect } from 'react'
import IntakeForm from './components/IntakeForm'
import Viewer3D from './components/Viewer3D'
import RoomPanel from './components/RoomPanel'
import PortfolioView from './components/PortfolioView'
import ComfortIndicator from './components/ComfortIndicator'
import RenderView from './components/RenderView'
import './App.css'

export default function App() {
  const [result, setResult] = useState(null)
  const [selectedRoom, setSelectedRoom] = useState(null)
  const [activeTab, setActiveTab] = useState('portfolio')
  const [beforeAfter, setBeforeAfter] = useState('before')
  // Whether an AI "after retrofit" render has been generated for this job.
  // Gates the Before/After toggle.
  const [hasRender, setHasRender] = useState(false)
  // The toggle buttons that set `beforeAfter` are themselves hidden until
  // hasRender is true, but every CONSUMER of `beforeAfter` (RoomPanel,
  // Viewer3D) should derive from this instead of the raw state — so that
  // an 'after' value can never leak into the UI before a render actually
  // exists, regardless of how `beforeAfter` got set.
  const effectiveBeforeAfter = hasRender ? beforeAfter : 'before'
  // Which rooms (by room_id) have at least one successful render — drives
  // the comfort ring turning green for that specific room once it has been
  // rendered, rather than globally for every room in the building.
  const [renderedRoomIds, setRenderedRoomIds] = useState(() => new Set())
  const viewerRef = useRef(null)

  // ── AI render view — replaces the sidebar while open ───────────────────
  // History of every render requested this session, with back/forward nav
  // (like browser history). renderOpen toggles the full-screen overlay.
  const [renderHistory, setRenderHistory] = useState([])
  const [renderIndex, setRenderIndex] = useState(-1)
  const [renderOpen, setRenderOpen] = useState(false)

  // Dark theme applies only to the intake/form page — results view keeps
  // the light theme (3D viewer + sidebar already use a dark canvas of
  // their own and were designed against light surfaces).
  useEffect(() => {
    document.body.classList.toggle('theme-dark', !result)
    return () => document.body.classList.remove('theme-dark')
  }, [result])

  // ── Resizable sidebar ──────────────────────────────────────────────────
  const [sidebarWidth, setSidebarWidth] = useState(340)
  const draggingRef = useRef(false)

  useEffect(() => {
    const onMove = (e) => {
      if (!draggingRef.current) return
      e.preventDefault()
      setSidebarWidth(Math.min(Math.max(e.clientX, 260), 720))
    }
    const onUp = () => {
      if (!draggingRef.current) return
      draggingRef.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])

  const startResize = (e) => {
    e.preventDefault()
    draggingRef.current = true
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }

  // Called by RetrofitCard when a strategy is focused/clicked
  const handleStrategyHighlight = useCallback((globalIds, hexColor, roomGlobalId) => {
    viewerRef.current?.highlightElements(globalIds, hexColor, true, { roomGlobalId })
  }, [])

  const handleHighlightClear = useCallback(() => {
    viewerRef.current?.clearHighlights()
  }, [])

  const handleStrategyHighlightGroups = useCallback((groups, opts) => {
    viewerRef.current?.highlightGroups(groups, true, opts)
  }, [])

  const handleInspectRoomToggle = useCallback((roomGlobalId, on, riskLevel) => {
    if (on) {
      viewerRef.current?.highlightInspectedRoom(roomGlobalId, riskLevel)
    } else {
      viewerRef.current?.clearInspectedRoomHighlight()
    }
  }, [])

  // Called by RenderView when it needs a fallback source image for AI
  // rendering (Street View had no coverage at the building's address).
  const handleCaptureScreenshot = useCallback(() => {
    return viewerRef.current?.captureScreenshot() ?? Promise.resolve(null)
  }, [])

  // Called by RetrofitCard's render button — opens the full-screen render
  // view (replacing the sidebar) and appends a new history entry. Exterior
  // strategies start in 'framing' so the user can adjust the Street View
  // camera (the building isn't always fully in the default frame) before
  // the paid AI render fires; interior strategies skip straight to 'idle',
  // which RenderView's effect picks up and turns into an API request.
  const handleOpenRender = useCallback((req) => {
    const initialStatus = req.viewType === 'exterior' ? 'framing' : 'idle'
    setRenderHistory(prev => {
      const next = [...prev, { ...req, status: initialStatus, imageUrl: null, error: null }]
      setRenderIndex(next.length - 1)
      return next
    })
    setRenderOpen(true)
  }, [])

  const handleRenderNavigate = useCallback((i) => setRenderIndex(i), [])

  const handleRenderClose = useCallback(() => setRenderOpen(false), [])

  // Called by RenderView to update one history entry's status/result as the
  // request progresses (idle → loading → done/error). The first successful
  // render in the whole session unlocks the Before/After toggle; each
  // successful render also marks its specific room as "improved" for the
  // comfort ring.
  const handleRenderResolve = useCallback((i, patch) => {
    setRenderHistory(prev => {
      const next = prev.map((h, idx) => idx === i ? { ...h, ...patch } : h)
      if (patch.status === 'done') {
        const roomId = next[i]?.room?.room_id
        if (roomId) {
          setRenderedRoomIds(prevSet => new Set(prevSet).add(roomId))
        }
      }
      return next
    })
    if (patch.status === 'done') setHasRender(true)
  }, [])

  const handleUploadSuccess = (data) => {
    setResult(data)
    setSelectedRoom(null)
    setActiveTab('portfolio')
    setBeforeAfter('before')
    setHasRender(false)
    setRenderHistory([])
    setRenderIndex(-1)
    setRenderOpen(false)
    setRenderedRoomIds(new Set())
  }

  const handleRoomSelect = (room) => {
    setSelectedRoom(room)
    setActiveTab('room')
  }

  if (!result) {
    return (
      <div className="app">
        <header className="app-header">
          <div className="header-inner">
            <span className="logo-tag">OASIS</span>
            <span className="header-sub">Heat Vulnerability Retrofit Assistant</span>
          </div>
        </header>
        <main className="app-main">
          <IntakeForm onSuccess={handleUploadSuccess} />
        </main>
      </div>
    )
  }

  return (
    <div className="app results-layout">
      <header className="app-header results-header">
        <div className="header-inner">
          <span className="logo-tag">OASIS</span>
          <span className="header-sub">Heat Vulnerability Retrofit Assistant</span>
        </div>

        <div className="header-center">
          {result.warnings?.length > 0 && (
            <span className="warn-pill">{result.warnings.length} warning{result.warnings.length > 1 ? 's' : ''}</span>
          )}
          <span className="header-meta">
            {result.neighbourhood} · UHI +{result.uhi_delta?.toFixed(1)}°C · {result.room_count} rooms
          </span>
        </div>

        <div className="header-actions">
          {!hasRender ? (
            <span className="render-hint" title="Open a room → expand a shading or window strategy card → click Render">
              Render a strategy to unlock before/after
            </span>
          ) : (
            <div className="ba-toggle">
              <button
                className={effectiveBeforeAfter === 'before' ? 'active' : ''}
                onClick={() => setBeforeAfter('before')}
              >
                Before
              </button>
              <button
                className={effectiveBeforeAfter === 'after' ? 'active' : ''}
                onClick={() => setBeforeAfter('after')}
              >
                After retrofit
              </button>
            </div>
          )}
          <button className="btn-new" onClick={() => { setResult(null); setSelectedRoom(null) }}>
            New assessment
          </button>
        </div>
      </header>

      <div className="results-body">
        <aside className="sidebar" style={{ width: sidebarWidth }}>
          {renderOpen && renderHistory.length > 0 ? (
            <RenderView
              history={renderHistory}
              index={renderIndex}
              onNavigate={handleRenderNavigate}
              onClose={handleRenderClose}
              onResolve={handleRenderResolve}
              onCaptureScreenshot={handleCaptureScreenshot}
            />
          ) : (
            <>
              <div className="sidebar-tabs">
                <button
                  className={activeTab === 'portfolio' ? 'tab active' : 'tab'}
                  onClick={() => setActiveTab('portfolio')}
                >
                  All rooms ({result.rooms.length})
                </button>
                <button
                  className={activeTab === 'room' ? 'tab active' : 'tab'}
                  onClick={() => setActiveTab('room')}
                  disabled={!selectedRoom}
                >
                  Room detail
                </button>
              </div>

              <div className="sidebar-content">
                {activeTab === 'portfolio' && (
                  <PortfolioView
                    rooms={result.rooms}
                    selectedRoom={selectedRoom}
                    onSelectRoom={handleRoomSelect}
                  />
                )}
                {activeTab === 'room' && selectedRoom && (
                  <RoomPanel
                    room={selectedRoom}
                    allRooms={result.rooms}
                    beforeAfter={effectiveBeforeAfter}
                    roofIds={result.roof_element_ids ?? []}
                    windDeg={result.prevailing_wind_deg}
                    crossVentSpaces={result.cross_ventilation?.spaces ?? []}
                    jobId={result.job_id}
                    onInspectRoomToggle={handleInspectRoomToggle}
                    onStrategyHighlight={handleStrategyHighlight}
                    onStrategyHighlightGroups={handleStrategyHighlightGroups}
                    onHighlightClear={handleHighlightClear}
                    onOpenRender={handleOpenRender}
                  />
                )}
                {activeTab === 'room' && !selectedRoom && (
                  <p className="no-selection">Click a room in the 3D viewer or the portfolio list to see details.</p>
                )}
              </div>
            </>
          )}
        </aside>

        <div
          className="sidebar-resizer"
          onMouseDown={startResize}
          title="Drag to resize panel"
        />

        <main className="viewer-wrap">
          <Viewer3D
            ref={viewerRef}
            key={result.job_id}
            jobId={result.job_id}
            rooms={result.rooms}
            selectedRoom={selectedRoom}
            onRoomSelect={handleRoomSelect}
            beforeAfter={effectiveBeforeAfter}
          />
          <div className="viewer-legend">
            <span className="leg critical">Critical</span>
            <span className="leg high">High</span>
            <span className="leg moderate">Moderate</span>
            <span className="leg safe">Safe</span>
            <span className="leg vent">Vent. deficit</span>
          </div>
          <ComfortIndicator
            rooms={result.rooms}
            selectedRoom={selectedRoom}
            roomRendered={selectedRoom ? renderedRoomIds.has(selectedRoom.room_id) : false}
          />
        </main>
      </div>
    </div>
  )
}

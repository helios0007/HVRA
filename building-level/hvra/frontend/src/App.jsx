import React, { useState, useRef, useCallback, useEffect } from 'react'
import IntakeForm from './components/IntakeForm'
import Viewer3D from './components/Viewer3D'
import RoomPanel from './components/RoomPanel'
import PortfolioView from './components/PortfolioView'
import './App.css'

export default function App() {
  const [result, setResult] = useState(null)
  const [selectedRoom, setSelectedRoom] = useState(null)
  const [activeTab, setActiveTab] = useState('portfolio')
  const [beforeAfter, setBeforeAfter] = useState('before')
  const viewerRef = useRef(null)

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

  const handleUploadSuccess = (data) => {
    setResult(data)
    setSelectedRoom(null)
    setActiveTab('portfolio')
    setBeforeAfter('before')
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
          <div className="ba-toggle">
            <button
              className={beforeAfter === 'before' ? 'active' : ''}
              onClick={() => setBeforeAfter('before')}
            >
              Before
            </button>
            <button
              className={beforeAfter === 'after' ? 'active' : ''}
              onClick={() => setBeforeAfter('after')}
            >
              After retrofit
            </button>
          </div>
          <button className="btn-new" onClick={() => { setResult(null); setSelectedRoom(null) }}>
            New assessment
          </button>
        </div>
      </header>

      <div className="results-body">
        <aside className="sidebar" style={{ width: sidebarWidth }}>
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
                beforeAfter={beforeAfter}
                roofIds={result.roof_element_ids ?? []}
                windDeg={result.prevailing_wind_deg}
                onInspectRoomToggle={handleInspectRoomToggle}
                onStrategyHighlight={handleStrategyHighlight}
                onStrategyHighlightGroups={handleStrategyHighlightGroups}
                onHighlightClear={handleHighlightClear}
              />
            )}
            {activeTab === 'room' && !selectedRoom && (
              <p className="no-selection">Click a room in the 3D viewer or the portfolio list to see details.</p>
            )}
          </div>
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
            beforeAfter={beforeAfter}
          />
          <div className="viewer-legend">
            <span className="leg critical">Critical</span>
            <span className="leg high">High</span>
            <span className="leg moderate">Moderate</span>
            <span className="leg safe">Safe</span>
            <span className="leg vent">Vent. deficit</span>
          </div>
        </main>
      </div>
    </div>
  )
}

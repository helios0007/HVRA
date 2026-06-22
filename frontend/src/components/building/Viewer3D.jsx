import React, { useRef, useEffect, useState, useImperativeHandle, forwardRef } from 'react'
import * as OBC from '@thatopen/components'
import * as THREE from 'three'
import './Viewer3D.css'

// [urban-port] her backend is reached through our Vite /bapi proxy (→ :8001)
const API_URL = import.meta.env.VITE_BUILDING_API_BASE_URL ?? '/bapi'

const RISK_HEX = {
  critical: 0xe74c3c,
  high:     0xe67e22,
  moderate: 0xf1c40f,
  safe:     0x2ecc71,
}

const RISK_HEX_STR = {
  critical: '#e74c3c',
  high:     '#e67e22',
  moderate: '#f1c40f',
  safe:     '#2ecc71',
}

const Viewer3D = forwardRef(function Viewer3D({ jobId, rooms, onRoomSelect, beforeAfter }, ref) {
  const containerRef = useRef(null)
  const modelRef = useRef(null)           // holds loaded FragmentsGroup
  // Original appearance store: fragment.id → { colorArray, mats } saved before
  // any highlight modifies a mesh, so clearing restores true IFC colors.
  const originalsRef = useRef(new Map())
  // Separate store for the "inspecting this room" outline — independent of
  // the strategy-card highlight cycle, so toggling it on/off never disturbs
  // (and is never disturbed by) whatever strategy highlight is active.
  const inspectOriginalsRef = useRef(new Map())
  const inspectedRoomRef = useRef(null)   // currently inspected room's GlobalId, or null
  const [loading, setLoading] = useState(true)
  const [loadMsg, setLoadMsg] = useState('Loading model…')
  const [error, setError] = useState(null)
  const [showSpaces, setShowSpaces] = useState(false)
  const showSpacesRef = useRef(showSpaces)
  showSpacesRef.current = showSpaces

  // ── Section cut state ──────────────────────────────────────────────────
  const rendererRef = useRef(null)        // WebGLRenderer for clipping planes
  const bboxRef = useRef(null)            // model bounding box
  const [clipAxis, setClipAxis] = useState('off')   // off | y | x | z
  const [clipPct, setClipPct] = useState(60)        // 0–100 along chosen axis

  // ── Ventilation flow arrows ────────────────────────────────────────────
  const sceneRef = useRef(null)           // THREE.Scene for adding arrow group
  const flowRef = useRef(null)            // THREE.Group holding flow arrows

  const clearFlow = () => {
    if (flowRef.current && sceneRef.current) {
      sceneRef.current.remove(flowRef.current)
      flowRef.current.traverse(o => {
        o.geometry?.dispose?.()
        o.material?.dispose?.()
      })
    }
    flowRef.current = null
  }

  // ── Public API exposed to parent via ref ──────────────────────────────
  useImperativeHandle(ref, () => ({
    /**
     * Highlight IFC elements by GlobalId.
     * @param {string[]} globalIds  — IFC GlobalIds to highlight
     * @param {string}   hexColor   — CSS hex color, e.g. '#e67e22'
     * @param {boolean}  [reset]    — if true, clear previous highlights first
     */
    highlightElements(globalIds, hexColor, reset = true, opts = {}) {
      const model = modelRef.current
      if (!model || !Array.isArray(model.items)) return
      if (reset) restoreOriginals(originalsRef.current, model)
      const ids = filterIdsNearRoom(model, globalIds, opts.roomGlobalId)
      paintElements(model, originalsRef.current, ids, hexColor)
    },

    /**
     * Highlight several element groups, each with its own color.
     * @param {Array<{globalIds: string[], hexColor: string}>} groups
     * @param {boolean} reset
     * @param {{airflowPath?: number[][]}} [opts]  airflowPath: backend-computed
     *        polyline of [x,y,z] points (cross_ventilation.py's airflow_path) —
     *        drawn exactly as given, since the backend already guarantees it
     *        only passes through real opening/room/door centroids.
     */
    highlightGroups(groups, reset = true, opts = {}) {
      const model = modelRef.current
      if (!model || !Array.isArray(model.items)) return
      if (reset) restoreOriginals(originalsRef.current, model)
      clearFlow()

      // Keep only elements actually near the involved room volumes — shared
      // walls can host windows that physically belong to other rooms
      const roomGids = opts.roomGlobalIds ?? opts.roomGlobalId
      const filtered = groups
        .map(g => ({
          ...g,
          globalIds: filterIdsNearRoom(model, g.globalIds, g.roomGlobalId ?? roomGids),
        }))
        .filter(g => g.globalIds.length > 0)

      console.info(
        `[Viewer3D] highlightGroups: ${groups.length} group(s) in → ` +
        `${filtered.length} after room filter (` +
        filtered.map(g => `${g.orientation ?? '?'}:${g.globalIds.length}`).join(', ') + ')'
      )

      for (const g of filtered) paintElements(model, originalsRef.current, g.globalIds, g.hexColor)

      if (opts.airflowPath?.length >= 2 && sceneRef.current) {
        const flow = new THREE.Group()
        const toScene = (p) => new THREE.Vector3(p[0], p[2], -p[1])
        const raw = opts.airflowPath.map(toScene)

        // The backend reports raw IFC world coordinates, but the loaded
        // fragments model can carry its own internal offset (e.g. the
        // loader centers huge IFC coordinates near the scene origin for
        // float precision) — drawing raw coordinates directly produced an
        // arrow floating far outside the building. Calibrate using a real
        // IFC element we have BOTH a GlobalId and its EXACT raw centroid
        // for (not "nearest path point" — that guess breaks down whenever
        // the offset is large relative to the path's own span, which is
        // exactly what happened on long multi-hop indirect paths): compare
        // the element's true rendered position (elementBox, transform-
        // aware) against its own known raw centroid, and shift the whole
        // path by that exact difference. Prefer a highlighted opening; an
        // indirect-path room can have zero of those, so fall back to a
        // connecting door (also has an exact raw centroid); if neither is
        // available, fall back to the model/path bounding-box centers —
        // coarser, but keeps the arrow anchored near the building instead
        // of floating off in raw-coordinate space.
        // Try, in order of precision: the room's own exterior opening
        // (exact GlobalId + exact raw centroid) → a connecting door (same
        // exactness) → the room volume itself (less precise than a single
        // opening, but still anchors to the correct ROOM rather than the
        // whole building) → finally the whole-model bbox as a last resort.
        let offset = null
        let calibrationSource = 'none'

        const refGroup = groups.find(g => g.globalIds?.length && g.refCentroid && elementBox(model, g.globalIds[0]))
        if (refGroup) {
          const refBox = elementBox(model, refGroup.globalIds[0])
          offset = refBox.getCenter(new THREE.Vector3()).sub(toScene(refGroup.refCentroid))
          calibrationSource = 'opening'
        }

        if (!offset) {
          const refDoor = opts.doorCentroids?.find(d => elementBox(model, d.id))
          if (refDoor) {
            const refBox = elementBox(model, refDoor.id)
            offset = refBox.getCenter(new THREE.Vector3()).sub(toScene(refDoor.centroid))
            calibrationSource = 'door'
          }
        }

        if (!offset) {
          const roomGid = Array.isArray(roomGids) ? roomGids[0] : roomGids
          const roomBox = roomGid ? elementBox(model, roomGid) : null
          if (roomBox) {
            const roomCenter = roomBox.getCenter(new THREE.Vector3())
            const pathCenter = new THREE.Box3().setFromPoints(raw).getCenter(new THREE.Vector3())
            offset = roomCenter.clone().sub(pathCenter)
            calibrationSource = 'room-bbox'
          }
        }

        if (!offset && bboxRef.current) {
          const modelCenter = bboxRef.current.getCenter(new THREE.Vector3())
          const pathCenter = new THREE.Box3().setFromPoints(raw).getCenter(new THREE.Vector3())
          offset = modelCenter.clone().sub(pathCenter)
          calibrationSource = 'model-bbox'
        }

        if (calibrationSource !== 'opening') {
          console.warn(`[Viewer3D] airflow path calibrated via fallback (${calibrationSource}) — ` +
                       'the room\'s own exterior opening GlobalId was not resolvable in the loaded model.')
        }

        const calibrated = offset ? raw.map(p => p.clone().add(offset)) : raw

        // Flatten to one horizontal plane (a single floor's height) so the
        // arrow reads as a clean top-down "wind enters here, exits there"
        // diagram rather than a diagonal line climbing between window-sill
        // and door-handle heights. Use the mean Y of the calibrated points
        // as that plane, nudged up slightly so it doesn't z-fight the floor.
        const meanY = calibrated.reduce((s, p) => s + p.y, 0) / calibrated.length
        const points = calibrated.map(p => new THREE.Vector3(p.x, meanY + 0.05, p.z))

        addFlowPath(flow, points)
        if (flow.children.length) {
          sceneRef.current.add(flow)
          flowRef.current = flow
        }
      }
    },

    /** Remove all highlights, restoring the original IFC appearance. */
    clearHighlights() {
      restoreOriginals(originalsRef.current, modelRef.current)
      clearFlow()
    },

    /**
     * Highlight the IfcSpace volume of the room currently being inspected
     * in the side panel. Independent of strategy highlights — forces the
     * space visible (in case "Show room risk volumes" is off) and tints it
     * the room's own risk-level colour (same palette as "Show room risk
     * volumes"), so the highlight reads as "this room, at its risk level"
     * rather than an unrelated accent colour.
     * @param {string} roomGlobalId
     * @param {string} [riskLevel]  'critical' | 'high' | 'moderate' | 'safe'
     */
    highlightInspectedRoom(roomGlobalId, riskLevel) {
      const model = modelRef.current
      if (!model || !roomGlobalId) return
      restoreOriginals(inspectOriginalsRef.current, model)
      setSpaceVisibilityByIds(model, [roomGlobalId], true)
      const hex = RISK_HEX_STR[(riskLevel ?? '').toLowerCase()] ?? RISK_HEX_STR.safe
      paintElements(model, inspectOriginalsRef.current, [roomGlobalId], hex)
      inspectedRoomRef.current = roomGlobalId
    },

    /** Remove the room-inspect highlight, restoring prior visibility/colour. */
    clearInspectedRoomHighlight() {
      const model = modelRef.current
      restoreOriginals(inspectOriginalsRef.current, model)
      if (model && inspectedRoomRef.current && !showSpacesRef.current) {
        setSpaceVisibilityByIds(model, [inspectedRoomRef.current], false)
      }
      inspectedRoomRef.current = null
    },

    /**
     * Capture the current 3D view as a JPEG Blob — used as the AI-render
     * fallback source image when Street View has no coverage for the
     * building's address.
     * @returns {Promise<Blob|null>}
     */
    captureScreenshot() {
      const renderer = rendererRef.current
      if (!renderer?.domElement) return Promise.resolve(null)
      return new Promise(resolve => {
        renderer.domElement.toBlob(blob => resolve(blob), 'image/jpeg', 0.92)
      })
    },
  }))

  // ── Room volume (IfcSpace) visibility toggle ───────────────────────────
  useEffect(() => {
    const model = modelRef.current
    if (!model || loading) return
    setSpaceVisibility(model, rooms, showSpaces)
  }, [showSpaces, loading, rooms])

  // ── Section cut plane ──────────────────────────────────────────────────
  useEffect(() => {
    const renderer = rendererRef.current
    const box = bboxRef.current
    if (!renderer || loading) return
    if (clipAxis === 'off' || !box) {
      renderer.clippingPlanes = []
      return
    }
    const normals = {
      y: new THREE.Vector3(0, -1, 0),   // horizontal cut — removes everything above
      x: new THREE.Vector3(-1, 0, 0),   // vertical cut along X
      z: new THREE.Vector3(0, 0, -1),   // vertical cut along Z
    }
    const min = box.min[clipAxis]
    const max = box.max[clipAxis]
    const pos = min + (max - min) * (clipPct / 100)
    renderer.clippingPlanes = [new THREE.Plane(normals[clipAxis], pos)]
  }, [clipAxis, clipPct, loading])

  useEffect(() => {
    if (!containerRef.current) return

    let cancelled = false
    setLoading(true)
    setError(null)
    setLoadMsg(beforeAfter === 'after' ? 'Generating retrofit model…' : 'Loading model…')

    // ── TOC init ──────────────────────────────────────────────────────────
    const components = new OBC.Components()
    const worlds = components.get(OBC.Worlds)
    const world = worlds.create()

    world.scene    = new OBC.SimpleScene(components)
    world.renderer = new OBC.SimpleRenderer(components, containerRef.current)
    world.camera   = new OBC.SimpleCamera(components)
    world.scene.setup()
    components.init()

    world.scene.three.add(new THREE.AmbientLight(0xffffff, 0.85))
    const dir = new THREE.DirectionalLight(0xffffff, 1.6)
    dir.position.set(8, 15, 10)
    world.scene.three.add(dir)

    let loadedModel = null

    // ── Click → room selection (plain Three.js raycaster) ─────────────────
    const raycaster = new THREE.Raycaster()
    const pointer   = new THREE.Vector2()

    const handleClick = (event) => {
      if (cancelled || !loadedModel) return
      const canvas = containerRef.current
      if (!canvas) return
      const rect = canvas.getBoundingClientRect()
      pointer.x =  ((event.clientX - rect.left) / rect.width)  * 2 - 1
      pointer.y = -((event.clientY - rect.top)  / rect.height) * 2 + 1

      raycaster.setFromCamera(pointer, world.camera.three)
      const meshes = loadedModel.items.map(f => f.mesh).filter(Boolean)
      const intersects = raycaster.intersectObjects(meshes)
      if (!intersects.length) return

      const hit = intersects[0]
      const fragment = loadedModel.items.find(f => f.mesh === hit.object)
      if (!fragment) return

      const expressId = fragment.getItemID(hit.instanceId)
      if (expressId == null) return

      try {
        for (const [globalId, raw] of loadedModel.globalToExpressIDs) {
          const exprSet = toIdSet(raw)
          if (exprSet?.has(expressId)) {
            const room = rooms.find(r => roomMatchesGlobalId(r, globalId))
            if (room) { onRoomSelect(room); return }
          }
        }
      } catch {}
    }

    containerRef.current.addEventListener('click', handleClick)

    // ── Load IFC ──────────────────────────────────────────────────────────
    const load = async () => {
      const url = beforeAfter === 'after'
        ? `${API_URL}/jobs/${jobId}/ifc_after`
        : `${API_URL}/jobs/${jobId}/ifc`

      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status} fetching model`)
      const buffer = await res.arrayBuffer()
      if (cancelled) return

      setLoadMsg('Parsing IFC…')
      const ifcLoader = components.get(OBC.IfcLoader)
      await ifcLoader.setup()
      // IfcSpaces load as an optional (hidden) category — the checkbox toggles them
      if (cancelled) return

      const model = await ifcLoader.load(new Uint8Array(buffer))
      if (cancelled) { try { model.dispose?.() } catch {}; return }

      loadedModel = model
      modelRef.current = model
      sceneRef.current = world.scene.three
      originalsRef.current.clear()
      world.scene.three.add(model)

      setLoadMsg('Applying risk overlay…')
      applyRiskColors(model, rooms)
      if (cancelled) return

      // Store renderer + bbox for the section cut control
      rendererRef.current = world.renderer?.three ?? null
      const box = new THREE.Box3().setFromObject(model)
      bboxRef.current = box.isEmpty() ? null : box

      // 3D ground compass, placed just below the building footprint
      if (!box.isEmpty()) {
        const compass = buildGroundCompass(box)
        world.scene.three.add(compass)
      }

      // Fit camera to model
      if (!box.isEmpty()) {
        const center = box.getCenter(new THREE.Vector3())
        const size   = box.getSize(new THREE.Vector3())
        const d      = Math.max(size.x, size.y, size.z)
        try {
          world.camera.controls.setLookAt(
            center.x + d, center.y + d * 0.6, center.z + d,
            center.x, center.y, center.z,
            true,
          )
        } catch {}
      }

      if (!cancelled) setLoading(false)
    }

    load().catch((err) => {
      if (!cancelled) { setError(err.message); setLoading(false) }
    })

    return () => {
      cancelled = true
      clearFlow()
      modelRef.current = null
      sceneRef.current = null
      rendererRef.current = null
      bboxRef.current = null
      originalsRef.current.clear()
      inspectOriginalsRef.current.clear()
      inspectedRoomRef.current = null
      try { containerRef.current?.removeEventListener('click', handleClick) } catch {}
      try { components.dispose() } catch {}
    }
  }, [jobId, beforeAfter])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />

      {!loading && !error && (
        <div className="viewer-controls">
          <label className="viewer-spaces-toggle">
            <input
              type="checkbox"
              checked={showSpaces}
              onChange={e => setShowSpaces(e.target.checked)}
            />
            Show room risk volumes
          </label>

          <div className="viewer-section-cut">
            <span className="vsc-label">Section cut</span>
            <select value={clipAxis} onChange={e => setClipAxis(e.target.value)}>
              <option value="off">Off</option>
              <option value="y">Horizontal (plan)</option>
              <option value="x">Vertical — X</option>
              <option value="z">Vertical — Z</option>
            </select>
            {clipAxis !== 'off' && (
              <input
                type="range"
                min="1" max="99"
                value={clipPct}
                onChange={e => setClipPct(Number(e.target.value))}
              />
            )}
          </div>
        </div>
      )}

      {loading && (
        <div className="viewer-overlay">
          <div className="viewer-spinner" />
          <p className="viewer-msg">{loadMsg}</p>
        </div>
      )}
      {error && (
        <div className="viewer-overlay viewer-overlay--error">
          <p>Model load failed</p>
          <p className="viewer-err-detail">{error}</p>
          <p className="viewer-err-hint">
            Is the backend running? <code>uvicorn main:app --reload</code>
          </p>
        </div>
      )}
    </div>
  )
})

export default Viewer3D

// ── Element painting ──────────────────────────────────────────────────────────

function paintElements(model, store, globalIds, hexColor) {
  const color = new THREE.Color(hexColor)
  for (const gid of globalIds) {
    const exprSet = toIdSet(model.globalToExpressIDs?.get(gid))
    if (!exprSet) continue
    for (const fragment of model.items) {
      const overlapping = [...exprSet].filter(id => fragment.ids.has(id))
      if (!overlapping.length) continue
      const mesh = fragment.mesh
      if (!mesh) continue

      saveOriginal(store, fragment)

      if (!mesh.instanceColor) {
        mesh.instanceColor = new THREE.InstancedBufferAttribute(
          new Float32Array(mesh.count * 3).fill(1), 3
        )
      }
      for (const expressId of overlapping) {
        const instances = fragment.itemToInstances.get(expressId)
        if (!instances) continue
        for (const idx of instances) mesh.setColorAt(idx, color)
      }
      mesh.instanceColor.needsUpdate = true
      // Note: deliberately NOT touching mesh.material here — fragment
      // materials are shared across many elements, and making them
      // transparent causes z-fighting glitches on unrelated geometry.
    }
  }
}

// ── Ventilation flow arrows ───────────────────────────────────────────────────

/**
 * Keep only elements whose bounding box intersects the room's volume
 * (expanded by a margin). Shared walls span several rooms, so a room's
 * facade can list windows that physically sit in a neighbouring room.
 */
function filterIdsNearRoom(model, globalIds, roomGlobalIds, margin = 0.6) {
  if (!roomGlobalIds) return globalIds
  const gids = Array.isArray(roomGlobalIds) ? roomGlobalIds : [roomGlobalIds]
  const boxes = gids
    .map(g => elementBox(model, g))
    .filter(Boolean)
    .map(b => b.expandByScalar(margin))
  if (!boxes.length) {
    console.warn('[Viewer3D] room volume not found for filtering — highlighting unfiltered')
    return globalIds
  }
  const kept = globalIds.filter(gid => {
    const b = elementBox(model, gid)
    return b ? boxes.some(rb => rb.intersectsBox(b)) : false
  })
  if (!kept.length && globalIds.length) {
    // Fail open: an empty highlight is worse than an occasionally-wrong one
    console.warn(
      `[Viewer3D] room filter removed all ${globalIds.length} element(s) — ` +
      'room box and element boxes do not intersect; highlighting unfiltered'
    )
    return globalIds
  }
  return kept
}

/** World-space bounding box of one IFC element (by GlobalId). */
function elementBox(model, gid) {
  const exprSet = toIdSet(model.globalToExpressIDs?.get(gid))
  if (!exprSet) return null
  const box = new THREE.Box3()
  const tmp = new THREE.Matrix4()
  let found = false
  for (const fragment of model.items) {
    const mesh = fragment.mesh
    if (!mesh) continue
    for (const eid of exprSet) {
      if (!fragment.ids.has(eid)) continue
      const instances = fragment.itemToInstances.get(eid)
      if (!instances) continue
      if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox()
      mesh.updateWorldMatrix(true, false)
      for (const idx of instances) {
        mesh.getMatrixAt(idx, tmp)
        const b = mesh.geometry.boundingBox.clone()
        b.applyMatrix4(tmp)
        b.applyMatrix4(mesh.matrixWorld)
        box.union(b)
        found = true
      }
    }
  }
  return found ? box : null
}

/**
 * Draw one flat polyline path with an arrowhead at the end.
 *
 * Uses straight segments through each waypoint (CatmullRomCurve3 was tried
 * here previously, but its un-clamped spline tangents overshoot far past
 * the waypoint bounds whenever the path has a sharp turn — e.g. an indirect
 * cross-ventilation path that doubles back through a connecting door. Since
 * these waypoints are a discrete sequence of real opening/room centroids,
 * not a smooth physical trajectory, straight segments are both more
 * correct and immune to that overshoot.
 */
function addFlowPath(group, points) {
  if (points.length < 2) return
  const total = points.reduce(
    (s, p, i) => i ? s + p.distanceTo(points[i - 1]) : 0, 0
  )
  if (total < 1e-3) return

  const radius = Math.min(Math.max(total * 0.012, 0.03), 0.1)
  const mat = new THREE.MeshBasicMaterial({
    color: 0x2e86de, transparent: true, opacity: 0.9, depthTest: false,
  })

  // One TubeGeometry segment per leg (instead of one spline through all
  // points) so each leg stays a straight line between its two waypoints.
  for (let i = 1; i < points.length; i++) {
    const legCurve = new THREE.LineCurve3(points[i - 1], points[i])
    const tube = new THREE.Mesh(new THREE.TubeGeometry(legCurve, 2, radius, 8), mat)
    tube.renderOrder = 999
    group.add(tube)
  }

  const dir = points[points.length - 1].clone()
    .sub(points[points.length - 2])
    .normalize()
  const cone = new THREE.Mesh(new THREE.ConeGeometry(radius * 3, radius * 9, 12), mat)
  cone.position.copy(points[points.length - 1])
  cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir)
  cone.renderOrder = 999
  group.add(cone)
}

// ── Original-appearance store ─────────────────────────────────────────────────

function saveOriginal(store, fragment) {
  if (store.has(fragment.id)) return
  const mesh = fragment.mesh
  if (!mesh) return
  const colorArray = mesh.instanceColor ? mesh.instanceColor.array.slice() : null
  const mats = (Array.isArray(mesh.material) ? mesh.material : [mesh.material])
    .filter(Boolean)
    .map(m => ({ transparent: m.transparent, opacity: m.opacity, depthWrite: m.depthWrite }))
  store.set(fragment.id, { colorArray, mats })
}

function restoreOriginals(store, model) {
  if (!model || !Array.isArray(model.items) || store.size === 0) return
  for (const fragment of model.items) {
    const saved = store.get(fragment.id)
    if (!saved) continue
    const mesh = fragment.mesh
    if (!mesh) continue

    if (saved.colorArray && mesh.instanceColor) {
      mesh.instanceColor.array.set(saved.colorArray)
      mesh.instanceColor.needsUpdate = true
    } else if (!saved.colorArray && mesh.instanceColor) {
      // Mesh had no instance colors originally — remove the buffer we added
      mesh.instanceColor = null
    }

    const mats = (Array.isArray(mesh.material) ? mesh.material : [mesh.material]).filter(Boolean)
    mats.forEach((m, i) => {
      const s = saved.mats[i]
      if (!s) return
      m.transparent = s.transparent
      m.opacity = s.opacity
      m.depthWrite = s.depthWrite
    })
  }
  store.clear()
}

// ── ExpressID normalisation ───────────────────────────────────────────────────
// Depending on the fragments version, globalToExpressIDs values can be a Set,
// an array, or a single number. Normalise to a Set.

function toIdSet(v) {
  if (v == null) return null
  if (v instanceof Set) return v
  if (Array.isArray(v)) return new Set(v)
  return new Set([v])
}

// ── Room → IFC GlobalId resolution ────────────────────────────────────────────
// Backend room_id is "R_" + first 8 chars of the IFC GlobalId. Newer payloads
// also include the full ifc_global_id. Match on whichever is available.

function roomMatchesGlobalId(room, globalId) {
  if (room.ifc_global_id) return room.ifc_global_id === globalId
  const frag = room.room_id?.startsWith('R_') ? room.room_id.slice(2) : room.room_id
  return frag ? (globalId.endsWith(frag) || globalId.startsWith(frag)) : false
}

function resolveExprSet(model, room) {
  const map = model.globalToExpressIDs
  if (!map) return null
  if (room.ifc_global_id && map.has(room.ifc_global_id)) return toIdSet(map.get(room.ifc_global_id))
  if (map.has(room.room_id)) return toIdSet(map.get(room.room_id))
  const frag = room.room_id?.startsWith('R_') ? room.room_id.slice(2) : room.room_id
  if (frag) {
    for (const [gid, set] of map) {
      if (gid.endsWith(frag) || gid.startsWith(frag)) return toIdSet(set)
    }
  }
  return null
}

// ── IfcSpace visibility ───────────────────────────────────────────────────────

function setSpaceVisibility(model, rooms, visible) {
  if (!model || !Array.isArray(model.items) || !model.globalToExpressIDs) return
  for (const room of rooms) {
    const exprSet = resolveExprSet(model, room)
    if (!exprSet) continue
    for (const fragment of model.items) {
      const overlapping = [...exprSet].filter(id => fragment.ids.has(id))
      if (!overlapping.length) continue
      try { fragment.setVisibility(visible, overlapping) } catch {}
    }
  }
}

/** Same as setSpaceVisibility but keyed directly by GlobalId, not room objects. */
function setSpaceVisibilityByIds(model, globalIds, visible) {
  if (!model || !Array.isArray(model.items) || !model.globalToExpressIDs) return
  for (const gid of globalIds) {
    const exprSet = toIdSet(model.globalToExpressIDs.get(gid))
    if (!exprSet) continue
    for (const fragment of model.items) {
      const overlapping = [...exprSet].filter(id => fragment.ids.has(id))
      if (!overlapping.length) continue
      try { fragment.setVisibility(visible, overlapping) } catch {}
    }
  }
}

// ── 3D ground compass ──────────────────────────────────────────────────────────
// Matches the backend's bearing convention used throughout the pipeline
// (ifc_parser._wall_orientation / _compass_label): 0°=N, 90°=E, 180°=S, 270°=W,
// measured as atan2(normal.x, normal.y) on the world XY plan, where Three.js
// world X ↔ IFC X and Three.js world -Z ↔ IFC Y (IFC's Z-up Y-forward axes
// become Three.js's Y-up -Z-forward on load). So on the ground (XZ) plane:
//   IFC North (bearing 0°, +Y)  → Three.js -Z
//   IFC East  (bearing 90°, +X) → Three.js +X
// A point at bearing θ sits at (sin θ, -cos θ) in (X, Z).

function bearingToXZ(bearingDeg, radius) {
  const rad = THREE.MathUtils.degToRad(bearingDeg)
  return new THREE.Vector3(Math.sin(rad) * radius, 0, -Math.cos(rad) * radius)
}

function makeLabelSprite(text, color) {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, size, size)
  ctx.fillStyle = color
  ctx.font = 'bold 76px Arial'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, size / 2, size / 2 + 4)

  const texture = new THREE.CanvasTexture(canvas)
  texture.minFilter = THREE.LinearFilter
  const material = new THREE.SpriteMaterial({
    map: texture, transparent: true, depthWrite: false, sizeAttenuation: true,
  })
  return new THREE.Sprite(material)
}

/**
 * Build a flat compass rose on the ground plane, placed just below the
 * building's footprint, oriented to true building north (not the camera).
 */
function buildGroundCompass(modelBox) {
  const group = new THREE.Group()

  const size = modelBox.getSize(new THREE.Vector3())
  const radius = Math.max(size.x, size.z) * 0.55 + 0.6
  const center = modelBox.getCenter(new THREE.Vector3())
  const y = modelBox.min.y - Math.max(size.y * 0.02, 0.05)
  group.position.set(center.x, y, center.z)

  // Ring
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(radius * 0.96, radius, 64),
    new THREE.MeshBasicMaterial({
      color: 0xdddddd, transparent: true, opacity: 0.55,
      side: THREE.DoubleSide, depthWrite: false,
    })
  )
  ring.rotation.x = -Math.PI / 2
  ring.renderOrder = 1
  group.add(ring)

  // Cardinal + intercardinal tick marks
  for (let deg = 0; deg < 360; deg += 30) {
    const isCardinal = deg % 90 === 0
    const outer = bearingToXZ(deg, radius)
    const inner = bearingToXZ(deg, radius * (isCardinal ? 0.80 : 0.90))
    const geom = new THREE.BufferGeometry().setFromPoints([inner, outer])
    const mat = new THREE.LineBasicMaterial({
      color: isCardinal ? 0xffffff : 0x999999,
      transparent: true, opacity: 0.8, depthWrite: false,
    })
    const line = new THREE.Line(geom, mat)
    line.renderOrder = 1
    group.add(line)
  }

  // N needle — red, pointing to true north, flat on the ground (XZ plane).
  // Built directly as a quad of two triangles, no Shape/rotation needed.
  const tip   = bearingToXZ(0,   radius * 0.78)
  const tail  = bearingToXZ(180, radius * 0.22)
  const left  = bearingToXZ(350, radius * 0.10)
  const right = bearingToXZ(10,  radius * 0.10)
  const needlePositions = new Float32Array([
    tip.x, 0, tip.z,    left.x, 0, left.z,   tail.x, 0, tail.z,
    tip.x, 0, tip.z,    tail.x, 0, tail.z,   right.x, 0, right.z,
  ])
  const needleGeom = new THREE.BufferGeometry()
  needleGeom.setAttribute('position', new THREE.BufferAttribute(needlePositions, 3))
  needleGeom.computeVertexNormals()
  const needle = new THREE.Mesh(
    needleGeom,
    new THREE.MeshBasicMaterial({
      color: 0xe74c3c, side: THREE.DoubleSide, depthWrite: false, transparent: true, opacity: 0.95,
    })
  )
  needle.position.y = 0.002
  needle.renderOrder = 2
  group.add(needle)

  // N/E/S/W labels — billboard sprites, positioned flat around the ring
  const labelDefs = [
    { bearing: 0,   text: 'N', color: '#e74c3c' },
    { bearing: 90,  text: 'E', color: '#eee' },
    { bearing: 180, text: 'S', color: '#eee' },
    { bearing: 270, text: 'W', color: '#eee' },
  ]
  const labelScale = Math.max(radius * 0.16, 0.25)
  for (const { bearing, text, color } of labelDefs) {
    const sprite = makeLabelSprite(text, color)
    const pos = bearingToXZ(bearing, radius * 1.18)
    sprite.position.set(pos.x, labelScale * 0.3, pos.z)
    sprite.scale.set(labelScale, labelScale, 1)
    sprite.renderOrder = 3
    group.add(sprite)
  }

  return group
}

// ── Risk color helper ─────────────────────────────────────────────────────────

function applyRiskColors(model, rooms) {
  if (!model || !Array.isArray(model.items)) return
  const globalToExpressIDs = model.globalToExpressIDs
  if (!globalToExpressIDs) return

  try {
    let matched = 0
    for (const room of rooms) {
      const exprSet = resolveExprSet(model, room)
      if (!exprSet) continue
      matched++

      const riskRaw = (room.thermal_scores?.risk_level ?? 'safe').toLowerCase()
      const hex = RISK_HEX[riskRaw] ?? RISK_HEX.safe
      const color = new THREE.Color(hex)

      for (const fragment of model.items) {
        const overlapping = [...exprSet].filter(id => fragment.ids.has(id))
        if (!overlapping.length) continue

        const mesh = fragment.mesh
        if (!mesh) continue

        // Ensure per-instance color buffer exists
        if (!mesh.instanceColor) {
          mesh.instanceColor = new THREE.InstancedBufferAttribute(
            new Float32Array(mesh.count * 3).fill(1), 3
          )
        }

        for (const expressId of overlapping) {
          const instances = fragment.itemToInstances.get(expressId)
          if (!instances) continue
          for (const idx of instances) {
            mesh.setColorAt(idx, color)
          }
        }
        mesh.instanceColor.needsUpdate = true
        // Make space volumes semi-transparent so they overlay the building shell
        if (mesh.material) {
          const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
          mats.forEach(m => { m.transparent = true; m.opacity = 0.45; m.depthWrite = false })
        }
      }
    }
    console.info(`[Viewer3D] risk colors applied: ${matched}/${rooms.length} rooms matched in model`)
  } catch (err) {
    console.warn('[Viewer3D] applyRiskColors error:', err)
  }
}

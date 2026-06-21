import React, { useMemo, useState } from 'react'
import './OverheatingTable.css'

const DAY_LABELS = {
  15: 'Day 1 (Mon)', 16: 'Day 2 (Tue)', 17: 'Day 3 (Wed)', 18: 'Day 4 (Thu)',
  19: 'Day 5 (Fri)', 20: 'Day 6 (Sat)', 21: 'Day 7 (Sun)',
}

/**
 * Renders the actual hours an occupant would experience overheating, grouped
 * by day of the representative EPW heatwave week — not just a bare count.
 *
 * events: [{ month, day, hour, T_op_C }, ...] — already filtered to hours
 * exceeding the occupant's age-bracket T_op threshold.
 */
export default function OverheatingTable({ events, threshold }) {
  const [expanded, setExpanded] = useState(false)

  const byDay = useMemo(() => {
    const groups = {}
    for (const e of events ?? []) {
      const key = e.day
      if (!groups[key]) groups[key] = []
      groups[key].push(e)
    }
    return Object.entries(groups)
      .sort(([a], [b]) => Number(a) - Number(b))
      .map(([day, hours]) => ({
        day: Number(day),
        hours: hours.sort((a, b) => a.hour - b.hour),
      }))
  }, [events])

  if (!events || events.length === 0) {
    return (
      <p className="oh-empty">
        No hours exceeded the {threshold != null ? `${threshold.toFixed(0)}°C ` : ''}
        threshold during the reference heatwave week.
      </p>
    )
  }

  const visibleDays = expanded ? byDay : byDay.slice(0, 2)

  return (
    <div className="oh-table">
      <p className="oh-note">
        Hours where estimated operative temperature exceeded{' '}
        {threshold != null ? `${threshold.toFixed(0)}°C` : 'the age-bracket threshold'},
        during the representative July heatwave week (EPW typical meteorological year —
        not specific calendar dates).
      </p>

      {visibleDays.map(({ day, hours }) => (
        <div key={day} className="oh-day">
          <div className="oh-day-header">
            <span className="oh-day-label">{DAY_LABELS[day] ?? `Day ${day}`}</span>
            <span className="oh-day-count">{hours.length}h over threshold</span>
          </div>
          <div className="oh-hours">
            {hours.map((h, i) => (
              <span key={i} className="oh-chip" title={`${String(h.hour % 24).padStart(2, '0')}:00 — ${h.T_op_C}°C`}>
                {String(h.hour % 24).padStart(2, '0')}:00
                <span className="oh-chip-temp">{h.T_op_C}°C</span>
              </span>
            ))}
          </div>
        </div>
      ))}

      {byDay.length > 2 && (
        <button className="oh-toggle" onClick={() => setExpanded(e => !e)}>
          {expanded ? 'Show fewer days' : `Show all ${byDay.length} days`}
        </button>
      )}
    </div>
  )
}

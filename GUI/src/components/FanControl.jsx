import { useState, useCallback } from 'react'
import { setFanSpeed } from '../api/client'

const SPEEDS = [
  { id: 0, label: 'ИЗКЛ',   icon: '⭕', hint: 'Fan OFF' },
  { id: 1, label: 'НИСКА',  icon: '🌬', hint: '~33 %' },
  { id: 2, label: 'СРЕДНА', icon: '💨', hint: '~66 %' },
  { id: 3, label: 'ВИСОКА', icon: '🌪', hint: '100 %' },
]

export default function FanControl({ speed, disabled }) {
  const [busy, setBusy] = useState(false)

  const handleClick = useCallback(async (id) => {
    if (disabled || busy || id === speed) return
    setBusy(true)
    try { await setFanSpeed(id) } catch (e) { console.error(e) } finally { setBusy(false) }
  }, [disabled, busy, speed])

  return (
    <div>
      {disabled && (
        <p style={{ fontSize: '.75rem', color: 'var(--text-muted)', marginBottom: '.75rem' }}>
          Превключете в РЪЧЕН режим за управление.
        </p>
      )}
      <div className="fan-buttons">
        {SPEEDS.map(s => (
          <button
            key={s.id}
            className={`fan-btn ${speed === s.id ? `active-${s.id}` : ''}`}
            disabled={disabled || busy}
            onClick={() => handleClick(s.id)}
            title={s.hint}
          >
            <span className="fan-icon">{s.icon}</span>
            {s.label}
          </button>
        ))}
      </div>
      <p style={{ marginTop: '.6rem', fontSize: '.75rem', color: 'var(--text-muted)' }}>
        Текущо: <strong style={{ color: 'var(--text)' }}>
          {SPEEDS.find(s => s.id === speed)?.label ?? '—'}
        </strong>
      </p>
    </div>
  )
}


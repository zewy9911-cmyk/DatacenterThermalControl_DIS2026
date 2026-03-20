import { useState, useCallback } from 'react'
import { setValve } from '../api/client'

function Toggle({ checked, onChange, disabled }) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={onChange} disabled={disabled} />
      <span className="slider" />
    </label>
  )
}

export default function ValveControl({ valve1, valve2, disabled }) {
  const [busy, setBusy] = useState(false)

  const toggle = useCallback(async (id, current) => {
    if (disabled || busy) return
    setBusy(true)
    try { await setValve(id, !current) } catch (e) { console.error(e) } finally { setBusy(false) }
  }, [disabled, busy])

  return (
    <div>
      {disabled && (
        <p style={{ fontSize: '.75rem', color: 'var(--text-muted)', marginBottom: '.75rem' }}>
          Превключете в РЪЧЕН режим за управление.
        </p>
      )}
      <div className="valve-list">
        <div className="valve-row">
          <div className="valve-info">
            <span className="valve-name">♻ Клапа 1 — Рециркулация</span>
            <span className="valve-desc">Въздухът се върти вътре в стаята</span>
          </div>
          <Toggle
            checked={!!valve1}
            onChange={() => toggle(1, valve1)}
            disabled={disabled || busy}
          />
        </div>
        <div className="valve-row">
          <div className="valve-info">
            <span className="valve-name">🌬 Клапа 2 — Изпускане навън</span>
            <span className="valve-desc">Горещият въздух се извежда навън</span>
          </div>
          <Toggle
            checked={!!valve2}
            onChange={() => toggle(2, valve2)}
            disabled={disabled || busy}
          />
        </div>
      </div>
    </div>
  )
}


import { useState, useCallback, useEffect } from 'react'
import { setSimulation, getSimulation } from '../api/client'

const SCENARIOS = [
  { label: '🌿 Нормална',   temp: 22, hum: 55, hint: 'Fan OFF · Recirculation' },
  { label: '☀ Топло',       temp: 27, hum: 60, hint: 'Fan LOW · Recirculation' },
  { label: '🌡 Горещо',     temp: 28, hum: 63, hint: 'Fan MEDIUM · Exhaust' },
  { label: '🔥 Критично',   temp: 34, hum: 71, hint: 'Fan HIGH · Exhaust + Alarms' },
  { label: '💧 Вис. влажн.', temp: 22, hum: 82, hint: 'High humidity warning' },
]

function predict(temp, hum) {
  let fan, v1, v2, alert = null
  if      (temp < 20) { fan = 'ИЗКЛ';   v1 = true;  v2 = false }
  else if (temp < 25) { fan = 'НИСКА';  v1 = true;  v2 = false }
  else if (temp < 30) { fan = 'СРЕДНА'; v1 = false; v2 = true  }
  else                { fan = 'ВИСОКА'; v1 = false; v2 = true; alert = 'critical' }
  if (hum >= 70 && !alert) alert = 'warning'
  return { fan, v1, v2, alert }
}

function TempBar({ value }) {
  const pct  = Math.min(100, Math.max(0, ((value - 10) / 40) * 100))
  const color = value >= 30 ? '#f85149' : value >= 25 ? '#e3b341' : value >= 22 ? '#d29922' : '#3fb950'
  return (
    <div style={{ position: 'relative', height: '10px', background: '#30363d', borderRadius: '6px', overflow: 'hidden' }}>
      <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '6px', transition: 'all .2s' }} />
    </div>
  )
}

function HumBar({ value }) {
  const pct  = Math.min(100, value)
  const color = value >= 70 ? '#f85149' : value <= 25 ? '#d29922' : '#58a6ff'
  return (
    <div style={{ position: 'relative', height: '10px', background: '#30363d', borderRadius: '6px', overflow: 'hidden' }}>
      <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '6px', transition: 'all .2s' }} />
    </div>
  )
}

export default function SimulationPanel() {
  const [enabled, setEnabled]   = useState(false)
  const [temp,    setTemp]      = useState(22)
  const [hum,     setHum]       = useState(55)
  const [busy,    setBusy]      = useState(false)
  const [applied, setApplied]   = useState(false)

  // Load current simulation state on mount
  useEffect(() => {
    getSimulation().then(r => {
      if (r.data.enabled) {
        setEnabled(true)
        setTemp(r.data.temperature ?? 22)
        setHum(r.data.humidity    ?? 55)
        setApplied(true)
      }
    }).catch(() => {})
  }, [])

  const apply = useCallback(async (t = temp, h = hum, en = true) => {
    setBusy(true)
    try {
      await setSimulation(en, en ? t : null, en ? h : null)
      setEnabled(en)
      if (en) { setTemp(t); setHum(h) }
      setApplied(en)
    } catch (e) { console.error(e) }
    finally { setBusy(false) }
  }, [temp, hum])

  const pred = predict(temp, hum)

  return (
    <div className="sim-panel">
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <div>
          <span style={{ fontSize: '.85rem', color: 'var(--text)' }}>
            Симулационен режим
          </span>
          {applied && (
            <span className="sim-active-badge">● АКТИВНА</span>
          )}
        </div>
        <label className="toggle" title={enabled ? 'Изключи симулация' : 'Включи симулация'}>
          <input type="checkbox" checked={enabled} onChange={e => {
            if (!e.target.checked) apply(temp, hum, false)
            else { setEnabled(true) }
          }} disabled={busy} />
          <span className="slider" />
        </label>
      </div>

      {!enabled ? (
        <p style={{ fontSize: '.8rem', color: 'var(--text-muted)' }}>
          Включете симулацията, за да замените стойностите на сензора.
        </p>
      ) : (
        <>
          {/* Temperature slider */}
          <div className="sim-row">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '.3rem' }}>
              <span style={{ fontSize: '.8rem', color: 'var(--text-muted)' }}>🌡 Температура</span>
              <strong style={{ fontSize: '.9rem', color: temp >= 30 ? 'var(--red)' : temp >= 25 ? 'var(--orange)' : 'var(--green)' }}>
                {temp.toFixed(1)} °C
              </strong>
            </div>
            <TempBar value={temp} />
            <input
              type="range" min="10" max="45" step="0.5"
              value={temp}
              onChange={e => setTemp(Number(e.target.value))}
              className="sim-slider"
            />
          </div>

          {/* Humidity slider */}
          <div className="sim-row">
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '.3rem' }}>
              <span style={{ fontSize: '.8rem', color: 'var(--text-muted)' }}>💧 Влажност</span>
              <strong style={{ fontSize: '.9rem', color: hum >= 70 ? 'var(--red)' : 'var(--accent)' }}>
                {hum.toFixed(0)} %
              </strong>
            </div>
            <HumBar value={hum} />
            <input
              type="range" min="10" max="95" step="1"
              value={hum}
              onChange={e => setHum(Number(e.target.value))}
              className="sim-slider"
            />
          </div>

          {/* Predicted outcome */}
          <div className="sim-preview">
            <span style={{ fontSize: '.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.05em' }}>
              Очаквано поведение
            </span>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '.4rem', marginTop: '.4rem' }}>
              <div className="pred-box">
                <span>💨 Вент.</span>
                <strong style={{ color: pred.fan === 'ВИСОКА' ? 'var(--red)' : pred.fan === 'СРЕДНА' ? 'var(--orange)' : pred.fan === 'НИСКА' ? 'var(--accent)' : 'var(--text-muted)' }}>
                  {pred.fan}
                </strong>
              </div>
              <div className="pred-box">
                <span>♻ Кл.1</span>
                <strong style={{ color: pred.v1 ? 'var(--green)' : 'var(--text-muted)' }}>{pred.v1 ? 'ОТВОРЕНА' : 'ЗАТВОРЕНА'}</strong>
              </div>
              <div className="pred-box">
                <span>🌬 Кл.2</span>
                <strong style={{ color: pred.v2 ? 'var(--green)' : 'var(--text-muted)' }}>{pred.v2 ? 'ОТВОРЕНА' : 'ЗАТВОРЕНА'}</strong>
              </div>
            </div>
            {pred.alert && (
              <div className={`alert-item ${pred.alert}`} style={{ marginTop: '.5rem', fontSize: '.78rem' }}>
                {pred.alert === 'critical' ? '🔴 Критична температура — ще се изпрати SNMP Trap' : '🟡 Висока влажност — предупреждение'}
              </div>
            )}
          </div>

          {/* Apply button */}
          <button
            onClick={() => apply(temp, hum, true)}
            disabled={busy}
            className="sim-apply-btn"
          >
            {busy ? '⏳ Прилага...' : '▶ Приложи симулация'}
          </button>

          {/* Quick scenarios */}
          <div style={{ marginTop: '1rem' }}>
            <p style={{ fontSize: '.72rem', color: 'var(--text-muted)', marginBottom: '.5rem', textTransform: 'uppercase', letterSpacing: '.05em' }}>
              Бързи сценарии
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.4rem' }}>
              {SCENARIOS.map(s => (
                <button
                  key={s.label}
                  className="scenario-btn"
                  disabled={busy}
                  onClick={() => apply(s.temp, s.hum, true)}
                  title={`${s.temp}°C / ${s.hum}% — ${s.hint}`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}


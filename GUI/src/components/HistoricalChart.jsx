import { useEffect, useState } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { getHistory } from '../api/client'

function fmt(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}

export default function HistoricalChart() {
  const [data,    setData]    = useState([])
  const [loading, setLoading] = useState(true)
  const [hours,   setHours]   = useState(24)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getHistory(hours)
      .then(r => {
        if (!cancelled) {
          // Downsample to max 200 points for performance
          const rows = r.data.readings ?? []
          const step = Math.max(1, Math.floor(rows.length / 200))
          setData(rows.filter((_, i) => i % step === 0).map(row => ({
            ts:   fmt(row.timestamp),
            temp: row.temperature,
            hum:  row.humidity,
          })))
        }
      })
      .catch(console.error)
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [hours])

  return (
    <div>
      <div style={{ display: 'flex', gap: '.5rem', marginBottom: '.75rem' }}>
        {[1, 6, 12, 24].map(h => (
          <button
            key={h}
            onClick={() => setHours(h)}
            style={{
              padding: '.25rem .7rem', borderRadius: '6px', border: '1px solid var(--border)',
              background: hours === h ? 'var(--accent)' : 'var(--surface2)',
              color: hours === h ? 'white' : 'var(--text-muted)',
              cursor: 'pointer', fontSize: '.78rem',
            }}
          >{h}ч</button>
        ))}
      </div>

      {loading ? (
        <p style={{ color: 'var(--text-muted)', fontSize: '.85rem' }}>Зарежда…</p>
      ) : data.length === 0 ? (
        <p style={{ color: 'var(--text-muted)', fontSize: '.85rem' }}>Няма данни за избрания период.</p>
      ) : (
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#30363d" />
              <XAxis dataKey="ts" tick={{ fill: '#8b949e', fontSize: 11 }} interval="preserveStartEnd" />
              <YAxis yAxisId="t" domain={['auto', 'auto']} tick={{ fill: '#8b949e', fontSize: 11 }}
                label={{ value: '°C', position: 'insideTopLeft', fill: '#8b949e', fontSize: 11 }} />
              <YAxis yAxisId="h" orientation="right" domain={[0, 100]}
                tick={{ fill: '#8b949e', fontSize: 11 }}
                label={{ value: '%', position: 'insideTopRight', fill: '#8b949e', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: '8px' }}
                labelStyle={{ color: '#8b949e' }}
              />
              <Legend wrapperStyle={{ fontSize: '.8rem' }} />
              <Line yAxisId="t" type="monotone" dataKey="temp" name="Температура (°C)"
                stroke="#f85149" dot={false} strokeWidth={2} />
              <Line yAxisId="h" type="monotone" dataKey="hum"  name="Влажност (%)"
                stroke="#58a6ff" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}


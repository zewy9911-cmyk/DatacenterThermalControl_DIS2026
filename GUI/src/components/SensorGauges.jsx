import {
  RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer,
} from 'recharts'

function tempClass(t) {
  if (t === null || t === undefined) return 'temp-ok'
  if (t >= 30) return 'temp-crit'
  if (t >= 25) return 'temp-hot'
  if (t >= 22) return 'temp-warn'
  return 'temp-ok'
}

function humClass(h) {
  if (h === null || h === undefined) return 'hum-ok'
  if (h >= 70 || h <= 25) return 'hum-warn'
  return 'hum-ok'
}

function GaugeChart({ value, max, color, unit }) {
  const pct = Math.min(100, Math.max(0, ((value ?? 0) / max) * 100))
  return (
    <ResponsiveContainer width={140} height={140}>
      <RadialBarChart
        cx="50%" cy="60%"
        innerRadius="65%" outerRadius="100%"
        startAngle={210} endAngle={-30}
        data={[{ value: pct, fill: color }]}
      >
        <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
        <RadialBar
          background={{ fill: '#30363d' }}
          dataKey="value"
          angleAxisId={0}
          cornerRadius={6}
        />
      </RadialBarChart>
    </ResponsiveContainer>
  )
}

export default function SensorGauges({ data }) {
  const temp = data?.temperature
  const hum  = data?.humidity

  return (
    <div className="gauge-row">
      <div className="gauge-box">
        <GaugeChart value={temp} max={60} color="var(--red)" unit="°C" />
        <div className={`gauge-value ${tempClass(temp)}`}>
          {temp != null ? `${temp.toFixed(1)} °C` : '—'}
        </div>
        <div className="gauge-label">Температура</div>
      </div>

      <div className="gauge-box">
        <GaugeChart value={hum} max={100} color="var(--accent)" unit="%" />
        <div className={`gauge-value ${humClass(hum)}`}>
          {hum != null ? `${hum.toFixed(1)} %` : '—'}
        </div>
        <div className="gauge-label">Влажност</div>
      </div>
    </div>
  )
}


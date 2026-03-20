import { useWebSocket }   from './hooks/useWebSocket'
import SensorGauges      from './components/SensorGauges'
import FanControl        from './components/FanControl'
import ValveControl      from './components/ValveControl'
import AirflowStatus     from './components/AirflowStatus'
import ModeToggle        from './components/ModeToggle'
import AlertsPanel       from './components/AlertsPanel'
import HistoricalChart   from './components/HistoricalChart'
import SimulationPanel   from './components/SimulationPanel'

export default function App() {
  const { data, connected } = useWebSocket()

  const isManual = data?.control_mode === 'manual'

  return (
    <div className="app">
      {/* ── Topbar ──────────────────────────────────────────────── */}
      <header className="topbar">
        <div>
          <h1>🌡 Термично управление на ЦД</h1>
          <span className="subtitle">
            {data?.node_name ?? 'Distributed Embedded Thermal Control'} — {data?.node_id ?? 'Raspberry Pi 5'}
          </span>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
          {data?.simulation && <span className="sim-badge">⚠ Симулация</span>}

          {/* MQTT status */}
          {data?.mqtt_connected != null && (
            <span className={`conn-badge ${data.mqtt_connected ? 'ok' : 'err'}`}
                  title={data.mqtt_fallback ? 'MQTT недостъпен — използва се SNMP' : 'MQTT свързан'}>
              <span className="dot" />
              {data.mqtt_connected ? 'MQTT ✓' : data.mqtt_fallback ? 'SNMP ↩' : 'MQTT …'}
            </span>
          )}

          {/* WebSocket status */}
          <span className={`conn-badge ${connected ? 'ok' : 'err'}`}>
            <span className="dot" />
            {connected ? 'WS Свързан' : 'WS Изключен'}
          </span>
        </div>
      </header>

      {/* ── Grid ────────────────────────────────────────────────── */}
      <main className="main">

        {/* Gauges */}
        <div className="card" style={{ gridColumn: 'span 2' }}>
          <h2>Сензори
            {data?.source === 'simulation_override' && (
              <span className="sim-active-badge" style={{ marginLeft: '.75rem' }}>⚗ СИМУЛАЦИЯ</span>
            )}
          </h2>
          <SensorGauges data={data} />
          {data?.timestamp && <p className="ts">Последно обновяване: {data.timestamp}</p>}
        </div>

        {/* Mode */}
        <div className="card">
          <h2>Режим на управление</h2>
          <ModeToggle mode={data?.control_mode ?? 'auto'} />
        </div>

        {/* Fan */}
        <div className="card">
          <h2>Вентилатор</h2>
          <FanControl speed={data?.fan_speed ?? 0} disabled={!isManual} />
        </div>

        {/* Valves */}
        <div className="card">
          <h2>Клапи</h2>
          <ValveControl
            valve1={data?.valve1_open ?? false}
            valve2={data?.valve2_open ?? false}
            disabled={!isManual}
          />
        </div>

        {/* Airflow */}
        <div className="card">
          <h2>Датчици за въздушен поток</h2>
          <AirflowStatus
            inlet={data?.airflow_inlet  ?? false}
            outlet={data?.airflow_outlet ?? false}
          />
        </div>

        {/* Fan RPM + valve feedback */}
        <div className="card">
          <h2>GPIO обратна връзка</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '.6rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', background: 'var(--surface2)', padding: '.6rem .8rem', borderRadius: '8px' }}>
              <span style={{ fontSize: '.85rem' }}>🌀 Вентилатор (RPM)</span>
              <strong style={{ color: 'var(--accent)' }}>
                {data?.fan_rpm != null ? data.fan_rpm : '—'}
              </strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', background: 'var(--surface2)', padding: '.6rem .8rem', borderRadius: '8px' }}>
              <span style={{ fontSize: '.85rem' }}>🚪 Клапа 1 (позиция)</span>
              <strong style={{ color: data?.valve1_feedback ? 'var(--green)' : 'var(--text-muted)' }}>
                {data?.valve1_feedback == null ? '—' : data.valve1_feedback ? 'ОТВОРЕНА' : 'ЗАТВОРЕНА'}
              </strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', background: 'var(--surface2)', padding: '.6rem .8rem', borderRadius: '8px' }}>
              <span style={{ fontSize: '.85rem' }}>🚪 Клапа 2 (позиция)</span>
              <strong style={{ color: data?.valve2_feedback ? 'var(--green)' : 'var(--text-muted)' }}>
                {data?.valve2_feedback == null ? '—' : data.valve2_feedback ? 'ОТВОРЕНА' : 'ЗАТВОРЕНА'}
              </strong>
            </div>
          </div>
        </div>

        {/* Alerts */}
        <div className="card">
          <h2>Известия</h2>
          <AlertsPanel alerts={data?.alerts ?? []} />
        </div>

        {/* Chart */}
        <div className="card wide">
          <h2>История — последните 24 часа</h2>
          <HistoricalChart />
        </div>

        {/* Simulation */}
        <div className="card wide">
          <h2>⚗ Симулационен модул</h2>
          <SimulationPanel />
        </div>

      </main>

      <footer>
        Datacenter Thermal Control v1.0 &nbsp;|&nbsp; Raspberry Pi 5 &nbsp;|&nbsp; 2026
      </footer>
    </div>
  )
}


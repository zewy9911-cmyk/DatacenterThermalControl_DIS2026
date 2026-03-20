export default function AlertsPanel({ alerts }) {
  if (!alerts || alerts.length === 0) {
    return (
      <div className="alerts-list">
        <div className="alert-item ok">
          ✅ Всички параметри в норма
        </div>
      </div>
    )
  }

  return (
    <div className="alerts-list">
      {alerts.map((a, i) => (
        <div key={i} className={`alert-item ${a.level}`}>
          {a.level === 'critical' && '🔴 '}
          {a.level === 'warning'  && '🟡 '}
          {a.level === 'info'     && '🔵 '}
          {a.message}
        </div>
      ))}
    </div>
  )
}


export default function AirflowStatus({ inlet, outlet }) {
  const items = [
    { key: 'inlet',  label: 'Входящ въздух',  icon: '⬇', active: inlet  },
    { key: 'outlet', label: 'Изходящ въздух', icon: '⬆', active: outlet },
  ]

  return (
    <div className="airflow-grid">
      {items.map(item => (
        <div key={item.key} className="airflow-item">
          <div style={{ fontSize: '1.6rem' }}>{item.icon}</div>
          <div className={`airflow-dot ${item.active ? 'on' : 'off'}`} />
          <div className="airflow-label">{item.label}</div>
          <div className={`airflow-status ${item.active ? 'on' : 'off'}`}>
            {item.active ? 'ЗАСЕЧЕН' : 'НЕ ЗАСЕЧЕН'}
          </div>
        </div>
      ))}
    </div>
  )
}


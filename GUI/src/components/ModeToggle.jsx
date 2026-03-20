import { useCallback, useState } from 'react'
import { setMode } from '../api/client'

export default function ModeToggle({ mode }) {
  const [busy, setBusy] = useState(false)

  const handleMode = useCallback(async (m) => {
    if (busy || m === mode) return
    setBusy(true)
    try { await setMode(m) } catch (e) { console.error(e) } finally { setBusy(false) }
  }, [busy, mode])

  return (
    <div className="mode-row">
      <p>
        {mode === 'auto'
          ? 'Системата управлява автоматично вентилатора и клапите по температура.'
          : 'Ръчно управление — промените се прилагат директно.'}
      </p>
      <div className="mode-tabs">
        <button
          className={`mode-tab ${mode === 'auto' ? 'active' : ''}`}
          onClick={() => handleMode('auto')}
          disabled={busy}
        >⚙ АВТО</button>
        <button
          className={`mode-tab ${mode === 'manual' ? 'active' : ''}`}
          onClick={() => handleMode('manual')}
          disabled={busy}
        >✋ РЪЧЕН</button>
      </div>
    </div>
  )
}


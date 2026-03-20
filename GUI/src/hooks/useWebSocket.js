import { useEffect, useRef, useState, useCallback } from 'react'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`

export function useWebSocket() {
  const [data,      setData]      = useState(null)
  const [connected, setConnected] = useState(false)
  const ws      = useRef(null)
  const retries = useRef(0)
  const timer   = useRef(null)

  const connect = useCallback(() => {
    if (ws.current) ws.current.close()

    const socket = new WebSocket(WS_URL)
    ws.current = socket

    socket.onopen = () => {
      setConnected(true)
      retries.current = 0
    }

    socket.onmessage = (evt) => {
      try { setData(JSON.parse(evt.data)) } catch (_) {}
    }

    socket.onclose = () => {
      setConnected(false)
      const delay = Math.min(1000 * 2 ** retries.current, 30_000)
      retries.current += 1
      timer.current = setTimeout(connect, delay)
    }

    socket.onerror = () => socket.close()
  }, [])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(timer.current)
      ws.current?.close()
    }
  }, [connect])

  return { data, connected }
}


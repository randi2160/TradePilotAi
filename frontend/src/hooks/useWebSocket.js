import { useEffect, useRef, useState } from 'react'

export function useWebSocket(token) {
  const [data, setData]       = useState(null)
  const [connected, setConn]  = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    if (!token) return

    function connect() {
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const url   = `${proto}://${window.location.host}/ws?token=${token}`
      const ws    = new WebSocket(url)
      wsRef.current = ws

      ws.onopen    = () => setConn(true)
      ws.onmessage = (e) => { try { setData(JSON.parse(e.data)) } catch {} }
      ws.onclose   = () => { setConn(false); setTimeout(connect, 3000) }
      ws.onerror   = () => ws.close()
    }

    connect()
    return () => { wsRef.current?.close() }
  }, [token])

  return { data, connected }
}

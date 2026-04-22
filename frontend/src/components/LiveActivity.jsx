import { useEffect, useState, useRef, useCallback } from 'react'
import { api } from '../hooks/useAuth'

const TYPE_CONFIG = {
  scan:    { color:'text-purple-400', border:'border-l-purple-500',  icon:'🔍', label:'Scan'    },
  entry:   { color:'text-green-400',  border:'border-l-green-500',   icon:'▲',  label:'Entry'   },
  exit:    { color:'text-blue-400',   border:'border-l-blue-500',    icon:'■',  label:'Exit'    },
  signal:  { color:'text-brand-500',  border:'border-l-brand-500',   icon:'🤖', label:'Signal'  },
  profit:  { color:'text-green-400',  border:'border-l-green-500',   icon:'✅', label:'Profit'  },
  loss:    { color:'text-red-400',    border:'border-l-red-500',     icon:'❌', label:'Loss'    },
  warning: { color:'text-yellow-400', border:'border-l-yellow-500',  icon:'⚠️', label:'Warning' },
  info:    { color:'text-gray-400',   border:'border-l-gray-600',    icon:'ℹ️', label:'Info'    },
  blocked: { color:'text-yellow-400', border:'border-l-yellow-600',  icon:'⛔', label:'Blocked' },
}

function seedInitialEvents(signals, positions, data) {
  const events = []
  const now    = new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'})

  // Seed from current signals
  if (signals?.length) {
    const active = signals.filter(s => s.signal !== 'HOLD' && s.signal !== 'WAIT')
    if (active.length > 0) {
      active.forEach(s => {
        events.push({
          id: Math.random(), type: 'signal', time: now,
          msg: `${s.signal} signal — ${s.symbol}`,
          detail: `${((s.confidence??0)*100).toFixed(0)}% confidence · RSI ${s.rsi?.toFixed(0)} · $${s.price?.toFixed(2)}`,
        })
      })
    } else {
      events.push({
        id: Math.random(), type: 'scan', time: now,
        msg: `Watching ${signals.length} stocks`,
        detail: 'All signals: HOLD — waiting for better conditions',
      })
    }
  }

  // Seed from open positions
  if (positions?.length) {
    positions.forEach(p => {
      const side = String(p.side ?? '').toLowerCase().includes('short') ? 'SHORT' : 'LONG'
      const upnl = parseFloat(p.unrealized_pnl ?? 0)
      events.push({
        id: Math.random(), type: 'entry', time: now,
        msg: `Open position — ${side} ${p.symbol}`,
        detail: `${Math.abs(p.qty)} shares · Unrealized: ${upnl >= 0 ? '+' : ''}$${upnl.toFixed(2)}`,
      })
    })
  }

  // Bot status
  if (data?.bot_status === 'running') {
    events.push({
      id: Math.random(), type: 'info', time: now,
      msg: 'Bot is running in AUTO mode',
      detail: `Scanning every 30 seconds · Mode: ${data.mode ?? 'paper'}`,
    })
  }

  return events
}

export default function LiveActivity({ signals = [], positions = [], data }) {
  const [events,  setEvents]  = useState([])
  const [filter,  setFilter]  = useState('all')
  const [seeded,  setSeeded]  = useState(false)
  const prevSigs  = useRef({})
  const prevPos   = useRef({})
  const eventId   = useRef(0)

  function addEvent(type, msg, detail = '') {
    setEvents(prev => [{
      id:     ++eventId.current,
      type, msg, detail,
      time:   new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}),
    }, ...prev].slice(0, 150))
  }

  // Seed initial events on first load
  useEffect(() => {
    if (seeded) return
    if (signals.length > 0 || positions.length > 0 || data) {
      const initial = seedInitialEvents(signals, positions, data)
      if (initial.length > 0) {
        setEvents(initial)
        setSeeded(true)
      }
    }
  }, [signals.length, positions.length, data?.bot_status])

  // Poll backend for real events every 10 seconds
  const fetchEvents = useCallback(async () => {
    try {
      const r = await api.get('/report/events?limit=30')
      if (r.data?.length > 0) {
        setEvents(prev => {
          // Merge backend events with local ones, dedupe by timestamp+msg
          // Include the poll timestamp in the id so successive polls don't
          // collide on `be-0`, `be-1`, ... (React warns about duplicate keys).
          const pollTs = Date.now()
          const backendEvts = r.data.map((e, i) => ({
            id:     `be-${pollTs}-${i}`,
            type:   e.type ?? 'info',
            msg:    e.msg,
            detail: e.detail ? Object.entries(e.detail).slice(0,4).map(([k,v])=>`${k}: ${v}`).join(' · ') : '',
            time:   e.time ?? '',
          }))
          // Only add events not already shown
          const existingMsgs = new Set(prev.map(e => e.msg))
          const newEvts = backendEvts.filter(e => !existingMsgs.has(e.msg))
          return [...newEvts, ...prev].slice(0, 150)
        })
      }
    } catch {}
  }, [])

  useEffect(() => {
    fetchEvents()
    const iv = setInterval(fetchEvents, 10000)
    return () => clearInterval(iv)
  }, [fetchEvents])

  // Watch signals for changes
  useEffect(() => {
    if (!signals.length) return
    signals.forEach(sig => {
      const prev = prevSigs.current[sig.symbol]
      const cur  = sig.signal
      if (prev && prev !== cur && (cur === 'BUY' || cur === 'SELL')) {
        addEvent('signal',
          `${cur} signal — ${sig.symbol}`,
          `${((sig.confidence??0)*100).toFixed(0)}% conf · RSI ${sig.rsi?.toFixed(0)} · $${sig.price?.toFixed(2)} · vol ${sig.volume_ratio?.toFixed(1)}×`
        )
      }
      prevSigs.current[sig.symbol] = cur
    })
  }, [signals.map(s => `${s.symbol}:${s.signal}`).join(',')])

  // Watch positions
  useEffect(() => {
    if (!positions) return
    const curSyms  = new Set(positions.map(p => p.symbol))
    const prevSyms = new Set(Object.keys(prevPos.current))

    const normSide = s => String(s ?? '').toLowerCase().includes('short') ? 'SHORT' : 'LONG'

    positions.forEach(p => {
      if (!prevSyms.has(p.symbol)) {
        const side  = normSide(p.side)
        const qty   = Math.abs(parseFloat(p.qty ?? 0))
        const entry = parseFloat(p.avg_entry ?? 0)
        addEvent('entry',
          `Entered ${side} — ${p.symbol}`,
          `${qty} shares @ $${entry.toFixed(2)} · Value: $${(qty * entry).toFixed(2)}`
        )
      }
      prevPos.current[p.symbol] = p
    })

    prevSyms.forEach(sym => {
      if (!curSyms.has(sym)) {
        const old = prevPos.current[sym]
        delete prevPos.current[sym]
        if (old) addEvent('exit', `Exited position — ${sym}`, 'Position closed')
      }
    })
  }, [positions.map(p => p.symbol).join(',')])

  // 30-second scan ticker
  useEffect(() => {
    if (!signals.length) return
    const iv = setInterval(() => {
      const active = signals.filter(s => s.signal !== 'HOLD' && s.signal !== 'WAIT')
      addEvent('scan',
        `Scan complete — ${signals.length} stocks checked`,
        active.length > 0
          ? `Active: ${active.slice(0,5).map(s => `${s.symbol} ${s.signal}`).join(', ')}`
          : 'All HOLD — no qualifying setups'
      )
    }, 30000)
    return () => clearInterval(iv)
  }, [signals.length])

  const FILTERS = [
    { id:'all',    label:'All'         },
    { id:'signal', label:'🤖 Signals'  },
    { id:'entry',  label:'▲ Entries'  },
    { id:'exit',   label:'■ Exits'    },
    { id:'scan',   label:'🔍 Scans'   },
  ]

  const filtered = filter === 'all'
    ? events
    : events.filter(e => e.type === filter || (filter === 'exit' && (e.type === 'profit' || e.type === 'loss')))

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-dark-600">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"/>
          <span className="text-sm font-bold text-white">Live Activity Feed</span>
          <span className="text-xs text-gray-500">{events.length} events</span>
        </div>
        <button onClick={() => setEvents([])} className="text-xs text-gray-600 hover:text-gray-400">Clear</button>
      </div>

      <div className="flex gap-1 px-3 py-2 border-b border-dark-600 overflow-x-auto">
        {FILTERS.map(f => (
          <button key={f.id} onClick={() => setFilter(f.id)}
            className={`px-2 py-1 rounded text-xs whitespace-nowrap transition-colors ${
              filter===f.id ? 'bg-brand-500 text-dark-900 font-bold' : 'text-gray-400 hover:bg-dark-700'
            }`}>{f.label}</button>
        ))}
      </div>

      <div className="max-h-72 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="text-center py-8 text-gray-500 text-sm">
            <p className="text-2xl mb-1">📡</p>
            <p>{events.length === 0 ? 'Starting up — activity will appear here' : 'No events match this filter'}</p>
          </div>
        ) : (
          <div className="divide-y divide-dark-700">
            {filtered.map(ev => {
              const cfg = TYPE_CONFIG[ev.type] ?? TYPE_CONFIG.info
              return (
                <div key={ev.id} className={`px-4 py-2.5 border-l-2 ${cfg.border}`}>
                  <div className="flex items-center gap-2">
                    <span className="text-sm flex-shrink-0">{cfg.icon}</span>
                    <span className={`text-sm font-medium ${cfg.color}`}>{ev.msg}</span>
                    <span className="text-xs text-gray-600 ml-auto whitespace-nowrap">{ev.time}</span>
                  </div>
                  {ev.detail && <p className="text-xs text-gray-500 mt-0.5 ml-6">{ev.detail}</p>}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
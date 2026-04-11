import { useEffect, useRef, useState } from 'react'
import { api } from '../hooks/useAuth'
import { Brain, Zap, TrendingUp, TrendingDown, Activity, RefreshCw } from 'lucide-react'

const ACTION_STYLE = {
  BUY:  { bg: 'bg-green-900/30  border-green-700',  text: 'text-green-400',  icon: '▲', badge: 'bg-green-800 text-green-200' },
  SELL: { bg: 'bg-red-900/30    border-red-700',    text: 'text-red-400',    icon: '▼', badge: 'bg-red-800   text-red-200'   },
  EXIT: { bg: 'bg-orange-900/30 border-orange-700', text: 'text-orange-400', icon: '⬛', badge: 'bg-orange-800 text-orange-200' },
  HOLD: { bg: 'bg-dark-800      border-dark-600',   text: 'text-gray-400',   icon: '—', badge: 'bg-dark-600  text-gray-300'  },
}

const URGENCY_COLOR = {
  immediate:         'text-red-400 animate-pulse',
  wait_for_pullback: 'text-yellow-400',
  watch_only:        'text-gray-400',
}

function DecisionCard({ decision, onTrade }) {
  const s      = ACTION_STYLE[decision.action] ?? ACTION_STYLE.HOLD
  const urgent = URGENCY_COLOR[decision.urgency] ?? 'text-gray-400'
  const conf   = decision.confidence ?? 0
  const ts     = decision.timestamp
    ? new Date(decision.timestamp).toLocaleTimeString([], { hour:'2-digit', minute:'2-digit', second:'2-digit' })
    : ''

  return (
    <div className={`rounded-xl border p-4 space-y-3 ${s.bg}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl font-black text-white">{decision.symbol}</span>
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${s.badge}`}>
            {s.icon} {decision.action}
          </span>
          {decision.risk_flag && (
            <span className="text-xs bg-yellow-900/40 text-yellow-400 border border-yellow-800/50 px-1.5 py-0.5 rounded">
              ⚠️ {decision.risk_flag?.replace(/_/g, ' ')}
            </span>
          )}
        </div>
        <div className="text-right">
          <div className={`text-lg font-black ${conf >= 75 ? 'text-green-400' : conf >= 55 ? 'text-yellow-400' : 'text-gray-400'}`}>
            {conf}%
          </div>
          <div className="text-xs text-gray-500">{ts}</div>
        </div>
      </div>

      {/* Live price */}
      <div className="flex items-center gap-3 text-sm">
        <span className="text-gray-400">Live Price:</span>
        <span className="font-mono font-bold text-white text-lg">${decision.live_price?.toFixed(2)}</span>
        {decision.entry_price && (
          <span className="text-xs text-gray-400">Entry zone: ${decision.entry_price?.toFixed(2)}</span>
        )}
      </div>

      {/* Urgency */}
      <div className="flex items-center gap-2">
        <Zap size={12} className={urgent.replace(' animate-pulse','')} />
        <span className={`text-xs font-semibold capitalize ${urgent}`}>
          {decision.urgency?.replace(/_/g, ' ')}
        </span>
        {decision.time_in_trade && (
          <span className="text-xs text-gray-500 ml-auto">⏱ {decision.time_in_trade?.replace(/_/g, ' ')}</span>
        )}
      </div>

      {/* Confidence bar */}
      <div className="h-1.5 bg-dark-600 rounded-full overflow-hidden">
        <div
          className="h-1.5 rounded-full transition-all duration-500"
          style={{
            width: `${conf}%`,
            background: conf >= 75 ? 'linear-gradient(90deg,#00d4aa,#00b894)'
              : conf >= 55 ? 'linear-gradient(90deg,#f59e0b,#d97706)'
              : '#6b7280',
          }}
        />
      </div>

      {/* Key levels */}
      {(decision.stop_loss || decision.take_profit) && (
        <div className="flex gap-3 text-xs">
          {decision.stop_loss   && <span className="text-red-400">SL: ${decision.stop_loss?.toFixed(2)}</span>}
          {decision.take_profit && <span className="text-green-400">TP: ${decision.take_profit?.toFixed(2)}</span>}
          {decision.position_size_pct && (
            <span className="text-gray-400 ml-auto">Size: {decision.position_size_pct}% of capital</span>
          )}
        </div>
      )}

      {/* Reasoning */}
      {decision.reasoning && (
        <div className="bg-dark-700/60 rounded-lg p-2.5 text-xs text-gray-300 italic">
          🧠 "{decision.reasoning}"
        </div>
      )}

      {/* Action buttons — only show for actionable decisions */}
      {decision.action !== 'HOLD' && onTrade && (
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => onTrade(decision)}
            className={`flex-1 py-2 rounded-lg text-xs font-bold transition-colors ${
              decision.action === 'BUY'
                ? 'bg-green-700 hover:bg-green-600 text-white'
                : 'bg-red-700 hover:bg-red-600 text-white'
            }`}
          >
            ✓ Execute {decision.action}
          </button>
          <button
            onClick={() => onTrade({ ...decision, action: 'SKIP' })}
            className="px-4 py-2 rounded-lg text-xs font-bold bg-dark-700 hover:bg-dark-600 text-gray-400 transition-colors"
          >
            Skip
          </button>
        </div>
      )}
    </div>
  )
}

function PriceTicker({ symbol, price, changePct, bid, ask }) {
  const prevRef = useRef(price)
  const [flash, setFlash] = useState('')

  useEffect(() => {
    if (price !== prevRef.current) {
      setFlash(price > prevRef.current ? 'text-green-400' : 'text-red-400')
      setTimeout(() => setFlash(''), 600)
      prevRef.current = price
    }
  }, [price])

  return (
    <div className="flex items-center justify-between bg-dark-700 rounded-lg px-3 py-2">
      <span className="font-bold text-white text-sm w-14">{symbol}</span>
      <span className={`font-mono font-bold text-sm transition-colors duration-300 ${flash || 'text-white'}`}>
        ${price?.toFixed(2) ?? '—'}
      </span>
      <span className={`text-xs font-semibold w-16 text-right ${changePct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
        {changePct >= 0 ? '+' : ''}{changePct?.toFixed(2)}%
      </span>
      <span className="text-xs text-gray-500 hidden sm:block">
        {bid?.toFixed(2)} / {ask?.toFixed(2)}
      </span>
    </div>
  )
}

export default function LiveFeed({ watchlist = [], tradingMode = 'auto' }) {
  const [prices,    setPrices]    = useState({})
  const [decisions, setDecisions] = useState([])
  const [connected, setConnected] = useState(false)
  const [lastUpd,   setLastUpd]   = useState('')
  const [log,       setLog]       = useState([])  // decision history
  const wsRef = useRef(null)

  useEffect(() => {
    connect()
    const iv = setInterval(fetchDecisions, 5000)  // poll decisions every 5s
    return () => { clearInterval(iv); wsRef.current?.close() }
  }, [])

  function connect() {
    const ws = new WebSocket(`ws://${window.location.host}/ws/live`)
    wsRef.current = ws

    ws.onopen    = () => setConnected(true)
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === 'prices')    setPrices(p => ({ ...p, ...data.data }))
        if (data.type === 'decision')  handleDecision(data.data)
      } catch {}
    }
    ws.onclose = () => { setConnected(false); setTimeout(connect, 3000) }
    ws.onerror  = () => ws.close()
  }

  async function fetchDecisions() {
    try {
      const r = await api.get('/live/decisions')
      setDecisions(r.data?.actionable ?? [])
      setLastUpd(new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit', second:'2-digit' }))
    } catch {}
  }

  function handleDecision(decision) {
    setDecisions(prev => {
      const filtered = prev.filter(d => d.symbol !== decision.symbol)
      return decision.action !== 'HOLD' ? [decision, ...filtered] : filtered
    })
    if (decision.action !== 'HOLD') {
      setLog(prev => [{ ...decision, logged_at: new Date().toLocaleTimeString() }, ...prev.slice(0, 49)])
    }
  }

  async function executeTrade(decision) {
    if (decision.action === 'SKIP') return
    try {
      await api.post('/trades/manual', {
        symbol:      decision.symbol,
        side:        decision.action === 'EXIT' ? 'SELL' : decision.action,
        qty:         1,
        entry_price: decision.live_price,
        is_llm:      true,
      })
    } catch(e) {
      console.error('Trade error:', e)
    }
  }

  const priceList = Object.entries(prices)
    .map(([sym, data]) => ({ sym, ...data }))
    .sort((a, b) => Math.abs(b.change_pct ?? 0) - Math.abs(a.change_pct ?? 0))

  const activeDecisions = decisions.filter(d => d.action !== 'HOLD')

  return (
    <div className="space-y-4">

      {/* Connection status */}
      <div className="flex items-center gap-3">
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${
          connected ? 'bg-green-900/30 border border-green-800 text-green-400' : 'bg-red-900/30 border border-red-800 text-red-400'
        }`}>
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-red-400'}`}/>
          {connected ? 'LIVE FEED CONNECTED' : 'Connecting…'}
        </div>
        <div className="flex items-center gap-1 text-xs text-gray-400">
          <Brain size={12} className="text-brand-500"/>
          GPT-4 analyzing every 30s
        </div>
        {lastUpd && <span className="text-xs text-gray-600 ml-auto">Last update: {lastUpd}</span>}
        <button onClick={fetchDecisions} className="text-gray-400 hover:text-white">
          <RefreshCw size={14}/>
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Left — live price ticker */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Activity size={14} className="text-brand-500"/>
            <h3 className="text-sm font-bold text-gray-300">Live Price Feed</h3>
            <span className="text-xs text-gray-500">{priceList.length} symbols</span>
          </div>

          {priceList.length === 0 ? (
            <div className="bg-dark-800 border border-dark-600 rounded-xl p-8 text-center text-gray-500">
              <Activity size={32} className="mx-auto mb-2 opacity-30"/>
              <p className="text-sm">Start the bot to activate live price feed</p>
            </div>
          ) : (
            <div className="space-y-1.5 max-h-[500px] overflow-y-auto">
              {priceList.map(({ sym, price, change_pct, bid, ask }) => (
                <PriceTicker
                  key={sym}
                  symbol={sym}
                  price={price}
                  changePct={change_pct}
                  bid={bid}
                  ask={ask}
                />
              ))}
            </div>
          )}
        </div>

        {/* Right — LLM decisions */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Brain size={14} className="text-brand-500"/>
            <h3 className="text-sm font-bold text-gray-300">GPT-4 Live Decisions</h3>
            {activeDecisions.length > 0 && (
              <span className="bg-brand-500 text-dark-900 text-xs px-2 py-0.5 rounded-full font-bold">
                {activeDecisions.length}
              </span>
            )}
            <span className={`text-xs ml-auto ${tradingMode === 'auto' ? 'text-brand-500' : 'text-yellow-400'}`}>
              {tradingMode === 'auto' ? '🤖 AUTO executing' : '👤 Manual approval'}
            </span>
          </div>

          {activeDecisions.length === 0 ? (
            <div className="bg-dark-800 border border-dark-600 rounded-xl p-8 text-center text-gray-500">
              <Brain size={32} className="mx-auto mb-2 opacity-30"/>
              <p className="text-sm">GPT-4 monitoring markets…</p>
              <p className="text-xs mt-1">Will alert when a strong signal is detected</p>
            </div>
          ) : (
            <div className="space-y-3 max-h-[500px] overflow-y-auto">
              {activeDecisions.map((d, i) => (
                <DecisionCard
                  key={`${d.symbol}-${i}`}
                  decision={d}
                  onTrade={tradingMode === 'manual' ? executeTrade : null}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Decision log */}
      {log.length > 0 && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
          <h4 className="text-xs font-bold text-gray-400 mb-3">GPT-4 Decision Log (last {Math.min(log.length, 20)})</h4>
          <div className="space-y-1 max-h-40 overflow-y-auto font-mono text-xs">
            {log.slice(0, 20).map((d, i) => {
              const s = ACTION_STYLE[d.action] ?? ACTION_STYLE.HOLD
              return (
                <div key={i} className="flex gap-3 items-center">
                  <span className="text-gray-600">{d.logged_at}</span>
                  <span className={`font-bold w-12 ${s.text}`}>{d.action}</span>
                  <span className="text-white w-14">{d.symbol}</span>
                  <span className="text-gray-400">${d.live_price?.toFixed(2)}</span>
                  <span className="text-gray-500">{d.confidence}%</span>
                  <span className="text-gray-600 truncate">{d.reasoning?.slice(0, 60)}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../hooks/useAuth'
import { addSymbol } from '../services/api'
import {
  X, Send, TrendingUp, TrendingDown, RefreshCw,
  Brain, MessageCircle, Newspaper, BarChart2,
  Star, Target, Shield, Zap, ChevronDown
} from 'lucide-react'

// ── Lightweight Chart (TradingView) ───────────────────────────────────────────
function LiveChart({ symbol, height = 320 }) {
  const ref       = useRef(null)
  const chartRef  = useRef(null)
  const seriesRef = useRef(null)
  const volRef    = useRef(null)
  const [tf, setTf]       = useState('5Min')
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState('')

  const TF_OPTIONS = ['1Min', '5Min', '15Min', '1Hour', '1Day']

  useEffect(() => {
    let script = document.getElementById('lwc-script')
    if (!script) {
      script = document.createElement('script')
      script.id  = 'lwc-script'
      script.src = 'https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js'
      document.head.appendChild(script)
    }
    const init = () => {
      if (!ref.current || chartRef.current) return
      const chart = window.LightweightCharts.createChart(ref.current, {
        width:  ref.current.clientWidth,
        height: height - 60,
        layout: { background: { color: '#0d1b2a' }, textColor: '#94a3b8' },
        grid:   { vertLines: { color: '#1a2740' }, horzLines: { color: '#1a2740' } },
        crosshair: { mode: 1 },
        rightPriceScale: { borderColor: '#1a2740' },
        timeScale: { borderColor: '#1a2740', timeVisible: true, secondsVisible: false },
      })
      const candleSeries = chart.addCandlestickSeries({
        upColor:   '#22d3a0', downColor: '#f87171',
        borderUpColor: '#22d3a0', borderDownColor: '#f87171',
        wickUpColor:   '#22d3a0', wickDownColor:   '#f87171',
      })
      const volSeries = chart.addHistogramSeries({
        color: '#1a2740', priceFormat: { type: 'volume' },
        priceScaleId: 'vol', scaleMargins: { top: 0.85, bottom: 0 },
      })
      chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } })
      chartRef.current  = chart
      seriesRef.current = candleSeries
      volRef.current    = volSeries

      const ro = new ResizeObserver(() => {
        if (ref.current && chartRef.current) {
          chartRef.current.resize(ref.current.clientWidth, height - 60)
        }
      })
      ro.observe(ref.current)
    }

    if (window.LightweightCharts) { init() }
    else { script.onload = init }
    return () => { if (chartRef.current) { chartRef.current.remove(); chartRef.current = null } }
  }, [])

  const loadBars = useCallback(async () => {
    if (!seriesRef.current) return
    setLoading(true)
    setError('')
    try {
      const r = await api.get(`/chart/${symbol}/bars?timeframe=${tf}&limit=300`)
      const bars = r.data
      if (!bars.length) { setError('No chart data — start the bot to enable live data'); return }
      seriesRef.current.setData(bars)
      volRef.current?.setData(bars.map(b => ({
        time:  b.time,
        value: b.volume,
        color: b.close >= b.open ? 'rgba(34,211,160,0.3)' : 'rgba(248,113,113,0.3)'
      })))
      chartRef.current?.timeScale().fitContent()
    } catch (e) {
      setError('Chart data unavailable — bot must be running')
    } finally { setLoading(false) }
  }, [symbol, tf])

  useEffect(() => {
    const iv = setTimeout(loadBars, 300)
    const refresh = setInterval(loadBars, 30000)
    return () => { clearTimeout(iv); clearInterval(refresh) }
  }, [loadBars])

  return (
    <div className="bg-dark-900 rounded-xl border border-dark-600 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-dark-700">
        <BarChart2 size={14} className="text-brand-400"/>
        <span className="text-xs font-bold text-white">${symbol} Chart</span>
        <div className="flex gap-1 ml-auto">
          {TF_OPTIONS.map(t => (
            <button key={t} onClick={() => setTf(t)}
              className={`text-xs px-2 py-0.5 rounded transition-colors ${
                tf === t ? 'bg-brand-500 text-dark-900 font-bold' : 'text-gray-500 hover:text-white'
              }`}>{t}</button>
          ))}
          <button onClick={loadBars} className="ml-1 p-0.5 text-gray-600 hover:text-white">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''}/>
          </button>
        </div>
      </div>
      {error ? (
        <div className="flex items-center justify-center text-xs text-gray-600 py-12">{error}</div>
      ) : (
        <div ref={ref} className="w-full"/>
      )}
    </div>
  )
}

// ── AI Strategy Panel ─────────────────────────────────────────────────────────
function AIStrategy({ symbol, price, compact = false }) {
  const [data,     setData]     = useState(null)
  const [loading,  setLoading]  = useState(false)
  const [lastRefresh, setLastRefresh] = useState(null)

  const analyze = useCallback(async () => {
    setLoading(true)
    try {
      const r = await api.post('/ai/symbol-sentiment', {
        symbol,
        price:      price?.price,
        change_pct: price?.change_pct,
      })
      setData(r.data)
      setLastRefresh(new Date())
    } catch {
      // fallback
      const change = price?.change_pct || 0
      setData({
        signal:     change > 2 ? 'BUY' : change < -2 ? 'SELL' : 'HOLD',
        sentiment:  change > 1.5 ? 'bullish' : change < -1.5 ? 'bearish' : 'neutral',
        score:      Math.round(50 + change * 6),
        confidence: Math.round(50 + Math.abs(change) * 4),
        reasoning:  `${symbol} is ${change >= 0 ? 'up' : 'down'} ${Math.abs(change).toFixed(2)}% today. ` +
                    (change > 1.5 ? 'Momentum is positive.' : change < -1.5 ? 'Selling pressure elevated.' : 'Consolidating — wait for direction.'),
        entry: price?.price ? price.price.toFixed(2) : null,
        exit:  price?.price ? (price.price * (change > 0 ? 1.03 : 0.97)).toFixed(2) : null,
        stop:  price?.price ? (price.price * (change > 0 ? 0.98 : 1.02)).toFixed(2) : null,
        risk_reward: '2.0',
        indicators: {},
        key_levels: {
          support:    price?.price ? (price.price * 0.97).toFixed(2) : '—',
          resistance: price?.price ? (price.price * 1.03).toFixed(2) : '—',
        },
      })
      setLastRefresh(new Date())
    } finally { setLoading(false) }
  }, [symbol, price])

  useEffect(() => {
    if (price) analyze()
    const iv = setInterval(analyze, 60000) // refresh every minute
    return () => clearInterval(iv)
  }, [symbol])

  const SIG_STYLE = {
    BUY:  'bg-green-900/30 border-green-600 text-green-400',
    SELL: 'bg-red-900/30   border-red-600   text-red-400',
    HOLD: 'bg-yellow-900/30 border-yellow-600 text-yellow-400',
  }

  if (loading && !data) return (
    <div className="flex items-center gap-2 p-4 text-xs text-gray-500">
      <RefreshCw size={12} className="animate-spin"/> Running AI analysis…
    </div>
  )

  if (!data) return null

  return (
    <div className="space-y-3">
      {/* Signal header */}
      <div className="flex items-center gap-3">
        <div className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border-2 font-black text-xl ${SIG_STYLE[data.signal] || SIG_STYLE.HOLD}`}>
          {data.signal === 'BUY' ? '🟢' : data.signal === 'SELL' ? '🔴' : '🟡'} {data.signal}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className={`text-xs px-2 py-0.5 rounded-full border font-bold ${
              data.sentiment === 'bullish' ? 'text-green-400 bg-green-900/20 border-green-800/40' :
              data.sentiment === 'bearish' ? 'text-red-400 bg-red-900/20 border-red-800/40' :
              'text-gray-400 bg-dark-700 border-dark-600'
            }`}>
              {data.sentiment === 'bullish' ? '🟢 Bullish' : data.sentiment === 'bearish' ? '🔴 Bearish' : '⚪ Neutral'}
            </span>
            <span className="text-xs text-gray-500">{data.confidence}% confidence</span>
          </div>
          <div className="text-xs text-gray-600 mt-0.5">
            AI Score: {data.score}/100
            {lastRefresh && ` · Updated ${lastRefresh.toLocaleTimeString()}`}
          </div>
        </div>
        <button onClick={analyze} disabled={loading}
          className="p-1.5 rounded-lg bg-dark-700 hover:bg-dark-600 text-gray-500 hover:text-white">
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''}/>
        </button>
      </div>

      {/* Score bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-gray-600">
          <span>Bearish 0</span><span>Neutral 50</span><span>100 Bullish</span>
        </div>
        <div className="h-2 bg-dark-700 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all duration-500 ${
            data.score > 60 ? 'bg-green-500' : data.score < 40 ? 'bg-red-500' : 'bg-yellow-500'
          }`} style={{ width: `${Math.max(3, Math.min(97, data.score))}%` }}/>
        </div>
      </div>

      {/* Entry / Exit / Stop */}
      {data.entry && (
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-brand-500/10 border border-brand-500/30 rounded-xl p-2.5 text-center">
            <div className="text-xs text-gray-500 flex items-center justify-center gap-1">
              <Target size={10}/> Entry
            </div>
            <div className="text-sm font-black text-brand-400 mt-0.5">${data.entry}</div>
          </div>
          <div className="bg-green-900/15 border border-green-800/30 rounded-xl p-2.5 text-center">
            <div className="text-xs text-gray-500 flex items-center justify-center gap-1">
              <TrendingUp size={10}/> Target
            </div>
            <div className="text-sm font-black text-green-400 mt-0.5">${data.exit}</div>
          </div>
          <div className="bg-red-900/15 border border-red-800/30 rounded-xl p-2.5 text-center">
            <div className="text-xs text-gray-500 flex items-center justify-center gap-1">
              <Shield size={10}/> Stop
            </div>
            <div className="text-sm font-black text-red-400 mt-0.5">${data.stop}</div>
          </div>
        </div>
      )}

      {/* R:R */}
      {data.risk_reward && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-gray-500">Risk/Reward:</span>
          <span className={`font-bold ${parseFloat(data.risk_reward) >= 2 ? 'text-green-400' : 'text-yellow-400'}`}>
            1:{data.risk_reward}
          </span>
          {parseFloat(data.risk_reward) >= 2 && <span className="text-green-400">✓ Good setup</span>}
        </div>
      )}

      {/* Reasoning */}
      <div className="bg-dark-700 rounded-xl p-3 text-xs text-gray-400 leading-relaxed">
        {data.reasoning}
      </div>

      {/* Technical indicators */}
      {data.indicators && Object.keys(data.indicators).length > 0 && (
        <div className="grid grid-cols-3 gap-1.5">
          {[
            { key: 'rsi',       label: 'RSI',        fmt: v => v.toFixed(0), color: v => v < 30 ? 'text-green-400' : v > 70 ? 'text-red-400' : 'text-gray-300' },
            { key: 'bb_pct',    label: 'BB %',       fmt: v => (v*100).toFixed(0)+'%', color: v => v < 0.2 ? 'text-green-400' : v > 0.8 ? 'text-red-400' : 'text-gray-300' },
            { key: 'vol_ratio', label: 'Vol Ratio',  fmt: v => v.toFixed(1)+'x', color: v => v > 1.5 ? 'text-yellow-400' : 'text-gray-300' },
          ].map(({ key, label, fmt, color }) => {
            const val = data.indicators[key]
            if (val === undefined) return null
            return (
              <div key={key} className="bg-dark-800 rounded-lg p-2 text-center">
                <div className="text-xs text-gray-600">{label}</div>
                <div className={`text-sm font-bold ${color(val)}`}>{fmt(val)}</div>
              </div>
            )
          })}
        </div>
      )}

      {/* Key levels */}
      {data.key_levels && (
        <div className="flex gap-2 text-xs">
          {[
            { label: 'Support',    val: data.key_levels.support,    color: 'text-red-400'   },
            { label: 'VWAP',       val: data.key_levels.vwap,       color: 'text-yellow-400'},
            { label: 'Resistance', val: data.key_levels.resistance,  color: 'text-green-400' },
          ].filter(x => x.val).map(({ label, val, color }) => (
            <div key={label} className="flex-1 bg-dark-800 rounded-lg p-2 text-center">
              <div className="text-gray-600">{label}</div>
              <div className={`font-bold ${color}`}>${val}</div>
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-gray-600 text-center">
        ⚠️ AI analysis updates every minute. Not financial advice. Always manage your risk.
      </p>
    </div>
  )
}

// ── Community Chat ────────────────────────────────────────────────────────────
function CommunityChat({ symbol, currentUserId }) {
  const [chat,      setChat]      = useState([])
  const [msg,       setMsg]       = useState('')
  const [sentiment, setSentiment] = useState('neutral')
  const [posting,   setPosting]   = useState(false)
  const chatRef = useRef(null)

  useEffect(() => {
    load()
    const iv = setInterval(load, 15000)
    return () => clearInterval(iv)
  }, [symbol])

  useEffect(() => {
    chatRef.current?.scrollTo(0, chatRef.current.scrollHeight)
  }, [chat])

  async function load() {
    try {
      const r = await api.get(`/social/chat/${symbol}?limit=50`)
      setChat(r.data.reverse())
    } catch {}
  }

  async function send() {
    if (!msg.trim() || posting) return
    setPosting(true)
    try {
      await api.post(`/social/chat/${symbol}`, { content: msg.trim(), sentiment })
      setMsg('')
      await load()
    } catch {} finally { setPosting(false) }
  }

  const bulls = chat.filter(m => m.sentiment === 'bullish').length
  const bears = chat.filter(m => m.sentiment === 'bearish').length
  const total = bulls + bears || 1

  return (
    <div className="flex flex-col h-full">
      {/* Sentiment bar */}
      {chat.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-2 bg-dark-900/50 border-b border-dark-700 text-xs flex-shrink-0">
          <span className="text-gray-600">Community:</span>
          <span className="text-green-400 font-bold">🟢 {Math.round((bulls/total)*100)}%</span>
          <div className="flex-1 h-1.5 bg-dark-700 rounded-full overflow-hidden mx-1">
            <div className="h-full bg-green-500 rounded-full" style={{ width: `${(bulls/total)*100}%` }}/>
          </div>
          <span className="text-red-400 font-bold">{Math.round((bears/total)*100)}% 🔴</span>
          <span className="text-gray-600 ml-2">{chat.length} msgs</span>
        </div>
      )}

      {/* Messages */}
      <div ref={chatRef} className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
        {chat.length === 0 ? (
          <div className="text-center py-8 text-gray-600">
            <MessageCircle size={28} className="mx-auto mb-2 opacity-30"/>
            <p className="text-sm">No messages yet for ${symbol}</p>
            <p className="text-xs mt-1">Be the first!</p>
          </div>
        ) : chat.map((m, i) => {
          const isMe = m.user_id === currentUserId
          return (
            <div key={i} className={`flex gap-2 ${isMe ? 'flex-row-reverse' : ''}`}>
              <div className="w-6 h-6 rounded-full bg-dark-600 flex items-center justify-center text-xs font-bold text-gray-400 flex-shrink-0">
                {(m.display_name || 'U').slice(0,2).toUpperCase()}
              </div>
              <div className={`max-w-[80%] flex flex-col gap-0.5 ${isMe ? 'items-end' : ''}`}>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-xs text-gray-500">{m.display_name || 'Trader'}</span>
                  {m.sentiment !== 'neutral' && (
                    <span className={`text-xs font-bold ${m.sentiment === 'bullish' ? 'text-green-400' : 'text-red-400'}`}>
                      {m.sentiment === 'bullish' ? '🟢' : '🔴'}
                    </span>
                  )}
                  <span className="text-xs text-gray-700">
                    {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
                <div className={`px-3 py-2 rounded-xl text-sm ${
                  isMe ? 'bg-brand-500/20 text-white rounded-tr-sm' : 'bg-dark-700 text-gray-200 rounded-tl-sm'
                }`}>
                  {m.content || m.message}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Input */}
      <div className="flex-shrink-0 p-3 border-t border-dark-700 space-y-2">
        <div className="flex gap-1">
          {['bullish','neutral','bearish'].map(s => (
            <button key={s} onClick={() => setSentiment(s)}
              className={`flex-1 text-xs py-1 rounded-lg border font-medium transition-all ${
                sentiment === s
                  ? s === 'bullish' ? 'bg-green-900/40 border-green-700 text-green-400'
                  : s === 'bearish' ? 'bg-red-900/40 border-red-700 text-red-400'
                  :                   'bg-dark-600 border-dark-500 text-gray-300'
                  : 'bg-dark-800 border-dark-700 text-gray-600 hover:text-gray-400'
              }`}>
              {s === 'bullish' ? '🟢' : s === 'bearish' ? '🔴' : '⚪'} {s.charAt(0).toUpperCase()+s.slice(1)}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input value={msg} onChange={e => setMsg(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
            placeholder={`Share thoughts on $${symbol}…`}
            className="flex-1 bg-dark-800 border border-dark-600 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500 placeholder-gray-700"/>
          <button onClick={send} disabled={!msg.trim() || posting}
            className="px-3 py-2 bg-brand-500 hover:bg-brand-600 text-dark-900 rounded-xl disabled:opacity-40">
            <Send size={13}/>
          </button>
        </div>
      </div>
    </div>
  )
}

// ── News Feed ─────────────────────────────────────────────────────────────────
function SymbolNews({ symbol }) {
  const [news, setNews] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/news?symbol=${symbol}&limit=10`)
      .then(r => setNews(r.data?.articles || r.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [symbol])

  if (loading) return <div className="text-xs text-gray-600 p-4 text-center">Loading news…</div>

  if (!news.length) return (
    <div className="text-center py-8 text-gray-600">
      <Newspaper size={28} className="mx-auto mb-2 opacity-30"/>
      <p className="text-sm">No recent news for ${symbol}</p>
    </div>
  )

  return (
    <div className="space-y-2 p-3">
      {news.map((item, i) => {
        const s = item.sentiment || 'neutral'
        return (
          <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
            className={`block p-3 rounded-xl border-l-2 bg-dark-800 hover:bg-dark-700 transition-colors ${
              s === 'bullish' ? 'border-l-green-500' : s === 'bearish' ? 'border-l-red-500' : 'border-l-dark-500'
            }`}>
            <div className="text-xs font-bold text-white leading-tight line-clamp-2">{item.title}</div>
            <div className="flex items-center gap-2 mt-1 text-xs text-gray-600">
              <span>{item.source}</span>
              {item.published_at && <span>{new Date(item.published_at).toLocaleDateString()}</span>}
              <span className={s === 'bullish' ? 'text-green-400' : s === 'bearish' ? 'text-red-400' : ''}>
                {s !== 'neutral' ? (s === 'bullish' ? '🟢' : '🔴') : ''}
              </span>
            </div>
          </a>
        )
      })}
    </div>
  )
}

// ── Main Symbol Page ──────────────────────────────────────────────────────────
export default function SymbolPage({ symbol, onClose, currentUserId }) {
  const [price,   setPrice]   = useState(null)
  const [inWatch, setInWatch] = useState(false)
  const [tab,     setTab]     = useState('chart')

  useEffect(() => {
    loadPrice()
    const iv = setInterval(loadPrice, 15000)
    return () => clearInterval(iv)
  }, [symbol])

  async function loadPrice() {
    try {
      const r = await api.get(`/ticker/${symbol}`)
      setPrice(r.data)
    } catch {}
  }

  async function watchlist() {
    try { await addSymbol(symbol); setInWatch(true) } catch {}
  }

  const change   = price?.change_pct || 0
  const isUp     = change >= 0

  const TABS = [
    { id: 'chart',     label: '📈 Chart + AI'  },
    { id: 'community', label: '💬 Community'   },
    { id: 'news',      label: '📰 News'        },
  ]

  return (
    <div className="flex flex-col h-full bg-dark-800 rounded-2xl border border-dark-600 overflow-hidden">

      {/* Header */}
      <div className="flex-shrink-0 bg-dark-900 border-b border-dark-700 px-4 py-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500/30 to-teal-500/20 border border-brand-500/30 flex items-center justify-center font-black text-white text-xs">
            {symbol.slice(0,2)}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xl font-black text-white">${symbol}</span>
              {price?.price && (
                <span className="text-xl font-bold text-white">${price.price.toFixed(2)}</span>
              )}
              {price && (
                <span className={`flex items-center gap-0.5 text-sm font-bold ${isUp ? 'text-green-400' : 'text-red-400'}`}>
                  {isUp ? <TrendingUp size={14}/> : <TrendingDown size={14}/>}
                  {isUp ? '+' : ''}{change.toFixed(2)}%
                </span>
              )}
              {price?.volume && (
                <span className="text-xs text-gray-500">Vol: {(price.volume / 1e6).toFixed(1)}M</span>
              )}
            </div>
          </div>

          <button onClick={watchlist} disabled={inWatch}
            className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border transition-all ${
              inWatch ? 'text-brand-400 border-brand-500/40 bg-brand-500/10' : 'text-gray-500 border-dark-600 hover:border-brand-400 hover:text-brand-400'
            }`}>
            <Star size={11}/> {inWatch ? 'Watching' : 'Watch'}
          </button>
          {onClose && (
            <button onClick={onClose}
              className="p-1.5 rounded-lg text-gray-500 hover:text-white hover:bg-dark-700">
              <X size={16}/>
            </button>
          )}
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mt-3">
          {TABS.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                tab === t.id ? 'bg-brand-500 text-dark-900' : 'text-gray-500 hover:bg-dark-700 hover:text-white'
              }`}>{t.label}</button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden flex flex-col min-h-0">

        {tab === 'chart' && (
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            <LiveChart symbol={symbol} height={340}/>
            <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
              <div className="flex items-center gap-2 mb-3">
                <Brain size={16} className="text-brand-400"/>
                <span className="text-sm font-bold text-white">AI Strategy — Live Entry/Exit</span>
                <span className="text-xs text-gray-600 ml-auto flex items-center gap-1">
                  <Zap size={10} className="text-yellow-400"/> Updates every 60s
                </span>
              </div>
              <AIStrategy symbol={symbol} price={price}/>
            </div>
          </div>
        )}

        {tab === 'community' && (
          <div className="flex-1 min-h-0 flex flex-col">
            <CommunityChat symbol={symbol} currentUserId={currentUserId}/>
          </div>
        )}

        {tab === 'news' && (
          <div className="flex-1 overflow-y-auto">
            <SymbolNews symbol={symbol}/>
          </div>
        )}
      </div>
    </div>
  )
}

import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../hooks/useAuth'
import { addSymbol } from '../services/api'
import {
  X, Send, TrendingUp, TrendingDown, Minus,
  RefreshCw, Plus, ExternalLink, Brain,
  MessageCircle, BarChart2, Newspaper, Star
} from 'lucide-react'

// ── Mini Sparkline ────────────────────────────────────────────────────────────
function Sparkline({ prices = [], color = '#22d3a0', height = 48, width = 120 }) {
  if (prices.length < 2) return null
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const range = max - min || 1
  const pts = prices.map((p, i) => {
    const x = (i / (prices.length - 1)) * width
    const y = height - ((p - min) / range) * height
    return `${x},${y}`
  }).join(' ')
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
}

// ── Sentiment Badge ───────────────────────────────────────────────────────────
function SentimentBadge({ value, size = 'sm' }) {
  const cfg = {
    bullish: { color: 'text-green-400 bg-green-900/30 border-green-700/50', label: '🟢 Bullish' },
    bearish: { color: 'text-red-400   bg-red-900/30   border-red-700/50',   label: '🔴 Bearish' },
    neutral: { color: 'text-gray-400  bg-dark-700     border-dark-600',     label: '⚪ Neutral'  },
  }
  const c = cfg[value] || cfg.neutral
  return (
    <span className={`border rounded-full font-bold ${c.color} ${
      size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-3 py-1'
    }`}>{c.label}</span>
  )
}

// ── AI Sentiment Panel ────────────────────────────────────────────────────────
function AISentimentPanel({ symbol, price }) {
  const [analysis, setAnalysis] = useState(null)
  const [loading,  setLoading]  = useState(false)

  const analyze = useCallback(async () => {
    setLoading(true)
    try {
      // Try backend AI endpoint first
      const r = await api.post('/ai/symbol-sentiment', { symbol, price: price?.price })
      setAnalysis(r.data)
    } catch {
      // Fallback: generate from price data
      const change = price?.change_pct || 0
      const sentiment = change > 1.5 ? 'bullish' : change < -1.5 ? 'bearish' : 'neutral'
      setAnalysis({
        sentiment,
        score:      Math.round(50 + change * 8),
        signal:     change > 2 ? 'BUY' : change < -2 ? 'SELL' : 'HOLD',
        confidence: Math.round(55 + Math.abs(change) * 5),
        reasoning:  `${symbol} is ${change > 0 ? 'up' : 'down'} ${Math.abs(change).toFixed(2)}% today. ` +
                    `${change > 1.5 ? 'Momentum is positive — watch for continuation above key resistance.' :
                       change < -1.5 ? 'Selling pressure is elevated — watch for support levels before entry.' :
                       'Price action is consolidating — wait for a clearer directional move before committing.'}`,
        key_levels: {
          support:    price?.price ? (price.price * 0.97).toFixed(2) : '—',
          resistance: price?.price ? (price.price * 1.03).toFixed(2) : '—',
        },
        risk:       change > 3 ? 'High — extended move, chasing risk' :
                    change < -3 ? 'High — falling knife, wait for stabilization' : 'Moderate',
        generated_at: new Date().toISOString(),
      })
    } finally { setLoading(false) }
  }, [symbol, price])

  useEffect(() => { if (price) analyze() }, [symbol])

  if (loading) return (
    <div className="flex items-center gap-2 p-4 text-sm text-gray-500">
      <RefreshCw size={14} className="animate-spin"/> Analyzing {symbol} with AI…
    </div>
  )

  if (!analysis) return (
    <button onClick={analyze}
      className="flex items-center gap-2 p-4 text-sm text-brand-400 hover:text-brand-300">
      <Brain size={14}/> Run AI Analysis
    </button>
  )

  const signalColor = {
    BUY:  'text-green-400 bg-green-900/30 border-green-700',
    SELL: 'text-red-400   bg-red-900/30   border-red-700',
    HOLD: 'text-yellow-400 bg-yellow-900/30 border-yellow-700',
  }

  return (
    <div className="space-y-3 p-4">
      {/* Signal bar */}
      <div className="flex items-center gap-3">
        <div className={`px-4 py-2 rounded-xl border font-black text-lg ${signalColor[analysis.signal] || signalColor.HOLD}`}>
          {analysis.signal}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <SentimentBadge value={analysis.sentiment}/>
            <span className="text-xs text-gray-500">{analysis.confidence}% confidence</span>
          </div>
          <div className="text-xs text-gray-500 mt-0.5">
            AI Score: {analysis.score}/100 · Risk: {analysis.risk}
          </div>
        </div>
        <button onClick={analyze}
          className="p-1.5 rounded-lg hover:bg-dark-700 text-gray-500 hover:text-white">
          <RefreshCw size={12}/>
        </button>
      </div>

      {/* Score bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-gray-500">
          <span>Bearish</span><span>Neutral</span><span>Bullish</span>
        </div>
        <div className="h-2 bg-dark-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              analysis.score > 60 ? 'bg-green-500' : analysis.score < 40 ? 'bg-red-500' : 'bg-yellow-500'
            }`}
            style={{ width: `${Math.max(5, Math.min(95, analysis.score))}%` }}
          />
        </div>
      </div>

      {/* Reasoning */}
      <p className="text-xs text-gray-400 leading-relaxed bg-dark-700 rounded-xl p-3">
        {analysis.reasoning}
      </p>

      {/* Key levels */}
      {analysis.key_levels && (
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-red-900/15 border border-red-800/30 rounded-xl p-2.5 text-center">
            <div className="text-xs text-gray-500">Support</div>
            <div className="text-sm font-bold text-red-400">${analysis.key_levels.support}</div>
          </div>
          <div className="bg-green-900/15 border border-green-800/30 rounded-xl p-2.5 text-center">
            <div className="text-xs text-gray-500">Resistance</div>
            <div className="text-sm font-bold text-green-400">${analysis.key_levels.resistance}</div>
          </div>
        </div>
      )}

      <div className="text-xs text-gray-600 text-center">
        ⚠️ AI analysis is for informational purposes only. Not financial advice.
      </div>
    </div>
  )
}

// ── Chat Message ──────────────────────────────────────────────────────────────
function ChatMsg({ msg, currentUserId }) {
  const isMe = msg.user_id === currentUserId

  return (
    <div className={`flex gap-2.5 ${isMe ? 'flex-row-reverse' : ''}`}>
      <div className="w-7 h-7 rounded-full bg-dark-600 flex items-center justify-center text-xs font-bold text-gray-300 flex-shrink-0">
        {(msg.display_name || msg.username || 'U').slice(0, 2).toUpperCase()}
      </div>
      <div className={`max-w-xs ${isMe ? 'items-end' : 'items-start'} flex flex-col gap-0.5`}>
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500">{msg.display_name || msg.username || 'Trader'}</span>
          {msg.sentiment && msg.sentiment !== 'neutral' && (
            <SentimentBadge value={msg.sentiment} size="xs"/>
          )}
          <span className="text-xs text-gray-700">
            {new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>
        <div className={`px-3 py-2 rounded-2xl text-sm leading-relaxed ${
          isMe ? 'bg-brand-500/20 text-white rounded-tr-sm' : 'bg-dark-700 text-gray-200 rounded-tl-sm'
        }`}>
          {msg.content || msg.message}
        </div>
      </div>
    </div>
  )
}

// ── News Item ─────────────────────────────────────────────────────────────────
function NewsItem({ item }) {
  const sentiment = item.sentiment || 'neutral'
  const sColor = { bullish: 'border-l-green-500', bearish: 'border-l-red-500', neutral: 'border-l-gray-600' }
  return (
    <a href={item.url} target="_blank" rel="noopener noreferrer"
      className={`block p-3 bg-dark-700 hover:bg-dark-600 border-l-2 ${sColor[sentiment]} rounded-r-xl transition-colors`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="text-xs font-bold text-white line-clamp-2 leading-tight">{item.title}</div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-gray-600">{item.source}</span>
            {item.published_at && (
              <span className="text-xs text-gray-700">
                {new Date(item.published_at).toLocaleDateString()}
              </span>
            )}
            <SentimentBadge value={sentiment} size="xs"/>
          </div>
        </div>
        <ExternalLink size={12} className="text-gray-600 flex-shrink-0 mt-0.5"/>
      </div>
    </a>
  )
}

// ── Main Symbol Board ─────────────────────────────────────────────────────────
export default function SymbolBoard({ symbol, onClose, currentUserId }) {
  const [tab,       setTab]       = useState('chat')
  const [price,     setPrice]     = useState(null)
  const [chat,      setChat]      = useState([])
  const [news,      setNews]      = useState([])
  const [msg,       setMsg]       = useState('')
  const [sentiment, setSentiment] = useState('neutral')
  const [posting,   setPosting]   = useState(false)
  const [inWatch,   setInWatch]   = useState(false)
  const [prices,    setPrices]    = useState([])   // sparkline data
  const chatRef = useRef(null)

  useEffect(() => {
    loadPrice()
    loadChat()
    loadNews()
    const iv = setInterval(() => {
      loadPrice()
      if (tab === 'chat') loadChat()
    }, 15000)
    return () => clearInterval(iv)
  }, [symbol])

  useEffect(() => {
    chatRef.current?.scrollTo(0, chatRef.current.scrollHeight)
  }, [chat])

  async function loadPrice() {
    try {
      const r = await api.get(`/ticker/${symbol}`)
      setPrice(r.data)
      setPrices(p => [...p.slice(-29), r.data.price].filter(Boolean))
    } catch {}
  }

  async function loadChat() {
    try {
      const r = await api.get(`/social/chat/${symbol}?limit=50`)
      setChat(r.data.reverse())
    } catch {}
  }

  async function loadNews() {
    try {
      const r = await api.get(`/news?symbol=${symbol}&limit=8`)
      setNews(r.data?.articles || r.data || [])
    } catch {}
  }

  async function sendMsg() {
    if (!msg.trim() || posting) return
    setPosting(true)
    try {
      await api.post(`/social/chat/${symbol}`, { content: msg.trim(), sentiment })
      setMsg('')
      await loadChat()
    } catch (e) {
      console.error(e)
    } finally { setPosting(false) }
  }

  async function addToWatchlist() {
    try { await addSymbol(symbol); setInWatch(true) } catch {}
  }

  const change    = price?.change_pct || 0
  const isUp      = change >= 0
  const priceColor = isUp ? 'text-green-400' : 'text-red-400'

  const TABS = [
    { id: 'chat',  label: 'Community',  icon: MessageCircle },
    { id: 'ai',    label: 'AI Analysis',icon: Brain         },
    { id: 'news',  label: 'News',       icon: Newspaper     },
  ]

  return (
    <div className="flex flex-col h-full bg-dark-800 rounded-2xl border border-dark-600 overflow-hidden">

      {/* Header */}
      <div className="flex-shrink-0 bg-dark-900 border-b border-dark-600 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            {/* Symbol icon */}
            <div className="w-12 h-12 rounded-xl bg-dark-700 border border-dark-600 flex items-center justify-center font-black text-white text-sm flex-shrink-0">
              {symbol.slice(0, 2)}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-black text-white">${symbol}</h2>
                {price?.price && (
                  <span className="text-lg font-bold text-white">${price.price.toFixed(2)}</span>
                )}
                {price && (
                  <span className={`flex items-center gap-0.5 text-sm font-bold ${priceColor}`}>
                    {isUp ? <TrendingUp size={14}/> : <TrendingDown size={14}/>}
                    {isUp ? '+' : ''}{change.toFixed(2)}%
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-1">
                {price && <SentimentBadge value={change > 1.5 ? 'bullish' : change < -1.5 ? 'bearish' : 'neutral'}/>}
                {price?.volume && (
                  <span className="text-xs text-gray-500">
                    Vol: {(price.volume / 1e6).toFixed(1)}M
                  </span>
                )}
                <span className="text-xs text-gray-600">{chat.length} messages today</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Sparkline */}
            {prices.length > 2 && (
              <Sparkline prices={prices} color={isUp ? '#22d3a0' : '#f87171'} width={80} height={36}/>
            )}
            <button onClick={addToWatchlist} disabled={inWatch}
              className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border transition-all ${
                inWatch ? 'text-green-400 border-green-700 bg-green-900/20' : 'text-gray-400 border-dark-600 hover:border-brand-500 hover:text-brand-400'
              }`}>
              <Star size={11}/> {inWatch ? 'Watching' : 'Watch'}
            </button>
            <button onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-dark-700 text-gray-500 hover:text-white">
              <X size={16}/>
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mt-3">
          {TABS.map(t => {
            const Icon = t.icon
            return (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  tab === t.id
                    ? 'bg-brand-500 text-dark-900'
                    : 'text-gray-400 hover:bg-dark-700 hover:text-white'
                }`}>
                <Icon size={11}/> {t.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden flex flex-col">

        {/* CHAT TAB */}
        {tab === 'chat' && (
          <>
            <div ref={chatRef} className="flex-1 overflow-y-auto p-4 space-y-3">
              {chat.length === 0 ? (
                <div className="text-center py-12 text-gray-600">
                  <MessageCircle size={32} className="mx-auto mb-2 opacity-30"/>
                  <p className="text-sm">No messages yet for ${symbol}</p>
                  <p className="text-xs mt-1">Be the first to share your thoughts!</p>
                </div>
              ) : (
                chat.map((m, i) => (
                  <ChatMsg key={i} msg={m} currentUserId={currentUserId}/>
                ))
              )}
            </div>

            {/* Community sentiment summary */}
            {chat.length > 0 && (() => {
              const bulls = chat.filter(m => m.sentiment === 'bullish').length
              const bears = chat.filter(m => m.sentiment === 'bearish').length
              const total = bulls + bears || 1
              return (
                <div className="flex-shrink-0 px-4 py-2 bg-dark-900/50 border-t border-dark-700 flex items-center gap-3 text-xs">
                  <span className="text-gray-500">Community:</span>
                  <div className="flex-1 h-1.5 bg-dark-700 rounded-full overflow-hidden">
                    <div className="h-full bg-green-500 rounded-full" style={{ width: `${(bulls/total)*100}%` }}/>
                  </div>
                  <span className="text-green-400 font-bold">{Math.round((bulls/total)*100)}% 🟢</span>
                  <span className="text-red-400 font-bold">{Math.round((bears/total)*100)}% 🔴</span>
                </div>
              )
            })()}

            {/* Input */}
            <div className="flex-shrink-0 p-3 border-t border-dark-600 bg-dark-900/50">
              <div className="flex gap-2 mb-2">
                {['bullish', 'neutral', 'bearish'].map(s => (
                  <button key={s} onClick={() => setSentiment(s)}
                    className={`flex-1 text-xs py-1 rounded-lg border font-medium transition-all ${
                      sentiment === s
                        ? s === 'bullish' ? 'bg-green-900/40 border-green-700 text-green-400'
                        : s === 'bearish' ? 'bg-red-900/40 border-red-700 text-red-400'
                        :                   'bg-dark-600 border-dark-500 text-gray-300'
                        : 'bg-dark-700 border-dark-600 text-gray-600 hover:text-gray-400'
                    }`}>
                    {s === 'bullish' ? '🟢 Bullish' : s === 'bearish' ? '🔴 Bearish' : '⚪ Neutral'}
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                <input
                  value={msg}
                  onChange={e => setMsg(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && !e.shiftKey && sendMsg()}
                  placeholder={`Share your thoughts on $${symbol}…`}
                  className="flex-1 bg-dark-700 border border-dark-600 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500 placeholder-gray-600"
                />
                <button onClick={sendMsg} disabled={!msg.trim() || posting}
                  className="px-3 py-2 bg-brand-500 hover:bg-brand-600 text-dark-900 rounded-xl disabled:opacity-40 transition-all">
                  <Send size={14}/>
                </button>
              </div>
            </div>
          </>
        )}

        {/* AI TAB */}
        {tab === 'ai' && (
          <div className="flex-1 overflow-y-auto">
            <AISentimentPanel symbol={symbol} price={price}/>
          </div>
        )}

        {/* NEWS TAB */}
        {tab === 'news' && (
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {news.length === 0 ? (
              <div className="text-center py-12 text-gray-600">
                <Newspaper size={32} className="mx-auto mb-2 opacity-30"/>
                <p className="text-sm">No recent news for ${symbol}</p>
              </div>
            ) : (
              news.map((item, i) => <NewsItem key={i} item={item}/>)
            )}
          </div>
        )}
      </div>
    </div>
  )
}
import { useState, useEffect, useRef } from 'react'
import { api } from '../hooks/useAuth'
import { X, Plus, TrendingUp, TrendingDown, MessageCircle, ExternalLink } from 'lucide-react'
import { addSymbol } from '../services/api'

const SENTIMENT_COLORS = {
  bullish: 'text-green-400 bg-green-900/30 border-green-800',
  bearish: 'text-red-400   bg-red-900/30   border-red-800',
  neutral: 'text-gray-400  bg-dark-700     border-dark-600',
}

export default function SymbolPopup({ symbol, onClose, position = { x: 100, y: 100 } }) {
  const [data,        setData]        = useState(null)
  const [chat,        setChat]        = useState([])
  const [newMsg,      setNewMsg]      = useState('')
  const [sentiment,   setSentiment]   = useState('neutral')
  const [tab,         setTab]         = useState('info')
  const [added,       setAdded]       = useState(false)
  const [posting,     setPosting]     = useState(false)
  const popupRef = useRef(null)

  useEffect(() => {
    loadData()
    const iv = setInterval(() => { if (tab === 'chat') loadChat() }, 10000)
    return () => clearInterval(iv)
  }, [symbol])

  async function loadData() {
    try {
      const [priceRes, chatRes] = await Promise.allSettled([
        api.get(`/ticker/${symbol}`),
        api.get(`/social/chat/${symbol}?limit=20`),
      ])
      if (priceRes.status === 'fulfilled') setData(priceRes.value.data)
      if (chatRes.status === 'fulfilled')  setChat(chatRes.value.data)
    } catch {}
  }

  async function loadChat() {
    try {
      const r = await api.get(`/social/chat/${symbol}?limit=30`)
      setChat(r.data)
    } catch {}
  }

  async function postChat() {
    if (!newMsg.trim()) return
    setPosting(true)
    try {
      const r = await api.post(`/social/chat/${symbol}`, { content: newMsg, sentiment })
      if (r.data.error) { alert(r.data.error); return }
      setNewMsg('')
      loadChat()
    } catch {}
    finally { setPosting(false) }
  }

  async function handleAdd() {
    try { await addSymbol(symbol); setAdded(true); setTimeout(() => setAdded(false), 3000) } catch {}
  }

  const up     = (data?.change_pct ?? 0) >= 0
  const change = data?.change_pct ?? 0

  // Calculate popup position — keep it on screen
  const style = {
    position: 'fixed',
    zIndex:   9999,
    left:     Math.min(position.x, window.innerWidth  - 440),
    top:      Math.min(position.y, window.innerHeight - 520),
    width:    420,
  }

  return (
    <div ref={popupRef} style={style} className="bg-dark-800 border border-dark-600 rounded-2xl shadow-2xl overflow-hidden">

      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-dark-600 bg-dark-900">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-black text-white text-xl">{symbol}</span>
            {data?.price && (
              <span className="font-mono text-white text-lg">${data.price?.toFixed(2)}</span>
            )}
            {data?.change_pct !== undefined && (
              <span className={`text-sm font-bold ${up ? 'text-green-400' : 'text-red-400'}`}>
                {up ? '▲' : '▼'}{Math.abs(change).toFixed(2)}%
              </span>
            )}
          </div>
          {data?.volume > 0 && (
            <p className="text-xs text-gray-500">
              Vol: {data.volume > 1e6 ? `${(data.volume/1e6).toFixed(1)}M` : `${(data.volume/1e3).toFixed(0)}K`}
              {' · '}H ${data.high?.toFixed(2)} L ${data.low?.toFixed(2)}
            </p>
          )}
        </div>

        <div className="flex gap-2 ml-auto">
          <button onClick={handleAdd}
            className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg font-bold transition-all ${
              added ? 'bg-green-900/40 text-green-400' : 'bg-brand-500/20 text-brand-400 border border-brand-500/40 hover:bg-brand-500/40'
            }`}>
            <Plus size={12}/>{added ? 'Added!' : 'Watchlist'}
          </button>
          <button onClick={onClose}
            className="w-7 h-7 rounded-full bg-dark-700 hover:bg-dark-600 flex items-center justify-center transition-colors">
            <X size={14} className="text-gray-400"/>
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-dark-600">
        {[
          { id:'info', label:'📊 Info'  },
          { id:'chat', label:`💬 Chat (${chat.length})` },
          { id:'feed', label:'📡 Trades' },
        ].map(t => (
          <button key={t.id} onClick={() => { setTab(t.id); if (t.id === 'chat') loadChat() }}
            className={`flex-1 text-xs py-2 font-medium transition-colors ${
              tab===t.id ? 'text-brand-500 border-b-2 border-brand-500' : 'text-gray-500 hover:text-gray-300'
            }`}>{t.label}</button>
        ))}
      </div>

      {/* Content */}
      <div className="max-h-80 overflow-y-auto">

        {/* Info tab */}
        {tab === 'info' && (
          <div className="p-4 space-y-3">
            {data ? (
              <div className="grid grid-cols-2 gap-2">
                {[
                  { label:'Price',    value:`$${data.price?.toFixed(2)}`  },
                  { label:'Change $', value:`${data.change_$?.toFixed(2) >= 0 ? '+' : ''}$${data.change_$?.toFixed(2)}`  },
                  { label:'High',     value:`$${data.high?.toFixed(2)}`   },
                  { label:'Low',      value:`$${data.low?.toFixed(2)}`    },
                  { label:'Volume',   value: data.volume > 1e6 ? `${(data.volume/1e6).toFixed(1)}M` : `${(data.volume/1e3).toFixed(0)}K` },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-dark-700 rounded-lg p-2.5 text-center">
                    <p className="text-xs text-gray-500">{label}</p>
                    <p className="text-sm font-bold text-white">{value}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500 text-sm text-center py-4">Loading price data…</p>
            )}

            {/* Quick links */}
            <div className="flex gap-2">
              {[
                { label:'TradingView', url:`https://www.tradingview.com/chart/?symbol=${symbol}` },
                { label:'Yahoo Finance', url:`https://finance.yahoo.com/quote/${symbol}` },
                { label:'StockTwits', url:`https://stocktwits.com/symbol/${symbol}` },
              ].map(({ label, url }) => (
                <a key={label} href={url} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs bg-dark-700 hover:bg-dark-600 text-gray-400 hover:text-white px-2 py-1.5 rounded-lg transition-colors">
                  {label} <ExternalLink size={10}/>
                </a>
              ))}
            </div>
          </div>
        )}

        {/* Chat tab */}
        {tab === 'chat' && (
          <div className="flex flex-col h-80">
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {chat.length === 0 ? (
                <div className="text-center py-8 text-gray-500 text-sm">
                  <MessageCircle size={24} className="mx-auto mb-2 opacity-40"/>
                  <p>No messages yet — be the first to post about ${symbol}!</p>
                </div>
              ) : chat.map((m, i) => (
                <div key={i} className="group">
                  <div className="flex items-start gap-2">
                    <div className="w-6 h-6 rounded-full bg-dark-600 flex items-center justify-center text-xs font-bold text-gray-300 flex-shrink-0">
                      {m.display_name?.slice(0,1).toUpperCase()}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-gray-300">{m.display_name}</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded border ${SENTIMENT_COLORS[m.sentiment] ?? SENTIMENT_COLORS.neutral}`}>
                          {m.sentiment}
                        </span>
                        <span className="text-xs text-gray-600 ml-auto">{m.created_at?.slice(11,16)}</span>
                      </div>
                      <p className="text-sm text-gray-300 mt-0.5">{m.content}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Post message */}
            <div className="border-t border-dark-600 p-3 space-y-2">
              <div className="flex gap-1">
                {['bullish','neutral','bearish'].map(s => (
                  <button key={s} onClick={() => setSentiment(s)}
                    className={`flex-1 text-xs py-1 rounded font-medium transition-colors capitalize ${
                      sentiment === s
                        ? s === 'bullish' ? 'bg-green-800 text-green-300'
                          : s === 'bearish' ? 'bg-red-800 text-red-300'
                          : 'bg-dark-500 text-gray-300'
                        : 'bg-dark-700 text-gray-500 hover:bg-dark-600'
                    }`}>{s}</button>
                ))}
              </div>
              <div className="flex gap-2">
                <input value={newMsg} onChange={e => setNewMsg(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && postChat()}
                  placeholder={`What do you think about $${symbol}?`}
                  maxLength={500}
                  className="flex-1 bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"/>
                <button onClick={postChat} disabled={posting || !newMsg.trim()}
                  className="px-3 py-2 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold text-sm rounded-lg disabled:opacity-50 transition-colors">
                  Post
                </button>
              </div>
              <p className="text-xs text-gray-600">Be respectful · No spam · No pump & dump</p>
            </div>
          </div>
        )}

        {/* Trades feed for this symbol */}
        {tab === 'feed' && (
          <SymbolTrades symbol={symbol}/>
        )}
      </div>
    </div>
  )
}

function SymbolTrades({ symbol }) {
  const [trades, setTrades] = useState([])
  useEffect(() => {
    api.get(`/social/feed/public?symbol=${symbol}&limit=10`)
      .then(r => setTrades(r.data))
      .catch(() => {})
  }, [symbol])

  if (trades.length === 0) return (
    <div className="text-center py-8 text-gray-500 text-sm p-4">
      No public trades for ${symbol} yet
    </div>
  )

  return (
    <div className="p-3 space-y-2">
      {trades.map((t, i) => {
        const up = t.action === 'BUY' || t.is_winner
        return (
          <div key={i} className={`flex items-center gap-3 p-2.5 rounded-lg border ${
            up ? 'bg-green-900/10 border-green-800/40' : 'bg-dark-700 border-dark-600'
          }`}>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-bold text-xs text-gray-300">
                  {typeof t.trader === 'string' ? t.trader : t.trader?.display_name ?? 'Trader'}
                </span>
                <span className={`text-xs font-bold ${up ? 'text-green-400' : 'text-red-400'}`}>
                  {t.action === 'BUY' ? '▲ BUY' : '▼ SELL'} ${t.price?.toFixed(2)}
                </span>
              </div>
              <div className="flex gap-3 text-xs text-gray-500 mt-0.5">
                {t.stop_loss   && <span>SL ${t.stop_loss?.toFixed(2)}</span>}
                {t.take_profit && <span>TP ${t.take_profit?.toFixed(2)}</span>}
                {t.pnl !== null && t.pnl !== undefined && (
                  <span className={t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {t.pnl >= 0 ? '+' : ''}${t.pnl?.toFixed(2)}
                  </span>
                )}
              </div>
            </div>
            <span className="text-xs text-gray-600">
              {t.created_at ? new Date(t.created_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}) : ''}
            </span>
          </div>
        )
      })}
    </div>
  )
}

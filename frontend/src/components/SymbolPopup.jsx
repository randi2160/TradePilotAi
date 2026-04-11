import { useState, useEffect, useRef } from 'react'
import { api } from '../hooks/useAuth'
import { X, Plus, ExternalLink, TrendingUp, TrendingDown, Send, MessageCircle } from 'lucide-react'
import { addSymbol } from '../services/api'

const SENTIMENT_BTN = {
  bullish: 'bg-green-800 text-green-300',
  neutral: 'bg-dark-600 text-gray-300',
  bearish: 'bg-red-800 text-red-300',
}

export default function SymbolPopup({ symbol, position, onClose }) {
  const [price,     setPrice]     = useState(null)
  const [chat,      setChat]      = useState([])
  const [feed,      setFeed]      = useState([])
  const [tab,       setTab]       = useState('info')
  const [msg,       setMsg]       = useState('')
  const [sentiment, setSentiment] = useState('neutral')
  const [posting,   setPosting]   = useState(false)
  const [added,     setAdded]     = useState(false)
  const chatRef = useRef(null)

  useEffect(() => {
    loadPrice()
    loadChat()
    loadFeed()
    const iv = setInterval(() => { loadPrice(); if (tab === 'chat') loadChat() }, 10000)
    return () => clearInterval(iv)
  }, [symbol])

  useEffect(() => {
    chatRef.current?.scrollTo(0, chatRef.current.scrollHeight)
  }, [chat])

  async function loadPrice() {
    try { const r = await api.get(`/ticker/${symbol}`); setPrice(r.data) } catch {}
  }

  async function loadChat() {
    try { const r = await api.get(`/social/chat/${symbol}?limit=30`); setChat(r.data.reverse()) } catch {}
  }

  async function loadFeed() {
    try { const r = await api.get(`/social/feed/public?symbol=${symbol}&limit=8`); setFeed(r.data) } catch {}
  }

  async function postChat() {
    if (!msg.trim()) return
    setPosting(true)
    try {
      const r = await api.post(`/social/chat/${symbol}`, { content: msg, sentiment })
      if (r.data?.error) {
        alert(`Blocked: ${r.data.error}`)
        return
      }
      if (r.data?.warning) {
        alert(`⚠️ Warning: ${r.data.warning}`)
      }
      setMsg('')
      await loadChat()
    } catch(e) {
      const detail = e.response?.data?.detail ?? e.message
      alert(`Could not post: ${detail}`)
    } finally { setPosting(false) }
  }

  async function handleAdd() {
    try { await addSymbol(symbol); setAdded(true); setTimeout(() => setAdded(false), 3000) } catch {}
  }

  const up      = (price?.change_pct ?? 0) >= 0
  const popupX  = Math.min(position?.x ?? 0, window.innerWidth  - 420)
  const popupY  = Math.min((position?.y ?? 0) + 10, window.innerHeight - 500)

  return (
    <div style={{ position:'fixed', left:popupX, top:popupY, width:400, zIndex:9999 }}
      className="bg-dark-800 border border-dark-600 rounded-2xl shadow-2xl overflow-hidden">

      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 bg-dark-900 border-b border-dark-700">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="font-black text-white text-xl">{symbol}</span>
            {price?.price && (
              <span className="font-mono text-white text-lg">${price.price.toFixed(2)}</span>
            )}
            {price?.change_pct !== undefined && (
              <span className={`text-sm font-bold flex items-center gap-0.5 ${up ? 'text-green-400' : 'text-red-400'}`}>
                {up ? <TrendingUp size={14}/> : <TrendingDown size={14}/>}
                {up ? '+' : ''}{price.change_pct.toFixed(2)}%
              </span>
            )}
          </div>
          {price?.volume > 0 && (
            <p className="text-xs text-gray-500 mt-0.5">
              Vol: {price.volume > 1e6 ? `${(price.volume/1e6).toFixed(1)}M` : `${(price.volume/1e3).toFixed(0)}K`}
              {' · '}H ${price.high?.toFixed(2)} · L ${price.low?.toFixed(2)}
            </p>
          )}
        </div>
        <button onClick={handleAdd}
          className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg font-bold transition-all ${
            added ? 'bg-green-900/40 text-green-400' : 'bg-brand-500/20 text-brand-400 border border-brand-500/30 hover:bg-brand-500/30'
          }`}>
          <Plus size={12}/>{added ? '✓ Added' : 'Watch'}
        </button>
        <button onClick={onClose} className="w-7 h-7 rounded-full bg-dark-700 hover:bg-dark-600 flex items-center justify-center">
          <X size={14} className="text-gray-400"/>
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-dark-700">
        {[
          { id:'info',  label:'📊 Info'               },
          { id:'chat',  label:`💬 Chat (${chat.length})`},
          { id:'trades',label:`📡 Trades (${feed.length})`},
        ].map(t => (
          <button key={t.id} onClick={() => { setTab(t.id); if (t.id==='chat') loadChat() }}
            className={`flex-1 text-xs py-2.5 font-medium transition-colors ${
              tab===t.id ? 'text-brand-500 border-b-2 border-brand-500 bg-dark-700/30' : 'text-gray-500 hover:text-gray-300'
            }`}>{t.label}</button>
        ))}
      </div>

      {/* Content */}
      <div className="max-h-72 overflow-hidden">

        {/* Info */}
        {tab === 'info' && (
          <div className="p-4 space-y-3">
            {price ? (
              <div className="grid grid-cols-2 gap-2">
                {[
                  { label:'Price',    value:`$${price.price?.toFixed(2)}`                                           },
                  { label:'Change',   value:`${price.change_$ >= 0 ? '+' : ''}$${price.change_$?.toFixed(2)}`,
                    color: price.change_$ >= 0 ? 'text-green-400' : 'text-red-400'                                  },
                  { label:'Day High', value:`$${price.high?.toFixed(2)}`                                            },
                  { label:'Day Low',  value:`$${price.low?.toFixed(2)}`                                             },
                  { label:'Volume',   value: price.volume > 1e6 ? `${(price.volume/1e6).toFixed(1)}M` : `${(price.volume/1e3).toFixed(0)}K` },
                  { label:'Change %', value:`${price.change_pct >= 0 ? '+' : ''}${price.change_pct?.toFixed(2)}%`,
                    color: price.change_pct >= 0 ? 'text-green-400' : 'text-red-400'                                },
                ].map(({ label, value, color }) => (
                  <div key={label} className="bg-dark-700 rounded-xl p-2.5 text-center">
                    <p className="text-xs text-gray-500 mb-0.5">{label}</p>
                    <p className={`text-sm font-bold ${color ?? 'text-white'}`}>{value}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500 text-sm text-center py-4">Loading price data…</p>
            )}

            {/* Quick links */}
            <div className="grid grid-cols-3 gap-2">
              {[
                { label:'TradingView', url:`https://www.tradingview.com/chart/?symbol=${symbol}` },
                { label:'Yahoo',       url:`https://finance.yahoo.com/quote/${symbol}`           },
                { label:'StockTwits',  url:`https://stocktwits.com/symbol/${symbol}`             },
              ].map(({ label, url }) => (
                <a key={label} href={url} target="_blank" rel="noopener noreferrer"
                  className="flex items-center justify-center gap-1 text-xs bg-dark-700 hover:bg-dark-600 text-gray-400 hover:text-white py-2 rounded-xl transition-colors">
                  {label}<ExternalLink size={10}/>
                </a>
              ))}
            </div>
          </div>
        )}

        {/* Chat */}
        {tab === 'chat' && (
          <div className="flex flex-col h-72">
            <div ref={chatRef} className="flex-1 overflow-y-auto p-3 space-y-2">
              {chat.length === 0 && (
                <div className="text-center py-8 text-gray-500 text-sm">
                  <MessageCircle size={24} className="mx-auto mb-2 opacity-40"/>
                  <p>No messages yet — be the first!</p>
                </div>
              )}
              {chat.map((m, i) => (
                <div key={i} className="flex gap-2">
                  <div className="w-6 h-6 rounded-full bg-dark-600 flex items-center justify-center text-xs font-bold text-gray-300 flex-shrink-0">
                    {(m.display_name ?? 'U').slice(0,1).toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-gray-300">{m.display_name}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded capitalize ${
                        m.sentiment === 'bullish' ? 'bg-green-900/40 text-green-400' :
                        m.sentiment === 'bearish' ? 'bg-red-900/40 text-red-400' :
                        'bg-dark-600 text-gray-400'
                      }`}>{m.sentiment}</span>
                      <span className="text-xs text-gray-600 ml-auto">{m.created_at?.slice(11,16)}</span>
                    </div>
                    <p className="text-sm text-gray-300 mt-0.5 break-words">{m.content}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Post */}
            <div className="border-t border-dark-700 p-3 space-y-2">
              <div className="flex gap-1">
                {['bullish','neutral','bearish'].map(s => (
                  <button key={s} onClick={() => setSentiment(s)}
                    className={`flex-1 text-xs py-1 rounded font-medium capitalize transition-colors ${
                      sentiment === s ? SENTIMENT_BTN[s] : 'bg-dark-700 text-gray-500 hover:bg-dark-600'
                    }`}>{s}</button>
                ))}
              </div>
              <div className="flex gap-2">
                <input value={msg} onChange={e => setMsg(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && postChat()}
                  placeholder={`Your thoughts on $${symbol}…`} maxLength={500}
                  className="flex-1 bg-dark-700 border border-dark-600 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"/>
                <button onClick={postChat} disabled={posting || !msg.trim()}
                  className="px-3 bg-brand-500 hover:bg-brand-600 text-dark-900 rounded-xl disabled:opacity-50 transition-colors">
                  <Send size={14}/>
                </button>
              </div>
              <p className="text-xs text-gray-600 text-center">Be respectful · No spam · No pump & dump</p>
            </div>
          </div>
        )}

        {/* Recent trades */}
        {tab === 'trades' && (
          <div className="p-3 space-y-2 overflow-y-auto max-h-72">
            {feed.length === 0 ? (
              <div className="text-center py-8 text-gray-500 text-sm">No public trades for ${symbol} yet</div>
            ) : feed.map((t, i) => {
              const isBuy = t.action === 'BUY'
              return (
                <div key={i} className={`flex items-center gap-3 p-2.5 rounded-xl border ${
                  isBuy ? 'bg-green-900/10 border-green-800/40' : 'bg-dark-700 border-dark-600'
                }`}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-gray-300">
                        {typeof t.trader === 'string' ? t.trader : t.trader?.display_name ?? 'Trader'}
                      </span>
                      <span className={`text-xs font-bold ${isBuy ? 'text-green-400' : 'text-red-400'}`}>
                        {isBuy ? '▲ BUY' : '▼ SELL'} @ ${t.price?.toFixed(2)}
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
                  <span className="text-xs text-gray-600 flex-shrink-0">
                    {t.created_at ? new Date(t.created_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}) : ''}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

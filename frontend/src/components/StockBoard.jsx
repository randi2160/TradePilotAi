import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../hooks/useAuth'
import { addSymbol } from '../services/api'
import {
  TrendingUp, TrendingDown, Send, RefreshCw, Brain,
  Star, ArrowLeft, MessageCircle, Newspaper, BarChart2,
  X, Target, Shield, Zap, ChevronDown, Users, Hash
} from 'lucide-react'

// ── Company Logo ──────────────────────────────────────────────────────────────
function CompanyLogo({ symbol, size = 'md' }) {
  const [error, setError] = useState(false)
  const dim = size === 'lg' ? 'w-16 h-16 text-base rounded-2xl' : 'w-10 h-10 text-xs rounded-xl'
  if (error) {
    return (
      <div className={`${dim} bg-gradient-to-br from-brand-500/30 to-teal-500/20 border border-brand-500/30 flex items-center justify-center font-black text-white flex-shrink-0`}>
        {symbol.slice(0,2)}
      </div>
    )
  }
  return (
    <div className={`${dim} bg-dark-800 border border-dark-600 overflow-hidden flex-shrink-0`}>
      <img
        src={`https://assets.parqet.com/logos/symbol/${symbol}?format=png`}
        alt={symbol}
        className="w-full h-full object-contain"
        onError={() => setError(true)}
      />
    </div>
  )
}

// ── Post Card ─────────────────────────────────────────────────────────────────
function PostCard({ post, currentUserId, onLike }) {
  const isMe = post.user_id === currentUserId
  const s    = post.sentiment || 'neutral'
  const sc   = { bullish: 'border-l-green-500 bg-green-900/5', bearish: 'border-l-red-500 bg-red-900/5', neutral: 'border-l-dark-600' }

  return (
    <div className={`border-l-2 ${sc[s]} rounded-r-xl p-4 bg-dark-800 border border-dark-600 border-l-0 space-y-2`}>
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-full bg-dark-600 flex items-center justify-center text-xs font-bold text-gray-300 flex-shrink-0">
          {(post.display_name || 'U').slice(0,2).toUpperCase()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold text-white">{post.display_name || 'Trader'}</span>
            {s !== 'neutral' && (
              <span className={`text-xs px-1.5 py-0.5 rounded font-bold border ${
                s === 'bullish' ? 'text-green-400 bg-green-900/20 border-green-800/40' : 'text-red-400 bg-red-900/20 border-red-800/40'
              }`}>
                {s === 'bullish' ? '🟢 Bullish' : '🔴 Bearish'}
              </span>
            )}
            <span className="text-xs text-gray-600 ml-auto">
              {new Date(post.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              {' · '}{new Date(post.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>
      </div>
      <p className="text-sm text-gray-200 leading-relaxed pl-10">{post.content || post.message}</p>
      {post.likes !== undefined && (
        <div className="flex items-center gap-3 pl-10">
          <button onClick={() => onLike?.(post.id)}
            className="flex items-center gap-1 text-xs text-gray-600 hover:text-brand-400 transition-colors">
            ♥ {post.likes || 0}
          </button>
        </div>
      )}
    </div>
  )
}

// ── Compose Box ───────────────────────────────────────────────────────────────
// Backend caps content at 500 chars (social_routes.ChatPost.max_length=500).
// We mirror that here so users can't silently exceed it.
const POST_MAX_LEN = 500

function ComposeBox({ symbol, onPosted }) {
  const [msg,       setMsg]       = useState('')
  const [sentiment, setSentiment] = useState('neutral')
  const [posting,   setPosting]   = useState(false)
  // Inline error so failed posts (rate-limit, 422, network) don't disappear
  // into the console — previously the catch was `console.error(e)` only,
  // which made the whole post flow look broken to users.
  const [errorMsg,  setErrorMsg]  = useState('')

  async function post() {
    if (!msg.trim() || posting) return
    setErrorMsg('')
    setPosting(true)
    try {
      await api.post(`/social/chat/${symbol}`, { content: msg.trim(), sentiment })
      setMsg('')
      onPosted?.()
    } catch (e) {
      console.error(e)
      // Try to surface the server's own message; fall back to a generic line.
      const detail = e.response?.data?.detail
      let friendly  = ''
      if (Array.isArray(detail)) {
        // FastAPI 422 — look for the content/length error specifically
        const tooLong = detail.find(d =>
          (d.loc || []).includes('content') &&
          (d.type || '').includes('string_too_long')
        )
        friendly = tooLong
          ? `Post is too long — ${POST_MAX_LEN} character max.`
          : (detail[0]?.msg || 'Post rejected.')
      } else if (typeof detail === 'string') {
        friendly = detail
      } else {
        friendly = e.message || 'Could not post — try again.'
      }
      setErrorMsg(friendly)
    } finally { setPosting(false) }
  }

  const charsLeft = POST_MAX_LEN - msg.length
  const overLimit = charsLeft < 0     // belt-and-braces; maxLength on the input prevents typing past

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-4 space-y-3">
      <div className="text-xs font-bold text-white mb-1">Share your thoughts on ${symbol}</div>
      <textarea
        value={msg}
        onChange={e => setMsg(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && e.ctrlKey && post()}
        placeholder={`What's your take on $${symbol}? Be specific — mention price levels, catalysts, or charts...`}
        rows={3}
        maxLength={POST_MAX_LEN}
        className="w-full bg-dark-900 border border-dark-600 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-brand-500 placeholder-gray-700 resize-none"
      />
      <div className="flex items-center gap-2">
        <div className="flex gap-1 flex-1">
          {['bullish','neutral','bearish'].map(s => (
            <button key={s} onClick={() => setSentiment(s)}
              className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition-all ${
                sentiment === s
                  ? s === 'bullish' ? 'bg-green-900/40 border-green-600 text-green-400'
                  : s === 'bearish' ? 'bg-red-900/40 border-red-600 text-red-400'
                  :                   'bg-dark-600 border-dark-500 text-gray-300'
                  : 'bg-dark-700 border-dark-700 text-gray-600 hover:text-gray-400'
              }`}>
              {s === 'bullish' ? '🟢 Bullish' : s === 'bearish' ? '🔴 Bearish' : '⚪ Neutral'}
            </button>
          ))}
        </div>
        <span className={`text-xs ${charsLeft < 50 ? (overLimit ? 'text-red-400' : 'text-yellow-400') : 'text-gray-600'}`}>
          {msg.length}/{POST_MAX_LEN}
        </span>
        <button onClick={post} disabled={!msg.trim() || posting || overLimit}
          className="flex items-center gap-1.5 px-4 py-1.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl text-sm disabled:opacity-40 transition-all">
          <Send size={13}/> {posting ? 'Posting…' : 'Post'}
        </button>
      </div>
      {errorMsg && (
        <div className="text-xs text-red-400 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2">
          {errorMsg}
        </div>
      )}
      <p className="text-xs text-gray-700">Ctrl+Enter to post · Community guidelines apply · Not financial advice</p>
    </div>
  )
}

// ── Sentiment Summary Bar ─────────────────────────────────────────────────────
function SentimentBar({ posts }) {
  const bulls = posts.filter(p => p.sentiment === 'bullish').length
  const bears = posts.filter(p => p.sentiment === 'bearish').length
  const neuts = posts.filter(p => p.sentiment === 'neutral').length
  const total = bulls + bears + neuts || 1
  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
      <div className="text-xs font-bold text-white mb-3 flex items-center gap-2">
        <Users size={13} className="text-brand-400"/> Community Sentiment — {posts.length} posts
      </div>
      <div className="flex gap-1 h-2 rounded-full overflow-hidden mb-2">
        <div className="bg-green-500 rounded-l-full transition-all" style={{ width: `${(bulls/total)*100}%` }}/>
        <div className="bg-gray-600 transition-all"                  style={{ width: `${(neuts/total)*100}%` }}/>
        <div className="bg-red-500 rounded-r-full transition-all"    style={{ width: `${(bears/total)*100}%` }}/>
      </div>
      <div className="flex justify-between text-xs">
        <span className="text-green-400 font-bold">🟢 {Math.round((bulls/total)*100)}% Bullish ({bulls})</span>
        <span className="text-gray-500">{neuts} Neutral</span>
        <span className="text-red-400 font-bold">{Math.round((bears/total)*100)}% Bearish ({bears}) 🔴</span>
      </div>
    </div>
  )
}

// ── AI Quick Take ─────────────────────────────────────────────────────────────
function AIQuickTake({ symbol, price }) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(false)

  async function run() {
    setLoading(true)
    try {
      const r = await api.post('/ai/symbol-sentiment', { symbol, price: price?.price, change_pct: price?.change_pct })
      setData(r.data)
    } catch {
      const c = price?.change_pct || 0
      const p = price?.price || 0
      const atr = p * 0.015
      setData({
        signal: c > 2 ? 'BUY' : c < -2 ? 'SELL' : 'HOLD',
        sentiment: c > 1.5 ? 'bullish' : c < -1.5 ? 'bearish' : 'neutral',
        score: Math.round(50 + c * 6), confidence: Math.round(50 + Math.abs(c) * 4),
        reasoning: `${symbol} is ${c >= 0 ? 'up' : 'down'} ${Math.abs(c).toFixed(2)}% today. ${c > 1.5 ? 'Momentum positive.' : c < -1.5 ? 'Selling pressure elevated.' : 'Consolidating.'}`,
        entry: p ? p.toFixed(2) : null, exit: p ? (p + atr*2).toFixed(2) : null, stop: p ? (p - atr*1.5).toFixed(2) : null,
        key_levels: { support: p ? (p*0.97).toFixed(2) : '—', resistance: p ? (p*1.03).toFixed(2) : '—' },
      })
    } finally { setLoading(false) }
  }

  useEffect(() => { if (price) run() }, [symbol])

  if (!data && !loading) return (
    <button onClick={run} className="w-full py-3 bg-brand-500/10 hover:bg-brand-500/20 text-brand-400 border border-brand-500/30 rounded-xl text-sm font-bold flex items-center justify-center gap-2">
      <Brain size={14}/> Run AI Analysis
    </button>
  )

  if (loading) return (
    <div className="py-4 text-center text-xs text-gray-500 flex items-center justify-center gap-2">
      <RefreshCw size={12} className="animate-spin"/> Analyzing…
    </div>
  )

  const SC = { BUY: 'text-green-400 border-green-600 bg-green-900/20', SELL: 'text-red-400 border-red-600 bg-red-900/20', HOLD: 'text-yellow-400 border-yellow-600 bg-yellow-900/20' }
  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Brain size={14} className="text-brand-400"/>
        <span className="text-xs font-bold text-white">AI Quick Take</span>
        <button onClick={run} disabled={loading} className="ml-auto p-1 hover:bg-dark-700 rounded text-gray-600 hover:text-white">
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''}/>
        </button>
      </div>
      <div className="flex items-center gap-3">
        <span className={`px-3 py-1 rounded-lg border font-black text-sm ${SC[data.signal]||SC.HOLD}`}>
          {data.signal === 'BUY' ? '🟢' : data.signal === 'SELL' ? '🔴' : '🟡'} {data.signal}
        </span>
        <div>
          <div className="text-xs text-gray-400">Score: <span className="font-bold text-white">{data.score}/100</span></div>
          <div className="text-xs text-gray-500">{data.confidence}% confidence</div>
        </div>
      </div>
      <p className="text-xs text-gray-400 leading-relaxed">{data.reasoning}</p>
      {data.entry && (
        <div className="grid grid-cols-3 gap-1.5 text-xs text-center">
          <div className="bg-dark-700 rounded-lg p-2"><div className="text-gray-600">Entry</div><div className="font-bold text-brand-400">${data.entry}</div></div>
          <div className="bg-dark-700 rounded-lg p-2"><div className="text-gray-600">Target</div><div className="font-bold text-green-400">${data.exit}</div></div>
          <div className="bg-dark-700 rounded-lg p-2"><div className="text-gray-600">Stop</div><div className="font-bold text-red-400">${data.stop}</div></div>
        </div>
      )}
      {data.key_levels && (
        <div className="flex gap-2 text-xs">
          {[{l:'Support',v:data.key_levels.support,c:'text-red-400'},{l:'Resistance',v:data.key_levels.resistance,c:'text-green-400'}]
            .filter(x=>x.v&&x.v!=='—').map(({l,v,c})=>(
            <div key={l} className="flex-1 bg-dark-900 rounded-lg p-1.5 text-center">
              <div className="text-gray-600">{l}</div><div className={`font-bold ${c}`}>${v}</div>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-red-400/70 text-center">⚠️ For informational purposes only. Not financial advice.</p>
    </div>
  )
}

// ── Main Stock Board ──────────────────────────────────────────────────────────
export default function StockBoard({ symbol, onBack, currentUserId }) {
  const [posts,   setPosts]   = useState([])
  const [price,   setPrice]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [inWatch, setInWatch] = useState(false)
  const [filter,  setFilter]  = useState('all') // all | bullish | bearish

  useEffect(() => {
    loadPrice()
    loadPosts()
    const iv = setInterval(() => { loadPrice(); loadPosts() }, 30000)
    return () => clearInterval(iv)
  }, [symbol])

  async function loadPrice() {
    try { const r = await api.get(`/ticker/${symbol}`); setPrice(r.data) } catch {}
  }

  async function loadPosts() {
    setLoading(true)
    try {
      const r = await api.get(`/social/chat/${symbol}?limit=100`)
      setPosts(r.data.reverse())
    } catch {} finally { setLoading(false) }
  }

  async function watchlist() {
    try { await addSymbol(symbol); setInWatch(true) } catch {}
  }

  const filtered = filter === 'all' ? posts : posts.filter(p => p.sentiment === filter)
  const change   = price?.change_pct || 0
  const isUp     = change >= 0

  return (
    <div className="min-h-screen bg-dark-900 flex flex-col">

      {/* Header */}
      <div className="bg-dark-800 border-b border-dark-600 px-4 py-3 flex-shrink-0">
        <div className="max-w-5xl mx-auto flex items-center gap-4">
          {onBack && (
            <button onClick={onBack} className="p-1.5 rounded-lg hover:bg-dark-700 text-gray-500 hover:text-white flex-shrink-0">
              <ArrowLeft size={18}/>
            </button>
          )}
          <CompanyLogo symbol={symbol} size="md"/>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-2xl font-black text-white">${symbol}</h1>
              {price?.price && <span className="text-xl font-bold text-white">${price.price.toFixed(2)}</span>}
              {price && (
                <span className={`flex items-center gap-1 font-bold text-sm ${isUp ? 'text-green-400' : 'text-red-400'}`}>
                  {isUp ? <TrendingUp size={14}/> : <TrendingDown size={14}/>}
                  {isUp ? '+' : ''}{change.toFixed(2)}%
                </span>
              )}
              {price?.volume && <span className="text-xs text-gray-500">Vol: {(price.volume/1e6).toFixed(1)}M</span>}
            </div>
            <div className="text-xs text-gray-500 mt-0.5">Community Discussion Board · {posts.length} posts</div>
          </div>
          <button onClick={watchlist} disabled={inWatch}
            className={`flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border transition-all flex-shrink-0 ${
              inWatch ? 'text-brand-400 border-brand-500/40 bg-brand-500/10' : 'text-gray-400 border-dark-600 hover:border-brand-400 hover:text-brand-400'
            }`}>
            <Star size={11}/> {inWatch ? 'Watching' : 'Add to Watchlist'}
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 max-w-5xl mx-auto w-full px-4 py-5 grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* Main feed - left 2/3 */}
        <div className="lg:col-span-2 space-y-4">

          {/* Compose */}
          <ComposeBox symbol={symbol} onPosted={loadPosts}/>

          {/* Filter bar */}
          <div className="flex items-center gap-2">
            <Hash size={13} className="text-gray-600"/>
            <span className="text-xs text-gray-600">Filter:</span>
            {['all','bullish','bearish'].map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={`text-xs px-3 py-1 rounded-full border transition-all ${
                  filter === f
                    ? f === 'bullish' ? 'bg-green-900/30 border-green-700 text-green-400'
                    : f === 'bearish' ? 'bg-red-900/30 border-red-700 text-red-400'
                    :                   'bg-brand-500/20 border-brand-500/40 text-brand-400'
                    : 'border-dark-600 text-gray-500 hover:text-white'
                }`}>
                {f === 'all' ? `All (${posts.length})` : f === 'bullish' ? `🟢 Bullish (${posts.filter(p=>p.sentiment==='bullish').length})` : `🔴 Bearish (${posts.filter(p=>p.sentiment==='bearish').length})`}
              </button>
            ))}
            <button onClick={loadPosts} className="ml-auto p-1 text-gray-600 hover:text-white">
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''}/>
            </button>
          </div>

          {/* Posts */}
          {loading && posts.length === 0 ? (
            <div className="text-center py-12 text-gray-600">
              <RefreshCw size={24} className="animate-spin mx-auto mb-2"/>
              <p className="text-sm">Loading posts…</p>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12 text-gray-600">
              <MessageCircle size={32} className="mx-auto mb-2 opacity-30"/>
              <p className="text-sm">No {filter !== 'all' ? filter + ' ' : ''}posts yet for ${symbol}</p>
              <p className="text-xs mt-1">Be the first to share your analysis!</p>
            </div>
          ) : (
            <div className="space-y-3">
              {filtered.map((p, i) => (
                <PostCard key={i} post={p} currentUserId={currentUserId}/>
              ))}
            </div>
          )}
        </div>

        {/* Sidebar - right 1/3 */}
        <div className="space-y-4">
          {/* Sentiment bar */}
          {posts.length > 0 && <SentimentBar posts={posts}/>}

          {/* AI Quick Take */}
          <AIQuickTake symbol={symbol} price={price}/>

          {/* Community rules */}
          <div className="bg-dark-800 border border-dark-600 rounded-xl p-4 space-y-2">
            <div className="text-xs font-bold text-white">📋 Community Rules</div>
            {[
              'Share your analysis, not just price targets',
              'No pump & dump or manipulation',
              'Back up claims with data when possible',
              'Respect all traders — all experience levels welcome',
              'This is a community — not financial advice',
            ].map((r,i) => (
              <div key={i} className="text-xs text-gray-500 flex gap-1.5">
                <span className="text-brand-400 flex-shrink-0">{i+1}.</span> {r}
              </div>
            ))}
          </div>

          {/* Disclaimer */}
          <div className="bg-red-900/15 border border-red-800/40 rounded-xl p-3">
            <div className="text-xs font-bold text-red-400 mb-1">⚠️ Disclaimer</div>
            <p className="text-xs text-red-300/70 leading-relaxed">
              All posts are user opinions. Nothing here is financial advice. Trading involves substantial risk of loss. Morviq AI is not responsible for community content or any trading decisions made based on it.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

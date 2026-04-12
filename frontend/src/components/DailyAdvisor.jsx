import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../hooks/useAuth'
import {
  Brain, Plus, X, ChevronDown, ChevronUp, RefreshCw,
  CheckCircle, XCircle, Eye, TrendingUp, TrendingDown,
  Target, Shield, Zap, AlertTriangle, Search
} from 'lucide-react'

const SIG_COLOR = {
  BUY:  'text-green-400 bg-green-900/20 border-green-700/50',
  SELL: 'text-red-400   bg-red-900/20   border-red-700/50',
  HOLD: 'text-gray-400  bg-dark-700     border-dark-600',
}

function StatusBadge({ status }) {
  const cfg = {
    pending:  { label: 'Pending Review', color: 'text-yellow-400 bg-yellow-900/20 border-yellow-700/40' },
    reviewed: { label: 'Reviewed',       color: 'text-blue-400   bg-blue-900/20   border-blue-700/40'   },
    accepted: { label: '✅ Accepted',    color: 'text-green-400  bg-green-900/20  border-green-700/40'  },
    rejected: { label: '❌ Rejected',    color: 'text-red-400    bg-red-900/20    border-red-700/40'     },
  }
  const c = cfg[status] || cfg.pending
  return <span className={`text-xs px-2 py-0.5 rounded-full border font-bold ${c.color}`}>{c.label}</span>
}

// ── Symbol Autocomplete Input ─────────────────────────────────────────────────
function SymbolInput({ onAdd }) {
  const [input,       setInput]       = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [showDropdown,setShowDropdown]= useState(false)
  const [loading,     setLoading]     = useState(false)
  const timerRef = useRef(null)
  const wrapRef  = useRef(null)

  useEffect(() => {
    function handleClick(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setShowDropdown(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  function onChange(val) {
    setInput(val.toUpperCase())
    clearTimeout(timerRef.current)
    if (!val.trim()) { setSuggestions([]); setShowDropdown(false); return }
    setLoading(true)
    timerRef.current = setTimeout(async () => {
      try {
        const r = await api.get(`/scanner/search?q=${encodeURIComponent(val)}`)
        setSuggestions(r.data || [])
        setShowDropdown(true)
      } catch {} finally { setLoading(false) }
    }, 200)
  }

  function select(sym) {
    setInput('')
    setSuggestions([])
    setShowDropdown(false)
    onAdd(sym)
  }

  function onKey(e) {
    if (e.key === 'Enter' && input.trim()) { select(input.trim().toUpperCase()) }
    if (e.key === 'Escape') setShowDropdown(false)
  }

  return (
    <div ref={wrapRef} className="relative flex-1">
      <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600 z-10"/>
      {loading && <RefreshCw size={11} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 animate-spin"/>}
      <input
        value={input}
        onChange={e => onChange(e.target.value)}
        onKeyDown={onKey}
        onFocus={() => input && setShowDropdown(true)}
        placeholder="Search symbol (e.g. AAPL, TSLA, BTC)…"
        className="w-full bg-dark-800 border border-dark-600 rounded-xl pl-8 pr-8 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500 placeholder-gray-700"
      />
      {showDropdown && suggestions.length > 0 && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-dark-800 border border-dark-600 rounded-xl shadow-2xl z-50 overflow-hidden">
          {suggestions.map(s => (
            <button key={s.symbol} onClick={() => select(s.symbol)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-dark-700 text-left transition-colors">
              <span className="font-black text-white text-sm w-16">{s.symbol}</span>
              <span className="text-xs text-gray-500 truncate">{s.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── AI Recommendation Card ────────────────────────────────────────────────────
function RecCard({ rec, onReview }) {
  const [expanded,   setExpanded]   = useState(false)
  const [reviewing,  setReviewing]  = useState(false)
  const [msg,        setMsg]        = useState('')
  const sigStyle = SIG_COLOR[rec.signal] || SIG_COLOR.HOLD

  async function handleReview(action) {
    setReviewing(true)
    try {
      const r = await api.post(`/daily/recommendations/${rec.id}/review`, { action })
      setMsg(r.data.message || '')
      onReview?.()
    } catch (e) { setMsg('Error: ' + (e.response?.data?.detail || e.message)) }
    finally { setReviewing(false) }
  }

  return (
    <div className={`border rounded-xl overflow-hidden transition-all ${
      rec.eligible_for_auto ? 'border-green-700/40 bg-green-900/5' :
      rec.status === 'rejected' ? 'border-dark-600 bg-dark-800 opacity-60' :
      'border-dark-600 bg-dark-800'
    }`}>
      <div className="p-3.5 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-brand-500 text-dark-900 font-black text-sm flex items-center justify-center flex-shrink-0">{rec.rank}</div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-black text-white text-base">${rec.symbol}</span>
            <span className={`text-xs px-2 py-0.5 rounded border font-bold ${sigStyle}`}>{rec.signal}</span>
            {rec.confidence && <span className="text-xs text-gray-500">{rec.confidence}% conf</span>}
            <StatusBadge status={rec.status}/>
          </div>
          {(rec.entry || rec.exit) && (
            <div className="flex gap-2 mt-1 flex-wrap">
              {rec.entry && <span className="text-xs font-mono text-brand-400">In: ${rec.entry}</span>}
              {rec.exit  && <span className="text-xs font-mono text-green-400">Out: ${rec.exit}</span>}
              {rec.stop  && <span className="text-xs font-mono text-red-400">Stop: ${rec.stop}</span>}
              {rec.suggested_alloc && <span className="text-xs text-yellow-400">💰 ${rec.suggested_alloc}</span>}
            </div>
          )}
        </div>
        <button onClick={() => setExpanded(e => !e)} className="p-1.5 hover:bg-dark-700 rounded-lg text-gray-500">
          {expanded ? <ChevronUp size={14}/> : <ChevronDown size={14}/>}
        </button>
      </div>

      {expanded && (
        <div className="border-t border-dark-700 p-3.5 space-y-3">
          <div className="grid grid-cols-3 gap-2 text-xs text-center">
            {[{l:'Entry',v:rec.entry,c:'text-brand-400'},{l:'Target',v:rec.exit,c:'text-green-400'},{l:'Stop',v:rec.stop,c:'text-red-400'}]
              .map(({l,v,c}) => (
              <div key={l} className="bg-dark-900 rounded-lg p-2">
                <div className="text-gray-600">{l}</div>
                <div className={`font-bold ${c} mt-0.5`}>{v?`$${v}`:'—'}</div>
              </div>
            ))}
          </div>
          {rec.risk_reward && (
            <div className="flex gap-3 text-xs">
              <span className="text-gray-500">R:R <span className="text-white font-bold">1:{parseFloat(rec.risk_reward).toFixed(1)}</span></span>
              <span className="text-gray-500">Qty <span className="text-white font-bold">{rec.suggested_qty} shares</span></span>
              <span className="text-yellow-400 font-bold">${rec.suggested_alloc} allocated</span>
            </div>
          )}
          {rec.reasoning && <p className="text-xs text-gray-400 leading-relaxed bg-dark-900 rounded-lg p-3">{rec.reasoning}</p>}
          {msg && (
            <div className={`text-xs p-2.5 rounded-lg ${msg.startsWith('✅')?'bg-green-900/20 text-green-400':msg.startsWith('❌')?'bg-red-900/20 text-red-400':'bg-dark-700 text-gray-400'}`}>{msg}</div>
          )}
          {rec.status === 'pending' && (
            <div className="space-y-2">
              <div className="text-xs text-yellow-400 font-bold flex items-center gap-1.5">
                <Eye size={12}/> Review Required — auto-trading only activates after you accept
              </div>
              <div className="flex gap-2 flex-wrap">
                <button onClick={() => handleReview('reviewed')} disabled={reviewing}
                  className="flex items-center gap-1.5 text-xs px-3 py-2 bg-dark-700 hover:bg-dark-600 text-gray-300 border border-dark-600 rounded-lg disabled:opacity-50">
                  <Eye size={12}/> Mark Reviewed
                </button>
                <button onClick={() => handleReview('accepted')} disabled={reviewing}
                  className="flex items-center gap-1.5 text-xs px-3 py-2 bg-green-900/30 hover:bg-green-900/50 text-green-400 border border-green-800/40 rounded-lg disabled:opacity-50">
                  <CheckCircle size={12}/> Accept & Auto-Trade
                </button>
                <button onClick={() => handleReview('rejected')} disabled={reviewing}
                  className="flex items-center gap-1.5 text-xs px-3 py-2 bg-red-900/20 hover:bg-red-900/40 text-red-400 border border-red-800/40 rounded-lg disabled:opacity-50">
                  <XCircle size={12}/> Reject
                </button>
              </div>
              <p className="text-xs text-gray-600">Decision is logged with timestamp for compliance.</p>
            </div>
          )}
          {rec.eligible_for_auto && (
            <div className="flex items-center gap-2 p-2.5 bg-green-900/15 border border-green-800/30 rounded-lg">
              <CheckCircle size={14} className="text-green-400 flex-shrink-0"/>
              <span className="text-xs text-green-400">Auto-trading enabled — accepted {rec.accepted_at ? new Date(rec.accepted_at).toLocaleTimeString() : ''}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── User Pick Card ────────────────────────────────────────────────────────────
function PickCard({ pick, onRemove, onAnalyze }) {
  const [expanded,  setExpanded]  = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const an = pick.analysis

  async function analyze() {
    setAnalyzing(true)
    try { await onAnalyze(pick.symbol); setExpanded(true) }
    finally { setAnalyzing(false) }
  }

  const sigStyle = an?.signal ? (SIG_COLOR[an.signal] || SIG_COLOR.HOLD) : ''

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl overflow-hidden">
      <div className="p-3.5 flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-black text-white">${pick.symbol}</span>
            {an?.signal && <span className={`text-xs px-2 py-0.5 rounded border font-bold ${sigStyle}`}>{an.signal}</span>}
            {an?.confidence && <span className="text-xs text-gray-500">{an.confidence}% conf</span>}
            {!an && <span className="text-xs text-gray-600 italic">Not analyzed yet</span>}
          </div>
          {an?.entry && (
            <div className="flex gap-2 mt-1 flex-wrap">
              {an.entry && <span className="text-xs font-mono text-brand-400">In: ${an.entry}</span>}
              {an.exit  && <span className="text-xs font-mono text-green-400">Out: ${an.exit}</span>}
              {an.stop  && <span className="text-xs font-mono text-red-400">Stop: ${an.stop}</span>}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <button onClick={analyze} disabled={analyzing}
            className="flex items-center gap-1 text-xs px-2.5 py-1.5 bg-brand-500/20 hover:bg-brand-500/30 text-brand-400 border border-brand-500/30 rounded-lg transition-all">
            {analyzing ? <RefreshCw size={10} className="animate-spin"/> : <Brain size={10}/>}
            {analyzing ? 'Analyzing…' : an ? 'Re-Analyze' : 'Analyze'}
          </button>
          {an && (
            <button onClick={() => setExpanded(e => !e)} className="p-1.5 hover:bg-dark-700 rounded text-gray-500">
              {expanded ? <ChevronUp size={13}/> : <ChevronDown size={13}/>}
            </button>
          )}
          <button onClick={() => onRemove(pick.symbol)} className="p-1.5 hover:bg-dark-700 rounded text-gray-600 hover:text-red-400">
            <X size={13}/>
          </button>
        </div>
      </div>

      {expanded && an && (
        <div className="border-t border-dark-700 p-3.5 space-y-3">
          <div className="grid grid-cols-3 gap-2 text-xs text-center">
            {[{l:'Entry',v:an.entry,c:'text-brand-400'},{l:'Target',v:an.exit,c:'text-green-400'},{l:'Stop',v:an.stop,c:'text-red-400'}]
              .map(({l,v,c}) => (
              <div key={l} className="bg-dark-900 rounded-lg p-2">
                <div className="text-gray-600">{l}</div>
                <div className={`font-bold ${c} mt-0.5`}>{v?`$${v}`:'—'}</div>
              </div>
            ))}
          </div>
          {an.reasoning && <p className="text-xs text-gray-400 leading-relaxed bg-dark-900 rounded-lg p-3">{an.reasoning}</p>}
          {an.vs_ai_verdict && (
            <div className={`p-3 rounded-xl border text-xs leading-relaxed ${
              an.vs_ai_verdict.startsWith('✅') ? 'bg-green-900/15 border-green-800/30 text-green-300' :
              an.vs_ai_verdict.startsWith('🟡') ? 'bg-yellow-900/15 border-yellow-800/30 text-yellow-300' :
              'bg-red-900/15 border-red-800/30 text-red-300'
            }`}>
              <div className="font-bold mb-1">🤖 AI Honest Opinion</div>
              {an.vs_ai_verdict}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Mini pick widget for dashboard embedding ──────────────────────────────────
export function DailyPicksMini({ onNavigate }) {
  const [picks,   setPicks]   = useState([])
  const [recs,    setRecs]    = useState([])
  const [pending, setPending] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.get('/daily/picks'), api.get('/daily/recommendations')])
      .then(([p, r]) => { setPicks(p.data.picks||[]); setRecs(r.data.recs||[]); setPending(r.data.pending||0) })
      .catch(() => {}).finally(() => setLoading(false))
  }, [])

  async function quickAdd(sym) {
    if (!sym) return
    await api.post('/daily/picks', { symbol: sym.toUpperCase() })
    const r = await api.get('/daily/picks')
    setPicks(r.data.picks || [])
  }

  if (loading) return <div className="py-4 flex items-center justify-center"><RefreshCw size={14} className="animate-spin text-brand-500"/></div>

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-white flex items-center gap-1.5">
          <Brain size={12} className="text-brand-400"/> Daily Picks
          {pending > 0 && <span className="text-xs bg-yellow-900/30 text-yellow-400 border border-yellow-800/40 px-1.5 py-0.5 rounded-full font-bold">{pending} pending</span>}
        </span>
        <button onClick={() => onNavigate?.('daily')} className="text-xs text-brand-400 hover:text-brand-300">View all →</button>
      </div>

      {/* Quick add */}
      <SymbolInput onAdd={quickAdd}/>

      {/* Mini pick list */}
      {picks.slice(0, 3).map(p => (
        <div key={p.symbol} className="flex items-center gap-2 p-2.5 bg-dark-700 border border-dark-600 rounded-lg">
          <span className="font-bold text-white text-sm">${p.symbol}</span>
          {p.analysis?.signal && (
            <span className={`text-xs px-1.5 py-0.5 rounded border font-bold ${SIG_COLOR[p.analysis.signal]||SIG_COLOR.HOLD}`}>{p.analysis.signal}</span>
          )}
          {!p.analysis && <span className="text-xs text-gray-600">tap to analyze</span>}
          <button onClick={() => onNavigate?.('daily')} className="ml-auto text-xs text-gray-600 hover:text-brand-400">→</button>
        </div>
      ))}

      {/* Mini AI recs */}
      {recs.slice(0,2).map(r => (
        <div key={r.id} className={`flex items-center gap-2 p-2.5 rounded-lg border ${
          r.eligible_for_auto ? 'bg-green-900/10 border-green-800/30' : 'bg-dark-700 border-dark-600'
        }`}>
          <span className="text-xs font-bold text-brand-400">#{r.rank}</span>
          <span className="font-bold text-white text-sm">${r.symbol}</span>
          <span className={`text-xs px-1.5 py-0.5 rounded border font-bold ${SIG_COLOR[r.signal]||SIG_COLOR.HOLD}`}>{r.signal}</span>
          {r.status === 'pending' && <span className="text-xs text-yellow-400 ml-auto">Review →</span>}
          {r.eligible_for_auto && <span className="text-xs text-green-400 ml-auto">✅ Auto</span>}
        </div>
      ))}

      {picks.length === 0 && recs.length === 0 && (
        <div className="text-center py-3 text-xs text-gray-600">
          Add symbols to watch · Run AI Scan for suggestions
        </div>
      )}

      <button onClick={() => onNavigate?.('daily')}
        className="w-full text-xs py-2 bg-dark-700 hover:bg-dark-600 text-gray-400 border border-dark-600 rounded-lg transition-all">
        Open Daily Advisor →
      </button>
    </div>
  )
}

// ── Main Full Page ────────────────────────────────────────────────────────────
export default function DailyAdvisor() {
  const [picks,    setPicks]    = useState([])
  const [recs,     setRecs]     = useState([])
  const [optimizer,setOptimizer]= useState(null)
  const [loading,  setLoading]  = useState(false)
  const [scanning, setScanning] = useState(false)
  const [pendingCount, setPendingCount] = useState(0)

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [picksR, recsR, optR] = await Promise.all([
        api.get('/daily/picks'),
        api.get('/daily/recommendations'),
        api.get('/daily/optimizer'),
      ])
      setPicks(picksR.data.picks || [])
      setRecs(recsR.data.recs || [])
      setPendingCount(recsR.data.pending || 0)
      setOptimizer(optR.data)
    } catch {} finally { setLoading(false) }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  async function addPick(symbol) {
    try { await api.post('/daily/picks', { symbol }); loadAll() } catch {}
  }

  async function removePick(symbol) {
    try { await api.delete(`/daily/picks/${symbol}`); loadAll() } catch {}
  }

  async function analyzePick(symbol) {
    try { await api.post(`/daily/picks/${symbol}/analyze`); loadAll() } catch {}
  }

  async function runScan() {
    setScanning(true)
    try { await api.post('/daily/scan'); loadAll() } catch {} finally { setScanning(false) }
  }

  const opt = optimizer

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-black text-white flex items-center gap-2">
            <Brain size={20} className="text-brand-400"/> Daily Trading Advisor
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">{new Date().toLocaleDateString('en-US',{weekday:'long',month:'long',day:'numeric'})}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadAll} disabled={loading} className="p-2 bg-dark-700 border border-dark-600 rounded-xl text-gray-500 hover:text-white">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''}/>
          </button>
          <button onClick={runScan} disabled={scanning}
            className="flex items-center gap-2 px-4 py-2 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl text-sm disabled:opacity-50">
            {scanning ? <RefreshCw size={14} className="animate-spin"/> : <Zap size={14}/>}
            {scanning ? 'Scanning Market…' : 'Run AI Scan'}
          </button>
        </div>
      </div>

      {/* Trading budget */}
      {opt && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
          <div className="text-xs font-bold text-white mb-3 flex items-center gap-2">
            <Target size={13} className="text-brand-400"/> Today's Trading Budget
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs">
            {[
              { l: 'Buying Power',    v: `$${(opt.account.buying_power||0).toLocaleString('en-US',{maximumFractionDigits:0})}`, c: 'text-white' },
              { l: 'Day Trades Left', v: opt.trade_budget.pdt_exempt ? '∞ Exempt' : `${opt.trade_budget.max_day_trades}`,        c: opt.trade_budget.pdt_exempt ? 'text-green-400' : opt.trade_budget.max_day_trades >= 2 ? 'text-yellow-400' : 'text-red-400' },
              { l: 'Daily Goal',      v: `$${opt.goal.min}–$${opt.goal.max}`,                                                    c: 'text-brand-400' },
              { l: 'Per-Trade Max',   v: `$${(opt.trade_budget.per_trade_max||0).toLocaleString('en-US',{maximumFractionDigits:0})}`, c: 'text-white' },
            ].map(({ l, v, c }) => (
              <div key={l} className="bg-dark-700 rounded-lg p-2.5">
                <div className="text-gray-500">{l}</div>
                <div className={`font-black text-sm mt-0.5 ${c}`}>{v}</div>
              </div>
            ))}
          </div>
          {!opt.trade_budget.pdt_exempt && opt.trade_budget.max_day_trades <= 1 && (
            <div className="mt-2 p-2 bg-red-900/20 border border-red-800/40 rounded-lg text-xs text-red-400">
              ⚠️ PDT limit almost reached — consider crypto (no PDT limit) or hold overnight
            </div>
          )}
        </div>
      )}

      {/* AI Recommendations */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <div className="text-sm font-bold text-white">🤖 AI Picks</div>
          {pendingCount > 0 && (
            <span className="text-xs px-2 py-0.5 bg-yellow-900/30 text-yellow-400 border border-yellow-800/40 rounded-full font-bold">
              {pendingCount} need review
            </span>
          )}
          {recs.length === 0 && !scanning && (
            <span className="text-xs text-gray-600 ml-2">Click "Run AI Scan" to generate picks</span>
          )}
        </div>
        {scanning && (
          <div className="flex items-center justify-center gap-2 py-6 text-sm text-gray-500">
            <RefreshCw size={14} className="animate-spin text-brand-500"/>
            Scanning market — analyzing movers, news, PDT budget…
          </div>
        )}
        {recs.map(rec => <RecCard key={rec.id} rec={rec} onReview={loadAll}/>)}
        {recs.length > 0 && (
          <p className="text-xs text-gray-600 text-center">Accept to enable auto-trading · All decisions are logged</p>
        )}
      </div>

      {/* User picks */}
      <div className="space-y-3">
        <div className="text-sm font-bold text-white">📋 My Daily Watch List</div>
        <div className="flex gap-2">
          <SymbolInput onAdd={addPick}/>
        </div>
        {picks.length === 0 ? (
          <div className="text-center py-8 bg-dark-800 border border-dark-600 rounded-xl text-gray-600">
            <Search size={24} className="mx-auto mb-2 opacity-30"/>
            <p className="text-sm">Search and add symbols you're considering today</p>
            <p className="text-xs mt-1">AI will analyze and compare to its own picks</p>
          </div>
        ) : (
          <div className="space-y-2">
            {picks.map(pick => (
              <PickCard key={pick.symbol} pick={pick} onRemove={removePick} onAnalyze={analyzePick}/>
            ))}
          </div>
        )}
      </div>

      <div className="p-3 bg-red-900/15 border border-red-800/30 rounded-xl text-xs text-red-300/70 leading-relaxed">
        ⚠️ AI analysis is informational only. Markets are unpredictable. Auto-trading only activates for accepted recommendations within your configured risk limits.
      </div>
    </div>
  )
}
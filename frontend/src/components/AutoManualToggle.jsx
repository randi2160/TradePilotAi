import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { RefreshCw, Plus, X } from 'lucide-react'

export default function AutoManualToggle({ data }) {
  const [tradingMode, setTradingMode] = useState('auto')
  const [wlDynamic,   setWlDynamic]   = useState(false)
  const [manualList,  setManualList]  = useState([])
  const [dynamicList, setDynamicList] = useState([])
  const [scores,      setScores]      = useState({})
  const [builtAt,     setBuiltAt]     = useState('')
  const [totalScanned,setTotalScanned]= useState(0)
  const [rebuilding,  setRebuilding]  = useState(false)
  const [pending,     setPending]     = useState([])
  const [newSymbol,   setNewSymbol]   = useState('')
  const [msg,         setMsg]         = useState('')
  const [prices,      setPrices]      = useState({})

  useEffect(() => {
    loadAll()
    fetchPrices()
    const iv = setInterval(fetchPrices, 15000)
    return () => clearInterval(iv)
  }, [])

  useEffect(() => {
    if (data?.trading_mode)   setTradingMode(data.trading_mode)
    if (data?.pending_trades) setPending(data.pending_trades)
    if (typeof data?.dynamic_watchlist === 'boolean') setWlDynamic(data.dynamic_watchlist)
  }, [data])

  async function loadAll() {
    try {
      const [wlRes, scoresRes] = await Promise.all([
        api.get('/watchlist'),
        api.get('/watchlist/scores').catch(() => ({ data: {} })),
      ])
      setManualList(wlRes.data.watchlist ?? [])
      const s = scoresRes.data
      setScores(s.scores ?? {})
      setBuiltAt(s.built_at ?? '')
      setTotalScanned(s.total_scanned ?? 0)
      setDynamicList(s.watchlist ?? [])
      if (typeof s.is_dynamic === 'boolean') setWlDynamic(s.is_dynamic)
    } catch {}
  }

  async function fetchPrices() {
    try {
      const r = await api.get('/ticker')
      setPrices(r.data)
    } catch {}
  }

  function flash(m) { setMsg(m); setTimeout(() => setMsg(''), 4000) }

  async function setMode(mode) {
    try {
      await api.put('/bot/trading-mode', { trading_mode: mode })
      setTradingMode(mode)
      flash(`✅ ${mode.toUpperCase()} mode activated`)
    } catch(e) { flash(`❌ ${e.message}`) }
  }

  async function setWlMode(dynamic) {
    try {
      await api.put('/bot/watchlist-mode', { dynamic })
      setWlDynamic(dynamic)
      if (dynamic) {
        flash('🧠 AI Dynamic enabled — scanning live market...')
        await rebuild()
      } else {
        flash('📋 Manual mode — using your saved symbols')
      }
    } catch(e) { flash(`❌ ${e.message}`) }
  }

  async function rebuild() {
    setRebuilding(true)
    try {
      const r = await api.post('/watchlist/rebuild')
      setDynamicList(r.data.watchlist ?? [])
      setScores(r.data.scores ?? {})
      setBuiltAt(r.data.built_at ?? new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}))
      setTotalScanned(r.data.total_scanned ?? 0)
      flash(`✅ Live scan complete — ${r.data.watchlist?.length} stocks selected from ${r.data.total_scanned} scanned`)
      fetchPrices()
    } catch(e) { flash(`❌ ${e.response?.data?.detail ?? e.message}`) }
    finally { setRebuilding(false) }
  }

  async function addSymbol() {
    const syms = newSymbol.toUpperCase().split(/[\s,]+/).filter(Boolean)
    if (!syms.length) return
    try {
      for (const sym of syms) await api.post('/watchlist/add', { symbol: sym })
      setNewSymbol('')
      await loadAll()
      flash(`✅ Added: ${syms.join(', ')}`)
    } catch(e) { flash(`❌ ${e.message}`) }
  }

  async function removeSymbol(sym) {
    try {
      await api.delete(`/watchlist/${sym}`)
      setManualList(l => l.filter(s => s !== sym))
      flash(`Removed ${sym}`)
    } catch {}
  }

  async function approve(sym) {
    try {
      await api.post(`/pending-trades/${sym}/approve`)
      setPending(p => p.filter(t => t.symbol !== sym))
      flash(`✅ ${sym} trade approved`)
    } catch {}
  }

  async function reject(sym) {
    try {
      await api.post(`/pending-trades/${sym}/reject`)
      setPending(p => p.filter(t => t.symbol !== sym))
    } catch {}
  }

  const activeList = wlDynamic ? dynamicList : manualList

  return (
    <div className="space-y-5">

      {msg && <div className="p-3 bg-dark-700 rounded-lg text-sm text-center">{msg}</div>}

      {/* Trading Mode */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5">
        <h3 className="font-bold text-white mb-1">Trading Mode</h3>
        <p className="text-xs text-gray-400 mb-3">Auto = AI executes trades automatically. Manual = AI suggests, you approve.</p>
        <div className="grid grid-cols-2 gap-3">
          {[
            { id:'auto',   icon:'🤖', label:'AUTO', desc:'AI executes within your risk limits 24/7' },
            { id:'manual', icon:'👤', label:'MANUAL', desc:'AI finds setups, you approve each trade' },
          ].map(m => (
            <button key={m.id} onClick={() => setMode(m.id)}
              className={`p-4 rounded-xl border text-left transition-all ${
                tradingMode === m.id ? 'border-brand-500 bg-brand-500/10' : 'border-dark-600 hover:border-dark-500'
              }`}>
              <p className="font-bold text-white">{m.icon} {m.label}</p>
              <p className="text-xs text-gray-400 mt-1">{m.desc}</p>
              {tradingMode === m.id && <p className="text-xs text-brand-500 mt-1 font-bold">✓ Active</p>}
            </button>
          ))}
        </div>
      </div>

      {/* Pending trade approvals */}
      {pending.length > 0 && (
        <div className="bg-yellow-900/20 border border-yellow-700 rounded-xl p-4">
          <h3 className="font-bold text-yellow-400 mb-3">⚡ {pending.length} Trade{pending.length>1?'s':''} Awaiting Your Approval</h3>
          <div className="space-y-2">
            {pending.map((t, i) => (
              <div key={i} className="flex items-center gap-3 bg-dark-800 rounded-lg p-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-white">{t.symbol}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      t.signal?.signal === 'BUY' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
                    }`}>{t.signal?.signal}</span>
                  </div>
                  <p className="text-xs text-gray-500">Confidence: {((t.signal?.confidence ?? 0)*100).toFixed(0)}%</p>
                </div>
                <button onClick={() => approve(t.symbol)} className="px-3 py-1.5 bg-green-700 hover:bg-green-600 text-white text-xs font-bold rounded-lg">✅ Approve</button>
                <button onClick={() => reject(t.symbol)} className="px-3 py-1.5 bg-red-900 hover:bg-red-800 text-red-300 text-xs font-bold rounded-lg">❌ Reject</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Watchlist Mode */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
        <div>
          <h3 className="font-bold text-white mb-1">Watchlist Mode</h3>
          <p className="text-xs text-gray-400">Dynamic = AI scans 100+ stocks every 30 min and picks real movers. Manual = your own list.</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {[
            { id: false, icon:'📋', label:'Manual List',  desc:'You control exactly which stocks to watch' },
            { id: true,  icon:'🧠', label:'AI Dynamic',   desc:'AI picks real movers from 100+ stocks every 30 min' },
          ].map(m => (
            <button key={String(m.id)} onClick={() => setWlMode(m.id)}
              className={`p-4 rounded-xl border text-left transition-all ${
                wlDynamic === m.id ? 'border-purple-500 bg-purple-500/10' : 'border-dark-600 hover:border-dark-500'
              }`}>
              <p className="font-bold text-white">{m.icon} {m.label}</p>
              <p className="text-xs text-gray-400 mt-1">{m.desc}</p>
              {wlDynamic === m.id && <p className="text-xs text-purple-400 mt-1 font-bold">✓ Active</p>}
            </button>
          ))}
        </div>

        {/* Dynamic mode controls */}
        {wlDynamic && (
          <div className="flex items-center justify-between">
            <div>
              {builtAt && <p className="text-xs text-gray-500">Last scan: {builtAt} · {totalScanned} stocks checked</p>}
              {!builtAt && <p className="text-xs text-yellow-400">⚠️ Not yet built — click Scan Now</p>}
            </div>
            <button onClick={rebuild} disabled={rebuilding}
              className="flex items-center gap-1.5 text-xs bg-purple-900/40 hover:bg-purple-900/70 text-purple-300 border border-purple-700 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50">
              <RefreshCw size={12} className={rebuilding ? 'animate-spin' : ''}/>
              {rebuilding ? 'Scanning 100+ stocks...' : '🔄 Scan Market Now'}
            </button>
          </div>
        )}

        {/* Manual mode — add/remove symbols */}
        {!wlDynamic && (
          <div className="flex gap-2">
            <input
              value={newSymbol}
              onChange={e => setNewSymbol(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && addSymbol()}
              placeholder="Add symbol e.g. AAPL, TSLA..."
              className="flex-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500 font-mono uppercase"
            />
            <button onClick={addSymbol}
              className="px-4 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold text-sm rounded-xl">
              <Plus size={16}/>
            </button>
          </div>
        )}

        {/* Stock list with live prices */}
        <div>
          <p className="text-xs font-bold text-gray-400 mb-2">
            {wlDynamic
              ? `🔥 AI Selected Today (${activeList.length} stocks)`
              : `📋 Your Watchlist (${activeList.length} symbols)`
            }
          </p>
          <div className="space-y-1 max-h-80 overflow-y-auto">
            {activeList.length === 0 && (
              <p className="text-sm text-gray-500 text-center py-6">
                {wlDynamic ? 'Click "Scan Market Now" to find today\'s movers' : 'Add symbols above to start watching'}
              </p>
            )}
            {activeList.map(sym => {
              const p   = prices[sym]
              const sc  = scores[sym]
              const up  = p ? p.change_pct >= 0 : null
              return (
                <div key={sym} className="flex items-center gap-3 bg-dark-700 hover:bg-dark-600 rounded-lg px-3 py-2 transition-colors">
                  {/* Symbol */}
                  <span className="font-black text-white w-14 text-sm">{sym}</span>

                  {/* Price + change */}
                  {p ? (
                    <div className="flex items-center gap-2 flex-1">
                      <span className="font-mono text-white text-sm">${p.price?.toFixed(2)}</span>
                      <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                        up ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'
                      }`}>
                        {up ? '▲' : '▼'}{Math.abs(p.change_pct).toFixed(2)}%
                      </span>
                      <span className={`text-xs ${up ? 'text-green-400' : 'text-red-400'}`}>
                        {p.change_$ > 0 ? '+' : ''}{p.change_$?.toFixed(2)}
                      </span>
                    </div>
                  ) : (
                    <span className="flex-1 text-xs text-gray-600">No price data</span>
                  )}

                  {/* Dynamic score flags */}
                  {wlDynamic && sc && (
                    <div className="flex gap-1 flex-wrap justify-end max-w-xs">
                      {(sc.flags ?? []).slice(0,2).map((f, i) => (
                        <span key={i} className="text-xs text-gray-500">{f}</span>
                      ))}
                    </div>
                  )}

                  {/* Volume */}
                  {p?.volume > 0 && (
                    <span className="text-xs text-gray-600 w-16 text-right">
                      {p.volume > 1e6 ? `${(p.volume/1e6).toFixed(1)}M` : `${(p.volume/1e3).toFixed(0)}K`}
                    </span>
                  )}

                  {/* Remove button (manual mode only) */}
                  {!wlDynamic && (
                    <button onClick={() => removeSymbol(sym)}
                      className="text-gray-600 hover:text-red-400 transition-colors ml-1">
                      <X size={14}/>
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

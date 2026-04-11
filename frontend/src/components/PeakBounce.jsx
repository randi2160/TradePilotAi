import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { TrendingUp, TrendingDown, RefreshCw, Zap, Target, BarChart2, CheckCircle, AlertTriangle } from 'lucide-react'

const WINDOWS = {
  '30min':   '30 min (scalp)',
  '1hour':   '1 hour (short swing)',
  '2hour':   '2 hours ⭐ Recommended',
  '4hour':   '4 hours (half day)',
  'fullday': 'Full day',
}

function StrengthBar({ value, max = 100 }) {
  const pct   = Math.min((value / max) * 100, 100)
  const color = value >= 70 ? '#00d4aa' : value >= 50 ? '#f59e0b' : '#ef4444'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-dark-600 rounded-full h-2">
        <div className="h-2 rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-xs font-bold w-8 text-right" style={{ color }}>{value}</span>
    </div>
  )
}

function PatternCard({ data, onCreateLadder }) {
  const p   = data.pattern
  const pos = data.position
  const sig = data.entry_signal

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-black text-white">{data.symbol}</h3>
          <p className="text-xs text-gray-400">{data.window_label}</p>
        </div>
        <div className={`px-3 py-1.5 rounded-xl text-sm font-bold ${
          p.pattern_strength >= 70 ? 'bg-green-900/40 text-green-400 border border-green-800' :
          p.pattern_strength >= 50 ? 'bg-yellow-900/40 text-yellow-400 border border-yellow-800' :
          'bg-red-900/40 text-red-400 border border-red-800'
        }`}>
          {p.pattern_strength >= 70 ? '🔥 Strong' : p.pattern_strength >= 50 ? '⚠️ Moderate' : '❌ Weak'}
        </div>
      </div>

      {/* Pattern strength */}
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Pattern Strength</span>
          <span>{p.pattern_strength}/100</span>
        </div>
        <StrengthBar value={p.pattern_strength} />
      </div>

      {/* Price levels */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-green-900/20 border border-green-800/40 rounded-lg p-2.5 text-center">
          <p className="text-xs text-gray-400">Valley (Buy)</p>
          <p className="text-sm font-black text-green-400">${p.avg_valley}</p>
        </div>
        <div className="bg-dark-700 rounded-lg p-2.5 text-center">
          <p className="text-xs text-gray-400">Bounce</p>
          <p className="text-sm font-black text-white">+${p.bounce_height} ({p.bounce_pct}%)</p>
        </div>
        <div className="bg-red-900/20 border border-red-800/40 rounded-lg p-2.5 text-center">
          <p className="text-xs text-gray-400">Peak (Sell)</p>
          <p className="text-sm font-black text-red-400">${p.avg_peak}</p>
        </div>
      </div>

      {/* Current price indicator */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-400">Current:</span>
        <span className="text-white font-bold">${p.current_price}</span>
        {p.near_valley && <span className="text-xs bg-green-900/40 text-green-400 px-2 py-0.5 rounded-full">📍 Near Valley — Good Entry!</span>}
        {p.near_peak   && <span className="text-xs bg-red-900/40 text-red-400 px-2 py-0.5 rounded-full">📍 Near Peak — Wait for dip</span>}
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div className="bg-dark-700 rounded-lg p-2">
          <p className="text-gray-400">Success Rate</p>
          <p className="font-bold text-white">{(p.success_rate * 100).toFixed(0)}%</p>
        </div>
        <div className="bg-dark-700 rounded-lg p-2">
          <p className="text-gray-400">Avg Recovery</p>
          <p className="font-bold text-white">{p.avg_recovery_min} min</p>
        </div>
        <div className="bg-dark-700 rounded-lg p-2">
          <p className="text-gray-400">Volume</p>
          <p className={`font-bold ${p.volume_confirmed ? 'text-green-400' : 'text-yellow-400'}`}>
            {p.volume_confirmed ? '✅ OK' : '⚠️ Low'}
          </p>
        </div>
      </div>

      {/* Position sizing */}
      {pos && (
        <div className="bg-dark-700 border border-dark-600 rounded-xl p-3 space-y-2">
          <p className="text-xs font-bold text-gray-300">📐 AI-Calculated Position</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            {[
              ['Shares to buy',   pos.shares],
              ['Entry price',     `$${pos.entry_price}`],
              ['Sell target',     `$${pos.exit_target}`],
              ['Stop loss',       `$${pos.stop_loss}`],
              ['Position value',  `$${pos.position_value}`],
              ['Est. net profit', `+$${pos.net_profit_est}`],
              ['Execution cost',  `$${pos.execution_cost}`],
              ['Min margin',      `${pos.min_margin_pct}%`],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-gray-400">{k}</span>
                <span className="text-white font-medium">{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Entry signal */}
      <div className={`p-3 rounded-xl border text-sm ${
        sig.should_enter
          ? 'bg-green-900/20 border-green-800 text-green-300'
          : 'bg-dark-700 border-dark-600 text-gray-400'
      }`}>
        <div className="flex items-center gap-2 mb-1">
          {sig.should_enter ? <CheckCircle size={14}/> : <AlertTriangle size={14}/>}
          <span className="font-bold">{sig.should_enter ? 'READY TO ENTER' : 'NOT YET'}</span>
          {sig.confidence > 0 && (
            <span className="ml-auto text-xs">{(sig.confidence * 100).toFixed(0)}% confidence</span>
          )}
        </div>
        <p className="text-xs opacity-80">{sig.reason}</p>
      </div>

      {/* Actions */}
      <button
        onClick={() => onCreateLadder(data.symbol)}
        className="w-full bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold py-2.5 rounded-xl text-sm transition-colors"
      >
        🪜 Create Profit Ladder for {data.symbol}
      </button>
    </div>
  )
}

function LadderProgress({ ladder, symbol }) {
  if (!ladder) return null
  const pct = Math.min((ladder.total_captured / ladder.daily_goal) * 100, 100)

  return (
    <div className="bg-dark-800 border border-brand-500/30 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target size={16} className="text-brand-500" />
          <span className="font-bold text-white">Profit Ladder — {symbol}</span>
        </div>
        {ladder.ai_calculated && (
          <span className="text-xs bg-purple-900/40 text-purple-400 border border-purple-800/50 px-2 py-0.5 rounded-full">
            🧠 AI Sized
          </span>
        )}
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>${ladder.total_captured.toFixed(2)} captured</span>
          <span>${ladder.daily_goal} goal</span>
        </div>
        <div className="h-3 bg-dark-600 rounded-full overflow-hidden">
          <div
            className="h-3 rounded-full transition-all duration-700"
            style={{
              width: `${pct}%`,
              background: ladder.is_complete
                ? 'linear-gradient(90deg,#00d4aa,#00b894)'
                : 'linear-gradient(90deg,#6366f1,#00d4aa)',
            }}
          />
        </div>
      </div>

      <p className="text-xs text-gray-400">{ladder.calculation_note}</p>

      {/* Completed rounds */}
      {ladder.completed_rounds?.length > 0 && (
        <div className="space-y-1">
          {ladder.completed_rounds.map((r, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <CheckCircle size={12} className="text-green-400" />
              <span className="text-gray-300">Round {r.round}</span>
              <span className="text-green-400 font-bold">+${r.profit}</span>
              <span className="text-gray-500 ml-auto">${r.cumulative} total</span>
            </div>
          ))}
        </div>
      )}

      {ladder.is_complete && (
        <div className="bg-green-900/30 border border-green-700 rounded-lg p-2 text-center">
          <p className="text-green-400 font-bold text-sm">🎯 Daily Goal Reached! Trading stopped.</p>
        </div>
      )}
    </div>
  )
}

export default function PeakBounce({ capital = 5000 }) {
  const [window,    setWindow]    = useState('2hour')
  const [symbol,    setSymbol]    = useState('AAPL')
  const [analysis,  setAnalysis]  = useState(null)
  const [candidates, setCandidates] = useState([])
  const [ladder,    setLadder]    = useState(null)
  const [loading,   setLoading]   = useState('')
  const [msg,       setMsg]       = useState('')
  const [bounceTarget, setBounceTarget] = useState('')
  const [useAI,     setUseAI]     = useState(true)
  const [tab,       setTab]       = useState('analyze')

  function flash(text) { setMsg(text); setTimeout(() => setMsg(''), 4000) }

  async function analyze() {
    if (!symbol) return
    setLoading('analyze')
    setAnalysis(null)
    try {
      const r = await api.post('/bounce/analyze', { symbol: symbol.toUpperCase(), window })
      setAnalysis(r.data)
    } catch(e) {
      flash(`❌ ${e.response?.data?.detail ?? e.message}`)
    } finally { setLoading('') }
  }

  async function scanCandidates() {
    setLoading('scan')
    try {
      const r = await api.get(`/bounce/scan?window=${window}`)
      setCandidates(r.data.candidates ?? [])
      flash(`✅ Scanned ${r.data.scanned} stocks — found ${r.data.found} with bounce patterns`)
    } catch(e) {
      flash(`❌ ${e.response?.data?.detail ?? e.message}`)
    } finally { setLoading('') }
  }

  async function createLadder(sym) {
    try {
      const target = useAI ? null : parseFloat(bounceTarget) || null
      const r = await api.post('/bounce/ladder/create', {
        symbol:        sym,
        bounce_target: target,
      })
      setLadder(r.data)
      flash(`✅ Ladder created for ${sym} — target $${r.data.bounce_target}/bounce`)
    } catch(e) {
      flash(`❌ ${e.response?.data?.detail ?? e.message}`)
    }
  }

  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
        <h2 className="font-black text-white text-lg flex items-center gap-2">
          <TrendingUp className="text-brand-500" size={20}/>
          Peak Bounce Profit Ladder
        </h2>
        <p className="text-xs text-gray-400 mt-1">
          Detects repeating peak/valley patterns, auto-sizes positions to hit your daily goal through repeated bounces.
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex gap-2">
        {[
          { id: 'analyze',    label: '🔬 Analyze Stock'  },
          { id: 'scan',       label: '📡 AI Scan Market' },
          { id: 'ladder',     label: '🪜 Ladder'         },
          { id: 'settings',   label: '⚙️ Settings'       },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
              tab === t.id ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {msg && <div className="p-3 bg-dark-700 rounded-lg text-sm text-center">{msg}</div>}

      {/* ── Analyze Tab ──────────────────────────────────────────────────────── */}
      {tab === 'analyze' && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())}
              placeholder="Symbol e.g. AAPL"
              className="flex-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500 font-mono uppercase"/>
            <button onClick={analyze} disabled={loading === 'analyze' || !symbol}
              className="px-4 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold text-sm rounded-xl disabled:opacity-50 transition-colors">
              {loading === 'analyze' ? <RefreshCw size={14} className="animate-spin"/> : '🔬 Analyze'}
            </button>
          </div>

          {/* Window selector */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {Object.entries(WINDOWS).map(([key, label]) => (
              <button key={key} onClick={() => setWindow(key)}
                className={`px-2 py-2 rounded-lg text-xs font-medium transition-colors text-center ${
                  window === key
                    ? 'bg-brand-500 text-dark-900'
                    : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
                }`}>
                {label}
              </button>
            ))}
          </div>

          {analysis && (
            analysis.found
              ? <PatternCard data={analysis} onCreateLadder={createLadder}/>
              : <div className="bg-dark-800 border border-dark-600 rounded-xl p-6 text-center">
                  <p className="text-4xl mb-2">📊</p>
                  <p className="text-white font-bold">{analysis.message}</p>
                  <p className="text-xs text-gray-400 mt-2">Try a different time window or stock</p>
                </div>
          )}
        </div>
      )}

      {/* ── Scan Tab ─────────────────────────────────────────────────────────── */}
      {tab === 'scan' && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <p className="text-sm text-gray-400 flex-1">
              AI scans your watchlist + top gainers for the best bounce patterns right now.
            </p>
            <button onClick={scanCandidates} disabled={loading === 'scan'}
              className="flex items-center gap-2 px-4 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold text-sm rounded-xl disabled:opacity-50 transition-colors">
              {loading === 'scan'
                ? <><RefreshCw size={14} className="animate-spin"/> Scanning…</>
                : '📡 AI Scan Now'
              }
            </button>
          </div>

          {candidates.length > 0 && (
            <div className="space-y-2">
              {candidates.map((c, i) => (
                <div key={c.symbol}
                  className={`flex items-center gap-3 p-3 rounded-xl border transition-all cursor-pointer ${
                    c.recommended
                      ? 'bg-green-900/10 border-green-800/50 hover:bg-green-900/20'
                      : 'bg-dark-800 border-dark-600 hover:bg-dark-700'
                  }`}
                  onClick={() => { setSymbol(c.symbol); setTab('analyze'); analyze() }}>

                  <span className="text-gray-500 text-xs w-5">{i+1}</span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-black text-white">{c.symbol}</span>
                      {c.recommended && (
                        <span className="text-xs bg-green-900/40 text-green-400 border border-green-800/50 px-1.5 py-0.5 rounded-full">
                          ✅ READY
                        </span>
                      )}
                      {c.flags?.map((f, fi) => (
                        <span key={fi} className="text-xs text-gray-400">{f}</span>
                      ))}
                    </div>
                    <div className="flex gap-3 text-xs text-gray-500 mt-0.5">
                      <span>Strength: {c.pattern_strength}/100</span>
                      <span>Success: {(c.success_rate * 100).toFixed(0)}%</span>
                      <span>Bounce: {c.bounce_pct?.toFixed(2)}%</span>
                    </div>
                  </div>

                  <div className="w-20">
                    <StrengthBar value={c.score} />
                  </div>

                  <span className="text-xs text-brand-500">→ Analyze</span>
                </div>
              ))}
            </div>
          )}

          {candidates.length === 0 && loading !== 'scan' && (
            <div className="text-center py-12 text-gray-500">
              <p className="text-3xl mb-2">📡</p>
              <p>Click "AI Scan Now" to find the best bounce stocks</p>
              <p className="text-xs mt-1">Requires bot to be running</p>
            </div>
          )}
        </div>
      )}

      {/* ── Ladder Tab ───────────────────────────────────────────────────────── */}
      {tab === 'ladder' && (
        <div className="space-y-4">
          {ladder
            ? <LadderProgress ladder={ladder} symbol={ladder.symbol ?? symbol}/>
            : (
              <div className="text-center py-12 text-gray-500">
                <p className="text-3xl mb-2">🪜</p>
                <p>No active ladder. Analyze a stock and click "Create Profit Ladder".</p>
              </div>
            )
          }
        </div>
      )}

      {/* ── Settings Tab ─────────────────────────────────────────────────────── */}
      {tab === 'settings' && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-5">
          <h3 className="font-bold text-white">Bounce Settings</h3>

          {/* AI vs Manual target */}
          <div>
            <p className="text-sm text-gray-300 mb-3">Bounce Profit Target</p>
            <div className="grid grid-cols-2 gap-3">
              <button onClick={() => setUseAI(true)}
                className={`p-3 rounded-xl border text-left transition-all ${
                  useAI ? 'border-brand-500 bg-brand-500/10' : 'border-dark-600 hover:border-dark-500'
                }`}>
                <p className="text-sm font-bold text-white">🧠 AI Calculates</p>
                <p className="text-xs text-gray-400 mt-1">
                  AI dynamically sizes each bounce based on pattern, capital and remaining goal
                </p>
                {useAI && <p className="text-xs text-brand-500 mt-1">✓ Active</p>}
              </button>
              <button onClick={() => setUseAI(false)}
                className={`p-3 rounded-xl border text-left transition-all ${
                  !useAI ? 'border-yellow-500 bg-yellow-500/10' : 'border-dark-600 hover:border-dark-500'
                }`}>
                <p className="text-sm font-bold text-white">✋ I Set Target</p>
                <p className="text-xs text-gray-400 mt-1">
                  Set a fixed profit goal per bounce cycle
                </p>
                {!useAI && <p className="text-xs text-yellow-400 mt-1">✓ Active</p>}
              </button>
            </div>

            {!useAI && (
              <div className="mt-3">
                <label className="block text-xs text-gray-400 mb-1">Target profit per bounce ($)</label>
                <input type="number" value={bounceTarget}
                  onChange={e => setBounceTarget(e.target.value)}
                  placeholder="e.g. 25"
                  className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500"/>
              </div>
            )}
          </div>

          {/* Default window */}
          <div>
            <p className="text-sm text-gray-300 mb-2">Default Time Window</p>
            <div className="grid grid-cols-1 gap-1.5">
              {Object.entries(WINDOWS).map(([key, label]) => (
                <button key={key} onClick={() => setWindow(key)}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                    window === key ? 'bg-brand-500 text-dark-900 font-bold' : 'bg-dark-700 text-gray-300 hover:bg-dark-600'
                  }`}>
                  <span>{label}</span>
                  {window === key && <span>✓</span>}
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-500 mt-2">
              ⭐ 2-hour is recommended — enough data for reliable patterns without being too stale
            </p>
          </div>

          {/* Capital info */}
          <div className="bg-dark-700 rounded-xl p-3 text-xs space-y-1 text-gray-400">
            <p>💰 Capital: <span className="text-white">${capital.toLocaleString()}</span></p>
            <p>📊 Max position: <span className="text-white">${(capital * 0.2).toLocaleString()} (20%)</span></p>
            <p>🔄 Execution cost model: <span className="text-white">0.05% slippage per side (Alpaca)</span></p>
          </div>
        </div>
      )}
    </div>
  )
}

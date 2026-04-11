import { useState, useEffect, useCallback } from 'react'
import { api } from '../hooks/useAuth'
import FloatingPanel from './FloatingPanel'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Legend
} from 'recharts'
import { Play, Pause, Square, RefreshCw, Zap, TrendingUp, Target, Brain } from 'lucide-react'

// ── Engine mini card (shown inside each panel) ────────────────────────────────

function EngineCard({ engine, name, color, onPause, onResume, onStop }) {
  if (!engine) return (
    <div className="p-4 text-center text-gray-500 text-sm">
      Not initialized — click Start Dual Mode
    </div>
  )

  const statusColor = {
    running: 'text-green-400', paused: 'text-yellow-400',
    stopped: 'text-red-400',   idle: 'text-gray-400',
  }[engine.status] ?? 'text-gray-400'

  const pnlColor = engine.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <div className="p-4 space-y-4">

      {/* P&L Hero */}
      <div className="text-center">
        <p className={`text-3xl font-black ${pnlColor}`}>
          {engine.realized_pnl >= 0 ? '+' : ''}${engine.realized_pnl.toFixed(2)}
        </p>
        <p className="text-xs text-gray-400 mt-0.5">
          today's realized P&L
        </p>
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Progress</span>
          <span>${engine.daily_target} target</span>
        </div>
        <div className="h-2.5 bg-dark-600 rounded-full overflow-hidden">
          <div
            className="h-2.5 rounded-full transition-all duration-700"
            style={{
              width: `${Math.min(engine.progress_pct, 100)}%`,
              background: engine.is_target_hit
                ? 'linear-gradient(90deg,#00d4aa,#00b894)'
                : `linear-gradient(90deg,${color}80,${color})`,
            }}
          />
        </div>
        <p className="text-xs text-gray-500 mt-1 text-right">{engine.progress_pct}%</p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        {[
          { label: 'Trades',   value: engine.trade_count },
          { label: 'Win Rate', value: `${engine.win_rate}%` },
          { label: 'Capital',  value: `$${engine.capital?.toLocaleString()}` },
        ].map(({ label, value }) => (
          <div key={label} className="bg-dark-700 rounded-lg p-2">
            <p className="text-gray-500">{label}</p>
            <p className="font-bold text-white">{value}</p>
          </div>
        ))}
      </div>

      {/* Status */}
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${
          engine.status === 'running' ? 'bg-green-400 animate-pulse' :
          engine.status === 'paused'  ? 'bg-yellow-400' : 'bg-red-500'
        }`}/>
        <span className={`text-xs font-bold uppercase ${statusColor}`}>
          {engine.status}
        </span>
        {engine.stop_reason && (
          <span className="text-xs text-gray-500 ml-1">— {engine.stop_reason}</span>
        )}
      </div>

      {/* Last trade */}
      {engine.last_trade && (
        <div className="bg-dark-700 rounded-lg px-3 py-1.5 text-xs text-gray-300">
          Last: {engine.last_trade}
        </div>
      )}

      {/* Recent trades */}
      {engine.recent_trades?.length > 0 && (
        <div className="space-y-1">
          {engine.recent_trades.map((t, i) => (
            <div key={i} className="flex justify-between text-xs">
              <span className="text-gray-400">{t.symbol}</span>
              <span className={t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                {t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Controls */}
      <div className="flex gap-2">
        {engine.status === 'running' ? (
          <button onClick={onPause}
            className="flex-1 flex items-center justify-center gap-1 py-2 bg-yellow-800/40 hover:bg-yellow-800/70 text-yellow-400 border border-yellow-800/50 rounded-lg text-xs font-bold transition-colors">
            <Pause size={12}/> Pause
          </button>
        ) : engine.status === 'paused' ? (
          <button onClick={onResume}
            className="flex-1 flex items-center justify-center gap-1 py-2 bg-green-800/40 hover:bg-green-800/70 text-green-400 border border-green-800/50 rounded-lg text-xs font-bold transition-colors">
            <Play size={12}/> Resume
          </button>
        ) : null}
        <button onClick={onStop}
          className="flex items-center justify-center gap-1 px-3 py-2 bg-red-900/30 hover:bg-red-900/60 text-red-400 border border-red-800/50 rounded-lg text-xs font-bold transition-colors">
          <Square size={12}/> Stop
        </button>
      </div>
    </div>
  )
}

// ── Combined chart ─────────────────────────────────────────────────────────────

function CombinedChart({ history }) {
  if (!history || history.length < 2) {
    return (
      <div className="flex items-center justify-center h-32 text-gray-500 text-xs">
        Start both engines to see live P&L chart
      </div>
    )
  }

  const data = history.map(h => ({
    time:    new Date(h.time).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}),
    Scalper: parseFloat(h.scalper?.toFixed(2) ?? 0),
    Bounce:  parseFloat(h.bounce?.toFixed(2)  ?? 0),
    Total:   parseFloat(h.total?.toFixed(2)   ?? 0),
  }))

  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={data} margin={{ top: 5, right: 5, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="gScalper" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.4}/>
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
          </linearGradient>
          <linearGradient id="gBounce" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.4}/>
            <stop offset="95%" stopColor="#f59e0b" stopOpacity={0}/>
          </linearGradient>
          <linearGradient id="gTotal" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="#00d4aa" stopOpacity={0.4}/>
            <stop offset="95%" stopColor="#00d4aa" stopOpacity={0}/>
          </linearGradient>
        </defs>
        <XAxis dataKey="time" tick={{ fill:'#6b7280', fontSize:9 }} tickLine={false}/>
        <YAxis tick={{ fill:'#6b7280', fontSize:9 }} tickLine={false} axisLine={false}
               tickFormatter={v=>`$${v}`} width={40}/>
        <Tooltip
          contentStyle={{ background:'#111827', border:'1px solid #374151', borderRadius:8 }}
          formatter={(v,n) => [`$${v}`, n]}/>
        <Legend wrapperStyle={{ fontSize:10, color:'#9ca3af' }}/>
        <Area type="monotone" dataKey="Scalper" stroke="#6366f1" fill="url(#gScalper)" strokeWidth={1.5} dot={false}/>
        <Area type="monotone" dataKey="Bounce"  stroke="#f59e0b" fill="url(#gBounce)"  strokeWidth={1.5} dot={false}/>
        <Area type="monotone" dataKey="Total"   stroke="#00d4aa" fill="url(#gTotal)"   strokeWidth={2}   dot={false}/>
      </AreaChart>
    </ResponsiveContainer>
  )
}

// ── Main dual dashboard ────────────────────────────────────────────────────────

export default function DualEngineDashboard({ capital = 5000 }) {
  const [summary,  setSummary]  = useState(null)
  const [loading,  setLoading]  = useState('')
  const [msg,      setMsg]      = useState('')
  const [panels,   setPanels]   = useState({
    combined: true, scalper: true, bounce: true,
  })
  const [zOrder, setZOrder] = useState({
    combined: 103, scalper: 102, bounce: 101,
  })

  useEffect(() => {
    load()
    const iv = setInterval(load, 3000)
    return () => clearInterval(iv)
  }, [])

  async function load() {
    try {
      const r = await api.get('/dual/summary')
      setSummary(r.data)
    } catch {}
  }

  function flash(m) { setMsg(m); setTimeout(() => setMsg(''), 3000) }

  function focusPanel(id) {
    setZOrder(z => {
      const maxZ = Math.max(...Object.values(z))
      return { ...z, [id]: maxZ + 1 }
    })
  }

  async function startDual() {
    setLoading('start')
    try {
      await api.post('/dual/start', { market_regime: 'unknown', sentiment: 0 })
      flash('✅ Both engines started!')
      load()
    } catch(e) { flash(`❌ ${e.response?.data?.detail ?? e.message}`) }
    finally { setLoading('') }
  }

  async function stopAll() {
    try { await api.post('/dual/stop'); flash('⛔ Both engines stopped'); load() }
    catch(e) { flash(`❌ ${e.message}`) }
  }

  async function pauseEngine(engine) {
    try { await api.post('/dual/pause', { engine }); load() } catch {}
  }
  async function resumeEngine(engine) {
    try { await api.post('/dual/resume', { engine }); load() } catch {}
  }
  async function stopEngine(engine) {
    try { await api.post('/dual/pause', { engine }); load() } catch {}
  }

  async function resplit() {
    setLoading('resplit')
    try {
      await api.post('/dual/resplit', { market_regime:'unknown', sentiment:0 })
      flash('✅ AI recalculated capital split')
      load()
    } catch(e) { flash(`❌ ${e.message}`) }
    finally { setLoading('') }
  }

  const s = summary
  const combinedPnl = s?.total_pnl ?? 0
  const combinedGoal = s?.total_goal ?? 250
  const pnlColor = combinedPnl >= 0 ? 'text-green-400' : 'text-red-400'

  return (
    <div className="space-y-5">

      {/* Controls bar */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-4 space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <h2 className="font-black text-white flex items-center gap-2">
            <Zap className="text-brand-500" size={18}/> Dual Engine Mode
          </h2>

          {s?.initialized && (
            <div className="flex items-center gap-2 ml-2">
              <div className="text-xs bg-dark-700 px-2 py-1 rounded-lg text-gray-300">
                🤖 Scalper: <span className="text-purple-400 font-bold">{s.split?.scalper?.pct}%</span>
              </div>
              <div className="text-xs bg-dark-700 px-2 py-1 rounded-lg text-gray-300">
                📉 Bounce: <span className="text-yellow-400 font-bold">{s.split?.bounce?.pct}%</span>
              </div>
            </div>
          )}

          <div className="flex gap-2 ml-auto">
            {/* Panel toggles */}
            {['combined','scalper','bounce'].map(p => (
              <button key={p} onClick={() => setPanels(v => ({...v,[p]:!v[p]}))}
                className={`text-xs px-2 py-1 rounded-lg transition-colors capitalize ${
                  panels[p] ? 'bg-brand-500 text-dark-900 font-bold' : 'bg-dark-700 text-gray-400'
                }`}>
                {p === 'combined' ? '📊' : p === 'scalper' ? '🤖' : '📉'} {p}
              </button>
            ))}
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex gap-2 flex-wrap">
          {!s?.initialized ? (
            <button onClick={startDual} disabled={loading === 'start'}
              className="flex items-center gap-2 px-5 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-black rounded-xl text-sm disabled:opacity-50 transition-colors">
              <Play size={15}/> {loading === 'start' ? 'Starting…' : 'Start Dual Mode'}
            </button>
          ) : (
            <>
              <button onClick={stopAll}
                className="flex items-center gap-2 px-4 py-2 bg-red-900/40 hover:bg-red-900/70 text-red-400 border border-red-800/50 rounded-xl text-sm font-bold transition-colors">
                <Square size={13}/> Stop All
              </button>
              <button onClick={resplit} disabled={loading === 'resplit'}
                className="flex items-center gap-2 px-4 py-2 bg-dark-700 hover:bg-dark-600 text-gray-300 rounded-xl text-sm transition-colors">
                <Brain size={13}/> {loading === 'resplit' ? 'Recalculating…' : 'AI Resplit'}
              </button>
              <button onClick={load}
                className="flex items-center gap-2 px-3 py-2 bg-dark-700 hover:bg-dark-600 text-gray-400 rounded-xl text-sm transition-colors">
                <RefreshCw size={13}/>
              </button>
            </>
          )}
        </div>

        {msg && <p className="text-sm text-center">{msg}</p>}

        {/* AI split reasoning */}
        {s?.split?.reasons?.length > 0 && (
          <div className="bg-dark-700 rounded-lg p-2.5">
            <p className="text-xs font-bold text-brand-500 mb-1">🧠 AI Split Reasoning</p>
            {s.split.reasons.map((r, i) => (
              <p key={i} className="text-xs text-gray-400">• {r}</p>
            ))}
          </div>
        )}
      </div>

      {/* Static combined summary card (always visible) */}
      {s?.initialized && (
        <div className="bg-dark-800 border border-brand-500/30 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold text-white flex items-center gap-2">
              <Target size={16} className="text-brand-500"/> Combined Daily P&L
            </h3>
            <span className={`text-2xl font-black ${pnlColor}`}>
              {combinedPnl >= 0 ? '+' : ''}${combinedPnl.toFixed(2)}
            </span>
          </div>

          {/* Master progress bar */}
          <div className="h-3 bg-dark-600 rounded-full overflow-hidden mb-1">
            <div
              className="h-3 rounded-full transition-all duration-700"
              style={{
                width: `${Math.min(s.progress_pct, 100)}%`,
                background: s.progress_pct >= 100
                  ? 'linear-gradient(90deg,#00d4aa,#00b894)'
                  : 'linear-gradient(90deg,#6366f1,#f59e0b,#00d4aa)',
              }}
            />
          </div>
          <div className="flex justify-between text-xs text-gray-400">
            <span>{s.progress_pct}% toward goal</span>
            <span>Target: ${combinedGoal}</span>
          </div>

          {/* Mini combined chart */}
          <div className="mt-3">
            <CombinedChart history={s.pnl_history}/>
          </div>
        </div>
      )}

      {/* Instructions when not started */}
      {!s?.initialized && (
        <div className="text-center py-16 text-gray-500">
          <Zap size={40} className="mx-auto mb-3 opacity-40"/>
          <p className="text-white font-bold mb-1">Dual Engine Mode</p>
          <p className="text-sm">AI splits your capital between two strategies running simultaneously.</p>
          <p className="text-sm mt-1">Make sure the main bot is running first, then click Start Dual Mode.</p>
        </div>
      )}

      {/* Hint about floating panels */}
      {s?.initialized && (
        <p className="text-xs text-gray-500 text-center">
          Use the panel toggles above to show/hide floating panels · Drag panels by their title bar
        </p>
      )}

      {/* ── Floating Panels ──────────────────────────────────────────────────── */}
      {s?.initialized && panels.scalper && (
        <FloatingPanel
          id="scalper"
          title="AI Scalper Engine"
          icon="🤖"
          color="#6366f1"
          defaultPos={{ x: 20, y: 300 }}
          defaultSize={{ w: 360 }}
          zIndex={zOrder.scalper}
          onFocus={() => focusPanel('scalper')}
          onClose={() => setPanels(v => ({...v, scalper: false}))}
        >
          <EngineCard
            engine={s.scalper}
            name="AI Scalper"
            color="#6366f1"
            onPause={() => pauseEngine('scalper')}
            onResume={() => resumeEngine('scalper')}
            onStop={() => stopEngine('scalper')}
          />
        </FloatingPanel>
      )}

      {s?.initialized && panels.bounce && (
        <FloatingPanel
          id="bounce"
          title="Peak Bounce Engine"
          icon="📉"
          color="#f59e0b"
          defaultPos={{ x: 420, y: 300 }}
          defaultSize={{ w: 360 }}
          zIndex={zOrder.bounce}
          onFocus={() => focusPanel('bounce')}
          onClose={() => setPanels(v => ({...v, bounce: false}))}
        >
          <EngineCard
            engine={s.bounce}
            name="Peak Bounce"
            color="#f59e0b"
            onPause={() => pauseEngine('bounce')}
            onResume={() => resumeEngine('bounce')}
            onStop={() => stopEngine('bounce')}
          />
        </FloatingPanel>
      )}

      {s?.initialized && panels.combined && (
        <FloatingPanel
          id="combined"
          title="Combined Performance"
          icon="📊"
          color="#00d4aa"
          defaultPos={{ x: 820, y: 300 }}
          defaultSize={{ w: 380 }}
          zIndex={zOrder.combined}
          onFocus={() => focusPanel('combined')}
          onClose={() => setPanels(v => ({...v, combined: false}))}
        >
          <div className="p-4 space-y-4">
            <div className="text-center">
              <p className={`text-3xl font-black ${pnlColor}`}>
                {combinedPnl >= 0 ? '+' : ''}${combinedPnl.toFixed(2)}
              </p>
              <p className="text-xs text-gray-400">combined today</p>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="bg-dark-700 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-400">🤖 Scalper</p>
                <p className={`text-lg font-black ${(s.scalper?.realized_pnl??0)>=0?'text-green-400':'text-red-400'}`}>
                  {(s.scalper?.realized_pnl??0)>=0?'+':''}${(s.scalper?.realized_pnl??0).toFixed(2)}
                </p>
                <p className="text-xs text-purple-400">{s.split?.scalper?.pct}% capital</p>
              </div>
              <div className="bg-dark-700 rounded-lg p-3 text-center">
                <p className="text-xs text-gray-400">📉 Bounce</p>
                <p className={`text-lg font-black ${(s.bounce?.realized_pnl??0)>=0?'text-green-400':'text-red-400'}`}>
                  {(s.bounce?.realized_pnl??0)>=0?'+':''}${(s.bounce?.realized_pnl??0).toFixed(2)}
                </p>
                <p className="text-xs text-yellow-400">{s.split?.bounce?.pct}% capital</p>
              </div>
            </div>

            <div className="h-2 bg-dark-600 rounded-full overflow-hidden">
              <div className="h-2 rounded-full transition-all"
                style={{
                  width:`${Math.min(s.progress_pct,100)}%`,
                  background:'linear-gradient(90deg,#6366f1,#f59e0b,#00d4aa)'
                }}/>
            </div>
            <p className="text-xs text-center text-gray-400">
              {s.progress_pct}% · ${combinedPnl.toFixed(2)} of ${combinedGoal} goal
            </p>

            <CombinedChart history={s.pnl_history}/>
          </div>
        </FloatingPanel>
      )}
    </div>
  )
}

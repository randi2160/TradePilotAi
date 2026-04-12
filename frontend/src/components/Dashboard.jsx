import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, Target, Activity, DollarSign, BarChart2, Zap, Brain } from 'lucide-react'
import { api } from '../hooks/useAuth'
import LiveActivity from './LiveActivity'

// ── Helpers ───────────────────────────────────────────────────────────────────
function pnlStr(val) {
  const n = parseFloat(val) || 0
  return (n >= 0 ? '+$' : '-$') + Math.abs(n).toFixed(2)
}

function cls(...args) { return args.filter(Boolean).join(' ') }

// ── Stat Card ─────────────────────────────────────────────────────────────────
function StatCard({ icon: Icon, label, value, sub, color, bg }) {
  return (
    <div className={cls('bg-dark-800 border border-dark-600 rounded-xl p-4 flex gap-3 items-start', bg)}>
      <div className="bg-dark-700 rounded-lg p-2 mt-0.5 flex-shrink-0">
        <Icon size={16} className="text-brand-500" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
        <p className={cls('text-lg font-bold truncate', color || 'text-white')}>{value}</p>
        {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

// ── Strategy Panel ────────────────────────────────────────────────────────────
function StrategyPanel({ title, icon, accentColor, engine, stats }) {
  if (!engine && !stats) return null
  const pnl      = parseFloat(engine?.realized_pnl  ?? stats?.realized_pnl  ?? 0)
  const target   = parseFloat(engine?.daily_target   ?? stats?.target_max    ?? 100)
  const progress = parseFloat(engine?.progress_pct   ?? stats?.progress_pct  ?? 0)
  const trades   = engine?.trade_count  ?? stats?.trade_count  ?? 0
  const winRate  = parseFloat(engine?.win_rate ?? stats?.win_rate ?? 0)
  const capital  = parseFloat(engine?.capital  ?? stats?.capital  ?? 0)
  const status   = engine?.status ?? (stats ? 'active' : 'idle')

  const dotClass = status === 'running' ? 'bg-green-400 animate-pulse' : status === 'paused' ? 'bg-yellow-400' : 'bg-gray-500'

  return (
    <div className="bg-dark-800 border rounded-xl overflow-hidden flex-1 min-w-[260px]"
      style={{ borderColor: accentColor + '40' }}>
      <div className="px-4 py-3 border-b border-dark-600 flex items-center justify-between"
        style={{ background: accentColor + '12' }}>
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <span className="font-bold text-white text-sm">{title}</span>
        </div>
        <div className={cls('w-2 h-2 rounded-full', dotClass)} />
      </div>
      <div className="p-4 space-y-4">
        <div className="text-center">
          <p className={cls('text-3xl font-black', pnl >= 0 ? 'text-green-400' : 'text-red-400')}>
            {pnlStr(pnl)}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">today&apos;s P&L</p>
        </div>
        <div>
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>Progress</span>
            <span>{'$'}{target} target</span>
          </div>
          <div className="h-2 bg-dark-600 rounded-full overflow-hidden">
            <div className="h-2 rounded-full transition-all duration-700"
              style={{ width: Math.min(progress, 100) + '%', background: accentColor }} />
          </div>
          <p className="text-xs text-right text-gray-500 mt-0.5">{progress.toFixed(1)}%</p>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <div className="bg-dark-700 rounded-lg p-2">
            <p className="text-gray-400">Capital</p>
            <p className="font-bold text-white">{'$'}{capital.toLocaleString()}</p>
          </div>
          <div className="bg-dark-700 rounded-lg p-2">
            <p className="text-gray-400">Trades</p>
            <p className="font-bold text-white">{trades}</p>
          </div>
          <div className="bg-dark-700 rounded-lg p-2">
            <p className="text-gray-400">Win %</p>
            <p className={cls('font-bold', winRate >= 50 ? 'text-green-400' : 'text-red-400')}>
              {winRate.toFixed(0)}%
            </p>
          </div>
        </div>
        {(engine?.recent_trades ?? []).slice(0, 3).map((t, i) => (
          <div key={i} className="flex justify-between text-xs">
            <span className="text-gray-300">{t.symbol}</span>
            <span className={t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>{pnlStr(t.pnl)}</span>
          </div>
        ))}
        {status === 'stopped' && engine?.stop_reason && (
          <p className="text-xs text-center text-yellow-400">{engine.stop_reason}</p>
        )}
      </div>
    </div>
  )
}

// ── Live Engine Status Banner ─────────────────────────────────────────────────
function LiveEngineStatus({ data, engineStatus, dualSummary, todayStats }) {
  const [starting, setStarting] = useState(false)
  const [msg,      setMsg]      = useState('')

  const botRunning    = data?.bot_status === 'running'
  const cryptoRunning = engineStatus?.crypto_running === true
  const cryptoState   = engineStatus?.crypto?.state || 'idle'
  const savedMode     = engineStatus?.mode || 'stocks_only'

  const now       = new Date()
  const isWeekend = now.getDay() === 0 || now.getDay() === 6
  const etHour    = (now.getUTCHours() - 5 + 24) % 24
  const marketOpen= !isWeekend && etHour >= 9 && etHour < 16

  const CRYPTO_LABEL = {
    idle: 'Waiting to scan', scanning: 'Scanning markets…',
    candidate_ranked: 'Candidate found', sizing: 'Calculating position…',
    order_pending: 'Order pending…', position_open: 'In a trade',
    exit_pending: 'Exiting trade…', funds_refreshing: 'Refreshing funds…',
    ready_for_reentry: 'Ready for next trade', locked_profit_mode: 'Profit locked',
    stopped_for_day: 'Done for today', error: 'Error — check logs',
  }

  async function startCrypto() {
    setStarting(true)
    try {
      const r = await api.post('/bot/engine-mode', {
        mode:         savedMode === 'stocks_only' ? 'hybrid' : savedMode,
        crypto_alloc: engineStatus?.crypto_alloc ?? 0.30,
      })
      setMsg('OK: ' + r.data.message)
      setTimeout(() => setMsg(''), 5000)
    } catch (e) {
      setMsg('ERR: ' + (e.response?.data?.detail || e.message))
    } finally { setStarting(false) }
  }

  async function stopCrypto() {
    setStarting(true)
    try {
      await api.post('/bot/engine-stop')
      setMsg('Crypto engine stopped')
      setTimeout(() => setMsg(''), 3000)
    } catch (e) { setMsg('ERR: ' + e.message) }
    finally { setStarting(false) }
  }

  // Overall status
  let oLabel, oColor, oBg, oDot
  if (botRunning && cryptoRunning)  { oLabel='Full Hybrid Active';    oColor='text-green-400';  oBg='bg-green-900/10 border-green-800/30';    oDot='bg-green-400' }
  else if (cryptoRunning)           { oLabel='Crypto Engine Active';  oColor='text-brand-400';  oBg='bg-brand-500/10 border-brand-500/30';    oDot='bg-brand-400' }
  else if (botRunning)              { oLabel='Stock Engine Active';   oColor='text-blue-400';   oBg='bg-blue-900/10 border-blue-800/30';      oDot='bg-blue-400'  }
  else                              { oLabel='All Engines Idle';      oColor='text-gray-400';   oBg='bg-dark-700 border-dark-600';            oDot='bg-gray-600'  }

  const msgBg = msg.startsWith('OK') ? 'bg-green-900/20 text-green-400' : msg.startsWith('ERR') ? 'bg-red-900/20 text-red-400' : 'bg-dark-700 text-gray-400'

  return (
    <div className={cls('rounded-xl border p-4 space-y-3', oBg)}>
      {/* Header */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <div className={cls('w-2.5 h-2.5 rounded-full', oDot, (botRunning || cryptoRunning) ? 'animate-pulse' : '')} />
          <span className={cls('text-sm font-black', oColor)}>{oLabel}</span>
        </div>
        <span className={cls('text-xs px-2 py-0.5 rounded-full border font-medium',
          isWeekend ? 'text-gray-500 bg-dark-700 border-dark-600' :
          marketOpen ? 'text-green-400 bg-green-900/20 border-green-800/40' :
          'text-yellow-400 bg-yellow-900/20 border-yellow-800/40')}>
          {isWeekend ? '📅 Weekend — Markets Closed' : marketOpen ? '🟢 Market Open' : '🌙 After Hours'}
        </span>
        {cryptoRunning && (
          <span className="text-xs px-2 py-0.5 rounded-full border text-brand-400 bg-brand-500/10 border-brand-500/30 font-medium animate-pulse">
            {'₿'} {CRYPTO_LABEL[cryptoState] || cryptoState}
          </span>
        )}
      </div>

      {/* Start / Stop button */}
      {savedMode !== 'stocks_only' && (
        <div className="flex gap-3 items-center flex-wrap">
          {!cryptoRunning ? (
            <button onClick={startCrypto} disabled={starting}
              className="flex items-center gap-2 px-5 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-black rounded-xl text-sm disabled:opacity-50">
              <Zap size={14} />
              {starting ? 'Starting…' : 'Start ' + (savedMode === 'hybrid' ? 'Hybrid' : 'Crypto') + ' Engine'}
            </button>
          ) : (
            <button onClick={stopCrypto} disabled={starting}
              className="flex items-center gap-2 px-5 py-2.5 bg-red-900/40 hover:bg-red-900/60 text-red-400 border border-red-800/40 font-bold rounded-xl text-sm disabled:opacity-50">
              {starting ? 'Stopping…' : '⏹ Stop Crypto Engine'}
            </button>
          )}
          <span className="text-xs text-gray-500">
            {savedMode === 'hybrid'
              ? 'Hybrid mode · ' + Math.round((engineStatus?.crypto_alloc || 0.3) * 100) + '% crypto'
              : 'Crypto only · 24/7 · No PDT'}
          </span>
        </div>
      )}

      {msg && <div className={cls('text-xs p-2.5 rounded-lg', msgBg)}>{msg}</div>}

      {/* Error detail */}
      {cryptoRunning && cryptoState === 'error' && (
        <div className="flex items-start gap-3 p-3 bg-red-900/20 border border-red-800/40 rounded-xl">
          <span className="text-red-400 flex-shrink-0">⚠️</span>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-bold text-red-400 mb-1">Crypto Engine Error</div>
            <div className="text-xs text-red-300/80 font-mono break-all">
              {engineStatus?.crypto?.last_error || 'Check the Activity log for details.'}
            </div>
            <button onClick={() => window.dispatchEvent(new CustomEvent('navigate', { detail: 'activity' }))}
              className="mt-2 text-xs px-3 py-1.5 bg-red-900/30 hover:bg-red-900/50 text-red-400 border border-red-800/40 rounded-lg">
              📋 View Activity Logs →
            </button>
          </div>
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <div className={cls('rounded-lg p-2.5 text-center border', botRunning ? 'bg-blue-900/10 border-blue-800/30' : 'bg-dark-800 border-dark-600')}>
          <div className="text-xs text-gray-500">📈 Stock Bot</div>
          <div className={cls('text-xs font-bold mt-0.5', botRunning ? 'text-green-400' : 'text-gray-500')}>
            {botRunning ? (marketOpen ? '● Trading' : '● Waiting for open') : '○ Stopped'}
          </div>
        </div>
        <div className={cls('rounded-lg p-2.5 text-center border', cryptoRunning ? 'bg-brand-500/10 border-brand-500/30' : 'bg-dark-800 border-dark-600')}>
          <div className="text-xs text-gray-500">₿ Crypto</div>
          <div className={cls('text-xs font-bold mt-0.5', cryptoRunning ? 'text-brand-400' : 'text-gray-500')}>
            {cryptoRunning ? '● ' + (cryptoState || '').replace(/_/g, ' ') : '○ Not running'}
          </div>
        </div>
        <div className="bg-dark-800 border border-dark-600 rounded-lg p-2.5 text-center">
          <div className="text-xs text-gray-500">Today&apos;s P&L</div>
          <div className={cls('text-sm font-black mt-0.5', (data?.realized_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400')}>
            {pnlStr(data?.realized_pnl ?? 0)}
          </div>
        </div>
        <div className="bg-dark-800 border border-dark-600 rounded-lg p-2.5 text-center">
          <div className="text-xs text-gray-500">Trades Today</div>
          <div className="text-sm font-black text-white mt-0.5">
            {data?.trade_count ?? todayStats?.trade_count ?? 0}
          </div>
          <div className="text-xs text-gray-600">
            {isWeekend && !cryptoRunning ? 'Start crypto to trade' : isWeekend && cryptoRunning ? 'Crypto scanning' : marketOpen ? 'Live' : 'After hours'}
          </div>
        </div>
      </div>

      {/* Crypto session row */}
      {cryptoRunning && engineStatus?.crypto && (
        <div className="flex gap-4 pt-2 border-t border-dark-700 text-xs flex-wrap">
          <span className="text-gray-500">Crypto →</span>
          <span className={cls('font-bold', (engineStatus.crypto.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400')}>
            P&L: {pnlStr(engineStatus.crypto.realized_pnl || 0)}
          </span>
          <span className="text-gray-500">To target: <span className="text-brand-400 font-bold">{'$'}{(engineStatus.crypto.remaining_to_min || 0).toFixed(2)}</span></span>
          <span className="text-gray-500">Cycle: <span className="text-white font-bold">{'#'}{engineStatus.crypto.cycle || 0}</span></span>
          <span className="text-gray-500">Positions: <span className="text-white font-bold">{engineStatus.crypto.open_positions || 0}</span></span>
          {engineStatus.crypto.locked_floor != null && (
            <span className="text-green-400 font-bold">🔒 Floor: {'$'}{engineStatus.crypto.locked_floor.toFixed(2)}</span>
          )}
        </div>
      )}

      {isWeekend && !cryptoRunning && savedMode !== 'stocks_only' && (
        <p className="text-xs text-yellow-400">
          It&apos;s the weekend — stock markets are closed. Click Start Hybrid Engine above to trade crypto 24/7 right now.
        </p>
      )}
    </div>
  )
}

// ── Crypto Live Panel ─────────────────────────────────────────────────────────
function CryptoLivePanel({ engineStatus }) {
  if (!engineStatus?.crypto_running) return null
  const crypto = engineStatus?.crypto
  if (!crypto) return null

  const scans    = crypto.scan_results || []
  const openList = crypto.open_position_list || []
  const state    = crypto.state || 'idle'

  const STATE_ICON = {
    idle: '🔍', scanning: '📡', candidate_ranked: '🎯',
    sizing: '📐', order_pending: '📤', position_open: '📈',
    exit_pending: '📤', funds_refreshing: '🔄',
    ready_for_reentry: '✅', locked_profit_mode: '🔒',
    stopped_for_day: '🏁', error: '⚠️',
  }

  return (
    <div className="bg-dark-800 border border-brand-500/30 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="bg-brand-500/10 border-b border-brand-500/20 px-4 py-3 flex items-center gap-3">
        <span className="text-lg">{STATE_ICON[state] || '₿'}</span>
        <span className="font-bold text-white text-sm">Crypto Engine — Live View</span>
        <span className="text-xs text-gray-500">Cycle #{crypto.cycle || 0} · Every 30s</span>
        <div className="ml-auto flex items-center gap-3 text-xs">
          <span className="text-gray-500">Buying power: <span className="text-white font-bold">{'$'}{(crypto.buying_power || 0).toLocaleString('en-US', { maximumFractionDigits: 0 })}</span></span>
          <span className={cls('font-bold', (crypto.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400')}>
            P&L: {pnlStr(crypto.realized_pnl || 0)}
          </span>
        </div>
      </div>

      <div className="p-4 space-y-4">

        {/* Open positions */}
        {openList.length > 0 && (
          <div>
            <p className="text-xs font-bold text-white mb-2">📈 Open Crypto Positions</p>
            <div className="space-y-2">
              {openList.map((pos, i) => (
                <div key={i} className="flex items-center gap-3 p-3 bg-green-900/15 border border-green-800/30 rounded-xl">
                  <span className="font-black text-white text-base">{pos.symbol}</span>
                  <span className="text-xs bg-green-900/30 text-green-400 px-2 py-0.5 rounded font-bold">{pos.side}</span>
                  <span className="text-xs text-gray-400">Qty: <span className="text-white font-bold">{pos.qty}</span></span>
                  <span className="text-xs text-gray-400">Entry: <span className="text-brand-400 font-bold">{'$'}{(pos.entry || 0).toFixed(4)}</span></span>
                  <span className="text-xs text-gray-400">Target: <span className="text-green-400 font-bold">{'$'}{(pos.target || 0).toFixed(4)}</span></span>
                  <span className="text-xs text-gray-400">Stop: <span className="text-red-400 font-bold">{'$'}{(pos.stop || 0).toFixed(4)}</span></span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Scan results */}
        {scans.length > 0 && (
          <div>
            <p className="text-xs font-bold text-white mb-2">
              📡 Last Scan Results
              <span className="text-gray-500 font-normal ml-2">— scored {scans.length} symbols, looking for score &gt; 60</span>
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {scans.map((s, i) => (
                <div key={i} className={cls('rounded-xl p-3 border text-center',
                  s.valid ? 'bg-green-900/15 border-green-700/50' : 'bg-dark-700 border-dark-600')}>
                  <div className="flex items-center justify-center gap-1 mb-1">
                    <span className="font-black text-white text-sm">{(s.symbol || '').split('/')[0]}</span>
                    {s.valid && <span className="text-xs text-green-400">✓</span>}
                  </div>
                  <div className="text-xs text-gray-500 mb-1">
                    {'$'}{(s.price || 0).toFixed(s.price > 100 ? 2 : 4)}
                  </div>
                  {/* Score bar */}
                  <div className="h-1.5 bg-dark-600 rounded-full overflow-hidden mb-1">
                    <div className={cls('h-1.5 rounded-full', s.score >= 60 ? 'bg-green-500' : s.score >= 40 ? 'bg-yellow-500' : 'bg-gray-600')}
                      style={{ width: Math.min(s.score, 100) + '%' }} />
                  </div>
                  <div className={cls('text-xs font-bold', s.score >= 60 ? 'text-green-400' : s.score >= 40 ? 'text-yellow-400' : 'text-gray-500')}>
                    Score: {s.score}
                  </div>
                  <div className="text-xs text-gray-600">
                    {s.momentum > 0 ? '▲' : '▼'} {Math.abs(s.momentum || 0).toFixed(2)}%
                  </div>
                </div>
              ))}
            </div>
            {scans.every(s => !s.valid) && (
              <p className="text-xs text-gray-500 text-center mt-2">
                No symbols above threshold yet — waiting for stronger momentum. Rescanning in 30s.
              </p>
            )}
          </div>
        )}

        {scans.length === 0 && state === 'idle' && (
          <div className="text-center py-4 text-gray-600">
            <p className="text-sm">First scan running… check back in 30 seconds</p>
          </div>
        )}
      </div>
    </div>
  )
}
export default function Dashboard({ data }) {
  const [dualSummary,  setDualSummary]  = useState(null)
  const [todayStats,   setTodayStats]   = useState(null)
  const [engineStatus, setEngineStatus] = useState(null)

  useEffect(() => {
    const load = () => {
      api.get('/dual/summary').then(r => setDualSummary(r.data)).catch(() => {})
      api.get('/analytics/today').then(r => setTodayStats(r.data)).catch(() => {})
      api.get('/bot/engine-status').then(r => setEngineStatus(r.data)).catch(() => {})
    }
    load()
    const iv = setInterval(load, 5000)
    return () => clearInterval(iv)
  }, [])

  if (!data) return (
    <div className="text-gray-400 p-8 text-center">
      <p className="text-4xl mb-2">📡</p>
      <p>Connecting to bot…</p>
    </div>
  )

  const pnl       = parseFloat(data.total_pnl    ?? data.realized_pnl ?? 0)
  const realized  = parseFloat(data.realized_pnl  ?? 0)
  const progress  = parseFloat(data.progress_pct  ?? 0)
  const targetMin = parseFloat(data.target_min    ?? data.settings?.daily_target_min ?? 100)
  const targetMax = parseFloat(data.target_max    ?? data.settings?.daily_target_max ?? 250)
  const capital   = parseFloat(data.capital       ?? data.settings?.capital ?? 5000)
  const winRate   = parseFloat(data.win_rate      ?? todayStats?.win_rate   ?? 0)
  const trades    = data.trade_count ?? todayStats?.trade_count ?? 0
  const equity    = capital + pnl
  const positions = data.positions ?? []
  const signals   = data.signals   ?? []
  const dualOn    = dualSummary?.initialized
  const combinedPnl = dualOn ? parseFloat(dualSummary.total_pnl ?? pnl) : pnl
  const activeSignals = signals.filter(s => s.signal !== 'HOLD' && s.signal !== 'WAIT')
  const totalReturn = capital > 0 ? ((equity - capital) / capital * 100).toFixed(2) : '0.00'

  return (
    <div className="space-y-5">

      <LiveEngineStatus
        data={data}
        engineStatus={engineStatus}
        dualSummary={dualSummary}
        todayStats={todayStats}
      />

      <CryptoLivePanel engineStatus={engineStatus} />

      {/* Master P&L */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5">
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">
              {dualOn ? 'Combined Strategy P&L' : "Today's P&L"}
            </p>
            <p className={cls('text-4xl font-black', combinedPnl >= 0 ? 'text-green-400' : 'text-red-400')}>
              {pnlStr(combinedPnl)}
            </p>
            <p className="text-sm text-gray-400 mt-1">
              Portfolio: <span className="text-white font-bold">{'$'}{equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-400">Daily Target</p>
            <p className="text-lg font-bold text-white">{'$'}{targetMin}–{'$'}{targetMax}</p>
            <p className="text-xs text-gray-500">Capital: {'$'}{capital.toLocaleString()}</p>
          </div>
        </div>
        <div className="w-full bg-dark-700 rounded-full h-3 overflow-hidden mb-2">
          <div className="h-3 rounded-full transition-all duration-700"
            style={{ width: Math.min(progress, 100) + '%', background: progress >= 100 ? 'linear-gradient(90deg,#00d4aa,#00b894)' : 'linear-gradient(90deg,#6366f1,#00d4aa)' }} />
        </div>
        <div className="flex justify-between text-xs text-gray-500">
          <span>{'$'}0</span>
          <span className="text-brand-500 font-medium">{'$'}{targetMin} min</span>
          <span>{'$'}{targetMax} max</span>
        </div>
        {data.min_target_hit && !data.locked_floor && <p className="mt-2 text-xs text-green-400 font-medium">✅ Minimum target hit! Protecting gains — trailing floor active.</p>}
        {data.locked_floor && (
          <div className="mt-2 flex items-center gap-3 text-xs">
            <span className="text-green-400 font-bold">🔒 Trailing Floor: {'$'}{(data.locked_floor).toFixed(2)}</span>
            <span className="text-gray-500">— Engine keeps trading. Stops only if P&L drops to floor.</span>
          </div>
        )}
        {data.max_target_hit && <p className="mt-2 text-xs text-brand-500 font-bold">🎯 MAX TARGET REACHED — Trailing lock protecting gains!</p>}
      </div>

      {/* Strategy Panels */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-gray-300">
            {dualOn ? '⚡ Dual Engine — Running Simultaneously' : '🤖 Trading Engine'}
          </h3>
          {!dualOn && (
            <button onClick={() => window.dispatchEvent(new CustomEvent('navigate', { detail: 'dual' }))}
              className="text-xs text-brand-500 hover:underline">Enable Dual Engine →</button>
          )}
        </div>
        <div className="flex gap-3 flex-wrap">
          <StrategyPanel title="AI Scalper" icon="🤖" accentColor="#6366f1"
            engine={dualOn ? dualSummary?.scalper : null}
            stats={!dualOn ? { realized_pnl: realized, target_max: targetMax, progress_pct: progress, trade_count: trades, win_rate: winRate, capital } : null}
          />
          {dualOn && <StrategyPanel title="Peak Bounce" icon="📉" accentColor="#f59e0b" engine={dualSummary?.bounce} stats={null} />}
          {!dualOn && (
            <div className="flex-1 min-w-[260px] bg-dark-800 border border-dashed border-dark-500 rounded-xl p-6 flex flex-col items-center justify-center gap-3 text-center">
              <Zap size={24} className="text-gray-600" />
              <div>
                <p className="text-sm font-bold text-gray-400">Peak Bounce Engine</p>
                <p className="text-xs text-gray-500 mt-1">Split capital between AI Scalper + Peak Bounce running simultaneously</p>
              </div>
              <button onClick={() => window.dispatchEvent(new CustomEvent('navigate', { detail: 'dual' }))}
                className="text-xs bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold px-4 py-2 rounded-lg">
                Enable Dual Engine
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Dual split reasoning */}
      {dualOn && (dualSummary?.split?.reasons ?? []).length > 0 && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-3">
          <p className="text-xs font-bold text-brand-500 mb-2 flex items-center gap-1">
            <Brain size={12} /> AI Capital Split Reasoning
          </p>
          <div className="flex gap-4 text-xs text-gray-400 mb-2">
            <span>🤖 Scalper: <strong className="text-purple-400">{dualSummary.split.scalper?.pct}%</strong></span>
            <span>📉 Bounce: <strong className="text-yellow-400">{dualSummary.split.bounce?.pct}%</strong></span>
          </div>
          {dualSummary.split.reasons.slice(0, 3).map((r, i) => <p key={i} className="text-xs text-gray-500">• {r}</p>)}
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard icon={DollarSign} label="Portfolio Value"
          value={'$' + equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}
          sub={totalReturn + '% total return'}
          color={equity >= capital ? 'text-green-400' : 'text-red-400'} />
        <StatCard icon={Activity} label="Win Rate Today"
          value={winRate + '%'}
          sub={trades + ' trade' + (trades !== 1 ? 's' : '') + ' today'}
          color={winRate >= 50 ? 'text-green-400' : 'text-red-400'} />
        <StatCard icon={TrendingUp} label="Active Signals"
          value={activeSignals.length}
          sub={activeSignals.slice(0, 2).map(s => s.symbol + ' ' + s.signal).join(' · ')}
          color={activeSignals.length > 0 ? 'text-brand-500' : 'text-gray-400'} />
        <StatCard icon={BarChart2} label="Open Positions"
          value={positions.length}
          sub={positions.slice(0, 2).map(p => p.symbol).join(', ') || 'None'} />
      </div>

      {/* Active signals */}
      {activeSignals.length > 0 && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">🤖 Live AI Signals</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {activeSignals.slice(0, 6).map(sig => (
              <div key={sig.symbol} className={cls('flex items-center gap-3 p-2.5 rounded-lg border',
                sig.signal === 'BUY' ? 'bg-green-900/10 border-green-800/40' : 'bg-red-900/10 border-red-800/40')}>
                <div className={cls('w-2 h-2 rounded-full flex-shrink-0', sig.signal === 'BUY' ? 'bg-green-400' : 'bg-red-400')} />
                <span className="font-bold text-white text-sm">{sig.symbol}</span>
                <span className={cls('text-xs font-bold', sig.signal === 'BUY' ? 'text-green-400' : 'text-red-400')}>
                  {sig.signal === 'BUY' ? '▲' : '▼'} {sig.signal}
                </span>
                <span className="text-xs text-gray-400 ml-auto">{((sig.confidence || 0) * 100).toFixed(0)}%</span>
                <span className="text-xs text-gray-500">{'$'}{(sig.price || 0).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Open positions */}
      {positions.length > 0 && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">📂 Open Positions</h3>
          <div className="space-y-2">
            {positions.map(p => {
              const side = String(p.side ?? '').toLowerCase().includes('short') ? 'short' : 'long'
              const qty  = Math.abs(parseFloat(p.qty ?? 0))
              const upnl = parseFloat(p.unrealized_pnl ?? p.unrealized_pl ?? 0)
              const upct = parseFloat(p.unrealized_pct ?? p.unrealized_plpc ?? 0)
              const cur  = parseFloat(p.current_price ?? 0)
              return (
                <div key={p.symbol} className="flex justify-between items-center bg-dark-700 rounded-lg px-3 py-2.5">
                  <div>
                    <span className="font-bold text-white">{p.symbol}</span>
                    <span className={cls('ml-2 text-xs px-2 py-0.5 rounded-full', side === 'long' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300')}>
                      {side.toUpperCase()} x{qty}
                    </span>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-white">{'$'}{cur.toFixed(2)}</p>
                    <p className={cls('text-xs', upnl >= 0 ? 'text-green-400' : 'text-red-400')}>
                      {pnlStr(upnl)} ({(upct * 100).toFixed(2)}%)
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <LiveActivity signals={signals} positions={positions} data={data} />
    </div>
  )
}
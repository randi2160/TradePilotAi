import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, Target, Activity, DollarSign, BarChart2, Zap, Brain } from 'lucide-react'
import { api } from '../hooks/useAuth'
import LiveActivity from './LiveActivity'

function StatCard({ icon: Icon, label, value, sub, color = 'text-white', bg = '' }) {
  return (
    <div className={`bg-dark-800 border border-dark-600 rounded-xl p-4 flex gap-3 items-start ${bg}`}>
      <div className="bg-dark-700 rounded-lg p-2 mt-0.5 flex-shrink-0">
        <Icon size={16} className="text-brand-500" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
        <p className={`text-lg font-bold truncate ${color}`}>{value}</p>
        {sub && <p className="text-xs text-gray-500 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

function StrategyPanel({ title, icon, color, accentColor, engine, stats }) {
  if (!engine && !stats) return null

  const pnl      = engine?.realized_pnl  ?? stats?.realized_pnl  ?? 0
  const target   = engine?.daily_target  ?? stats?.target_max     ?? 100
  const progress = engine?.progress_pct  ?? stats?.progress_pct   ?? 0
  const trades   = engine?.trade_count   ?? stats?.trade_count    ?? 0
  const winRate  = engine?.win_rate      ?? stats?.win_rate       ?? 0
  const capital  = engine?.capital       ?? stats?.capital        ?? 0
  const status   = engine?.status        ?? (stats ? 'active' : 'idle')
  const isUp     = pnl >= 0

  return (
    <div className="bg-dark-800 border rounded-xl overflow-hidden flex-1 min-w-[260px]"
      style={{ borderColor: `${accentColor}40` }}>

      {/* Header */}
      <div className="px-4 py-3 border-b border-dark-600 flex items-center justify-between"
        style={{ background: `${accentColor}12` }}>
        <div className="flex items-center gap-2">
          <span className="text-lg">{icon}</span>
          <span className="font-bold text-white text-sm">{title}</span>
        </div>
        <div className={`w-2 h-2 rounded-full ${
          status === 'running' ? 'bg-green-400 animate-pulse' :
          status === 'paused'  ? 'bg-yellow-400' : 'bg-gray-500'
        }`}/>
      </div>

      <div className="p-4 space-y-4">
        {/* P&L */}
        <div className="text-center">
          <p className={`text-3xl font-black ${isUp ? 'text-green-400' : 'text-red-400'}`}>
            {isUp ? '+' : ''}${pnl.toFixed(2)}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">today's P&L</p>
        </div>

        {/* Progress bar */}
        <div>
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>Progress</span>
            <span>${target} target</span>
          </div>
          <div className="h-2 bg-dark-600 rounded-full overflow-hidden">
            <div className="h-2 rounded-full transition-all duration-700"
              style={{
                width: `${Math.min(progress, 100)}%`,
                background: progress >= 100
                  ? 'linear-gradient(90deg,#00d4aa,#00b894)'
                  : `${accentColor}`,
              }}/>
          </div>
          <p className="text-xs text-right text-gray-500 mt-0.5">{progress.toFixed(1)}%</p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <div className="bg-dark-700 rounded-lg p-2">
            <p className="text-gray-400">Capital</p>
            <p className="font-bold text-white">${capital?.toLocaleString()}</p>
          </div>
          <div className="bg-dark-700 rounded-lg p-2">
            <p className="text-gray-400">Trades</p>
            <p className="font-bold text-white">{trades}</p>
          </div>
          <div className="bg-dark-700 rounded-lg p-2">
            <p className="text-gray-400">Win %</p>
            <p className={`font-bold ${winRate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
              {winRate.toFixed(0)}%
            </p>
          </div>
        </div>

        {/* Recent trades */}
        {(engine?.recent_trades ?? []).length > 0 && (
          <div className="space-y-1">
            <p className="text-xs text-gray-500 font-medium">Recent trades</p>
            {engine.recent_trades.slice(0,3).map((t, i) => (
              <div key={i} className="flex justify-between text-xs">
                <span className="text-gray-300">{t.symbol}</span>
                <span className={t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                  {t.pnl >= 0 ? '+' : ''}${t.pnl?.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        )}

        {status === 'stopped' && engine?.stop_reason && (
          <p className="text-xs text-center text-yellow-400">
            ✅ {engine.stop_reason}
          </p>
        )}
      </div>
    </div>
  )
}

export default function Dashboard({ data }) {
  const [dualSummary, setDualSummary] = useState(null)
  const [todayStats,  setTodayStats]  = useState(null)

  useEffect(() => {
    // Load dual engine summary and today's stats
    api.get('/dual/summary').then(r => setDualSummary(r.data)).catch(() => {})
    api.get('/analytics/today').then(r => setTodayStats(r.data)).catch(() => {})
    const iv = setInterval(() => {
      api.get('/dual/summary').then(r => setDualSummary(r.data)).catch(() => {})
      api.get('/analytics/today').then(r => setTodayStats(r.data)).catch(() => {})
    }, 5000)
    return () => clearInterval(iv)
  }, [])

  if (!data) return (
    <div className="text-gray-400 p-8 text-center">
      <p className="text-4xl mb-2">📡</p>
      <p>Connecting to bot…</p>
    </div>
  )

  const pnl       = data.total_pnl     ?? data.realized_pnl ?? 0
  const realized  = data.realized_pnl  ?? 0
  const progress  = data.progress_pct  ?? 0
  const targetMin = data.target_min    ?? data.settings?.daily_target_min ?? 100
  const targetMax = data.target_max    ?? data.settings?.daily_target_max ?? 250
  const capital   = data.capital       ?? data.settings?.capital          ?? 5000
  const winRate   = data.win_rate      ?? todayStats?.win_rate            ?? 0
  const trades    = data.trade_count   ?? todayStats?.trade_count         ?? 0
  // Use configured capital + today's P&L (NOT Alpaca's $100K paper balance)
  const equity    = capital + pnl
  const positions = data.positions     ?? []
  const signals   = data.signals       ?? []
  const dualOn    = dualSummary?.initialized

  const combinedPnl = dualOn ? (dualSummary.total_pnl ?? pnl) : pnl
  const activeSignals = signals.filter(s => s.signal !== 'HOLD' && s.signal !== 'WAIT')

  return (
    <div className="space-y-5">

      {/* ── Master P&L Banner ──────────────────────────────────────────────── */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5">
        <div className="flex items-start justify-between mb-4">
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">
              {dualOn ? 'Combined Strategy P&L' : 'Today\'s P&L'}
            </p>
            <p className={`text-4xl font-black ${combinedPnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {combinedPnl >= 0 ? '+' : ''}${combinedPnl.toFixed(2)}
            </p>
            <p className="text-sm text-gray-400 mt-1">
              Portfolio: <span className="text-white font-bold">${equity.toLocaleString('en-US',{minimumFractionDigits:2})}</span>
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-400">Daily Target</p>
            <p className="text-lg font-bold text-white">${targetMin}–${targetMax}</p>
            <p className="text-xs text-gray-500">Capital: ${capital.toLocaleString()}</p>
          </div>
        </div>

        {/* Master progress bar */}
        <div className="w-full bg-dark-700 rounded-full h-3 overflow-hidden mb-2">
          <div className="h-3 rounded-full transition-all duration-700"
            style={{
              width: `${Math.min(progress, 100)}%`,
              background: progress >= 100
                ? 'linear-gradient(90deg,#00d4aa,#00b894)'
                : 'linear-gradient(90deg,#6366f1,#00d4aa)',
            }}/>
        </div>
        <div className="flex justify-between text-xs text-gray-500">
          <span>$0</span>
          <span className="text-brand-500 font-medium">${targetMin} min</span>
          <span>${targetMax} max</span>
        </div>

        {data.min_target_hit && (
          <p className="mt-2 text-xs text-green-400 font-medium">
            ✅ Minimum target hit! Protecting gains.
          </p>
        )}
        {data.max_target_hit && (
          <p className="mt-2 text-xs text-brand-500 font-bold">
            🎯 MAX TARGET REACHED — Trading halted for today!
          </p>
        )}
      </div>

      {/* ── Strategy Panels (side by side) ────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-bold text-gray-300">
            {dualOn ? '⚡ Dual Engine — Running Simultaneously' : '🤖 Trading Engine'}
          </h3>
          {!dualOn && (
            <a href="#" onClick={e => { e.preventDefault(); window.dispatchEvent(new CustomEvent('navigate', {detail:'dual'})) }}
              className="text-xs text-brand-500 hover:underline">
              Enable Dual Engine →
            </a>
          )}
        </div>

        <div className="flex gap-3 flex-wrap">
          {/* AI Scalper — always show */}
          <StrategyPanel
            title="AI Scalper"
            icon="🤖"
            color="text-purple-400"
            accentColor="#6366f1"
            engine={dualOn ? dualSummary?.scalper : null}
            stats={!dualOn ? {
              realized_pnl: realized,
              target_max:   targetMax,
              progress_pct: progress,
              trade_count:  trades,
              win_rate:     winRate,
              capital:      dualOn ? dualSummary?.scalper?.capital : capital,
            } : null}
          />

          {/* Peak Bounce — show if dual mode on */}
          {dualOn && (
            <StrategyPanel
              title="Peak Bounce"
              icon="📉"
              color="text-yellow-400"
              accentColor="#f59e0b"
              engine={dualSummary?.bounce}
              stats={null}
            />
          )}

          {/* If dual mode off, show a "Start Dual" prompt panel */}
          {!dualOn && (
            <div className="flex-1 min-w-[260px] bg-dark-800 border border-dashed border-dark-500 rounded-xl p-6 flex flex-col items-center justify-center gap-3 text-center">
              <Zap size={24} className="text-gray-600"/>
              <div>
                <p className="text-sm font-bold text-gray-400">Peak Bounce Engine</p>
                <p className="text-xs text-gray-500 mt-1">
                  Split capital between AI Scalper + Peak Bounce running simultaneously
                </p>
              </div>
              <button
                onClick={() => window.dispatchEvent(new CustomEvent('navigate', {detail:'dual'}))}
                className="text-xs bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold px-4 py-2 rounded-lg transition-colors">
                Enable Dual Engine
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Dual split info ────────────────────────────────────────────────── */}
      {dualOn && dualSummary?.split?.reasons?.length > 0 && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-3">
          <p className="text-xs font-bold text-brand-500 mb-2 flex items-center gap-1">
            <Brain size={12}/> AI Capital Split Reasoning
          </p>
          <div className="flex gap-4 text-xs text-gray-400 mb-2">
            <span>🤖 Scalper: <strong className="text-purple-400">{dualSummary.split.scalper?.pct}%</strong> (${dualSummary.split.scalper?.capital})</span>
            <span>📉 Bounce: <strong className="text-yellow-400">{dualSummary.split.bounce?.pct}%</strong> (${dualSummary.split.bounce?.capital})</span>
          </div>
          {dualSummary.split.reasons.slice(0,3).map((r, i) => (
            <p key={i} className="text-xs text-gray-500">• {r}</p>
          ))}
        </div>
      )}

      {/* ── Stat cards ────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          icon={DollarSign}
          label="Portfolio Value"
          value={`$${equity.toLocaleString('en-US',{minimumFractionDigits:2})}`}
          sub={`${((equity-capital)/capital*100).toFixed(2)}% total return`}
          color={equity >= capital ? 'text-green-400' : 'text-red-400'}
        />
        <StatCard
          icon={Activity}
          label="Win Rate Today"
          value={`${winRate}%`}
          sub={`${trades} trade${trades !== 1 ? 's' : ''} today`}
          color={winRate >= 50 ? 'text-green-400' : 'text-red-400'}
        />
        <StatCard
          icon={TrendingUp}
          label="Active Signals"
          value={activeSignals.length}
          sub={activeSignals.slice(0,2).map(s=>`${s.symbol} ${s.signal}`).join(' · ')}
          color={activeSignals.length > 0 ? 'text-brand-500' : 'text-gray-400'}
        />
        <StatCard
          icon={BarChart2}
          label="Open Positions"
          value={positions.length}
          sub={positions.slice(0,2).map(p=>p.symbol).join(', ') || 'None'}
        />
      </div>

      {/* ── Active AI signals ──────────────────────────────────────────────── */}
      {activeSignals.length > 0 && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">🤖 Live AI Signals</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {activeSignals.slice(0,6).map(sig => (
              <div key={sig.symbol}
                className={`flex items-center gap-3 p-2.5 rounded-lg border ${
                  sig.signal === 'BUY'
                    ? 'bg-green-900/10 border-green-800/40'
                    : 'bg-red-900/10 border-red-800/40'
                }`}>
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  sig.signal === 'BUY' ? 'bg-green-400' : 'bg-red-400'
                }`}/>
                <span className="font-bold text-white text-sm">{sig.symbol}</span>
                <span className={`text-xs font-bold ${
                  sig.signal === 'BUY' ? 'text-green-400' : 'text-red-400'
                }`}>
                  {sig.signal === 'BUY' ? '▲' : '▼'} {sig.signal}
                </span>
                <span className="text-xs text-gray-400 ml-auto">
                  {(sig.confidence * 100).toFixed(0)}%
                </span>
                <span className="text-xs text-gray-500">${sig.price?.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Open positions ────────────────────────────────────────────────── */}
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
                    <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${
                      side === 'long' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
                    }`}>
                      {side.toUpperCase()} × {qty}
                    </span>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-bold text-white">${cur.toFixed(2)}</p>
                    <p className={`text-xs ${upnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {upnl >= 0 ? '+' : ''}${upnl.toFixed(2)}
                      {' '}({(upct * 100).toFixed(2)}%)
                    </p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* ── Live Activity Feed ────────────────────────────────────────────── */}
      <LiveActivity
        signals={signals}
        positions={positions}
        data={data}
      />
    </div>
  )
}

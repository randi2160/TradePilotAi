import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { RefreshCw, TrendingUp, TrendingDown, Target, Clock, Database } from 'lucide-react'

function StatCard({ label, value, color = 'text-white', icon, sub }) {
  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-3 text-center">
      {icon && <div className="flex justify-center mb-1 text-gray-500">{icon}</div>}
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-black ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

function TradeRow({ t }) {
  const isOpen = t.status === 'open'
  const pnl    = parseFloat(t.pnl ?? 0)
  return (
    <div className={`p-3 rounded-xl border transition-colors ${
      isOpen        ? 'bg-dark-800 border-brand-500/30' :
      pnl > 0       ? 'bg-green-900/10 border-green-800/40' :
      pnl < 0       ? 'bg-red-900/10   border-red-800/40'   :
                      'bg-dark-800     border-dark-600'
    }`}>
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-black text-white">{t.symbol}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${
            t.side === 'BUY' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'
          }`}>{t.side} × {t.qty}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${
            isOpen ? 'bg-brand-500/20 text-brand-400' : pnl > 0 ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'
          }`}>{isOpen ? '🟢 OPEN' : pnl > 0 ? '✅ WIN' : '❌ LOSS'}</span>
        </div>
        {!isOpen && (
          <span className={`font-black text-lg ml-auto ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
          </span>
        )}
        {isOpen && <span className="text-brand-400 font-bold ml-auto">In progress…</span>}
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2 text-xs text-gray-400">
        <span>Entry: <strong className="text-white">${parseFloat(t.entry_price ?? 0).toFixed(2)}</strong></span>
        {t.exit_price  && <span>Exit: <strong className="text-white">${parseFloat(t.exit_price).toFixed(2)}</strong></span>}
        {t.stop_loss   && <span>Stop: <strong className="text-red-300">${parseFloat(t.stop_loss).toFixed(2)}</strong></span>}
        {t.take_profit && <span>Target: <strong className="text-green-300">${parseFloat(t.take_profit).toFixed(2)}</strong></span>}
        {t.confidence  && <span>Conf: <strong className="text-white">{((t.confidence ?? 0)*100).toFixed(0)}%</strong></span>}
        {t.opened_at   && <span>Time: <strong className="text-white">{t.opened_at?.slice(11,19)}</strong></span>}
      </div>
    </div>
  )
}

export default function DailyReport() {
  const [report,  setReport]  = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab,     setTab]     = useState('summary')
  const [error,   setError]   = useState(null)

  useEffect(() => {
    load()
    const iv = setInterval(load, 15000)
    return () => clearInterval(iv)
  }, [])

  async function load() {
    try {
      const r = await api.get('/report/today')
      setReport(r.data)
      setError(null)
    } catch(e) {
      setError(e.response?.data?.detail ?? 'Could not load report')
    } finally {
      setLoading(false)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center py-20">
      <RefreshCw size={24} className="animate-spin text-brand-500"/>
    </div>
  )

  if (error) return (
    <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-xl">
      <p className="text-red-400">{error}</p>
      <button onClick={load} className="mt-3 text-sm text-brand-500 hover:underline">Retry</button>
    </div>
  )

  if (!report) return null

  const s   = report.summary ?? {}
  const pnl = s.total_pnl ?? 0
  const realized = s.realized_pnl ?? 0
  const unrealized = s.unrealized_pnl ?? 0
  const progress = s.progress_pct ?? 0
  const trades = report.trades ?? []
  const session = report.session ?? {}

  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-black text-white">📄 Daily Report</h2>
          <p className="text-xs text-gray-500">{report.date} · {session.db_loaded ? '✅ Loaded from database' : '⚡ Live session only'}</p>
        </div>
        <button onClick={load} className="p-2 bg-dark-700 rounded-lg hover:bg-dark-600 transition-colors">
          <RefreshCw size={14} className="text-gray-400"/>
        </button>
      </div>

      {/* Big P&L */}
      <div className={`rounded-2xl p-6 border text-center ${
        pnl >= 0 ? 'bg-green-900/20 border-green-800/50' : 'bg-red-900/20 border-red-800/50'
      }`}>
        <p className="text-sm text-gray-400 mb-1">Today's Total P&L</p>
        <p className={`text-5xl font-black ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
        </p>
        <div className="flex justify-center gap-6 mt-3 text-sm">
          <span className="text-gray-400">Realized: <strong className={realized >= 0 ? 'text-green-400' : 'text-red-400'}>${realized.toFixed(2)}</strong></span>
          <span className="text-gray-400">Unrealized: <strong className={unrealized >= 0 ? 'text-green-300' : 'text-red-300'}>${unrealized.toFixed(2)}</strong></span>
        </div>

        {/* Progress bar */}
        <div className="mt-4">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>$0</span>
            <span className="text-brand-500">${s.target_min} min</span>
            <span>${s.target_max} max</span>
          </div>
          <div className="w-full bg-dark-700 rounded-full h-3 overflow-hidden">
            <div className="h-3 rounded-full transition-all duration-700" style={{
              width: `${Math.min(progress, 100)}%`,
              background: s.max_target_hit ? '#00d4aa' : s.min_target_hit ? '#22c55e' : 'linear-gradient(90deg,#6366f1,#00d4aa)',
            }}/>
          </div>
          <p className="text-xs text-gray-400 mt-1 text-center">
            {s.max_target_hit ? '🎯 MAX TARGET HIT!' : s.min_target_hit ? '✅ Min target reached' : `${progress.toFixed(1)}% to daily target`}
          </p>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
        <StatCard label="Trades"     value={s.total_trades ?? 0}/>
        <StatCard label="Wins"       value={s.wins ?? 0}       color="text-green-400"/>
        <StatCard label="Losses"     value={s.losses ?? 0}     color="text-red-400"/>
        <StatCard label="Win Rate"   value={`${s.win_rate ?? 0}%`} color={(s.win_rate ?? 0) >= 50 ? 'text-green-400' : 'text-red-400'}/>
        <StatCard label="Best Trade" value={`$${(s.best_trade ?? 0).toFixed(2)}`}  color="text-green-400"/>
        <StatCard label="Worst Trade" value={`$${(s.worst_trade ?? 0).toFixed(2)}`} color="text-red-400"/>
      </div>

      {/* Session info */}
      {(session.session_start || session.session_stop) && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-3 flex flex-wrap gap-4 text-xs text-gray-400">
          <span className="flex items-center gap-1">
            <Clock size={12}/>
            {session.bot_status === 'running' ? '🟢 Bot running' : '⚫ Bot stopped'}
          </span>
          {session.session_start && (
            <span>Started: <strong className="text-white">{session.session_start?.slice(11,19)}</strong></span>
          )}
          {session.session_stop && (
            <span>Stopped: <strong className="text-white">{session.session_stop?.slice(11,19)}</strong></span>
          )}
          <span className="flex items-center gap-1">
            <Database size={12}/>
            {session.db_loaded ? 'History restored from DB' : 'Fresh session'}
          </span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2">
        {[
          { id:'trades',   label:`📋 Trades (${trades.length})`         },
          { id:'signals',  label:`🤖 Signals (${(report.signals??[]).length})` },
          { id:'events',   label:`📡 Events (${(report.events??[]).length})`   },
          { id:'goal',     label:'🎯 Goal'                               },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
              tab===t.id ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}>{t.label}</button>
        ))}
      </div>

      {/* Trades tab */}
      {tab === 'trades' && (
        <div className="space-y-2">
          {trades.length === 0 ? (
            <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-xl text-gray-500">
              <p className="text-3xl mb-2">📋</p>
              <p className="font-bold text-white mb-1">No trades today yet</p>
              <p className="text-sm">Start the bot to begin trading. Completed trades appear here.</p>
            </div>
          ) : trades.map((t, i) => <TradeRow key={i} t={t}/>)}
        </div>
      )}

      {/* Signals tab */}
      {tab === 'signals' && (
        <div className="space-y-2">
          {(report.signals ?? []).length === 0 ? (
            <div className="text-center py-8 text-gray-500">No signals yet — bot needs to be running</div>
          ) : (report.signals ?? []).map((s, i) => (
            <div key={i} className={`flex items-center gap-3 p-3 rounded-xl border ${
              s.signal === 'BUY' ? 'bg-green-900/10 border-green-800/40' :
              s.signal === 'SELL' ? 'bg-red-900/10 border-red-800/40' :
              'bg-dark-800 border-dark-600'
            }`}>
              <span className="font-black text-white w-14">{s.symbol}</span>
              <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                s.signal === 'BUY' ? 'bg-green-900 text-green-300' :
                s.signal === 'SELL' ? 'bg-red-900 text-red-300' :
                'bg-dark-700 text-gray-400'
              }`}>{s.signal}</span>
              <span className="text-xs text-gray-400">{((s.confidence ?? 0)*100).toFixed(0)}% conf</span>
              <span className="text-xs text-gray-500 ml-auto">${s.price?.toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}

      {/* Events tab */}
      {tab === 'events' && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl divide-y divide-dark-700 max-h-96 overflow-y-auto">
          {(report.events ?? []).length === 0 ? (
            <div className="text-center py-8 text-gray-500">No events logged yet</div>
          ) : (report.events ?? []).map((ev, i) => (
            <div key={i} className="px-4 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-300">{ev.msg}</span>
                <span className="text-xs text-gray-600 ml-auto whitespace-nowrap">{ev.time}</span>
              </div>
              {ev.detail && (
                <p className="text-xs text-gray-500 mt-0.5">
                  {typeof ev.detail === 'object' ? Object.entries(ev.detail).slice(0,3).map(([k,v]) => `${k}: ${v}`).join(' · ') : String(ev.detail)}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Goal tab */}
      {tab === 'goal' && report.goal && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-3">
          <h3 className="font-bold text-white">🎯 Daily Goal Plan</h3>
          {Object.entries(report.goal).map(([k, v]) => (
            <div key={k} className="flex justify-between text-sm">
              <span className="text-gray-400 capitalize">{k.replace(/_/g,' ')}</span>
              <span className="text-white font-bold">{typeof v === 'number' ? `$${v.toFixed(2)}` : String(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
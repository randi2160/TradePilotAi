import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { RefreshCw, Download } from 'lucide-react'

const TYPE_COLORS = {
  entry:   { bg:'bg-green-900/20 border-green-800/50',  text:'text-green-400',  icon:'▲', label:'Entry'   },
  exit:    { bg:'bg-blue-900/20  border-blue-800/50',   text:'text-blue-400',   icon:'■', label:'Exit'    },
  signal:  { bg:'bg-dark-700    border-dark-600',       text:'text-brand-500',  icon:'🤖',label:'Signal'  },
  scan:    { bg:'bg-dark-700    border-dark-600',       text:'text-purple-400', icon:'🔍',label:'Scan'    },
  profit:  { bg:'bg-green-900/20 border-green-800/50',  text:'text-green-400',  icon:'✅',label:'Profit'  },
  loss:    { bg:'bg-red-900/20   border-red-800/50',    text:'text-red-400',    icon:'❌',label:'Loss'    },
  blocked: { bg:'bg-yellow-900/20 border-yellow-800/50',text:'text-yellow-400', icon:'⛔',label:'Blocked' },
  info:    { bg:'bg-dark-700    border-dark-600',       text:'text-gray-400',   icon:'ℹ️',label:'Info'    },
}

export default function ActivityLog() {
  const [report,    setReport]    = useState(null)
  const [events,    setEvents]    = useState([])
  const [trades,    setTrades]    = useState([])
  const [tab,       setTab]       = useState('trades')
  const [filter,    setFilter]    = useState('all')
  const [loading,   setLoading]   = useState(false)

  useEffect(() => { loadAll() }, [])
  useEffect(() => {
    const iv = setInterval(loadAll, 15000)
    return () => clearInterval(iv)
  }, [])

  async function loadAll() {
    setLoading(true)
    try {
      const [rpt, evts, trd] = await Promise.all([
        api.get('/report/today').then(r => r.data).catch(() => null),
        api.get('/report/events?limit=100').then(r => r.data).catch(() => []),
        api.get('/trades').then(r => r.data).catch(() => []),
      ])
      setReport(rpt)
      setEvents(evts)
      setTrades(trd)
    } catch {}
    finally { setLoading(false) }
  }

  function exportCSV() {
    const rows = [
      ['Time', 'Symbol', 'Side', 'Qty', 'Entry', 'Exit', 'P&L', 'Status'],
      ...trades.map(t => [
        t.opened_at?.slice(11,19) ?? '',
        t.symbol, t.side, t.qty,
        t.entry_price, t.exit_price ?? '',
        t.pnl ?? '', t.status,
      ])
    ]
    const csv  = rows.map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type:'text/csv' })
    const a    = document.createElement('a')
    a.href     = URL.createObjectURL(blob)
    a.download = `trades-${new Date().toISOString().slice(0,10)}.csv`
    a.click()
  }

  const todayTrades = trades.filter(t => {
    const d = new Date(t.opened_at ?? '').toDateString()
    return d === new Date().toDateString()
  })

  const s   = report?.summary ?? {}
  const pnl = s.total_pnl ?? 0

  const filteredEvents = filter === 'all' ? events : events.filter(e => e.type === filter)

  return (
    <div className="space-y-4">

      {/* Today summary bar */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          { label:"Today's P&L",  value:`${pnl>=0?'+':''}$${pnl.toFixed(2)}`,    color: pnl>=0?'text-green-400':'text-red-400' },
          { label:'Trades',       value: s.total_trades ?? todayTrades.length,    color:'text-white' },
          { label:'Wins / Losses',value:`${s.wins??0} / ${s.losses??0}`,          color:'text-white' },
          { label:'Win Rate',     value:`${s.win_rate?.toFixed(1)??0}%`,           color: (s.win_rate??0)>=50?'text-green-400':'text-red-400' },
          { label:'Open Positions',value: s.open_positions??0,                    color:'text-white' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-dark-800 border border-dark-600 rounded-xl p-3 text-center">
            <p className="text-xs text-gray-500">{label}</p>
            <p className={`text-lg font-bold ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2">
        {[
          { id:'trades',   label:`📋 Trades Today (${todayTrades.length})` },
          { id:'all_trades',label:`📁 All Trades (${trades.length})`       },
          { id:'activity', label:`📡 Activity Log (${events.length})`      },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
              tab===t.id ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}>{t.label}</button>
        ))}
        <div className="ml-auto flex gap-2">
          <button onClick={loadAll} disabled={loading}
            className="p-2 bg-dark-700 rounded-lg hover:bg-dark-600 transition-colors">
            <RefreshCw size={14} className={`text-gray-400 ${loading?'animate-spin':''}`}/>
          </button>
          <button onClick={exportCSV}
            className="flex items-center gap-1 px-3 py-1.5 bg-dark-700 hover:bg-dark-600 text-gray-400 text-xs rounded-lg transition-colors">
            <Download size={12}/> CSV
          </button>
        </div>
      </div>

      {/* Trades today */}
      {(tab === 'trades' || tab === 'all_trades') && (
        <div className="space-y-2">
          {(tab === 'trades' ? todayTrades : trades).length === 0 ? (
            <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-xl text-gray-500">
              <p className="text-3xl mb-2">📋</p>
              <p className="font-bold text-white mb-1">No trades yet today</p>
              <p className="text-sm">The bot is scanning — trades appear here when executed</p>
            </div>
          ) : (
            (tab === 'trades' ? todayTrades : trades).map((t, i) => {
              const isOpen = t.status === 'open'
              const pnl    = parseFloat(t.pnl ?? 0)
              return (
                <div key={i} className={`p-4 rounded-xl border ${
                  isOpen ? 'bg-dark-800 border-brand-500/30' :
                  pnl > 0 ? 'bg-green-900/10 border-green-800/40' :
                  pnl < 0 ? 'bg-red-900/10   border-red-800/40'   :
                  'bg-dark-800 border-dark-600'
                }`}>
                  <div className="flex items-center gap-3 flex-wrap">
                    {/* Symbol + side */}
                    <div className="flex items-center gap-2">
                      <span className="font-black text-white text-lg">{t.symbol}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${
                        t.side === 'BUY' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'
                      }`}>{t.side} {t.qty}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        isOpen ? 'bg-brand-500/20 text-brand-400' : 'bg-dark-600 text-gray-400'
                      }`}>{isOpen ? '🟢 OPEN' : '⬜ CLOSED'}</span>
                    </div>

                    {/* P&L */}
                    {!isOpen && (
                      <span className={`font-black text-lg ml-auto ${pnl>=0?'text-green-400':'text-red-400'}`}>
                        {pnl>=0?'+':''}${pnl.toFixed(2)}
                      </span>
                    )}
                    {isOpen && (
                      <span className="text-brand-500 font-bold ml-auto">In Progress</span>
                    )}
                  </div>

                  {/* Details */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 text-xs text-gray-400">
                    <span>Entry: <strong className="text-white">${parseFloat(t.entry_price??0).toFixed(2)}</strong></span>
                    {t.exit_price && <span>Exit: <strong className="text-white">${parseFloat(t.exit_price).toFixed(2)}</strong></span>}
                    {t.stop_loss  && <span>Stop: <strong className="text-red-300">${parseFloat(t.stop_loss).toFixed(2)}</strong></span>}
                    {t.take_profit && <span>Target: <strong className="text-green-300">${parseFloat(t.take_profit).toFixed(2)}</strong></span>}
                    <span>Risk: <strong className="text-white">${parseFloat(t.risk_dollars??0).toFixed(2)}</strong></span>
                    <span>Conf: <strong className="text-white">{((t.confidence??0)*100).toFixed(0)}%</strong></span>
                    <span>Time: <strong className="text-white">{t.opened_at?.slice(11,19)}</strong></span>
                    {t.trade_date && <span>Date: <strong className="text-white">{t.trade_date}</strong></span>}
                  </div>
                </div>
              )
            })
          )}
        </div>
      )}

      {/* Activity log */}
      {tab === 'activity' && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl overflow-hidden">
          {/* Filter bar */}
          <div className="flex gap-1 px-3 py-2 border-b border-dark-600 overflow-x-auto">
            {['all','entry','exit','signal','scan','blocked','info'].map(f => (
              <button key={f} onClick={() => setFilter(f)}
                className={`px-2 py-1 rounded text-xs capitalize whitespace-nowrap ${
                  filter===f ? 'bg-brand-500 text-dark-900 font-bold' : 'text-gray-400 hover:bg-dark-700'
                }`}>{f}</button>
            ))}
          </div>

          <div className="max-h-[600px] overflow-y-auto divide-y divide-dark-700">
            {filteredEvents.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <p className="text-3xl mb-2">📡</p>
                <p>No activity logged yet — start the bot to see events</p>
              </div>
            ) : filteredEvents.map((ev, i) => {
              const cfg = TYPE_COLORS[ev.type] ?? TYPE_COLORS.info
              const detail = ev.detail && typeof ev.detail === 'object'
                ? Object.entries(ev.detail).slice(0,5).map(([k,v])=>`${k}: ${v}`).join(' · ')
                : String(ev.detail ?? '')
              return (
                <div key={i} className={`px-4 py-3 border-l-4 ${cfg.bg} ${
                  cfg.bg.includes('dark-700') ? 'border-l-gray-600' :
                  cfg.bg.includes('green')    ? 'border-l-green-600' :
                  cfg.bg.includes('blue')     ? 'border-l-blue-600' :
                  cfg.bg.includes('red')      ? 'border-l-red-600' :
                  cfg.bg.includes('yellow')   ? 'border-l-yellow-600' : 'border-l-purple-600'
                }`}>
                  <div className="flex items-center gap-2">
                    <span className="text-sm">{cfg.icon}</span>
                    <span className={`text-sm font-medium ${cfg.text}`}>{ev.msg}</span>
                    <span className="text-xs text-gray-600 ml-auto">{ev.time}</span>
                  </div>
                  {detail && <p className="text-xs text-gray-500 mt-0.5 ml-6 truncate">{detail}</p>}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

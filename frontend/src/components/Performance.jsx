import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, LineChart, Line } from 'recharts'
import { api } from '../hooks/useAuth'

function safeNum(v, fallback = 0) {
  const n = parseFloat(v)
  return isNaN(n) ? fallback : n
}

function fmt(v, prefix = '$') {
  const n = safeNum(v)
  return `${prefix}${n >= 0 ? '' : '-'}${Math.abs(n).toFixed(2)}`
}

export default function Performance() {
  const [stats,     setStats]     = useState(null)
  const [period,    setPeriod]    = useState(30)
  const [pdt,       setPdt]       = useState(null)
  const [bt,        setBt]        = useState(null)
  const [btLoading, setBtLoading] = useState(false)
  const [loading,   setLoading]   = useState(false)

  useEffect(() => { loadStats() }, [period])

  async function loadStats() {
    setLoading(true)
    try {
      const [perf, pdtData] = await Promise.all([
        api.get(`/analytics/performance?days=${period}`).then(r => r.data),
        api.get('/analytics/pdt').then(r => r.data),
      ])
      setStats(perf)
      setPdt(pdtData)
    } catch {}
    finally { setLoading(false) }
  }

  async function runBacktest() {
    setBtLoading(true)
    try {
      const r = await api.post('/analytics/backtest?symbol=SPY&limit=500')
      setBt(r.data)
    } catch(e) {
      setBt({ error: e.response?.data?.detail ?? e.message })
    } finally { setBtLoading(false) }
  }

  const noTrades = !stats || safeNum(stats.total_trades) === 0

  const symbolData = stats?.pnl_by_symbol
    ? Object.entries(stats.pnl_by_symbol)
        .sort((a,b) => b[1]-a[1])
        .slice(0,10)
        .map(([sym, pnl]) => ({ sym, pnl: Math.round(safeNum(pnl) * 100) / 100 }))
    : []

  const GRADE_COLOR = { A:'#00d4aa', B:'#f59e0b', C:'#f97316', D:'#ef4444' }

  return (
    <div className="space-y-5">

      {/* Period selector */}
      <div className="flex gap-2">
        {[7,14,30,90].map(d => (
          <button key={d} onClick={() => setPeriod(d)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              period===d ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}>{d}D</button>
        ))}
        <button onClick={loadStats} disabled={loading}
          className="ml-auto text-xs bg-dark-700 text-gray-400 px-3 py-1.5 rounded-lg hover:bg-dark-600">
          ↻ Refresh
        </button>
      </div>

      {/* PDT Status */}
      {pdt && (
        <div className={`p-3 rounded-xl border text-sm ${
          pdt.pdt_risk
            ? 'bg-red-900/20 border-red-800 text-red-400'
            : 'bg-dark-800 border-dark-600 text-gray-300'
        }`}>
          {pdt.pdt_risk ? '⚠️' : '✅'} PDT Status: {pdt.message}
          {pdt.pdt_risk && (
            <p className="text-xs text-red-300/60 mt-1">
              Equity under $25K — limited to 3 day trades per 5 business days.
            </p>
          )}
        </div>
      )}

      {/* No trades yet */}
      {noTrades && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-8 text-center">
          <p className="text-4xl mb-3">📊</p>
          <p className="text-white font-bold mb-1">No trades recorded yet</p>
          <p className="text-sm text-gray-400">
            Start the bot and let it trade — performance stats will appear here after the first trade closes.
          </p>
          <p className="text-xs text-gray-500 mt-2">
            The bot is scanning signals but needs market conditions to meet entry criteria before executing.
          </p>
        </div>
      )}

      {/* Stats grid — only show when trades exist */}
      {!noTrades && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label:'Total P&L',     value: fmt(stats.total_pnl),        color: safeNum(stats.total_pnl)>=0?'text-green-400':'text-red-400' },
              { label:'Win Rate',      value: `${safeNum(stats.win_rate_pct).toFixed(1)}%`,  color: safeNum(stats.win_rate_pct)>=50?'text-green-400':'text-red-400' },
              { label:'Profit Factor', value: safeNum(stats.profit_factor)>=999 ? '∞' : safeNum(stats.profit_factor).toFixed(2), color: safeNum(stats.profit_factor)>=1.5?'text-green-400':'text-yellow-400' },
              { label:'Total Trades',  value: safeNum(stats.total_trades), color:'text-white' },
              { label:'Avg Win',       value: `+${fmt(stats.avg_win)}`,    color:'text-green-400' },
              { label:'Avg Loss',      value: fmt(stats.avg_loss),         color:'text-red-400' },
              { label:'AI Trades',     value: safeNum(stats.ai_trades),    color:'text-brand-500' },
              { label:'Manual Trades', value: safeNum(stats.manual_trades),color:'text-yellow-400' },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-dark-800 border border-dark-600 rounded-xl p-3 text-center">
                <p className="text-xs text-gray-500 mb-1">{label}</p>
                <p className={`text-sm font-bold ${color}`}>{value}</p>
              </div>
            ))}
          </div>

          {symbolData.length > 0 && (
            <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
              <p className="text-sm font-bold text-gray-300 mb-4">P&L by Symbol ({period} days)</p>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={symbolData} margin={{top:5,right:10,left:0,bottom:5}}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1f2937"/>
                  <XAxis dataKey="sym" tick={{fill:'#9ca3af',fontSize:11}} tickLine={false}/>
                  <YAxis tick={{fill:'#9ca3af',fontSize:11}} tickLine={false} axisLine={false} tickFormatter={v=>`$${v}`}/>
                  <Tooltip contentStyle={{background:'#111827',border:'1px solid #374151',borderRadius:8}} formatter={v=>[`$${v}`,'P&L']}/>
                  <Bar dataKey="pnl" radius={[4,4,0,0]}>
                    {symbolData.map((d,i) => <Cell key={i} fill={d.pnl>=0?'#00d4aa':'#ef4444'}/>)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}

      {/* Backtester — always available */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold text-white">Strategy Backtester</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              Test the AI strategy on historical SPY data before risking real money
            </p>
          </div>
          <button onClick={runBacktest} disabled={btLoading}
            className="px-4 py-2 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold text-sm rounded-lg transition-colors disabled:opacity-50">
            {btLoading ? '⟳ Running…' : '▶ Run Backtest'}
          </button>
        </div>

        {bt?.error && <p className="text-red-400 text-sm">❌ {bt.error}</p>}

        {bt?.summary && (
          <div className="space-y-4">
            <div className="flex items-center gap-4 p-4 rounded-xl"
              style={{background:`${GRADE_COLOR[bt.verdict?.grade]}15`,border:`1px solid ${GRADE_COLOR[bt.verdict?.grade]}40`}}>
              <span className="text-5xl font-black" style={{color:GRADE_COLOR[bt.verdict?.grade]}}>
                {bt.verdict?.grade}
              </span>
              <div>
                <p className="text-white font-bold">Strategy Rating</p>
                <p className="text-sm text-gray-300">{bt.verdict?.text}</p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              {[
                ['Win Rate',       `${safeNum(bt.summary.win_rate_pct)}%`],
                ['Profit Factor',  safeNum(bt.summary.profit_factor)],
                ['Total P&L',      `$${safeNum(bt.summary.total_pnl).toFixed(2)}`],
                ['Max Drawdown',   `${safeNum(bt.summary.max_drawdown_pct)}%`],
                ['Exp. Value',     `$${safeNum(bt.summary.expected_value).toFixed(2)}/trade`],
                ['Est. Daily P&L', `$${safeNum(bt.summary.est_daily_pnl).toFixed(2)}`],
                ['Total Trades',   bt.summary.total_trades],
                ['Days Tested',    bt.summary.trading_days_est],
                ['Return',         `${safeNum(bt.summary.total_return_pct)}%`],
              ].map(([k,v]) => (
                <div key={k} className="bg-dark-700 rounded-lg p-2.5 text-center">
                  <p className="text-xs text-gray-500">{k}</p>
                  <p className="text-sm font-bold text-white">{v}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

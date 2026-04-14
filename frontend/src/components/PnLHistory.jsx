import { useState, useEffect } from 'react'

const PERIODS = [
  { label: '7D',  value: '7d' },
  { label: '30D', value: '30d' },
  { label: '90D', value: '90d' },
  { label: 'All', value: 'all' },
]

function fmt(n) {
  if (n === null || n === undefined) return '$0.00'
  const abs = Math.abs(n).toFixed(2)
  return (n >= 0 ? '+$' : '-$') + abs
}

function fmtDate(d) {
  if (!d) return ''
  const dt = new Date(d)
  return dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
}

function fmtTime(t) {
  if (!t) return ''
  try {
    return new Date(t).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
  } catch { return t }
}

export default function PnLHistory() {
  const [period,      setPeriod]      = useState('30d')
  const [data,        setData]        = useState(null)
  const [loading,     setLoading]     = useState(true)
  const [selectedDay, setSelectedDay] = useState(null)
  const [error,       setError]       = useState('')

  useEffect(() => {
    load()
  }, [period])

  async function load() {
    setLoading(true)
    setError('')
    try {
      const { api } = await import('../hooks/useAuth')
      const r = await api.get(`/report/history?period=${period}`)
      setData(r.data)
      // Auto-select most recent day that has trades
      if (r.data.days?.length > 0) {
        setSelectedDay(r.data.days[r.data.days.length - 1])
      }
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  const day = selectedDay

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-white">P&L History</h2>
          <p className="text-xs text-gray-500">Compound gains over time</p>
        </div>
        <div className="flex gap-1 bg-dark-800 rounded-lg p-1">
          {PERIODS.map(p => (
            <button key={p.value} onClick={() => setPeriod(p.value)}
              className={`px-3 py-1 rounded text-xs font-bold transition-colors ${
                period === p.value
                  ? 'bg-brand-500 text-dark-900'
                  : 'text-gray-400 hover:text-white'
              }`}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-xl p-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center h-40">
          <div className="w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {data && !loading && (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              { l: 'All-Time P&L',  v: data.all_time_total, big: true },
              { l: `${period.toUpperCase()} P&L`, v: data.total_pnl },
              { l: 'Best Day',      v: data.best_day },
              { l: 'Avg Day',       v: data.avg_day },
            ].map(({ l, v, big }) => (
              <div key={l} className={`rounded-xl p-3 text-center ${big ? 'bg-brand-500/10 border border-brand-500/30' : 'bg-dark-800'}`}>
                <div className="text-xs text-gray-500 mb-1">{l}</div>
                <div className={`font-bold text-lg ${
                  v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-gray-400'
                }`}>
                  {fmt(v)}
                </div>
              </div>
            ))}
          </div>

          {/* Stats row */}
          <div className="flex gap-4 text-xs text-gray-500 px-1">
            <span>📅 {data.days.length} trading days</span>
            <span className="text-green-400">✅ {data.winning_days}W</span>
            <span className="text-red-400">❌ {data.losing_days}L</span>
            <span>🔢 {data.total_trades} trades</span>
          </div>

          {/* Main layout: calendar list + trade detail */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">

            {/* Left: Day list */}
            <div className="space-y-1 max-h-[480px] overflow-y-auto pr-1">
              {data.days.length === 0 && (
                <div className="text-center text-gray-500 text-sm py-8">
                  No closed trades in this period
                </div>
              )}
              {[...data.days].reverse().map(d => (
                <button key={d.date}
                  onClick={() => setSelectedDay(d)}
                  className={`w-full text-left rounded-xl p-3 border transition-all ${
                    selectedDay?.date === d.date
                      ? 'border-brand-500/60 bg-brand-500/10'
                      : 'border-dark-700 bg-dark-800 hover:border-dark-600'
                  }`}>
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-sm font-semibold text-white">{fmtDate(d.date)}</div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        {d.trades} trades · {d.wins}W {d.losses}L · {d.win_rate}% WR
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-bold text-base ${
                        d.day_pnl > 0 ? 'text-green-400' : d.day_pnl < 0 ? 'text-red-400' : 'text-gray-400'
                      }`}>
                        {fmt(d.day_pnl)}
                      </div>
                      <div className="text-xs text-gray-500">
                        Total: <span className={d.running_total >= 0 ? 'text-green-300' : 'text-red-300'}>
                          {fmt(d.running_total)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Mini P&L bar */}
                  <div className="mt-2 h-1 bg-dark-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${d.day_pnl >= 0 ? 'bg-green-500' : 'bg-red-500'}`}
                      style={{ width: `${Math.min(100, Math.abs(d.day_pnl) / Math.max(1, data.best_day) * 100)}%` }}
                    />
                  </div>
                </button>
              ))}
            </div>

            {/* Right: Trade detail for selected day */}
            <div className="bg-dark-800 rounded-xl border border-dark-700 overflow-hidden">
              {day ? (
                <>
                  <div className="px-4 py-3 border-b border-dark-700 flex items-center justify-between">
                    <div>
                      <div className="text-sm font-bold text-white">{fmtDate(day.date)}</div>
                      <div className="text-xs text-gray-500">{day.trades} trades · Rolling P&L</div>
                    </div>
                    <div className={`text-lg font-bold ${
                      day.day_pnl > 0 ? 'text-green-400' : day.day_pnl < 0 ? 'text-red-400' : 'text-gray-400'
                    }`}>
                      {fmt(day.day_pnl)}
                    </div>
                  </div>

                  <div className="divide-y divide-dark-700 max-h-[400px] overflow-y-auto">
                    {day.trade_list.map((t, i) => (
                      <div key={t.id || i} className="px-4 py-2.5 flex items-center gap-3 hover:bg-dark-700/50 transition-colors">
                        {/* Symbol + side */}
                        <div className="w-16 shrink-0">
                          <div className="text-xs font-bold text-white">{t.symbol}</div>
                          <div className="text-xs text-gray-600">{t.side}</div>
                        </div>

                        {/* Entry → Exit */}
                        <div className="flex-1 min-w-0">
                          <div className="text-xs text-gray-400">
                            ${t.entry?.toFixed(4)} → ${t.exit?.toFixed(4)}
                          </div>
                          <div className="text-xs text-gray-600">{fmtTime(t.time)}</div>
                        </div>

                        {/* Trade P&L */}
                        <div className="text-right shrink-0">
                          <div className={`text-xs font-bold ${t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                            {fmt(t.pnl)}
                          </div>
                          {/* Running total */}
                          {t.running !== null && (
                            <div className={`text-xs ${t.running >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                              ∑ {fmt(t.running)}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Day footer */}
                  <div className="px-4 py-2 bg-dark-900/50 border-t border-dark-700 flex justify-between text-xs">
                    <span className="text-gray-500">
                      Compound total after day:
                    </span>
                    <span className={`font-bold ${day.running_total >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {fmt(day.running_total)}
                    </span>
                  </div>
                </>
              ) : (
                <div className="flex items-center justify-center h-48 text-gray-600 text-sm">
                  Select a day to see trades
                </div>
              )}
            </div>
          </div>

          {/* Compound P&L chart — simple bar chart */}
          {data.days.length > 1 && (
            <div className="bg-dark-800 rounded-xl p-4 border border-dark-700">
              <div className="text-xs font-bold text-gray-400 mb-3">Compound P&L Over Time</div>
              <div className="flex items-end gap-0.5 h-20">
                {data.days.map((d, i) => {
                  const maxAbs = Math.max(...data.days.map(x => Math.abs(x.running_total)), 1)
                  const pct    = Math.abs(d.running_total) / maxAbs * 100
                  const isPos  = d.running_total >= 0
                  return (
                    <div key={i} className="flex-1 flex flex-col items-center justify-end h-full group relative"
                      onClick={() => setSelectedDay(d)} style={{ cursor: 'pointer' }}>
                      <div
                        className={`w-full rounded-t transition-all ${isPos ? 'bg-green-500/70 group-hover:bg-green-400' : 'bg-red-500/70 group-hover:bg-red-400'}`}
                        style={{ height: `${Math.max(2, pct)}%` }}
                      />
                      {/* Tooltip on hover */}
                      <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:block bg-dark-900 border border-dark-600 rounded px-2 py-1 text-xs whitespace-nowrap z-10">
                        <div className="text-gray-400">{d.date}</div>
                        <div className={isPos ? 'text-green-400' : 'text-red-400'}>{fmt(d.running_total)}</div>
                      </div>
                    </div>
                  )
                })}
              </div>
              <div className="flex justify-between text-xs text-gray-600 mt-1">
                <span>{data.days[0]?.date}</span>
                <span>{data.days[data.days.length - 1]?.date}</span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

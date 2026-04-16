import { useEffect, useState } from 'react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer, Cell, Legend,
} from 'recharts'
import { getDashboardHistory, getDashboardToday } from '../services/api'

// Ranges kept as user requested. 1H/4H/1D collapse to "today"; 7D shows last 7 sessions.
const RANGES = [
  { label: '1H', days: 1 },
  { label: '4H', days: 1 },
  { label: '1D', days: 1 },
  { label: '7D', days: 7 },
]

function money(v, digits = 2) {
  const n = parseFloat(v) || 0
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function cls(...a) { return a.filter(Boolean).join(' ') }

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="bg-dark-800 border border-dark-600 rounded-lg p-3 text-xs shadow-xl min-w-[180px]">
      <p className="text-gray-400 mb-1">{p.label}</p>
      <div className="space-y-1">
        <div className="flex justify-between gap-3">
          <span className="text-gray-500">Realized</span>
          <span className={p.realized >= 0 ? 'text-green-400 font-bold' : 'text-red-400 font-bold'}>
            {p.realized >= 0 ? '+' : ''}${money(p.realized)}
          </span>
        </div>
        {(p.unrealized || 0) !== 0 && (
          <div className="flex justify-between gap-3">
            <span className="text-gray-500">Unrealized</span>
            <span className={p.unrealized >= 0 ? 'text-green-400 font-bold' : 'text-red-400 font-bold'}>
              {p.unrealized >= 0 ? '+' : ''}${money(p.unrealized)}
            </span>
          </div>
        )}
        <div className="flex justify-between gap-3 border-t border-dark-600 pt-1">
          <span className="text-gray-400">Compound</span>
          <span className={p.compound >= 0 ? 'text-brand-400 font-bold' : 'text-red-400 font-bold'}>
            {p.compound >= 0 ? '+' : ''}${money(p.compound)}
          </span>
        </div>
        <div className="flex justify-between gap-3 text-gray-500">
          <span>Trades</span>
          <span className="text-white">{p.trades} · {p.wins} W / {p.losses} L</span>
        </div>
      </div>
    </div>
  )
}

export default function PortfolioChart({ capital = 5000 }) {
  const [history, setHistory] = useState([])
  const [today,   setToday]   = useState(null)
  const [range,   setRange]   = useState(RANGES[3])   // default 7D
  const [loading, setLoading] = useState(false)

  useEffect(() => { load() /* eslint-disable-next-line */ }, [range])
  useEffect(() => {
    const iv = setInterval(load, 15000)
    return () => clearInterval(iv)
    // eslint-disable-next-line
  }, [range])

  async function load() {
    setLoading(true)
    try {
      const [hist, tod] = await Promise.all([
        getDashboardHistory(range.days).catch(() => []),
        getDashboardToday().catch(() => null),
      ])
      setHistory(Array.isArray(hist) ? hist : [])
      setToday(tod)
    } finally {
      setLoading(false)
    }
  }

  // Merge today's live row on top of history (history may or may not include it)
  const byDate = new Map()
  for (const row of history) byDate.set(row.trade_date, row)
  if (today?.trade_date) byDate.set(today.trade_date, { ...byDate.get(today.trade_date), ...today })

  const rows = [...byDate.values()].sort((a, b) => a.trade_date.localeCompare(b.trade_date))

  // Shape for Recharts: one entry per day with realized, unrealized, compound, counts
  const chartData = rows.map(r => ({
    label:      r.trade_date,
    realized:   parseFloat(r.realized_pnl   || 0),
    unrealized: parseFloat(r.unrealized_pnl || 0),
    compound:   parseFloat(r.compound_total || 0),
    trades:     parseInt(r.trade_count || 0, 10),
    wins:       parseInt(r.win_count   || 0, 10),
    losses:     parseInt(r.loss_count  || 0, 10),
  }))

  // Header numbers come from today's row (the latest truth)
  const ending   = parseFloat(today?.ending_equity  || 0) || capital
  const compound = parseFloat(today?.compound_total || 0)
  const compPct  = parseFloat(today?.compound_pct   || 0)
  const todayTotal = parseFloat(today?.total_pnl    || 0)
  const up         = todayTotal >= 0
  const cUp        = compound   >= 0

  // Nothing to chart yet
  const empty = chartData.length === 0 || chartData.every(d => !d.realized && !d.unrealized && !d.compound)

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
      {/* Header */}
      <div className="flex justify-between items-start flex-wrap gap-3">
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Portfolio Equity</p>
          <p className="text-3xl font-black text-white">${money(ending)}</p>
          <div className="flex gap-3 mt-1 flex-wrap text-sm">
            <span className={up ? 'text-green-400' : 'text-red-400'}>
              {up ? '▲ +' : '▼ '}${money(todayTotal)} today
            </span>
            <span className="text-gray-600">·</span>
            <span className={cls('font-semibold', cUp ? 'text-green-400' : 'text-red-400')}>
              Since start: {cUp ? '+' : ''}${money(compound)} ({cUp ? '+' : ''}{compPct.toFixed(2)}%)
            </span>
          </div>
        </div>

        <div className="flex gap-1">
          {RANGES.map(r => (
            <button
              key={r.label}
              onClick={() => setRange(r)}
              className={cls('px-2.5 py-1 rounded text-xs font-medium transition-colors',
                range.label === r.label
                  ? 'bg-brand-500 text-dark-900'
                  : 'bg-dark-700 text-gray-400 hover:bg-dark-600')}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="relative">
        {loading && (
          <div className="absolute top-0 right-0 z-10">
            <span className="text-brand-500 text-xs animate-pulse">Updating…</span>
          </div>
        )}
        {empty ? (
          <div className="flex flex-col items-center justify-center h-48 text-gray-500 text-sm gap-2">
            <span className="text-2xl">📈</span>
            <p>No activity yet — start the bot to build your equity history.</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={chartData} margin={{ top: 10, right: 15, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                dataKey="label"
                tick={{ fill: '#6b7280', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              {/* Left axis: daily P&L (bars) */}
              <YAxis
                yAxisId="pnl"
                tick={{ fill: '#6b7280', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => `$${v >= 1000 || v <= -1000 ? (v/1000).toFixed(1)+'k' : v.toFixed(0)}`}
                width={50}
              />
              {/* Right axis: compound cumulative (line) */}
              <YAxis
                yAxisId="compound"
                orientation="right"
                tick={{ fill: '#00d4aa', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => `$${v >= 1000 || v <= -1000 ? (v/1000).toFixed(1)+'k' : v.toFixed(0)}`}
                width={55}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(99,102,241,0.08)' }} />
              <ReferenceLine y={0} yAxisId="pnl" stroke="#374151" />
              <Legend
                verticalAlign="top"
                height={24}
                iconType="circle"
                wrapperStyle={{ fontSize: 11, color: '#9ca3af' }}
              />
              {/* Daily P&L bars — green if positive, red if negative */}
              <Bar yAxisId="pnl" dataKey="realized" name="Realized/day" radius={[3, 3, 0, 0]}>
                {chartData.map((d, i) => (
                  <Cell key={i} fill={d.realized >= 0 ? '#00d4aa' : '#ef4444'} fillOpacity={0.85} />
                ))}
              </Bar>
              {/* Cumulative compound line */}
              <Line
                yAxisId="compound"
                type="monotone"
                dataKey="compound"
                name="Compound total"
                stroke="#6366f1"
                strokeWidth={2.5}
                dot={{ r: 3, fill: '#6366f1' }}
                activeDot={{ r: 5 }}
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Stats row — now sourced from persisted DailyPnL so Current Value and
          Total Return reflect reality even before the chart has history. */}
      <div className="grid grid-cols-3 gap-3 pt-2 border-t border-dark-600">
        <div className="text-center">
          <p className="text-xs text-gray-500">Starting Capital</p>
          <p className="text-sm font-bold text-white">${money(capital, 0)}</p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-500">Current Value</p>
          <p className="text-sm font-bold text-white">${money(ending)}</p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-500">Total Return</p>
          <p className={cls('text-sm font-bold', cUp ? 'text-green-400' : 'text-red-400')}>
            {cUp ? '+' : ''}{compPct.toFixed(2)}%
          </p>
        </div>
      </div>
    </div>
  )
}

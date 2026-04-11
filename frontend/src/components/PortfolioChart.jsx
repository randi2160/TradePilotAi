import { useEffect, useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'
import { getEquityHistory } from '../services/api'

const RANGES = [
  { label: '1H',  hours: 1  },
  { label: '4H',  hours: 4  },
  { label: '1D',  hours: 24 },
  { label: '7D',  hours: 168 },
]

function CustomTooltip({ active, payload, capital }) {
  if (!active || !payload?.length) return null
  const val   = payload[0].value
  const pnl   = val - capital
  const pct   = ((pnl / capital) * 100).toFixed(2)
  const color = pnl >= 0 ? '#00d4aa' : '#ef4444'
  return (
    <div className="bg-dark-800 border border-dark-600 rounded-lg p-3 text-sm shadow-xl">
      <p className="text-gray-400 text-xs mb-1">{payload[0].payload.label}</p>
      <p className="font-bold text-white">${val.toLocaleString('en-US', {minimumFractionDigits:2})}</p>
      <p style={{ color }} className="font-medium">
        {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} ({pnl >= 0 ? '+' : ''}{pct}%)
      </p>
    </div>
  )
}

export default function PortfolioChart({ capital = 5000 }) {
  const [data,    setData]    = useState([])
  const [range,   setRange]   = useState(24)
  const [loading, setLoading] = useState(false)

  useEffect(() => { load() }, [range])

  // Simulate live tick every 5 seconds if bot is running
  useEffect(() => {
    const iv = setInterval(load, 30000)
    return () => clearInterval(iv)
  }, [range])

  async function load() {
    setLoading(true)
    try {
      const raw = await getEquityHistory(range)
      const formatted = raw.map(p => ({
        time:  new Date(p.time).getTime(),
        value: p.value,
        label: new Date(p.time).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}),
      }))
      setData(formatted)
    } catch {
      // show flat line at capital if no data
      setData([
        { time: Date.now() - 3600000, value: capital, label: '1h ago' },
        { time: Date.now(),           value: capital, label: 'Now'    },
      ])
    } finally {
      setLoading(false)
    }
  }

  const latest   = data[data.length - 1]?.value ?? capital
  const earliest = data[0]?.value               ?? capital
  const pnl      = latest - capital
  const pct      = ((pnl / capital) * 100).toFixed(2)
  const isUp     = pnl >= 0
  const color    = isUp ? '#00d4aa' : '#ef4444'
  const minVal   = Math.min(...data.map(d => d.value), capital) * 0.999
  const maxVal   = Math.max(...data.map(d => d.value), capital) * 1.001

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-1">Portfolio Value</p>
          <p className="text-3xl font-black text-white">
            ${latest.toLocaleString('en-US', {minimumFractionDigits:2})}
          </p>
          <p className={`text-sm font-semibold mt-0.5 ${isUp ? 'text-green-400' : 'text-red-400'}`}>
            {isUp ? '▲' : '▼'} {isUp ? '+' : ''}${pnl.toFixed(2)} ({isUp ? '+' : ''}{pct}%)
          </p>
        </div>

        {/* Range selector */}
        <div className="flex gap-1">
          {RANGES.map(r => (
            <button
              key={r.label}
              onClick={() => setRange(r.hours)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                range === r.hours
                  ? 'bg-brand-500 text-dark-900'
                  : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div className="relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <span className="text-brand-500 text-xs animate-pulse">Updating…</span>
          </div>
        )}
        {data.length < 2 ? (
          <div className="flex items-center justify-center h-48 text-gray-500 text-sm">
            Start the bot to record portfolio history
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={data} margin={{ top: 5, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="equity" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor={color} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={color} stopOpacity={0}   />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                dataKey="label"
                tick={{ fill: '#6b7280', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={[minVal, maxVal]}
                tick={{ fill: '#6b7280', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={v => `$${(v/1000).toFixed(1)}k`}
                width={55}
              />
              <Tooltip content={<CustomTooltip capital={capital} />} />
              <ReferenceLine y={capital} stroke="#374151" strokeDasharray="4 2" />
              <Area
                type="monotone"
                dataKey="value"
                stroke={color}
                strokeWidth={2}
                fill="url(#equity)"
                dot={false}
                activeDot={{ r: 4, fill: color }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3 pt-1 border-t border-dark-600">
        {[
          { label: 'Starting Capital', value: `$${capital.toLocaleString()}` },
          { label: 'Current Value',    value: `$${latest.toLocaleString('en-US',{minimumFractionDigits:2})}` },
          { label: 'Total Return',     value: `${isUp?'+':''}${pct}%`, color },
        ].map(({ label, value, color: c }) => (
          <div key={label} className="text-center">
            <p className="text-xs text-gray-500">{label}</p>
            <p className="text-sm font-bold" style={{ color: c || '#fff' }}>{value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

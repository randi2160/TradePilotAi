import { useState } from 'react'
import { TrendingUp, TrendingDown, Download } from 'lucide-react'

export default function TradeLog({ trades = [] }) {
  const [filter, setFilter] = useState('all')

  const pnlOf = t => parseFloat(t.pnl ?? 0)

  const filtered = trades.filter(t => {
    if (filter === 'wins')   return pnlOf(t) > 0
    if (filter === 'losses') return pnlOf(t) < 0
    return true
  })

  const totalPnl   = trades.reduce((s, t) => s + pnlOf(t), 0)
  const wins       = trades.filter(t => pnlOf(t) > 0).length
  const losses     = trades.filter(t => pnlOf(t) < 0).length
  const winRate    = trades.length ? ((wins / trades.length) * 100).toFixed(1) : 0
  const avgWin     = wins   ? (trades.filter(t=>pnlOf(t)>0).reduce((s,t)=>s+pnlOf(t),0)/wins).toFixed(2) : 0
  const avgLoss    = losses ? (trades.filter(t=>pnlOf(t)<0).reduce((s,t)=>s+pnlOf(t),0)/losses).toFixed(2) : 0

  function exportCSV() {
    const cols = ['id','symbol','side','qty','entry_price','exit_price','pnl','pnl_pct','timestamp']
    const rows = [cols.join(','), ...trades.map(t => cols.map(c => t[c]).join(','))]
    const blob = new Blob([rows.join('\n')], { type: 'text/csv' })
    const a    = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'trades.csv' })
    a.click()
  }

  return (
    <div className="space-y-4">
      {/* Summary row */}
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: 'Total P&L',  value: `${totalPnl>=0?'+':''}$${totalPnl.toFixed(2)}`,  color: totalPnl>=0?'text-green-400':'text-red-400' },
          { label: 'Win Rate',   value: `${winRate}%`,  color: parseFloat(winRate)>=50?'text-green-400':'text-red-400' },
          { label: 'Avg Win',    value: `+$${avgWin}`,  color: 'text-green-400' },
          { label: 'Avg Loss',   value: `$${avgLoss}`,  color: 'text-red-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-dark-800 border border-dark-600 rounded-xl p-3 text-center">
            <p className="text-xs text-gray-500">{label}</p>
            <p className={`text-sm font-bold ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Filters + export */}
      <div className="flex items-center gap-2">
        {['all','wins','losses'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-lg text-xs font-medium capitalize transition-colors ${
              filter === f ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}
          >
            {f} {f === 'all' ? `(${trades.length})` : f === 'wins' ? `(${wins})` : `(${losses})`}
          </button>
        ))}
        <button
          onClick={exportCSV}
          className="ml-auto flex items-center gap-1 text-xs text-gray-400 hover:text-white bg-dark-700 hover:bg-dark-600 px-3 py-1 rounded-lg transition-colors"
        >
          <Download size={12} /> Export CSV
        </button>
      </div>

      {/* Trade table */}
      {filtered.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <p className="text-4xl mb-3">📋</p>
          <p>No trades yet — start the bot to begin trading.</p>
        </div>
      ) : (
        <div className="space-y-2 max-h-[520px] overflow-y-auto pr-1">
          {filtered.map(t => (
            <div
              key={t.id}
              className={`flex items-center gap-3 p-3 rounded-xl border transition-colors ${
                pnlOf(t) >= 0
                  ? 'bg-green-900/10 border-green-900/40'
                  : 'bg-red-900/10 border-red-900/40'
              }`}
            >
              {/* Icon */}
              <div className={`rounded-lg p-1.5 ${pnlOf(t)>=0?'bg-green-900/50':'bg-red-900/50'}`}>
                {pnlOf(t) >= 0
                  ? <TrendingUp  size={14} className="text-green-400" />
                  : <TrendingDown size={14} className="text-red-400"  />
                }
              </div>

              {/* Symbol + side */}
              <div className="w-24">
                <p className="font-bold text-white text-sm">{t.symbol}</p>
                <span className={`text-xs px-1.5 py-0.5 rounded ${
                  t.side === 'BUY'
                    ? 'bg-green-900/60 text-green-300'
                    : 'bg-red-900/60 text-red-300'
                }`}>
                  {t.side} {t.qty}
                </span>
              </div>

              {/* Entry / Exit */}
              <div className="flex-1 text-xs text-gray-400">
                <span>${t.entry_price}</span>
                <span className="mx-1 text-gray-600">→</span>
                <span>${t.exit_price}</span>
              </div>

              {/* AI confidence */}
              {t.confidence > 0 && (
                <div className="text-xs text-gray-500 hidden md:block">
                  {(t.confidence * 100).toFixed(0)}% conf
                </div>
              )}

              {/* P&L */}
              <div className="text-right min-w-[70px]">
                <p className={`font-bold text-sm ${pnlOf(t)>=0?'text-green-400':'text-red-400'}`}>
                  {pnlOf(t)>=0?'+':''}${pnlOf(t).toFixed(2)}
                </p>
                <p className={`text-xs ${(parseFloat(t.pnl_pct??0))>=0?'text-green-500':'text-red-500'}`}>
                  {(parseFloat(t.pnl_pct??0))>=0?'+':''}{(parseFloat(t.pnl_pct??0)).toFixed(2)}%
                </p>
              </div>

              {/* Time */}
              <div className="text-xs text-gray-600 hidden lg:block min-w-[60px] text-right">
                {new Date(t.timestamp).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

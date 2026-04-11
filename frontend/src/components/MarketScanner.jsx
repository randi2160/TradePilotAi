import { useEffect, useState } from 'react'
import { runScan } from '../services/api'

function StockRow({ stock, rank, onAddToWatchlist }) {
  const up = stock.change_pct >= 0
  return (
    <div className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-dark-700 transition-colors group">
      <span className="text-xs text-gray-600 w-5 text-right">{rank}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-bold text-white text-sm">{stock.symbol}</span>
          <span className="text-xs text-gray-500 truncate hidden sm:block">{stock.name}</span>
        </div>
        <div className="flex gap-2 text-xs text-gray-500 mt-0.5">
          <span>Vol: {(stock.volume/1_000_000).toFixed(1)}M</span>
          {stock.high > 0 && <span>H: ${stock.high}</span>}
          {stock.low  > 0 && <span>L: ${stock.low}</span>}
        </div>
      </div>
      <div className="text-right">
        <p className="font-bold text-sm text-white">${stock.price?.toFixed(2) ?? '—'}</p>
        <p className={`text-xs font-semibold ${up?'text-green-400':'text-red-400'}`}>
          {up?'+':''}{stock.change_pct?.toFixed(2)}%
        </p>
      </div>
      {onAddToWatchlist && (
        <button
          onClick={() => onAddToWatchlist(stock.symbol)}
          className="opacity-0 group-hover:opacity-100 text-xs text-brand-500 hover:text-brand-400 px-2 py-1 rounded bg-dark-600 transition-all"
          title="Add to watchlist"
        >
          +
        </button>
      )}
    </div>
  )
}

export default function MarketScanner({ onAddToWatchlist }) {
  const [data,    setData]    = useState(null)
  const [tab,     setTab]     = useState('gainers')
  const [loading, setLoading] = useState(false)
  const [lastUpd, setLastUpd] = useState('')

  useEffect(() => { load() }, [])
  useEffect(() => {
    const iv = setInterval(load, 60000)
    return () => clearInterval(iv)
  }, [])

  async function load() {
    setLoading(true)
    try {
      const res = await runScan()
      setData(res)
      setLastUpd(new Date().toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}))
    } catch { /* silent */ }
    finally { setLoading(false) }
  }

  const lists = {
    gainers:     data?.gainers      ?? [],
    losers:      data?.losers       ?? [],
    most_active: data?.most_active  ?? [],
  }

  const TABS = [
    { id: 'gainers',     label: '🟢 Top Gainers', color: 'text-green-400' },
    { id: 'losers',      label: '🔴 Top Losers',  color: 'text-red-400'   },
    { id: 'most_active', label: '🔥 Most Active',  color: 'text-yellow-400'},
  ]

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          {TABS.map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                tab === t.id ? 'bg-dark-600 text-white' : 'text-gray-400 hover:bg-dark-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          {lastUpd && <span className="text-xs text-gray-500">Updated {lastUpd}</span>}
          <button
            onClick={load}
            disabled={loading}
            className="text-xs bg-dark-700 hover:bg-dark-600 text-gray-400 px-2 py-1 rounded transition-colors"
          >
            {loading ? '⟳' : '↻'} Scan
          </button>
        </div>
      </div>

      {/* Note */}
      {onAddToWatchlist && (
        <p className="text-xs text-gray-500">Hover a stock and click <span className="text-brand-500">+</span> to add it to your watchlist</p>
      )}

      {/* List */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl overflow-hidden">
        {lists[tab].length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p className="text-3xl mb-2">📡</p>
            <p className="text-sm">Scanning market… {loading ? 'Loading…' : 'Click Scan to refresh'}</p>
          </div>
        ) : (
          <div className="divide-y divide-dark-700">
            {lists[tab].map((stock, i) => (
              <StockRow
                key={stock.symbol}
                stock={stock}
                rank={i + 1}
                onAddToWatchlist={onAddToWatchlist}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

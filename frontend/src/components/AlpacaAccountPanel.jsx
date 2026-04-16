import { useEffect, useState } from 'react'
import { Wallet, TrendingUp, TrendingDown, Zap, AlertTriangle } from 'lucide-react'
import { getAlpacaSnapshot } from '../services/api'

function money(v, digits = 2) {
  const n = parseFloat(v) || 0
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function cls(...a) { return a.filter(Boolean).join(' ') }

/**
 * AlpacaAccountPanel — mirrors the live Alpaca account (equity, cash, buying
 * power, today's gain/loss, PDT). Refreshes every 10s. Shows a connect CTA if
 * no broker is wired up yet.
 */
export default function AlpacaAccountPanel() {
  const [snap,    setSnap]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [err,     setErr]     = useState('')

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const r = await getAlpacaSnapshot()
        if (!alive) return
        setSnap(r); setErr('')
      } catch (e) {
        if (!alive) return
        setErr(e?.response?.data?.detail || e.message || 'Failed to load')
      } finally {
        if (alive) setLoading(false)
      }
    }
    load()
    const iv = setInterval(load, 10000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  if (loading && !snap) {
    return (
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 h-full flex items-center justify-center">
        <p className="text-xs text-gray-500">Loading Alpaca account…</p>
      </div>
    )
  }

  if (err || !snap?.connected) {
    return (
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 h-full flex flex-col items-center justify-center gap-3 text-center">
        <Wallet size={28} className="text-gray-600" />
        <p className="text-sm font-bold text-gray-300">Alpaca Account</p>
        <p className="text-xs text-gray-500 max-w-xs">
          {snap?.error || err || 'Not connected.'}
        </p>
        <button
          onClick={() => window.dispatchEvent(new CustomEvent('navigate', { detail: 'broker' }))}
          className="text-xs px-3 py-1.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-lg"
        >
          Connect Broker →
        </button>
      </div>
    )
  }

  const dayUp    = (snap.pnl_today || 0) >= 0
  const dayColor = dayUp ? 'text-green-400' : 'text-red-400'
  const DayIcon  = dayUp ? TrendingUp : TrendingDown

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Wallet size={16} className="text-brand-500" />
          <h3 className="text-sm font-bold text-gray-200">Alpaca Account</h3>
        </div>
        <span className="text-xs px-2 py-0.5 rounded-full bg-green-900/30 text-green-400 border border-green-800/40 font-bold">
          ● LIVE
        </span>
      </div>

      {/* Equity + day gain */}
      <div className="mb-4">
        <p className="text-xs text-gray-400 uppercase tracking-wide">Account Equity</p>
        <p className="text-3xl font-black text-white mt-0.5">
          ${money(snap.equity)}
        </p>
        <div className={cls('flex items-center gap-1.5 text-sm font-semibold mt-1', dayColor)}>
          <DayIcon size={14} />
          <span>{dayUp ? '+' : ''}${money(snap.pnl_today)}</span>
          <span className="text-xs text-gray-500 font-normal">today</span>
        </div>
      </div>

      {/* Balance grid */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="bg-dark-700 rounded-lg p-2.5">
          <p className="text-xs text-gray-500">Cash</p>
          <p className="text-sm font-bold text-white">${money(snap.cash)}</p>
        </div>
        <div className="bg-dark-700 rounded-lg p-2.5">
          <p className="text-xs text-gray-500">Portfolio Value</p>
          <p className="text-sm font-bold text-white">${money(snap.portfolio_value)}</p>
        </div>
        <div className="bg-dark-700 rounded-lg p-2.5">
          <p className="text-xs text-gray-500 flex items-center gap-1">
            <Zap size={10} /> Buying Power
          </p>
          <p className="text-sm font-bold text-brand-400">${money(snap.buying_power)}</p>
        </div>
        <div className="bg-dark-700 rounded-lg p-2.5">
          <p className="text-xs text-gray-500">Day Trade BP</p>
          <p className="text-sm font-bold text-white">${money(snap.daytrading_bp)}</p>
        </div>
      </div>

      {/* PDT status */}
      <div className="mt-auto pt-3 border-t border-dark-600">
        {snap.is_pdt_exempt ? (
          <p className="text-xs text-green-400 flex items-center gap-1.5">
            ✅ PDT exempt — trade freely
          </p>
        ) : (
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400">Day trades today</span>
            <span className={cls('font-bold',
              (snap.day_trades_remaining || 0) === 0 ? 'text-red-400' :
              (snap.day_trades_remaining || 0) === 1 ? 'text-yellow-400' :
              'text-green-400')}>
              {snap.daytrade_count || 0} / 3 used · {snap.day_trades_remaining || 0} left
            </span>
          </div>
        )}
        {!snap.is_pdt_exempt && (snap.day_trades_remaining || 0) === 0 && (
          <p className="text-xs text-red-400 mt-2 flex items-start gap-1.5">
            <AlertTriangle size={12} className="flex-shrink-0 mt-0.5" />
            <span>New entries must hold overnight. Crypto is exempt.</span>
          </p>
        )}
      </div>
    </div>
  )
}

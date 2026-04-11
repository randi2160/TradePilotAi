import { useState } from 'react'
import { api } from '../hooks/useAuth'
import { TrendingUp, TrendingDown, AlertTriangle } from 'lucide-react'

export default function ManualTrade({ capital = 5000, onTrade }) {
  const [side,    setSide]    = useState('BUY')
  const [symbol,  setSymbol]  = useState('')
  const [qty,     setQty]     = useState(1)
  const [price,   setPrice]   = useState('')
  const [loading, setLoading] = useState(false)
  const [msg,     setMsg]     = useState('')
  const [confirm, setConfirm] = useState(false)

  const posValue    = qty * (parseFloat(price) || 0)
  const pctOfCap    = capital > 0 ? (posValue / capital * 100).toFixed(1) : 0
  const isOversized = posValue > capital * 0.25

  function flash(text) { setMsg(text); setTimeout(() => setMsg(''), 4000) }

  async function fetchPrice() {
    if (!symbol.trim()) return
    try {
      const r = await api.get(`/chart/${symbol.trim().toUpperCase()}?timeframe=1Min&limit=2`)
      if (r.data?.length) setPrice(r.data[r.data.length-1].close.toFixed(2))
    } catch { flash('Could not fetch price — enter manually') }
  }

  async function submit() {
    if (!symbol || !qty || !price) { flash('❌ Fill in all fields'); return }
    if (!confirm) { setConfirm(true); return }

    setLoading(true)
    setConfirm(false)
    try {
      await api.post('/trades/manual', {
        symbol:      symbol.toUpperCase(),
        side,
        qty:         parseFloat(qty),
        entry_price: parseFloat(price),
      })
      flash(`✅ ${side} ${qty}× ${symbol.toUpperCase()} @ $${price} submitted!`)
      setSymbol(''); setQty(1); setPrice('')
      onTrade?.()
    } catch(e) {
      flash(`❌ ${e.response?.data?.detail ?? e.message}`)
    } finally { setLoading(false) }
  }

  async function closePosition(symbol) {
    try {
      await api.post(`/trades/manual/close/${symbol.toUpperCase()}`)
      flash(`✅ ${symbol} position closed`)
      onTrade?.()
    } catch(e) { flash(`❌ ${e.response?.data?.detail ?? e.message}`) }
  }

  return (
    <div className="space-y-5">
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
        <h3 className="font-bold text-white flex items-center gap-2">
          ✋ Manual Trade Ticket
          <span className="text-xs bg-yellow-900/40 text-yellow-400 border border-yellow-800/50 px-2 py-0.5 rounded-full">
            PAPER MODE
          </span>
        </h3>

        {/* BUY / SELL */}
        <div className="grid grid-cols-2 gap-2">
          {['BUY','SELL'].map(s => (
            <button key={s} onClick={() => setSide(s)}
              className={`py-3 rounded-xl font-black text-sm flex items-center justify-center gap-2 transition-all ${
                side === s
                  ? s === 'BUY'
                    ? 'bg-green-600 text-white'
                    : 'bg-red-600 text-white'
                  : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
              }`}>
              {s === 'BUY' ? <TrendingUp size={16}/> : <TrendingDown size={16}/>} {s}
            </button>
          ))}
        </div>

        {/* Symbol */}
        <div>
          <label className="block text-xs text-gray-400 mb-1">Symbol</label>
          <div className="flex gap-2">
            <input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())}
              placeholder="AAPL" maxLength={8}
              className="flex-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500 font-mono uppercase"
              onBlur={fetchPrice}/>
            <button onClick={fetchPrice}
              className="px-3 py-2 bg-dark-700 hover:bg-dark-600 text-gray-400 rounded-xl text-xs transition-colors">
              Get Price
            </button>
          </div>
        </div>

        {/* Qty + Price */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Quantity (shares)</label>
            <input type="number" value={qty} onChange={e => setQty(e.target.value)} min={1} step={1}
              className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500"/>
          </div>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Price ($)</label>
            <input type="number" value={price} onChange={e => setPrice(e.target.value)} step="0.01"
              placeholder="Market price"
              className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500"/>
          </div>
        </div>

        {/* Position summary */}
        {posValue > 0 && (
          <div className={`p-3 rounded-xl text-sm space-y-1 ${
            isOversized ? 'bg-red-900/20 border border-red-800/50' : 'bg-dark-700'
          }`}>
            <div className="flex justify-between">
              <span className="text-gray-400">Position Value</span>
              <span className="text-white font-bold">${posValue.toLocaleString('en-US',{minimumFractionDigits:2})}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">% of Capital</span>
              <span className={`font-bold ${isOversized ? 'text-red-400' : 'text-white'}`}>{pctOfCap}%</span>
            </div>
            {isOversized && (
              <p className="text-red-400 text-xs flex items-center gap-1 mt-1">
                <AlertTriangle size={12}/> Position exceeds 25% of capital — consider reducing size
              </p>
            )}
          </div>
        )}

        {/* Warning + confirm */}
        {confirm && (
          <div className="bg-yellow-900/30 border border-yellow-700 rounded-xl p-3 text-sm text-yellow-300">
            ⚠️ Confirm: {side} {qty} shares of {symbol} @ ${price}?
            <br/>Position value: ${posValue.toFixed(2)}
          </div>
        )}

        {msg && <p className="text-sm text-center">{msg}</p>}

        <button onClick={submit} disabled={loading || !symbol || !qty}
          className={`w-full py-3.5 rounded-xl font-black text-sm transition-colors disabled:opacity-40 ${
            confirm
              ? 'bg-yellow-500 text-dark-900 animate-pulse'
              : side === 'BUY'
              ? 'bg-green-600 hover:bg-green-500 text-white'
              : 'bg-red-600 hover:bg-red-500 text-white'
          }`}>
          {loading ? 'Submitting…' : confirm ? '⚠️ Click again to CONFIRM' : `${side} ${qty || ''} ${symbol || 'shares'}`}
        </button>
      </div>

      {/* Close position shortcut */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-4 space-y-3">
        <h4 className="text-sm font-bold text-white">Quick Close Position</h4>
        <div className="flex gap-2">
          <input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())}
            placeholder="Symbol to close" maxLength={8}
            className="flex-1 bg-dark-700 border border-dark-600 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500"/>
          <button onClick={() => closePosition(symbol)} disabled={!symbol}
            className="px-4 py-2 bg-red-800 hover:bg-red-700 text-white text-sm font-bold rounded-xl transition-colors disabled:opacity-40">
            Close
          </button>
        </div>
        <p className="text-xs text-gray-500">Closes the full position at market price immediately</p>
      </div>
    </div>
  )
}

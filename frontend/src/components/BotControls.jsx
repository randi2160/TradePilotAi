import { useState } from 'react'
import { Play, Square, RefreshCw, AlertTriangle, Zap, Shield } from 'lucide-react'
import { startBot, stopBot, closeAll, retrain } from '../services/api'

export default function BotControls({ data }) {
  const [loading, setLoading] = useState('')
  const [mode, setMode]       = useState('paper')
  const [msg, setMsg]         = useState('')

  const status = data?.bot_status ?? 'stopped'
  const running = status === 'running'

  async function act(fn, label, confirmMsg) {
    if (confirmMsg && !window.confirm(confirmMsg)) return
    setLoading(label)
    setMsg('')
    try {
      const res = await fn()
      setMsg(`✅ ${res.status ?? label}`)
    } catch (e) {
      setMsg(`❌ Error: ${e.message}`)
    } finally {
      setLoading('')
    }
  }

  return (
    <div className="space-y-5">

      {/* Status banner */}
      <div className={`flex items-center gap-3 p-4 rounded-xl border ${
        running
          ? 'bg-green-900/20 border-green-800'
          : 'bg-dark-700 border-dark-600'
      }`}>
        <div className={`w-3 h-3 rounded-full ${running ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`} />
        <div>
          <p className="font-bold text-white capitalize">{status}</p>
          <p className="text-xs text-gray-400">
            {running ? `Trading in ${data?.mode?.toUpperCase() ?? 'PAPER'} mode` : 'Bot is idle'}
          </p>
        </div>
        {running && (
          <span className="ml-auto text-xs bg-green-900 text-green-300 px-2 py-1 rounded-full font-medium">
            {data?.mode?.toUpperCase()}
          </span>
        )}
      </div>

      {/* Mode selector */}
      {!running && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
          <p className="text-sm text-gray-400 mb-3">Select trading mode before starting:</p>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => setMode('paper')}
              className={`p-3 rounded-lg border text-left transition-all ${
                mode === 'paper'
                  ? 'border-brand-500 bg-brand-500/10'
                  : 'border-dark-600 hover:border-dark-500'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Shield size={15} className="text-brand-500" />
                <span className="font-semibold text-white text-sm">Paper</span>
              </div>
              <p className="text-xs text-gray-400">Fake money, real market. Safe for testing.</p>
            </button>
            <button
              onClick={() => setMode('live')}
              className={`p-3 rounded-lg border text-left transition-all ${
                mode === 'live'
                  ? 'border-red-500 bg-red-500/10'
                  : 'border-dark-600 hover:border-dark-500'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Zap size={15} className="text-red-400" />
                <span className="font-semibold text-white text-sm">Live</span>
              </div>
              <p className="text-xs text-gray-400">Real money. Only use after paper testing.</p>
            </button>
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="grid grid-cols-2 gap-3">
        {!running ? (
          <button
            onClick={() => act(() => startBot(mode), 'start')}
            disabled={!!loading}
            className="col-span-2 flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold py-3 rounded-xl transition-colors disabled:opacity-50"
          >
            <Play size={18} />
            {loading === 'start' ? 'Starting…' : `Start Bot (${mode.toUpperCase()})`}
          </button>
        ) : (
          <button
            onClick={() => act(stopBot, 'stop')}
            disabled={!!loading}
            className="col-span-2 flex items-center justify-center gap-2 bg-gray-700 hover:bg-gray-600 text-white font-bold py-3 rounded-xl transition-colors disabled:opacity-50"
          >
            <Square size={18} />
            {loading === 'stop' ? 'Stopping…' : 'Stop Bot'}
          </button>
        )}

        <button
          onClick={() => act(retrain, 'retrain')}
          disabled={!!loading || !running}
          className="flex items-center justify-center gap-2 bg-dark-700 hover:bg-dark-600 text-white py-2.5 rounded-xl text-sm transition-colors disabled:opacity-40"
        >
          <RefreshCw size={15} />
          {loading === 'retrain' ? 'Training…' : 'Retrain AI'}
        </button>

        <button
          onClick={() => act(
            closeAll, 'close-all',
            '⚠️ Close ALL open positions immediately?'
          )}
          disabled={!!loading}
          className="flex items-center justify-center gap-2 bg-red-900/40 hover:bg-red-900/70 text-red-400 border border-red-800 py-2.5 rounded-xl text-sm transition-colors disabled:opacity-40"
        >
          <AlertTriangle size={15} />
          {loading === 'close-all' ? 'Closing…' : 'Close All'}
        </button>
      </div>

      {msg && (
        <p className="text-sm text-center text-gray-300 bg-dark-700 rounded-lg py-2">{msg}</p>
      )}

      {/* Config summary */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-4 space-y-2">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Current Config</p>
        {[
          ['Capital',        `$${data?.capital?.toLocaleString() ?? '5,000'}`],
          ['Daily Target',   `$${data?.target_min ?? 100} – $${data?.target_max ?? 250}`],
          ['Max Daily Loss', '$150 (kill-switch)'],
          ['Max Positions',  '3 concurrent'],
          ['Risk Model',     'AI Dynamic (ATR-based)'],
          ['Scan Interval',  'Every 30 seconds'],
          ['Timeframe',      '5-min bars'],
        ].map(([k, v]) => (
          <div key={k} className="flex justify-between text-sm">
            <span className="text-gray-400">{k}</span>
            <span className="text-white font-medium">{v}</span>
          </div>
        ))}
      </div>

      {/* Safety rules */}
      <div className="bg-yellow-900/20 border border-yellow-800/50 rounded-xl p-4">
        <p className="text-xs font-bold text-yellow-400 mb-2">⚠️ Safety Rules (always active)</p>
        <ul className="text-xs text-yellow-200/70 space-y-1">
          <li>• Bot stops automatically when $250 target is hit</li>
          <li>• Bot stops if daily loss exceeds $150</li>
          <li>• No new trades after 3:30 PM ET</li>
          <li>• All positions auto-closed at 3:55 PM ET</li>
          <li>• Max 3 open positions at any time</li>
        </ul>
      </div>
    </div>
  )
}

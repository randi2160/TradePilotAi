import { useState, useEffect } from 'react'
import { Play, Square, RefreshCw, AlertTriangle, Zap, Shield } from 'lucide-react'
import { startBot, stopBot, closeAll, retrain } from '../services/api'
import { api } from '../hooks/useAuth'

// ── Crypto / Hybrid Engine Panel ──────────────────────────────────────────────
function CryptoEnginePanel({ settings }) {
  const [status,  setStatus]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [msg,     setMsg]     = useState('')

  const savedMode = settings?.engine_mode || 'stocks_only'

  useEffect(() => {
    loadStatus()
    const iv = setInterval(loadStatus, 10000)
    return () => clearInterval(iv)
  }, [])

  async function loadStatus() {
    try {
      const r = await api.get('/bot/engine-status')
      setStatus(r.data)
    } catch {}
  }

  async function startCrypto() {
    setLoading(true)
    setMsg('⏳ Starting engine — this can take a few seconds…')
    try {
      const r = await api.post('/bot/engine-mode', {
        mode:         savedMode === 'stocks_only' ? 'hybrid' : savedMode,
        crypto_alloc: settings?.crypto_alloc_pct || 0.30,
      }, { timeout: 30000 })
      setMsg('✅ ' + r.data.message)
      // Update running state immediately from response, then refresh full status
      if (r.data.crypto_running) {
        setStatus(prev => ({ ...prev, crypto_running: true }))
      }
      await loadStatus()
    } catch (e) {
      const detail = e.response?.data?.detail || e.message
      setMsg('❌ ' + (e.code === 'ECONNABORTED' ? 'Request timed out — check AWS logs' : detail))
    } finally {
      setLoading(false)
    }
  }

  async function stopCrypto() {
    setLoading(true)
    try {
      const r = await api.post('/bot/engine-stop')
      setMsg('⏹ ' + r.data.message)
      loadStatus()
    } catch (e) {
      setMsg('❌ ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  // Always show the crypto/hybrid panel so users can start it from any mode.
  // When savedMode is 'stocks_only', clicking Start will auto-switch to 'hybrid'.

  const crypto  = status?.crypto
  const running = status?.crypto_running

  const STATE_COLOR = {
    idle:               'text-gray-400',
    scanning:           'text-yellow-400',
    position_open:      'text-green-400',
    locked_profit_mode: 'text-green-400',
    stopped_for_day:    'text-red-400',
    error:              'text-red-400',
    funds_refreshing:   'text-blue-400',
    ready_for_reentry:  'text-brand-400',
  }

  const borderClass = running
    ? 'border-brand-500/40 bg-brand-500/5'
    : 'border-dark-600 bg-dark-800'

  return (
    <div className={'border rounded-xl p-4 space-y-3 ' + borderClass}>
      <div className="flex items-center gap-2">
        <span className="text-sm font-bold text-white">₿ Crypto Engine</span>
        {settings?.crypto_strategy === 'bounce' && (
          <span className="text-xs px-2 py-0.5 rounded-full font-bold border text-purple-400 bg-purple-900/20 border-purple-800/40">
            🔄 Bounce
          </span>
        )}
        {settings?.crypto_strategy !== 'bounce' && (
          <span className="text-xs px-2 py-0.5 rounded-full font-bold border text-blue-400 bg-blue-900/20 border-blue-800/40">
            ⚡ Scalp
          </span>
        )}
        <span className={'text-xs px-2 py-0.5 rounded-full font-bold border ' + (
          running
            ? 'text-green-400 bg-green-900/20 border-green-800/40'
            : 'text-gray-500 bg-dark-700 border-dark-600'
        )}>
          {running ? '● ACTIVE' : '○ IDLE'}
        </span>
        <span className="text-xs text-gray-500 ml-1">
          {savedMode === 'hybrid'
            ? 'Hybrid · ' + Math.round((settings?.crypto_alloc_pct || 0.3) * 100) + '% crypto'
            : savedMode === 'crypto_only' ? 'Crypto Only'
            : 'Stocks Only · click Start to enable Hybrid'}
        </span>
        <button onClick={loadStatus} className="ml-auto p-1 text-gray-600 hover:text-white">
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''}/>
        </button>
      </div>

      {running && crypto && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs text-center">
          <div className="bg-dark-700 rounded-lg p-2">
            <div className="text-gray-500">State</div>
            <div className={'font-bold mt-0.5 capitalize ' + (STATE_COLOR[crypto.state] || 'text-white')}>
              {(crypto.state || '').replace(/_/g, ' ')}
            </div>
          </div>
          <div className="bg-dark-700 rounded-lg p-2">
            <div className="text-gray-500">P&L Today</div>
            <div className={'font-bold mt-0.5 ' + ((crypto.realized_pnl || 0) >= 0 ? 'text-green-400' : 'text-red-400')}>
              {'$' + (crypto.realized_pnl || 0).toFixed(2)}
            </div>
          </div>
          <div className="bg-dark-700 rounded-lg p-2">
            <div className="text-gray-500">To Min Target</div>
            <div className="font-bold mt-0.5 text-brand-400">
              {'$' + (crypto.remaining_to_min || 0).toFixed(2)}
            </div>
          </div>
          <div className="bg-dark-700 rounded-lg p-2">
            <div className="text-gray-500">Positions</div>
            <div className="font-bold mt-0.5 text-white">{crypto.open_positions || 0}</div>
          </div>
        </div>
      )}

      {running && crypto?.locked_floor != null && (
        <div className="text-xs flex items-center gap-2 p-2 bg-green-900/15 border border-green-800/30 rounded-lg">
          <span className="text-green-400">🔒 Profit floor locked at ${crypto.locked_floor.toFixed(2)} — gains protected</span>
        </div>
      )}

      {msg && (
        <div className={'text-xs p-2 rounded-lg ' + (
          msg.startsWith('✅') ? 'bg-green-900/20 text-green-400' :
          msg.startsWith('❌') ? 'bg-red-900/20 text-red-400' :
          'bg-dark-700 text-gray-400'
        )}>
          {msg}
        </div>
      )}

      <div className="flex gap-2">
        {!running ? (
          <button
            onClick={startCrypto}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl text-sm disabled:opacity-50"
          >
            <Zap size={14}/>
            {loading ? 'Starting…' : 'Start ' + (savedMode === 'crypto_only' ? 'Crypto' : 'Hybrid') + ' Engine'}
          </button>
        ) : (
          <button
            onClick={stopCrypto}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-red-900/40 hover:bg-red-900/60 text-red-400 border border-red-800/40 rounded-xl text-sm disabled:opacity-50"
          >
            <Square size={14}/>
            {loading ? 'Stopping…' : 'Stop Crypto Engine'}
          </button>
        )}
      </div>

      <p className="text-xs text-gray-600">
        {running
          ? 'Scanning crypto markets every 30 seconds · No PDT restrictions · 24/7'
          : 'Broker must be connected to start crypto trading.'}
      </p>
    </div>
  )
}

// ── Main BotControls ──────────────────────────────────────────────────────────
export default function BotControls({ data, user }) {
  const [loading,  setLoading]  = useState('')
  const [mode,     setMode]     = useState('paper')
  const [msg,      setMsg]      = useState('')
  const [settings, setSettings] = useState(null)

  const status  = data?.bot_status ?? 'stopped'
  const running = status === 'running'

  useEffect(() => {
    api.get('/settings').then(r => setSettings(r.data)).catch(() => {})
  }, [])

  async function act(fn, label, confirmMsg) {
    if (confirmMsg && !window.confirm(confirmMsg)) return
    setLoading(label)
    try {
      await fn()
      setMsg('')
    } catch (e) {
      setMsg('Error: ' + (e.response?.data?.detail || e.message))
    } finally {
      setLoading('')
    }
  }

  const configRows = [
    ['Capital',        '$' + (data?.settings?.capital ?? settings?.capital ?? 5000).toLocaleString()],
    ['Daily Target',   '$' + (data?.target_min ?? settings?.daily_target_min ?? 100) + ' – $' + (data?.target_max ?? settings?.daily_target_max ?? 250)],
    ['Max Daily Loss', '$' + (settings?.max_daily_loss ?? 150) + ' (kill-switch)'],
    ['Max Positions',  (settings?.max_open_positions ?? 3) + ' concurrent'],
    ['Risk Model',     'AI Dynamic (ATR-based)'],
    ['Scan Interval',  'Every 30 seconds'],
    ['Timeframe',      '5-min bars'],
  ]

  return (
    <div className="space-y-4">

      {/* Status */}
      <div className={'rounded-xl p-4 border ' + (running ? 'bg-green-900/20 border-green-800/40' : 'bg-dark-800 border-dark-600')}>
        <div className="flex items-center gap-3">
          <div className={'w-3 h-3 rounded-full ' + (running ? 'bg-green-400 animate-pulse' : 'bg-gray-600')}/>
          <span className={'font-bold ' + (running ? 'text-green-400' : 'text-gray-400')}>
            {running ? 'Running' : 'Stopped'}
          </span>
          <span className="text-xs text-gray-500">
            Trading in {(data?.mode || 'PAPER').toUpperCase()} mode
          </span>
          {data?.mode === 'live' && (
            <span className="ml-auto text-xs px-2 py-1 rounded font-bold bg-red-900 text-red-300 animate-pulse">
              ⚠️ LIVE $
            </span>
          )}
          {data?.mode !== 'live' && (
            <span className="ml-auto text-xs px-2 py-1 rounded bg-dark-600 text-gray-400 font-bold">PAPER</span>
          )}
        </div>
      </div>

      {/* Mode selector */}
      {!running && (() => {
        const tier    = user?.subscription_tier || 'free'
        const isAdmin = user?.is_admin
        const canLive = isAdmin || (tier !== 'free')
        return (
          <div className="grid grid-cols-2 gap-3">
            {[
              { id: 'paper', icon: '🛡️', title: 'Paper',  desc: 'Fake money, real market. Safe for testing.' },
              { id: 'live',  icon: '⚡', title: 'Live',   desc: canLive ? 'Real money. Only use after paper testing.' : 'Upgrade to a paid plan to enable live trading.' },
            ].map(m => {
              const locked = m.id === 'live' && !canLive
              return (
                <button
                  key={m.id}
                  onClick={() => !locked && setMode(m.id)}
                  disabled={locked}
                  className={'p-4 rounded-xl border text-left transition-all ' + (
                    locked
                      ? 'border-dark-600 bg-dark-800 opacity-50 cursor-not-allowed'
                      : mode === m.id
                        ? m.id === 'live'
                          ? 'border-red-600 bg-red-900/20'
                          : 'border-brand-500 bg-brand-500/10'
                        : 'border-dark-600 bg-dark-800 hover:border-dark-500'
                  )}
                >
                  <div className="flex items-center gap-2 font-bold text-white mb-1">
                    <span>{m.icon}</span> {m.title}
                    {locked && <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-900/40 text-yellow-400 font-medium ml-auto">PRO</span>}
                  </div>
                  <p className="text-xs text-gray-400">{m.desc}</p>
                </button>
              )
            })}
          </div>
        )
      })()}

      {/* Start / Stop */}
      {!running ? (
        <button
          onClick={() => act(() => startBot(mode, 'auto'), 'start')}
          disabled={loading === 'start'}
          className="w-full flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold px-6 py-3.5 rounded-xl disabled:opacity-50 transition-colors text-base"
        >
          <Play size={18}/>
          {loading === 'start' ? 'Starting…' : 'Start Bot (' + mode.toUpperCase() + ')'}
        </button>
      ) : (
        <button
          onClick={() => act(stopBot, 'stop', 'Stop the bot? Open positions will remain open.')}
          disabled={loading === 'stop'}
          className="w-full flex items-center justify-center gap-2 bg-dark-700 hover:bg-dark-600 text-white border border-dark-500 font-bold px-6 py-3 rounded-xl disabled:opacity-50 transition-colors"
        >
          <Square size={16}/>
          {loading === 'stop' ? 'Stopping…' : 'Stop Bot'}
        </button>
      )}

      {/* Retrain / Close All */}
      <div className="grid grid-cols-2 gap-3">
        <button
          onClick={() => act(retrain, 'retrain')}
          disabled={!!loading}
          className="flex items-center justify-center gap-2 bg-dark-700 hover:bg-dark-600 text-gray-300 border border-dark-600 font-medium px-4 py-2.5 rounded-xl disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading === 'retrain' ? 'animate-spin' : ''}/>
          Retrain AI
        </button>
        <button
          onClick={() => act(closeAll, 'close', 'Close ALL open positions immediately? This cannot be undone.')}
          disabled={!!loading}
          className="flex items-center justify-center gap-2 bg-red-900/30 hover:bg-red-900/50 text-red-400 border border-red-800/40 font-medium px-4 py-2.5 rounded-xl disabled:opacity-50"
        >
          <AlertTriangle size={14}/>
          Close All
        </button>
      </div>

      {msg && (
        <div className="p-3 bg-red-900/20 border border-red-800/40 rounded-xl text-xs text-red-400">{msg}</div>
      )}

      {/* Current config */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-4 space-y-2">
        <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Current Config</p>
        {configRows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between text-sm">
            <span className="text-gray-400">{k}</span>
            <span className="text-white font-medium">{v}</span>
          </div>
        ))}
      </div>

      {/* Crypto engine panel */}
      <CryptoEnginePanel settings={settings}/>

      {/* Safety rules */}
      <div className="bg-yellow-900/20 border border-yellow-800/50 rounded-xl p-4">
        <p className="text-xs font-bold text-yellow-400 mb-2">⚠️ Safety Rules (always active)</p>
        <ul className="text-xs text-yellow-200/70 space-y-1">
          <li>• Bot stops automatically when <strong className="text-white">${settings?.daily_target_max ?? 250}</strong> target is hit</li>
          <li>• Bot stops if daily loss exceeds <strong className="text-white">${settings?.max_daily_loss ?? 150}</strong></li>
          <li>• No new trades after <strong className="text-white">{settings?.stop_new_trades_hour ?? 15}:{String(settings?.stop_new_trades_minute ?? 30).padStart(2, '0')} ET</strong></li>
          <li>• All positions auto-closed at <strong className="text-white">3:55 PM ET</strong></li>
          <li>• Max <strong className="text-white">{settings?.max_open_positions ?? 3}</strong> open positions at any time</li>
        </ul>
      </div>

    </div>
  )
}
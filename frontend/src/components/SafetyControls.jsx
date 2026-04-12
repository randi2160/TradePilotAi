import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { Power, AlertTriangle, PauseCircle, PlayCircle, Shield, TrendingDown, CheckCircle } from 'lucide-react'

export default function SafetyControls({ botStatus, onStatusChange }) {
  const [closing,  setClosing]  = useState(false)
  const [stopping, setStopping] = useState(false)
  const [starting, setStarting] = useState(false)
  const [positions, setPositions] = useState([])
  const [pnl,      setPnl]      = useState(0)
  const [msg,      setMsg]      = useState(null)
  const [confirm,  setConfirm]  = useState(null)
  const [liveSettings, setLiveSettings] = useState(null)

  const isRunning = botStatus === 'running' || botStatus === 'started'

  useEffect(() => {
    if (isRunning) loadPositions()
    loadSettings()
  }, [isRunning])

  async function loadSettings() {
    try { const r = await api.get('/settings'); setLiveSettings(r.data) } catch {}
  }

  function flash(text, type = 'success') {
    setMsg({ text, type })
    setTimeout(() => setMsg(null), 5000)
  }

  async function loadPositions() {
    try {
      const r = await api.get('/positions')
      setPositions(r.data || [])
      const total = (r.data || []).reduce((s, p) => s + parseFloat(p.unrealized_pnl || 0), 0)
      setPnl(total)
    } catch {}
  }

  async function emergencyStop() {
    setConfirm(null)
    setClosing(true)
    try {
      // Stop bot first
      await api.post('/bot/stop')
      // Close all open positions
      await api.post('/positions/close-all')
      flash('✅ Emergency stop complete — bot stopped and all positions closed', 'success')
      if (onStatusChange) onStatusChange('stopped')
      setPositions([])
      setPnl(0)
    } catch (e) {
      flash('❌ ' + (e.response?.data?.detail ?? e.message), 'error')
    } finally { setClosing(false) }
  }

  async function stopBot() {
    setConfirm(null)
    setStopping(true)
    try {
      await api.post('/bot/stop')
      flash('⏸ Bot paused — open positions kept open', 'warning')
      if (onStatusChange) onStatusChange('stopped')
    } catch (e) {
      flash('❌ ' + (e.response?.data?.detail ?? e.message), 'error')
    } finally { setStopping(false) }
  }

  async function startBot() {
    setStarting(true)
    try {
      await api.post('/bot/start', { mode: 'paper', trading_mode: 'auto' })
      flash('▶ Bot started — AI is now scanning markets', 'success')
      if (onStatusChange) onStatusChange('running')
    } catch (e) {
      flash('❌ ' + (e.response?.data?.detail ?? e.message), 'error')
    } finally { setStarting(false) }
  }

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="flex items-center gap-3">
        <Shield size={20} className="text-brand-500"/>
        <div>
          <h3 className="font-bold text-white">Your Trading Safety Controls</h3>
          <p className="text-xs text-gray-500">You have full control of your trading at all times</p>
        </div>
        {/* Live status pill */}
        <div className={`ml-auto flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-bold ${
          isRunning
            ? 'bg-green-900/20 border-green-700/40 text-green-400'
            : 'bg-dark-700 border-dark-600 text-gray-400'
        }`}>
          <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`}/>
          {isRunning ? 'Bot Active' : 'Bot Stopped'}
        </div>
      </div>

      {/* Flash message */}
      {msg && (
        <div className={`p-3 rounded-xl border text-sm flex items-center gap-2 ${
          msg.type === 'success' ? 'bg-green-900/20 border-green-800/40 text-green-400' :
          msg.type === 'error'   ? 'bg-red-900/20 border-red-800/40 text-red-400' :
                                   'bg-yellow-900/20 border-yellow-800/40 text-yellow-400'
        }`}>
          {msg.type === 'success' ? <CheckCircle size={16}/> : <AlertTriangle size={16}/>}
          {msg.text}
        </div>
      )}

      {/* Open Positions Summary */}
      {isRunning && (
        <div className={`rounded-xl border p-4 ${
          pnl >= 0
            ? 'bg-dark-800 border-dark-600'
            : 'bg-red-900/10 border-red-800/30'
        }`}>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-gray-400">Open Positions</span>
            <span className={`text-sm font-black ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} unrealized
            </span>
          </div>
          {positions.length === 0 ? (
            <p className="text-xs text-gray-500">No open positions right now</p>
          ) : (
            <div className="space-y-1">
              {positions.slice(0, 5).map((p, i) => {
                const upnl = parseFloat(p.unrealized_pnl || 0)
                return (
                  <div key={i} className="flex items-center justify-between text-xs">
                    <span className="font-bold text-white">{p.symbol}</span>
                    <span className="text-gray-400">{p.qty} shares</span>
                    <span className={upnl >= 0 ? 'text-green-400 font-bold' : 'text-red-400 font-bold'}>
                      {upnl >= 0 ? '+' : ''}${upnl.toFixed(2)}
                    </span>
                  </div>
                )
              })}
              {positions.length > 5 && (
                <p className="text-xs text-gray-600">+{positions.length - 5} more positions</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Main Control Buttons */}
      <div className="grid grid-cols-1 gap-3">

        {/* EMERGENCY STOP */}
        {confirm === 'emergency' ? (
          <div className="bg-red-900/20 border border-red-700 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2">
              <AlertTriangle size={18} className="text-red-400"/>
              <span className="font-bold text-red-400">Confirm Emergency Stop</span>
            </div>
            <p className="text-xs text-red-300/80">
              This will immediately <strong>stop the bot AND close ALL open positions</strong> at current market prices.
              You may receive prices different from the displayed values due to slippage.
            </p>
            <div className="flex gap-2">
              <button onClick={emergencyStop} disabled={closing}
                className="flex-1 py-2.5 bg-red-600 hover:bg-red-700 text-white font-bold rounded-xl text-sm disabled:opacity-50">
                {closing ? 'Closing positions…' : 'YES — Close Everything Now'}
              </button>
              <button onClick={() => setConfirm(null)}
                className="px-4 py-2.5 bg-dark-700 text-gray-400 hover:text-white rounded-xl text-sm border border-dark-600">
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => isRunning ? setConfirm('emergency') : null}
            disabled={!isRunning || closing}
            className={`w-full flex items-center gap-3 p-4 rounded-xl border font-bold text-left transition-all ${
              isRunning
                ? 'bg-red-900/15 border-red-800/50 hover:bg-red-900/30 hover:border-red-700 cursor-pointer'
                : 'bg-dark-800 border-dark-600 opacity-40 cursor-not-allowed'
            }`}>
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
              isRunning ? 'bg-red-900/40' : 'bg-dark-700'
            }`}>
              <Power size={20} className={isRunning ? 'text-red-400' : 'text-gray-600'}/>
            </div>
            <div className="flex-1">
              <div className={`text-sm font-bold ${isRunning ? 'text-red-400' : 'text-gray-600'}`}>
                Emergency Stop
              </div>
              <div className="text-xs text-gray-500 mt-0.5">
                Stop bot AND close all open positions immediately at market price
              </div>
            </div>
            <div className={`text-xs px-2 py-1 rounded border ${
              isRunning ? 'text-red-400 border-red-800/40 bg-red-900/20' : 'text-gray-600 border-dark-600'
            }`}>
              NUCLEAR
            </div>
          </button>
        )}

        {/* PAUSE / RESUME BOT */}
        {confirm === 'stop' ? (
          <div className="bg-yellow-900/20 border border-yellow-700/40 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2">
              <PauseCircle size={18} className="text-yellow-400"/>
              <span className="font-bold text-yellow-400">Confirm Pause Bot</span>
            </div>
            <p className="text-xs text-yellow-300/80">
              The bot will stop scanning for new trades. <strong>Your open positions will remain open</strong> — they will not be automatically managed until you restart the bot.
            </p>
            <div className="flex gap-2">
              <button onClick={stopBot} disabled={stopping}
                className="flex-1 py-2.5 bg-yellow-600 hover:bg-yellow-700 text-black font-bold rounded-xl text-sm disabled:opacity-50">
                {stopping ? 'Pausing…' : 'YES — Pause Bot'}
              </button>
              <button onClick={() => setConfirm(null)}
                className="px-4 py-2.5 bg-dark-700 text-gray-400 hover:text-white rounded-xl text-sm border border-dark-600">
                Cancel
              </button>
            </div>
          </div>
        ) : isRunning ? (
          <button onClick={() => setConfirm('stop')} disabled={stopping}
            className="w-full flex items-center gap-3 p-4 rounded-xl border bg-yellow-900/10 border-yellow-800/40 hover:bg-yellow-900/20 hover:border-yellow-700 cursor-pointer transition-all font-bold text-left">
            <div className="w-10 h-10 rounded-xl bg-yellow-900/30 flex items-center justify-center flex-shrink-0">
              <PauseCircle size={20} className="text-yellow-400"/>
            </div>
            <div className="flex-1">
              <div className="text-sm font-bold text-yellow-400">Pause Bot</div>
              <div className="text-xs text-gray-500 mt-0.5">
                Stop new trades — keep all open positions open
              </div>
            </div>
            <div className="text-xs px-2 py-1 rounded border text-yellow-400 border-yellow-800/40 bg-yellow-900/20">
              SAFE
            </div>
          </button>
        ) : (
          <button onClick={startBot} disabled={starting}
            className="w-full flex items-center gap-3 p-4 rounded-xl border bg-green-900/10 border-green-800/40 hover:bg-green-900/20 hover:border-green-700 cursor-pointer transition-all font-bold text-left">
            <div className="w-10 h-10 rounded-xl bg-green-900/30 flex items-center justify-center flex-shrink-0">
              <PlayCircle size={20} className="text-green-400"/>
            </div>
            <div className="flex-1">
              <div className="text-sm font-bold text-green-400">
                {starting ? 'Starting…' : 'Resume Auto-Trading'}
              </div>
              <div className="text-xs text-gray-500 mt-0.5">
                Restart the AI bot — it will resume scanning and trading
              </div>
            </div>
            <div className="text-xs px-2 py-1 rounded border text-green-400 border-green-800/40 bg-green-900/20">
              START
            </div>
          </button>
        )}
      </div>

      {/* Risk Reminders */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-4 space-y-2">
        <div className="text-xs font-bold text-gray-400 mb-3">Your Current Risk Settings</div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          {[
            { label: 'Daily Target',     value: liveSettings ? `$${liveSettings.daily_target_min} – $${liveSettings.daily_target_max}` : '—', color: 'text-green-400' },
              { label: 'Max Daily Loss',   value: liveSettings ? `$${liveSettings.max_daily_loss}` : '—', color: 'text-red-400'   },
            { label: 'Trading Mode',     value: 'Auto',          color: 'text-brand-500' },
            { label: 'Broker Mode',      value: 'Paper',         color: 'text-yellow-400'},
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-dark-700 rounded-lg p-2">
              <div className="text-gray-500">{label}</div>
              <div className={`font-bold mt-0.5 ${color}`}>{value}</div>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-600 mt-2">
          The bot automatically stops if your daily loss exceeds ${liveSettings?.max_daily_loss ?? 150}. You can change these limits in Settings.
        </p>
      </div>

      {/* Legal reminder */}
      <div className="text-xs text-gray-600 text-center leading-relaxed">
        You are in full control of your trading at all times. Morviq AI executes only within limits you set.
        You can pause or stop trading at any moment. <br/>
        All actions are logged for your protection.
      </div>
    </div>
  )
}

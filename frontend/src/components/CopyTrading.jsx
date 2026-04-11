import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { Copy, TrendingUp, TrendingDown, Shield, X, Play, Square, RefreshCw } from 'lucide-react'

function LeaderCard({ leader, myConfigs, onStart, onStop }) {
  const [showSetup, setShowSetup] = useState(false)
  const [form, setForm] = useState({
    mode:             'pct_of_capital',
    copy_pct:         10,
    max_per_trade:    500,
    max_open:         3,
    use_leader_stop:  true,
    pause_after_loss: 100,
  })
  const [perf,     setPerf]    = useState(null)
  const [starting, setStarting]= useState(false)

  const activeConfig = myConfigs.find(c => c.leader_id === leader.user_id && c.is_active)

  async function loadPerf() {
    try { const r = await api.get(`/copy/performance/${leader.user_id}`); setPerf(r.data) } catch {}
  }

  async function handleStart() {
    setStarting(true)
    try {
      await onStart({ leader_id: leader.user_id, ...form })
      setShowSetup(false)
    } finally { setStarting(false) }
  }

  return (
    <div className={`bg-dark-800 border rounded-2xl p-4 space-y-3 transition-all ${
      activeConfig ? 'border-brand-500/50' : 'border-dark-600'
    }`}>
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-brand-500/30 flex items-center justify-center text-brand-400 font-black">
          {(leader.display_name ?? 'T').slice(0,2).toUpperCase()}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <p className="font-bold text-white">{leader.display_name}</p>
            <span className="text-xs bg-green-900/30 text-green-400 border border-green-800/40 px-1.5 py-0.5 rounded-full">✓ Copyable</span>
          </div>
          <p className="text-xs text-gray-500">{leader.days_tracked} days · {leader.followers} followers</p>
        </div>
        <div className="text-right">
          <p className={`font-black text-xl ${leader.win_rate >= 60 ? 'text-green-400' : 'text-yellow-400'}`}>
            {leader.win_rate?.toFixed(0)}%
          </p>
          <p className="text-xs text-gray-500">win rate</p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-2 text-center text-xs">
        <div className="bg-dark-700 rounded-xl p-2">
          <p className="text-gray-500">Total P&L</p>
          <p className={`font-bold ${leader.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {leader.total_pnl >= 0 ? '+' : ''}${leader.total_pnl?.toFixed(0)}
          </p>
        </div>
        <div className="bg-dark-700 rounded-xl p-2">
          <p className="text-gray-500">Avg Profit</p>
          <p className="font-bold text-white">${leader.avg_profit?.toFixed(2)}</p>
        </div>
        <div className="bg-dark-700 rounded-xl p-2">
          <p className="text-gray-500">Trades</p>
          <p className="font-bold text-white">{leader.total_trades}</p>
        </div>
      </div>

      {/* Recent 20 P&L */}
      {leader.recent_pnl_20 !== undefined && (
        <p className="text-xs text-gray-400">
          Last 20 trades: <span className={leader.recent_pnl_20 >= 0 ? 'text-green-400 font-bold' : 'text-red-400 font-bold'}>
            {leader.recent_pnl_20 >= 0 ? '+' : ''}${leader.recent_pnl_20?.toFixed(2)}
          </span>
        </p>
      )}

      {/* Performance details toggle */}
      {perf ? (
        <div className="bg-dark-700 rounded-xl p-3 space-y-1 text-xs">
          <div className="flex justify-between"><span className="text-gray-400">Avg Win</span><span className="text-green-400 font-bold">+${perf.summary?.avg_win}</span></div>
          <div className="flex justify-between"><span className="text-gray-400">Avg Loss</span><span className="text-red-400 font-bold">${perf.summary?.avg_loss}</span></div>
          <div className="flex justify-between"><span className="text-gray-400">Best Trade</span><span className="text-green-400 font-bold">+${perf.summary?.best_trade}</span></div>
          <div className="flex justify-between"><span className="text-gray-400">Worst Trade</span><span className="text-red-400 font-bold">${perf.summary?.worst_trade}</span></div>
          <button onClick={() => setPerf(null)} className="text-gray-600 hover:text-gray-400 mt-1">Hide details</button>
        </div>
      ) : (
        <button onClick={loadPerf} className="text-xs text-brand-500 hover:underline">View detailed performance →</button>
      )}

      {/* Action buttons */}
      {activeConfig ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 bg-brand-500/10 border border-brand-500/30 rounded-xl px-3 py-2">
            <div className="w-2 h-2 rounded-full bg-brand-500 animate-pulse"/>
            <span className="text-xs text-brand-400 font-bold">Auto-copying active</span>
            <span className="text-xs text-gray-500 ml-auto">
              {activeConfig.copy_pct}{activeConfig.mode === 'fixed_dollar' ? '$' : '%'} · max ${activeConfig.max_per_trade}/trade
            </span>
          </div>
          <button onClick={() => onStop(leader.user_id)}
            className="w-full flex items-center justify-center gap-2 py-2 bg-red-900/20 hover:bg-red-900/40 text-red-400 border border-red-800/40 rounded-xl text-sm font-bold transition-colors">
            <Square size={14}/> Stop Copying
          </button>
        </div>
      ) : (
        <button onClick={() => setShowSetup(s => !s)}
          className="w-full flex items-center justify-center gap-2 py-2.5 bg-brand-500/20 hover:bg-brand-500/30 text-brand-400 border border-brand-500/30 rounded-xl text-sm font-bold transition-colors">
          <Copy size={14}/> {showSetup ? 'Cancel' : 'Copy This Trader'}
        </button>
      )}

      {/* Setup form */}
      {showSetup && !activeConfig && (
        <div className="bg-dark-700 rounded-2xl p-4 space-y-3 border border-dark-600">
          <h4 className="font-bold text-white text-sm">⚙️ Copy Settings</h4>

          <div>
            <label className="text-xs text-gray-400">Sizing Mode</label>
            <select value={form.mode} onChange={e => setForm(f => ({...f, mode: e.target.value}))}
              className="w-full mt-1 bg-dark-800 border border-dark-600 rounded-xl px-3 py-2 text-white text-sm">
              <option value="pct_of_capital">% of My Capital</option>
              <option value="pct_of_leader">% of Leader's Position</option>
              <option value="fixed_dollar">Fixed $ Amount</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400">
                {form.mode === 'fixed_dollar' ? 'Fixed $ per Trade' : 'Copy %'}
              </label>
              <input type="number" value={form.copy_pct}
                onChange={e => setForm(f => ({...f, copy_pct: parseFloat(e.target.value)}))}
                min={1} max={form.mode === 'fixed_dollar' ? 10000 : 100}
                className="w-full mt-1 bg-dark-800 border border-dark-600 rounded-xl px-3 py-2 text-white text-sm"/>
            </div>
            <div>
              <label className="text-xs text-gray-400">Max $ Per Trade</label>
              <input type="number" value={form.max_per_trade}
                onChange={e => setForm(f => ({...f, max_per_trade: parseFloat(e.target.value)}))}
                min={10}
                className="w-full mt-1 bg-dark-800 border border-dark-600 rounded-xl px-3 py-2 text-white text-sm"/>
            </div>
            <div>
              <label className="text-xs text-gray-400">Max Open Positions</label>
              <input type="number" value={form.max_open}
                onChange={e => setForm(f => ({...f, max_open: parseInt(e.target.value)}))}
                min={1} max={10}
                className="w-full mt-1 bg-dark-800 border border-dark-600 rounded-xl px-3 py-2 text-white text-sm"/>
            </div>
            <div>
              <label className="text-xs text-gray-400">Pause if Loss Exceeds $</label>
              <input type="number" value={form.pause_after_loss}
                onChange={e => setForm(f => ({...f, pause_after_loss: parseFloat(e.target.value)}))}
                min={10}
                className="w-full mt-1 bg-dark-800 border border-dark-600 rounded-xl px-3 py-2 text-white text-sm"/>
            </div>
          </div>

          <label className="flex items-center gap-3 cursor-pointer">
            <input type="checkbox" checked={form.use_leader_stop}
              onChange={e => setForm(f => ({...f, use_leader_stop: e.target.checked}))}
              className="w-4 h-4"/>
            <span className="text-sm text-gray-300">Use leader's stop loss</span>
          </label>

          <div className="bg-yellow-900/20 border border-yellow-800/40 rounded-xl p-3">
            <p className="text-xs text-yellow-400">
              ⚠️ Copy trading carries risk. You are solely responsible for all trades placed in your account.
              This is not financial advice.
            </p>
          </div>

          <button onClick={handleStart} disabled={starting}
            className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-black rounded-xl disabled:opacity-50 transition-colors">
            {starting ? 'Starting…' : '▶ Start Auto-Copy'}
          </button>
        </div>
      )}
    </div>
  )
}

export default function CopyTrading() {
  const [leaders,    setLeaders]    = useState([])
  const [myConfigs,  setMyConfigs]  = useState([])
  const [loading,    setLoading]    = useState(true)
  const [msg,        setMsg]        = useState('')

  useEffect(() => { loadAll() }, [])

  async function loadAll() {
    setLoading(true)
    try {
      const [leadersRes, configsRes] = await Promise.all([
        api.get('/copy/leaders').then(r => r.data),
        api.get('/copy/my-configs').then(r => r.data),
      ])
      setLeaders(leadersRes)
      setMyConfigs(configsRes)
    } catch {}
    finally { setLoading(false) }
  }

  function flash(m) { setMsg(m); setTimeout(() => setMsg(''), 4000) }

  async function handleStart(body) {
    try {
      await api.post('/copy/start', body)
      flash('✅ Auto-copy started! Trades will mirror automatically')
      loadAll()
    } catch(e) { flash('❌ ' + (e.response?.data?.detail ?? e.message)) }
  }

  async function handleStop(leaderId) {
    try {
      await api.delete(`/copy/stop/${leaderId}`)
      flash('Copy stopped')
      loadAll()
    } catch(e) { flash('❌ ' + e.message) }
  }

  const activeCount = myConfigs.filter(c => c.is_active).length

  return (
    <div className="space-y-5 max-w-2xl">

      {/* Header */}
      <div className="bg-dark-800 border border-dark-600 rounded-2xl p-5">
        <div className="flex items-center gap-3 mb-3">
          <Copy size={20} className="text-brand-500"/>
          <h2 className="font-black text-white text-lg">Copy Trading</h2>
          {activeCount > 0 && (
            <span className="text-xs bg-brand-500/20 text-brand-400 border border-brand-500/30 px-2 py-1 rounded-full font-bold">
              {activeCount} active
            </span>
          )}
          <button onClick={loadAll} className="ml-auto p-1.5 bg-dark-700 rounded-lg hover:bg-dark-600">
            <RefreshCw size={14} className={`text-gray-400 ${loading ? 'animate-spin' : ''}`}/>
          </button>
        </div>
        <p className="text-sm text-gray-400">
          Automatically mirror trades from top-performing traders. Your position size
          is calculated based on your own capital — you stay in full control.
        </p>

        {/* How it works */}
        <div className="grid grid-cols-3 gap-3 mt-4 text-center text-xs">
          {[
            { step:'1', label:'Choose a leader', desc:'Pick a copyable trader with proven track record' },
            { step:'2', label:'Set your limits',  desc:'Control position size, max loss, and open trades' },
            { step:'3', label:'Auto-mirrors',     desc:'Every leader trade instantly placed in your account' },
          ].map(s => (
            <div key={s.step} className="bg-dark-700 rounded-xl p-3">
              <div className="w-6 h-6 rounded-full bg-brand-500/30 text-brand-400 font-black text-sm flex items-center justify-center mx-auto mb-1">{s.step}</div>
              <p className="font-bold text-white mb-0.5">{s.label}</p>
              <p className="text-gray-500">{s.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {msg && <div className="p-3 bg-dark-700 border border-dark-600 rounded-xl text-sm text-center">{msg}</div>}

      {/* Active configs summary */}
      {myConfigs.filter(c => c.is_active).length > 0 && (
        <div className="bg-brand-500/5 border border-brand-500/20 rounded-2xl p-4">
          <h3 className="font-bold text-brand-400 mb-3">📡 Currently Copying</h3>
          <div className="space-y-2">
            {myConfigs.filter(c => c.is_active).map(c => (
              <div key={c.id} className="flex items-center gap-3 bg-dark-800 rounded-xl px-3 py-2.5">
                <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse"/>
                <span className="font-bold text-white flex-1">{c.leader_name}</span>
                <span className="text-xs text-gray-400">
                  {c.mode === 'pct_of_capital' ? `${c.copy_pct}% capital` :
                   c.mode === 'fixed_dollar'    ? `$${c.copy_pct}/trade` :
                   `${c.copy_pct}% of leader`}
                </span>
                <span className="text-xs text-green-400">{c.leader_win_rate?.toFixed(0)}% WR</span>
                <button onClick={() => handleStop(c.leader_id)}
                  className="text-xs text-red-400 hover:text-red-300 ml-2">Stop</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Leaders list */}
      <div className="space-y-4">
        <h3 className="font-bold text-white">Available Leaders</h3>
        {loading ? (
          <div className="text-center py-12 text-gray-500">
            <RefreshCw size={24} className="animate-spin mx-auto mb-2"/>
            <p>Loading leaders…</p>
          </div>
        ) : leaders.length === 0 ? (
          <div className="text-center py-16 bg-dark-800 border border-dark-600 rounded-2xl text-gray-500 space-y-3">
            <Shield size={32} className="mx-auto opacity-40"/>
            <p className="font-bold text-white">No public traders yet</p>
            <p className="text-sm">To see leaders here:</p>
            <div className="text-sm space-y-1 text-left max-w-xs mx-auto">
              <p>1. Go to <strong className="text-white">👥 Social → My Profile</strong></p>
              <p>2. Set your profile to <strong className="text-white">Public</strong></p>
              <p>3. Other users will appear here as leaders</p>
            </div>
            <p className="text-xs text-gray-600 mt-2">For testing: make your own profile public, register a second test account, then copy yourself</p>
          </div>
        ) : (
          leaders.map(leader => (
            <LeaderCard key={leader.user_id} leader={leader}
              myConfigs={myConfigs} onStart={handleStart} onStop={handleStop}/>
          ))
        )}
      </div>

      {/* Disclaimer */}
      <div className="bg-dark-800 border border-dark-600 rounded-2xl p-4">
        <p className="text-xs text-gray-500 text-center">
          ⚠️ Copy trading is risky. Past performance does not guarantee future results.
          All trades are executed in your own broker account. You are solely responsible
          for all trading decisions and losses. This platform is a technology tool, not
          financial advice.
        </p>
      </div>
    </div>
  )
}

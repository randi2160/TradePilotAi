import { useState, useEffect } from 'react'
import { getSettings, updateCapital, updateTargets, addSymbol, removeSymbol, setWatchlist } from '../services/api'
import { Plus, X, Save, DollarSign, Target, List } from 'lucide-react'

function InputField({ label, value, onChange, prefix='$', min, max, step=1, help }) {
  return (
    <div>
      <label className="block text-xs text-gray-400 mb-1">{label}</label>
      <div className="relative">
        {prefix && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">{prefix}</span>
        )}
        <input
          type="number"
          value={value}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          min={min} max={max} step={step}
          className={`w-full bg-dark-700 border border-dark-600 rounded-lg py-2 text-white text-sm
            focus:outline-none focus:border-brand-500 ${prefix ? 'pl-8 pr-3' : 'px-3'}`}
        />
      </div>
      {help && <p className="text-xs text-gray-600 mt-1">{help}</p>}
    </div>
  )
}

export default function Settings() {
  const [cfg,     setCfg]     = useState(null)
  const [capital, setCapital] = useState(5000)
  const [tMin,    setTMin]    = useState(100)
  const [tMax,    setTMax]    = useState(250)
  const [maxLoss, setMaxLoss] = useState(150)
  const [watchlist, setWl]    = useState([])
  const [newSym,  setNewSym]  = useState('')
  const [saving,  setSaving]  = useState('')
  const [msg,     setMsg]     = useState('')
  // Engine settings
  const [engineMode,    setEngineMode]    = useState('stocks_only')
  const [cryptoAlloc,   setCryptoAlloc]   = useState(30)
  const [stopHour,      setStopHour]      = useState(15)
  const [stopMinute,    setStopMinute]    = useState(30)
  const [maxPositions,  setMaxPositions]  = useState(3)

  useEffect(() => { load() }, [])

  async function load() {
    try {
      const s = await getSettings()
      setCfg(s)
      setCapital(s.capital)
      setTMin(s.daily_target_min)
      setTMax(s.daily_target_max)
      setMaxLoss(s.max_daily_loss)
      setWl(s.watchlist ?? [])
      setEngineMode(s.engine_mode   || 'stocks_only')
      setCryptoAlloc(Math.round((s.crypto_alloc_pct || 0.30) * 100))
      setStopHour(s.stop_new_trades_hour   ?? 15)
      setStopMinute(s.stop_new_trades_minute ?? 30)
      setMaxPositions(s.max_open_positions   ?? 3)
    } catch {}
  }

  function flash(text) {
    setMsg(text)
    setTimeout(() => setMsg(''), 3000)
  }

  async function saveCapital() {
    setSaving('capital')
    try {
      await updateCapital(capital)
      flash('✅ Capital updated!')
    } catch(e) {
      flash(`❌ ${e.response?.data?.detail ?? e.message}`)
    } finally { setSaving('') }
  }

  async function saveTargets() {
    if (tMin >= tMax) { flash('❌ Min target must be less than max'); return }
    setSaving('targets')
    try {
      await updateTargets(tMin, tMax, maxLoss)
      flash('✅ Targets updated!')
    } catch(e) {
      flash(`❌ ${e.response?.data?.detail ?? e.message}`)
    } finally { setSaving('') }
  }

  async function handleAddSymbol() {
    const sym = newSym.trim().toUpperCase()
    if (!sym || watchlist.includes(sym)) return
    try {
      await addSymbol(sym)
      setWl(prev => [...prev, sym])
      setNewSym('')
      flash(`✅ ${sym} added to watchlist`)
    } catch(e) {
      flash(`❌ ${e.message}`)
    }
  }

  async function handleRemove(sym) {
    try {
      await removeSymbol(sym)
      setWl(prev => prev.filter(s => s !== sym))
      flash(`✅ ${sym} removed`)
    } catch(e) {
      flash(`❌ ${e.message}`)
    }
  }

  const dailyTargetPct = capital > 0 ? ((tMin / capital) * 100).toFixed(1) : 0

  return (
    <div className="space-y-6 max-w-2xl">

      {msg && (
        <div className="p-3 bg-dark-700 rounded-lg text-sm text-center">{msg}</div>
      )}

      {/* ── Capital ─────────────────────────────────────────────────────────── */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <DollarSign size={16} className="text-brand-500" />
          <h3 className="font-bold text-white">Trading Capital</h3>
        </div>

        <InputField
          label="Capital Amount"
          value={capital}
          onChange={setCapital}
          min={100}
          max={1000000}
          step={100}
          help={`Bot will use up to 20% ($${(capital*0.2).toFixed(0)}) per position`}
        />

        <div className="bg-dark-700 rounded-lg p-3 text-xs text-gray-400 space-y-1">
          <p>📊 Max position size: <span className="text-white">${(capital * 0.2).toLocaleString()}</span></p>
          <p>🛡️ Daily loss limit:  <span className="text-red-400">${maxLoss}</span></p>
          <p>🎯 Target return:     <span className="text-green-400">{dailyTargetPct}% – {((tMax/capital)*100).toFixed(1)}% per day</span></p>
        </div>

        <button
          onClick={saveCapital}
          disabled={saving === 'capital'}
          className="w-full flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold py-2.5 rounded-lg transition-colors disabled:opacity-50"
        >
          <Save size={15} />
          {saving === 'capital' ? 'Saving…' : 'Save Capital'}
        </button>
      </div>

      {/* ── Daily Targets ────────────────────────────────────────────────────── */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <Target size={16} className="text-brand-500" />
          <h3 className="font-bold text-white">Daily Profit Targets</h3>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <InputField
            label="Min Daily Target ($)"
            value={tMin}
            onChange={setTMin}
            min={10}
            help="Bot slows down after hitting this"
          />
          <InputField
            label="Max Daily Target ($)"
            value={tMax}
            onChange={setTMax}
            min={10}
            help="Bot stops trading after hitting this"
          />
        </div>

        <InputField
          label="Max Daily Loss ($)"
          value={maxLoss}
          onChange={setMaxLoss}
          min={10}
          help="Bot stops and closes all positions if this is hit"
        />

        {/* Visual range */}
        <div className="relative pt-1">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>−${maxLoss} (stop)</span>
            <span>$0</span>
            <span>+${tMin} (min)</span>
            <span>+${tMax} (stop)</span>
          </div>
          <div className="h-2 bg-dark-600 rounded-full overflow-hidden flex">
            <div className="h-2 bg-red-500/60" style={{width:'25%'}}/>
            <div className="h-2 bg-gray-600"   style={{width:'25%'}}/>
            <div className="h-2 bg-yellow-500/60" style={{width:'25%'}}/>
            <div className="h-2 bg-green-500/60"  style={{width:'25%'}}/>
          </div>
        </div>

        <button
          onClick={saveTargets}
          disabled={saving === 'targets'}
          className="w-full flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold py-2.5 rounded-lg transition-colors disabled:opacity-50"
        >
          <Save size={15} />
          {saving === 'targets' ? 'Saving…' : 'Save Targets'}
        </button>
      </div>

      {/* ── Engine & Trading Mode ──────────────────────────────────────────────── */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-lg">⚡</span>
          <h3 className="font-bold text-white">Engine Mode & Safety Rules</h3>
        </div>

        {/* Engine mode selector */}
        <div className="space-y-2">
          <label className="text-xs font-bold text-gray-400">Trading Engine</label>
          <div className="grid grid-cols-3 gap-2">
            {[
              { id: 'stocks_only', label: '📈 Stocks Only',   desc: 'US equities · PDT rules apply' },
              { id: 'crypto_only', label: '₿ Crypto Only',    desc: '24/7 · No PDT · Scalping mode' },
              { id: 'hybrid',      label: '⚡ Hybrid',         desc: 'AI splits capital between both' },
            ].map(m => (
              <button key={m.id} onClick={() => setEngineMode(m.id)}
                className={`p-3 rounded-xl border text-left transition-all ${
                  engineMode === m.id
                    ? 'border-brand-500 bg-brand-500/10 text-brand-400'
                    : 'border-dark-600 bg-dark-700 text-gray-400 hover:border-dark-500'
                }`}>
                <div className="text-xs font-bold">{m.label}</div>
                <div className="text-xs text-gray-600 mt-0.5">{m.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Crypto allocation slider (only for hybrid) */}
        {engineMode === 'hybrid' && (
          <div className="space-y-2">
            <label className="text-xs font-bold text-gray-400">
              Crypto Allocation: <span className="text-brand-400">{cryptoAlloc}%</span>
              <span className="text-gray-600 ml-2">(Stocks: {100 - cryptoAlloc}%)</span>
            </label>
            <input type="range" min={10} max={70} step={5} value={cryptoAlloc}
              onChange={e => setCryptoAlloc(Number(e.target.value))}
              className="w-full accent-brand-500"/>
            <div className="flex justify-between text-xs text-gray-600">
              <span>10% Crypto</span><span>40% Split</span><span>70% Crypto</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs text-center">
              {cfg?.capital && [
                { l: 'Crypto Budget', v: `$${((cfg.capital * cryptoAlloc / 100)).toFixed(0)}`, c: 'text-yellow-400' },
                { l: 'Stock Budget',  v: `$${((cfg.capital * (100-cryptoAlloc) / 100)).toFixed(0)}`, c: 'text-brand-400' },
              ].map(({ l, v, c }) => (
                <div key={l} className="bg-dark-700 rounded-lg p-2">
                  <div className="text-gray-500">{l}</div>
                  <div className={`font-bold mt-0.5 ${c}`}>{v}</div>
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-600">AI dynamically adjusts this split based on PDT remaining, time of day, and P&L progress.</p>
          </div>
        )}

        {/* Safety rules */}
        <div className="space-y-3 border-t border-dark-700 pt-3">
          <label className="text-xs font-bold text-gray-400">Safety Rules (Stocks)</label>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500">Stop New Trades At</label>
              <div className="flex gap-2 mt-1">
                <select value={stopHour} onChange={e => setStopHour(Number(e.target.value))}
                  className="flex-1 bg-dark-700 border border-dark-600 rounded-lg px-2 py-2 text-white text-sm focus:outline-none focus:border-brand-500">
                  {[9,10,11,12,13,14,15,16].map(h => (
                    <option key={h} value={h}>{h}:00</option>
                  ))}
                </select>
                <select value={stopMinute} onChange={e => setStopMinute(Number(e.target.value))}
                  className="flex-1 bg-dark-700 border border-dark-600 rounded-lg px-2 py-2 text-white text-sm focus:outline-none focus:border-brand-500">
                  {[0,15,30,45].map(m => (
                    <option key={m} value={m}>:{m.toString().padStart(2,'0')}</option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-gray-600 mt-1">No new positions after this time (ET)</p>
            </div>
            <div>
              <label className="text-xs text-gray-500">Max Open Positions</label>
              <input type="number" min={1} max={10} value={maxPositions}
                onChange={e => setMaxPositions(Number(e.target.value))}
                className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500"/>
              <p className="text-xs text-gray-600 mt-1">Bot won't open more than this many at once</p>
            </div>
          </div>

          {/* Live safety rules summary */}
          <div className="bg-dark-900 border border-dark-700 rounded-xl p-3 space-y-1.5">
            <div className="text-xs font-bold text-white mb-2">Current Safety Rules (from your settings)</div>
            {[
              { label: 'Bot stops when target hit', val: `$${tMax}` },
              { label: 'Bot stops if daily loss exceeds', val: `$${maxLoss}` },
              { label: 'No new trades after', val: `${stopHour}:${stopMinute.toString().padStart(2,'0')} ET` },
              { label: 'All positions closed at', val: '3:55 PM ET (always)' },
              { label: 'Max open positions', val: `${maxPositions} concurrent` },
              { label: 'Crypto PDT restriction', val: 'None (24/7)' },
            ].map(({ label, val }) => (
              <div key={label} className="flex items-center gap-2 text-xs">
                <span className="text-green-400">•</span>
                <span className="text-gray-400 flex-1">{label}</span>
                <span className="text-white font-bold">{val}</span>
              </div>
            ))}
          </div>
        </div>

        <button onClick={async () => {
          setSaving('engine')
          try {
            const { api } = await import('../hooks/useAuth')
            await api.put('/settings/engine', {
              stop_new_trades_hour:   stopHour,
              stop_new_trades_minute: stopMinute,
              max_open_positions:     maxPositions,
              engine_mode:            engineMode,
              crypto_alloc_pct:       cryptoAlloc / 100,
            })
            flash('✅ Engine settings saved!')
          } catch(e) {
            flash(`❌ ${e.response?.data?.detail ?? e.message}`)
          } finally { setSaving('') }
        }} disabled={saving === 'engine'}
          className="w-full flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold px-4 py-3 rounded-xl disabled:opacity-50 transition-colors">
          {saving === 'engine' ? '⏳ Saving…' : '⚡ Save Engine Settings'}
        </button>
      </div>

      {/* ── Watchlist Manager ────────────────────────────────────────────────── */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 mb-1">
          <List size={16} className="text-brand-500" />
          <h3 className="font-bold text-white">Watchlist Manager</h3>
          <span className="ml-auto text-xs text-gray-500">{watchlist.length} / 50 symbols</span>
        </div>

        {/* Add symbol */}
        <div className="flex gap-2">
          <input
            type="text"
            value={newSym}
            onChange={e => setNewSym(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleAddSymbol()}
            placeholder="e.g. AAPL, TSLA…"
            maxLength={8}
            className="flex-1 bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500 placeholder-gray-600"
          />
          <button
            onClick={handleAddSymbol}
            disabled={!newSym.trim()}
            className="flex items-center gap-1 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold px-4 py-2 rounded-lg disabled:opacity-40 transition-colors"
          >
            <Plus size={16} /> Add
          </button>
        </div>

        {/* Symbol chips */}
        <div className="flex flex-wrap gap-2">
          {watchlist.map(sym => (
            <div
              key={sym}
              className="flex items-center gap-1.5 bg-dark-700 border border-dark-600 rounded-lg px-2.5 py-1.5 group"
            >
              <span className="text-sm font-bold text-white">{sym}</span>
              <button
                onClick={() => handleRemove(sym)}
                className="text-gray-600 hover:text-red-400 transition-colors"
              >
                <X size={12} />
              </button>
            </div>
          ))}
          {watchlist.length === 0 && (
            <p className="text-xs text-gray-500">No symbols — add some above</p>
          )}
        </div>

        <p className="text-xs text-gray-500">
          The bot scans all symbols above every 30 seconds. More symbols = more opportunities but slower scan.
        </p>
      </div>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { Target, TrendingUp, Calendar, DollarSign, Save, Brain } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, BarChart, Bar, Cell } from 'recharts'

export default function GoalSetting({ capital = 5000 }) {
  const [plan,      setPlan]      = useState(null)
  const [monthly,   setMonthly]   = useState(null)
  const [history,   setHistory]   = useState([])
  const [saving,    setSaving]    = useState(false)
  const [msg,       setMsg]       = useState('')
  const [tab,       setTab]       = useState('set')

  // Form
  const [goal,      setGoal]      = useState('')
  const [cap,       setCap]       = useState(capital)
  const [risk,      setRisk]      = useState('moderate')

  useEffect(() => { loadAll() }, [])

  async function loadAll() {
    try {
      const [p, m, h] = await Promise.all([
        api.get('/goals/plan').then(r => r.data),
        api.get('/goals/monthly').then(r => r.data),
        api.get('/goals/history?days=30').then(r => r.data),
      ])
      setPlan(p)
      setMonthly(m)
      setHistory(h)
      if (p?.monthly_goal) setGoal(p.monthly_goal)
      if (p?.capital)      setCap(p.capital)
      if (p?.risk_tolerance) setRisk(p.risk_tolerance)
    } catch {}
  }

  function flash(m) { setMsg(m); setTimeout(() => setMsg(''), 4000) }

  async function savePlan() {
    if (!goal || parseFloat(goal) <= 0) { flash('❌ Enter a valid monthly goal'); return }
    setSaving(true)
    try {
      const r = await api.post('/goals/set', {
        monthly_goal:   parseFloat(goal),
        capital:        parseFloat(cap),
        risk_tolerance: risk,
      })
      setPlan(r.data)
      flash('✅ Goal set! Daily targets updated automatically.')
      setTab('progress')
      loadAll()
    } catch(e) {
      flash(`❌ ${e.response?.data?.detail ?? e.message}`)
    } finally { setSaving(false) }
  }

  async function recordToday() {
    try {
      await api.post('/goals/record-day')
      flash('✅ Today recorded!')
      loadAll()
    } catch(e) { flash(`❌ ${e.message}`) }
  }

  const historyChart = [...history].reverse().map(d => ({
    date:   d.date?.slice(5),   // MM-DD
    pnl:    d.realized_pnl ?? 0,
    target: d.daily_target ?? plan?.daily_target ?? 0,
    hit:    d.hit_target,
  }))

  return (
    <div className="space-y-5 max-w-3xl">

      {/* Tabs */}
      <div className="flex gap-2">
        {[
          { id: 'set',      label: '🎯 Set Goal'     },
          { id: 'progress', label: '📊 Monthly Progress' },
          { id: 'history',  label: '📅 Day History'  },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t.id ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {msg && <div className="p-3 bg-dark-700 rounded-lg text-sm text-center">{msg}</div>}

      {/* ── Set Goal ─────────────────────────────────────────────────────────── */}
      {tab === 'set' && (
        <div className="space-y-5">
          <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-5">
            <h3 className="font-bold text-white flex items-center gap-2">
              <Target size={16} className="text-brand-500"/> Monthly Profit Goal
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Monthly Goal ($)</label>
                <input type="number" value={goal} onChange={e => setGoal(e.target.value)}
                  placeholder="e.g. 2000"
                  className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500"/>
                <p className="text-xs text-gray-500 mt-1">How much do you want to make this month?</p>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Trading Capital ($)</label>
                <input type="number" value={cap} onChange={e => setCap(e.target.value)}
                  className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500"/>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Risk Tolerance</label>
                <select value={risk} onChange={e => setRisk(e.target.value)}
                  className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500">
                  <option value="conservative">Conservative (85% of target)</option>
                  <option value="moderate">Moderate (100% of target)</option>
                  <option value="aggressive">Aggressive (120% of target)</option>
                </select>
              </div>
            </div>

            {/* Preview */}
            {goal && parseFloat(goal) > 0 && (
              <div className="bg-dark-700 rounded-xl p-4 space-y-3">
                <p className="text-xs font-bold text-brand-500 flex items-center gap-1">
                  <Brain size={12}/> AI Calculation Preview
                </p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center text-xs">
                  {[
                    { label: 'Monthly Goal',    value: `$${parseFloat(goal).toLocaleString()}`, color: 'text-white' },
                    { label: 'Est. Daily Min',  value: `$${(parseFloat(goal)/21*0.7).toFixed(2)}`, color: 'text-yellow-400' },
                    { label: 'Est. Daily Max',  value: `$${(parseFloat(goal)/21*1.3).toFixed(2)}`, color: 'text-green-400' },
                    { label: 'Daily % Needed',  value: `${(parseFloat(goal)/21/parseFloat(cap||5000)*100).toFixed(2)}%`, color: 'text-brand-500' },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="bg-dark-600 rounded-lg p-2.5">
                      <p className="text-gray-400">{label}</p>
                      <p className={`font-bold ${color}`}>{value}</p>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-400">
                  Based on ~21 trading days/month. AI adjusts daily targets as days pass.
                </p>
              </div>
            )}

            <button onClick={savePlan} disabled={saving || !goal}
              className="w-full flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-600 text-dark-900 font-black py-3 rounded-xl transition-colors disabled:opacity-50">
              <Save size={16}/>
              {saving ? 'Setting Goal…' : 'Set Goal & Update Daily Targets'}
            </button>
          </div>

          {/* Current plan summary */}
          {plan?.daily_target > 0 && (
            <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
              <p className="text-sm font-bold text-gray-300 mb-3">📋 Current Active Plan</p>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                {[
                  ['Monthly Goal',    `$${plan.monthly_goal?.toLocaleString()}`],
                  ['Month',          plan.month],
                  ['Days Remaining', plan.days_remaining],
                  ['Daily Target',   `$${plan.daily_target_min}–$${plan.daily_target_max}`],
                  ['Required Daily %',`${plan.daily_pct_required}%`],
                  ['Earned So Far',  `$${plan.earned_so_far}`],
                ].map(([k,v]) => (
                  <div key={k} className="bg-dark-700 rounded-lg p-2.5">
                    <p className="text-gray-400">{k}</p>
                    <p className="font-bold text-white">{v}</p>
                  </div>
                ))}
              </div>
              {plan.warning && (
                <p className="mt-3 text-xs text-yellow-300 bg-yellow-900/20 border border-yellow-800/40 rounded-lg p-2.5">
                  {plan.warning}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Monthly Progress ──────────────────────────────────────────────────── */}
      {tab === 'progress' && monthly && (
        <div className="space-y-4">
          {/* Hero */}
          <div className="bg-dark-800 border border-brand-500/30 rounded-xl p-5">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-xs text-gray-400 uppercase tracking-wide">{monthly.month} Progress</p>
                <p className={`text-4xl font-black mt-1 ${monthly.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  ${monthly.total_pnl?.toFixed(2)}
                </p>
                <p className="text-sm text-gray-400 mt-1">of ${monthly.monthly_goal?.toLocaleString()} goal</p>
              </div>
              <div className="text-right">
                <p className={`text-2xl font-black ${monthly.on_track ? 'text-brand-500' : 'text-yellow-400'}`}>
                  {monthly.on_track ? '✅ On Track' : '⚠️ Behind'}
                </p>
                <p className="text-sm text-gray-400">{monthly.progress_pct?.toFixed(1)}% complete</p>
              </div>
            </div>

            <div className="h-3 bg-dark-600 rounded-full overflow-hidden mb-2">
              <div className="h-3 rounded-full transition-all duration-700"
                style={{
                  width: `${Math.min(monthly.progress_pct, 100)}%`,
                  background: monthly.on_track
                    ? 'linear-gradient(90deg,#00d4aa,#00b894)'
                    : 'linear-gradient(90deg,#f59e0b,#d97706)',
                }}/>
            </div>
            <div className="flex justify-between text-xs text-gray-500">
              <span>$0</span>
              <span>${monthly.monthly_goal?.toLocaleString()}</span>
            </div>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label:'Days Traded',     value: monthly.days_traded,    color:'text-white' },
              { label:'Target Hit Rate', value:`${monthly.target_hit_rate}%`, color: monthly.target_hit_rate>=60?'text-green-400':'text-red-400' },
              { label:'Total Trades',    value: monthly.total_trades,   color:'text-white' },
              { label:'Win Rate',        value:`${monthly.win_rate}%`,  color: monthly.win_rate>=50?'text-green-400':'text-red-400' },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-dark-800 border border-dark-600 rounded-xl p-3 text-center">
                <p className="text-xs text-gray-500">{label}</p>
                <p className={`text-lg font-bold ${color}`}>{value}</p>
              </div>
            ))}
          </div>

          {/* Record today button */}
          <button onClick={recordToday}
            className="w-full py-2.5 bg-dark-700 hover:bg-dark-600 text-gray-300 text-sm rounded-xl transition-colors border border-dark-600">
            📝 Record Today's Results
          </button>
        </div>
      )}

      {/* ── Day History ───────────────────────────────────────────────────────── */}
      {tab === 'history' && (
        <div className="space-y-4">
          {historyChart.length > 0 ? (
            <>
              <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
                <p className="text-sm font-bold text-gray-300 mb-3">Daily P&L vs Target (30 days)</p>
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart data={historyChart}>
                    <XAxis dataKey="date" tick={{fill:'#6b7280',fontSize:10}} tickLine={false}/>
                    <YAxis tick={{fill:'#6b7280',fontSize:10}} tickLine={false} axisLine={false} tickFormatter={v=>`$${v}`}/>
                    <Tooltip contentStyle={{background:'#111827',border:'1px solid #374151',borderRadius:8}}
                      formatter={(v,n) => [`$${v}`, n]}/>
                    <ReferenceLine y={plan?.daily_target ?? 0} stroke="#00d4aa" strokeDasharray="4 2" label={{value:'Target',fill:'#00d4aa',fontSize:10}}/>
                    <Bar dataKey="pnl" radius={[4,4,0,0]}>
                      {historyChart.map((d,i) => <Cell key={i} fill={d.hit ? '#00d4aa' : d.pnl >= 0 ? '#6366f1' : '#ef4444'}/>)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="space-y-2">
                {history.map((d, i) => (
                  <div key={i} className={`flex items-center gap-3 p-3 rounded-xl border ${
                    d.hit_target ? 'bg-green-900/10 border-green-800/40' :
                    d.realized_pnl >= 0 ? 'bg-dark-800 border-dark-600' :
                    'bg-red-900/10 border-red-800/40'
                  }`}>
                    <div className="text-xs text-gray-400 w-20 flex-shrink-0">{d.date}</div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className={`font-bold text-sm ${d.realized_pnl>=0?'text-green-400':'text-red-400'}`}>
                          {d.realized_pnl>=0?'+':''}${d.realized_pnl?.toFixed(2)}
                        </span>
                        {d.hit_target && <span className="text-xs bg-green-900/40 text-green-400 px-1.5 py-0.5 rounded">✅ Target hit</span>}
                      </div>
                      <p className="text-xs text-gray-500">{d.trade_count} trades · {d.win_rate}% win rate</p>
                    </div>
                    <div className="text-xs text-gray-500 text-right">
                      <p>Target: ${d.daily_target?.toFixed(0)}</p>
                      <p>{((d.realized_pnl / d.daily_target) * 100).toFixed(0)}% of target</p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="text-center py-12 text-gray-500">
              <Calendar size={32} className="mx-auto mb-2 opacity-40"/>
              <p>No history yet. Set a goal and start trading!</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

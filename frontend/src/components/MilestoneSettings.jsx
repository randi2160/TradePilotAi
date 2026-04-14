import { useState, useEffect } from 'react'

const DEFAULT_MILESTONES = [
  { threshold: 400, floor_pct: 0.953, size_pct: 0.00, label: "🏆 $400 — Exits only" },
  { threshold: 300, floor_pct: 0.950, size_pct: 0.40, label: "🥇 $300 — 40% size" },
  { threshold: 200, floor_pct: 0.950, size_pct: 0.50, label: "🥈 $200 — 50% size" },
  { threshold: 150, floor_pct: 0.953, size_pct: 0.60, label: "🥉 $150 — 60% size" },
  { threshold: 100, floor_pct: 0.950, size_pct: 0.75, label: "✅ $100 — 75% size" },
]

export default function MilestoneSettings() {
  const [milestones, setMilestones] = useState(DEFAULT_MILESTONES)
  const [saving,     setSaving]     = useState(false)
  const [msg,        setMsg]        = useState('')
  const [loading,    setLoading]    = useState(true)

  useEffect(() => { load() }, [])

  async function load() {
    try {
      const { api } = await import('../hooks/useAuth')
      const r = await api.get('/milestones')
      if (r.data.milestones?.length) setMilestones(r.data.milestones)
    } catch {} finally { setLoading(false) }
  }

  async function save() {
    setSaving(true)
    try {
      const { api } = await import('../hooks/useAuth')
      await api.put('/milestones', { milestones })
      setMsg('✅ Milestones saved!')
    } catch (e) {
      setMsg(`❌ ${e.response?.data?.detail || e.message}`)
    } finally {
      setSaving(false)
      setTimeout(() => setMsg(''), 3000)
    }
  }

  function update(i, field, val) {
    const m = [...milestones]
    m[i] = { ...m[i], [field]: val }
    // Auto-update label
    m[i].label = `${m[i].size_pct === 0 ? '🏆' : m[i].size_pct <= 0.4 ? '🥇' : m[i].size_pct <= 0.5 ? '🥈' : m[i].size_pct <= 0.6 ? '🥉' : '✅'} $${m[i].threshold} — ${m[i].size_pct === 0 ? 'Exits only' : `${Math.round(m[i].size_pct * 100)}% size`}`
    setMilestones(m)
  }

  function reset() {
    setMilestones(DEFAULT_MILESTONES)
  }

  if (loading) return <div className="text-gray-500 text-sm">Loading milestones...</div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-bold text-white">🎯 Profit Milestones</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            When P&L hits a milestone, the floor locks in and trade size reduces.
            If P&L drops below the floor — all positions close, profit secured.
          </p>
        </div>
        <button onClick={reset} className="text-xs text-gray-500 hover:text-gray-300 px-2 py-1 rounded">
          Reset defaults
        </button>
      </div>

      {/* Visual milestone ladder */}
      <div className="space-y-2">
        {[...milestones].sort((a,b) => b.threshold - a.threshold).map((m, i) => {
          const origIdx = milestones.findIndex(x => x.threshold === m.threshold)
          const floor = Math.round(m.threshold * m.floor_pct)
          const isExitsOnly = m.size_pct === 0

          return (
            <div key={i} className={`rounded-xl border p-3 ${
              isExitsOnly
                ? 'border-yellow-500/40 bg-yellow-500/5'
                : 'border-dark-700 bg-dark-800'
            }`}>
              <div className="flex items-center gap-3">
                {/* Threshold */}
                <div className="shrink-0">
                  <div className="text-xs text-gray-500 mb-1">Hit $</div>
                  <input
                    type="number" min={10} max={10000} step={50}
                    value={m.threshold}
                    onChange={e => update(origIdx, 'threshold', Number(e.target.value))}
                    className="w-20 bg-dark-700 border border-dark-600 rounded-lg px-2 py-1 text-sm text-white text-center"
                  />
                </div>

                {/* Arrow */}
                <div className="text-gray-600">→</div>

                {/* Floor */}
                <div className="shrink-0">
                  <div className="text-xs text-gray-500 mb-1">Floor ${floor}</div>
                  <div className="flex items-center gap-1">
                    <input
                      type="range" min={0.85} max={0.99} step={0.005}
                      value={m.floor_pct}
                      onChange={e => update(origIdx, 'floor_pct', Number(e.target.value))}
                      className="w-20 accent-green-500"
                    />
                    <span className="text-xs text-green-400 w-8">{Math.round(m.floor_pct * 100)}%</span>
                  </div>
                </div>

                {/* Arrow */}
                <div className="text-gray-600">→</div>

                {/* Size */}
                <div className="flex-1">
                  <div className="text-xs text-gray-500 mb-1">
                    {isExitsOnly ? '🛑 Stop new trades' : `Trade size: ${Math.round(m.size_pct * 100)}%`}
                  </div>
                  <div className="flex items-center gap-2">
                    <input
                      type="range" min={0} max={1} step={0.05}
                      value={m.size_pct}
                      onChange={e => update(origIdx, 'size_pct', Number(e.target.value))}
                      className="flex-1 accent-brand-500"
                    />
                    <span className={`text-xs font-bold w-12 text-right ${
                      isExitsOnly ? 'text-red-400' : 'text-brand-400'
                    }`}>
                      {isExitsOnly ? 'EXIT' : `${Math.round(m.size_pct * 100)}%`}
                    </span>
                  </div>
                </div>
              </div>

              {/* Summary */}
              <div className="mt-2 text-xs text-gray-500">
                {isExitsOnly
                  ? `At $${m.threshold}: No new entries. Manage open positions to exit. Floor=$${floor}.`
                  : `At $${m.threshold}: New trade size drops to ${Math.round(m.size_pct*100)}% of normal. Floor=$${floor} locked.`
                }
              </div>
            </div>
          )
        })}
      </div>

      {/* How it works */}
      <div className="bg-dark-900/60 rounded-xl p-3 border border-dark-700">
        <div className="text-xs font-bold text-gray-400 mb-2">How it works</div>
        <div className="space-y-1 text-xs text-gray-500">
          <div>📈 <span className="text-white">Profit grows</span> → hits milestone → floor locks in automatically</div>
          <div>📉 <span className="text-white">Profit drops below floor</span> → all positions close, day ends</div>
          <div>🔄 <span className="text-white">Still above floor</span> → keeps trading with reduced size</div>
          <div>🏆 <span className="text-white">Top milestone hit</span> → exits only mode, no new trades</div>
        </div>
      </div>

      {msg && (
        <div className={`text-sm px-3 py-2 rounded-lg ${
          msg.startsWith('✅') ? 'text-green-400 bg-green-900/20' : 'text-red-400 bg-red-900/20'
        }`}>{msg}</div>
      )}

      <button onClick={save} disabled={saving}
        className="w-full bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold px-4 py-3 rounded-xl disabled:opacity-50 transition-colors text-sm">
        {saving ? '⏳ Saving…' : '💾 Save Milestones'}
      </button>
    </div>
  )
}

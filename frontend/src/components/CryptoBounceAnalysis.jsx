import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { RefreshCw, TrendingUp, TrendingDown, Target, AlertTriangle, Zap, Eye } from 'lucide-react'

const SCORE_COLOR = (s) =>
  s >= 70 ? 'text-green-400' :
  s >= 50 ? 'text-yellow-400' :
  s >= 30 ? 'text-orange-400' : 'text-gray-500'

const SCORE_BG = (s) =>
  s >= 70 ? 'bg-green-900/20 border-green-800/40' :
  s >= 50 ? 'bg-yellow-900/20 border-yellow-800/40' :
  s >= 30 ? 'bg-orange-900/20 border-orange-800/40' :
  'bg-dark-700 border-dark-600'

const ACTION_STYLE = {
  BUY_BOUNCE: { bg: 'bg-green-900/30 border-green-700', text: 'text-green-400', icon: '🎯' },
  WAIT:       { bg: 'bg-yellow-900/20 border-yellow-700', text: 'text-yellow-400', icon: '⏳' },
  SKIP:       { bg: 'bg-dark-700 border-dark-600', text: 'text-gray-500', icon: '⏭' },
}

export default function CryptoBounceAnalysis() {
  const [data,      setData]      = useState(null)
  const [loading,   setLoading]   = useState(false)
  const [expanded,  setExpanded]  = useState(null)
  const [useLlm,    setUseLlm]    = useState(true)
  const [error,     setError]     = useState('')

  async function runAnalysis() {
    setLoading(true)
    setError('')
    try {
      const r = await api.get(`/crypto/bounce-analysis?use_llm=${useLlm}`, { timeout: 30000 })
      setData(r.data)
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadCached() {
    try {
      const r = await api.get('/crypto/bounce-analysis/cached')
      if (r.data.count > 0) setData(r.data)
    } catch {}
  }

  useEffect(() => { loadCached() }, [])

  const coins = data?.coins ? Object.values(data.coins) : []

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Eye size={18} className="text-brand-400"/>
            <h2 className="font-bold text-white text-lg">Crypto Bounce Analyzer</h2>
            <span className="text-xs px-2 py-0.5 rounded-full bg-purple-900/30 border border-purple-800/40 text-purple-400">
              Observation Only
            </span>
          </div>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1 text-xs text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={e => setUseLlm(e.target.checked)}
                className="rounded border-dark-500"
              />
              AI Recommendations
            </label>
            <button
              onClick={runAnalysis}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-lg text-sm disabled:opacity-50"
            >
              {loading ? <RefreshCw size={14} className="animate-spin"/> : <Zap size={14}/>}
              {loading ? 'Analyzing…' : 'Run Analysis'}
            </button>
          </div>
        </div>
        <p className="text-xs text-gray-500">
          Analyzes price windows, spike patterns, support/resistance, mean reversion speed, and bounce frequency.
          No trades executed — review results and decide manually.
        </p>
        {error && (
          <div className="mt-2 text-xs text-red-400 bg-red-900/20 border border-red-800/40 rounded-lg p-2">
            {error}
          </div>
        )}
      </div>

      {/* Results */}
      {coins.length > 0 && (
        <div className="space-y-2">
          {coins.map(coin => {
            const isExpanded = expanded === coin.ticker
            const llm = coin.llm_recommendation || {}
            const actionStyle = ACTION_STYLE[llm.action] || ACTION_STYLE.SKIP
            const trend = coin.trend || {}
            const entry = coin.entry_exit || {}
            const entryZone = entry.entry_zone || {}
            const bounce = coin.bounce_stats || {}
            const w = coin.windows?.['1hr'] || coin.windows?.['20min'] || {}

            return (
              <div key={coin.ticker}
                className={'border rounded-xl overflow-hidden transition-all ' + SCORE_BG(coin.bounce_score)}
              >
                {/* Summary row */}
                <div
                  className="flex items-center justify-between p-3 cursor-pointer hover:bg-white/5"
                  onClick={() => setExpanded(isExpanded ? null : coin.ticker)}
                >
                  <div className="flex items-center gap-3">
                    <div className="text-center min-w-[50px]">
                      <div className={'text-xl font-black ' + SCORE_COLOR(coin.bounce_score)}>
                        {coin.bounce_score}
                      </div>
                      <div className="text-[10px] text-gray-600">SCORE</div>
                    </div>
                    <div>
                      <div className="font-bold text-white">{coin.ticker}</div>
                      <div className="text-xs text-gray-400">${coin.price?.toFixed(coin.price > 100 ? 2 : 4)}</div>
                    </div>
                    <div className="hidden sm:flex items-center gap-3 text-xs">
                      <span className={trend.type === 'ranging' ? 'text-green-400' : trend.type === 'trending' ? 'text-red-400' : 'text-yellow-400'}>
                        {trend.type === 'ranging' ? '↔ Ranging' : trend.type === 'trending' ? (trend.direction === 'up' ? '↑ Trending' : '↓ Trending') : '~ Mixed'}
                      </span>
                      <span className="text-gray-500">
                        {bounce.count || 0} bounces | avg {bounce.avg_bounce_pct?.toFixed(2) || 0}%
                      </span>
                      <span className="text-gray-500">
                        Band: {(w.band_pos * 100)?.toFixed(0) || 50}%
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {llm.action && (
                      <span className={'text-xs px-2 py-1 rounded-lg border font-bold ' + actionStyle.bg + ' ' + actionStyle.text}>
                        {actionStyle.icon} {llm.action?.replace('_', ' ')}
                      </span>
                    )}
                    <span className="text-gray-600 text-xs">{isExpanded ? '▲' : '▼'}</span>
                  </div>
                </div>

                {/* Expanded detail */}
                {isExpanded && (
                  <div className="border-t border-dark-600 p-3 space-y-3 bg-dark-900/50">
                    {/* Stat grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                      <StatBox label="Bounce Count" value={bounce.count || 0} />
                      <StatBox label="Avg Bounce" value={`${bounce.avg_bounce_pct?.toFixed(2) || 0}%`} />
                      <StatBox label="Avg Hold" value={`${bounce.avg_bounce_bars?.toFixed(0) || 0} bars`} />
                      <StatBox label="R:R Ratio" value={entry.risk_reward?.toFixed(1) || '—'} color={entry.risk_reward >= 2 ? 'text-green-400' : 'text-yellow-400'} />
                      <StatBox label="Trend" value={trend.type || '—'} color={trend.type === 'ranging' ? 'text-green-400' : 'text-gray-400'} />
                      <StatBox label="R²" value={trend.r_squared?.toFixed(2) || '—'} />
                      <StatBox label="Reversion Speed" value={`${coin.reversion_stats?.avg_reversion_bars?.toFixed(0) || '?'} bars`} />
                      <StatBox label="Vol at Bounce" value={`${coin.vol_at_bounces?.avg_bounce_vol_ratio?.toFixed(1) || 1}×`}
                        color={coin.vol_at_bounces?.vol_surge_at_bounce ? 'text-green-400' : 'text-gray-400'} />
                    </div>

                    {/* Support/Resistance */}
                    <div className="flex gap-4 text-xs">
                      <div>
                        <span className="text-gray-500">Support: </span>
                        <span className="text-green-400 font-mono">
                          ${coin.nearest_support?.toFixed(coin.price > 100 ? 2 : 4) || '—'}
                        </span>
                        {coin.dist_to_support_pct != null && (
                          <span className="text-gray-600 ml-1">({coin.dist_to_support_pct.toFixed(2)}% away)</span>
                        )}
                      </div>
                      <div>
                        <span className="text-gray-500">Resistance: </span>
                        <span className="text-red-400 font-mono">
                          ${coin.nearest_resistance?.toFixed(coin.price > 100 ? 2 : 4) || '—'}
                        </span>
                        {coin.dist_to_resistance_pct != null && (
                          <span className="text-gray-600 ml-1">({coin.dist_to_resistance_pct.toFixed(2)}% away)</span>
                        )}
                      </div>
                    </div>

                    {/* Entry/Exit zones */}
                    <div className="bg-dark-800 rounded-lg p-2.5 text-xs space-y-1">
                      <div className="font-bold text-gray-300 mb-1">Suggested Entry/Exit (Math-Based)</div>
                      <div className="flex gap-4 flex-wrap">
                        <span><span className="text-gray-500">Entry zone: </span><span className="text-brand-400 font-mono">${entryZone.ideal?.toFixed(coin.price > 100 ? 2 : 4) || '—'}</span></span>
                        <span><span className="text-gray-500">Stop: </span><span className="text-red-400 font-mono">${entry.stop?.toFixed(coin.price > 100 ? 2 : 4) || '—'}</span></span>
                        <span><span className="text-gray-500">Target: </span><span className="text-green-400 font-mono">${entry.target_conservative?.toFixed(coin.price > 100 ? 2 : 4) || '—'}</span></span>
                        <span><span className="text-gray-500">Aggressive: </span><span className="text-green-300 font-mono">${entry.target_aggressive?.toFixed(coin.price > 100 ? 2 : 4) || '—'}</span></span>
                      </div>
                      <div className="text-gray-600">
                        Est profit: {entry.est_profit_pct?.toFixed(2) || 0}% | Hold: ~{entry.est_hold_bars || 0} bars | Dist to entry: {entryZone.dist_to_entry_pct?.toFixed(2) || 0}%
                      </div>
                    </div>

                    {/* LLM recommendation */}
                    {llm.action && (
                      <div className={'rounded-lg p-2.5 text-xs border ' + actionStyle.bg}>
                        <div className="font-bold text-gray-300 mb-1">AI Recommendation</div>
                        <div className={'font-bold ' + actionStyle.text}>
                          {actionStyle.icon} {llm.action?.replace('_', ' ')} — Confidence: {((llm.confidence || 0) * 100).toFixed(0)}%
                        </div>
                        {llm.entry && <div className="text-gray-400 mt-1">Entry: {llm.entry} | Stop: {llm.stop} | Target: {llm.target}</div>}
                        {llm.reasoning && <div className="text-gray-500 mt-1 italic">{llm.reasoning}</div>}
                      </div>
                    )}

                    {/* Window breakdown */}
                    <div className="text-xs text-gray-600">
                      Windows: {Object.entries(coin.windows || {}).map(([k, v]) => (
                        <span key={k} className="mr-3">
                          {k}: band={((v.band_pos || 0) * 100).toFixed(0)}% vol={v.vol_pct?.toFixed(2)}%
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Empty state */}
      {!loading && coins.length === 0 && !error && (
        <div className="text-center py-12 text-gray-500">
          <Eye size={40} className="mx-auto mb-3 opacity-30"/>
          <p className="font-bold text-gray-400">No analysis yet</p>
          <p className="text-sm">Click "Run Analysis" to scan crypto for bounce patterns</p>
        </div>
      )}

      {/* Info box */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-3 text-xs text-gray-600">
        <strong className="text-gray-400">How scoring works:</strong>{' '}
        Ranging market (20pts) + Price near lower band (20pts) + Historical bounces (15pts) +
        Bounce size (15pts) + Mean reversion speed (10pts) + Volume confirmation (10pts) +
        Near support (10pts) = max 100. Score ≥ 60 with AI BUY_BOUNCE ≥ 65% confidence = actionable.
      </div>
    </div>
  )
}

function StatBox({ label, value, color = 'text-white' }) {
  return (
    <div className="bg-dark-800 rounded-lg p-2 text-center">
      <div className="text-gray-500 text-[10px]">{label}</div>
      <div className={'font-bold mt-0.5 ' + color}>{value}</div>
    </div>
  )
}

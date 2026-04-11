import { useState, useEffect } from 'react'
import { getAdvice, suggestWatchlist, getUnusualVolume } from '../services/api'
import { Brain, TrendingUp, TrendingDown, AlertTriangle, RefreshCw, Zap, CheckCircle } from 'lucide-react'

const CONVICTION_COLOR = (c) =>
  c >= 80 ? 'text-green-400' : c >= 65 ? 'text-yellow-400' : 'text-orange-400'

const REGIME_CONFIG = {
  trending_bullish: { color: 'text-green-400', bg: 'bg-green-900/20 border-green-800', icon: '📈', label: 'Trending Bullish' },
  trending_bearish: { color: 'text-red-400',   bg: 'bg-red-900/20 border-red-800',     icon: '📉', label: 'Trending Bearish' },
  choppy:           { color: 'text-yellow-400', bg: 'bg-yellow-900/20 border-yellow-800', icon: '〰️', label: 'Choppy Market' },
  risk_on:          { color: 'text-brand-500',  bg: 'bg-teal-900/20 border-teal-800',   icon: '🚀', label: 'Risk-On' },
  risk_off:         { color: 'text-orange-400', bg: 'bg-orange-900/20 border-orange-800',icon: '🛡️', label: 'Risk-Off' },
  stay_out:         { color: 'text-red-500',    bg: 'bg-red-900/30 border-red-700',     icon: '⛔', label: 'STAY OUT' },
  unknown:          { color: 'text-gray-400',   bg: 'bg-dark-700 border-dark-600',      icon: '❓', label: 'Unknown' },
}

function TradeCard({ trade, onAddToWatchlist }) {
  const [expanded, setExpanded] = useState(false)
  const isLong = trade.action === 'BUY'
  const rr     = trade.risk_reward ?? 0

  return (
    <div className={`rounded-xl border p-4 space-y-3 ${
      isLong ? 'bg-green-900/10 border-green-800/60' :
      trade.action === 'SELL' ? 'bg-red-900/10 border-red-800/60' :
      'bg-dark-700 border-dark-600'
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-2xl font-black text-white">{trade.symbol}</span>
          <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
            isLong ? 'bg-green-800 text-green-300' : 'bg-red-800 text-red-300'
          }`}>
            {isLong ? '▲' : '▼'} {trade.action}
          </span>
          {trade.timeframe && (
            <span className="text-xs bg-dark-600 text-gray-300 px-2 py-0.5 rounded-full">
              {trade.timeframe}
            </span>
          )}
        </div>
        <div className="text-right">
          <div className={`text-lg font-black ${CONVICTION_COLOR(trade.conviction)}`}>
            {trade.conviction}%
          </div>
          <div className="text-xs text-gray-500">conviction</div>
        </div>
      </div>

      {/* Probability bar */}
      <div>
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Probability of hitting target</span>
          <span className="font-bold text-white">{trade.probability_of_target}%</span>
        </div>
        <div className="h-2 bg-dark-600 rounded-full overflow-hidden">
          <div
            className="h-2 rounded-full transition-all"
            style={{
              width: `${trade.probability_of_target}%`,
              background: trade.probability_of_target >= 70
                ? 'linear-gradient(90deg,#00d4aa,#00b894)'
                : trade.probability_of_target >= 55
                ? 'linear-gradient(90deg,#f59e0b,#d97706)'
                : 'linear-gradient(90deg,#ef4444,#dc2626)',
            }}
          />
        </div>
      </div>

      {/* Key levels */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'Entry Zone', value: `$${trade.entry_zone?.low?.toFixed(2)}–$${trade.entry_zone?.high?.toFixed(2)}`, color: 'text-white' },
          { label: 'Stop Loss',  value: `$${trade.stop_loss?.toFixed(2)}`,  color: 'text-red-400' },
          { label: 'Take Profit',value: `$${trade.take_profit?.toFixed(2)}`, color: 'text-green-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-dark-700/60 rounded-lg p-2 text-center">
            <p className="text-xs text-gray-500">{label}</p>
            <p className={`text-sm font-bold ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* R:R */}
      <div className="flex gap-3 text-sm">
        <div className="flex items-center gap-1">
          <span className="text-gray-400">Risk/Reward:</span>
          <span className={`font-bold ${rr >= 3 ? 'text-green-400' : rr >= 2 ? 'text-yellow-400' : 'text-red-400'}`}>
            1:{rr.toFixed(1)}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-gray-400">Position:</span>
          <span className="text-white font-bold">{trade.position_size_pct}% of capital</span>
        </div>
      </div>

      {/* Entry trigger */}
      {trade.entry_trigger && (
        <div className="bg-dark-700/80 rounded-lg p-2.5 text-xs">
          <span className="text-gray-400">🎯 Entry: </span>
          <span className="text-white">{trade.entry_trigger}</span>
        </div>
      )}

      {/* Toggle details */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-brand-500 hover:text-brand-400 flex items-center gap-1"
      >
        {expanded ? '▲ Hide' : '▼ Show'} signal details
      </button>

      {expanded && (
        <div className="space-y-2 text-xs">
          {(trade.signals_confluence ?? []).length > 0 && (
            <div>
              <p className="text-gray-400 mb-1">✅ Confirming signals:</p>
              {trade.signals_confluence.map((s,i) => (
                <p key={i} className="text-green-300 ml-2">• {s}</p>
              ))}
            </div>
          )}
          {(trade.risks ?? []).length > 0 && (
            <div>
              <p className="text-gray-400 mb-1">⚠️ Risks:</p>
              {trade.risks.map((r,i) => (
                <p key={i} className="text-yellow-300 ml-2">• {r}</p>
              ))}
            </div>
          )}
          {trade.exit_trigger && (
            <div>
              <p className="text-gray-400">🚪 Exit: <span className="text-white">{trade.exit_trigger}</span></p>
            </div>
          )}
        </div>
      )}

      {onAddToWatchlist && (
        <button
          onClick={() => onAddToWatchlist(trade.symbol)}
          className="w-full text-xs bg-dark-700 hover:bg-dark-600 text-brand-500 py-1.5 rounded-lg transition-colors"
        >
          + Add {trade.symbol} to Watchlist
        </button>
      )}
    </div>
  )
}

export default function AIAdvisor({ onAddToWatchlist }) {
  const [advice,  setAdvice]  = useState(null)
  const [loading, setLoading] = useState(false)
  const [unusual, setUnusual] = useState([])
  const [tab,     setTab]     = useState('advice')

  useEffect(() => { fetchAdvice(); fetchUnusual() }, [])

  async function fetchAdvice(force = false) {
    setLoading(true)
    try {
      const data = await getAdvice(force)
      setAdvice(data)
    } catch(e) {
      setAdvice({ error: e.message, top_trades: [] })
    } finally {
      setLoading(false)
    }
  }

  async function fetchUnusual() {
    try {
      const data = await getUnusualVolume()
      setUnusual(Array.isArray(data) ? data : [])
    } catch {}
  }

  const regime  = advice?.market_regime ?? 'unknown'
  const regConf = REGIME_CONFIG[regime] ?? REGIME_CONFIG.unknown

  return (
    <div className="space-y-4">
      {/* Tab bar */}
      <div className="flex gap-2">
        {[
          { id: 'advice',  label: '🧠 AI Advice' },
          { id: 'unusual', label: `⚡ Unusual Volume ${unusual.length > 0 ? `(${unusual.length})` : ''}` },
        ].map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              tab === t.id ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}
          >
            {t.label}
          </button>
        ))}
        <button
          onClick={() => fetchAdvice(true)}
          disabled={loading}
          className="ml-auto flex items-center gap-1.5 text-xs bg-dark-700 hover:bg-dark-600 text-gray-300 px-3 py-2 rounded-lg transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Analyzing…' : 'Refresh Analysis'}
        </button>
      </div>

      {tab === 'advice' && (
        <>
          {/* No key warning */}
          {advice?.error && advice.error.includes('key') && (
            <div className="bg-yellow-900/20 border border-yellow-700 rounded-xl p-4">
              <p className="text-yellow-400 font-bold flex items-center gap-2">
                <AlertTriangle size={16} /> OpenAI API Key Required
              </p>
              <p className="text-yellow-200/70 text-sm mt-1">{advice.setup}</p>
              <p className="text-xs text-gray-400 mt-2">
                Add <code className="bg-dark-700 px-1 rounded">OPENAI_API_KEY=sk-...</code> to your <code className="bg-dark-700 px-1 rounded">backend/.env</code> file and restart.
              </p>
              <a
                href="https://platform.openai.com/api-keys"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block mt-3 text-xs text-brand-500 hover:underline"
              >
                → Get your OpenAI API key here
              </a>
            </div>
          )}

          {!advice && !loading && (
            <div className="text-center py-16 text-gray-500">
              <Brain size={40} className="mx-auto mb-3 opacity-40" />
              <p>Click "Refresh Analysis" to get GPT-4 trade recommendations</p>
            </div>
          )}

          {loading && (
            <div className="text-center py-16">
              <Brain size={40} className="mx-auto mb-3 text-brand-500 animate-pulse" />
              <p className="text-brand-500 font-medium">AI analyzing all market data…</p>
              <p className="text-xs text-gray-500 mt-1">Scanning news, technicals, volume, sentiment…</p>
            </div>
          )}

          {advice && !loading && (
            <>
              {/* Market regime */}
              {advice.market_regime && (
                <div className={`flex items-center gap-3 p-4 rounded-xl border ${regConf.bg}`}>
                  <span className="text-2xl">{regConf.icon}</span>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className={`font-bold text-sm ${regConf.color}`}>{regConf.label}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${
                        advice.overall_stance === 'stay_out' ? 'bg-red-800 text-red-300' :
                        advice.overall_stance === 'aggressive' ? 'bg-green-800 text-green-300' :
                        'bg-dark-600 text-gray-300'
                      }`}>
                        {advice.overall_stance?.replace(/_/g,' ')} stance
                      </span>
                    </div>
                    {advice.regime_explanation && (
                      <p className="text-xs text-gray-300 mt-1">{advice.regime_explanation}</p>
                    )}
                  </div>
                  {advice.confidence_score > 0 && (
                    <div className="text-right">
                      <p className={`text-lg font-black ${CONVICTION_COLOR(advice.confidence_score)}`}>
                        {advice.confidence_score}%
                      </p>
                      <p className="text-xs text-gray-500">AI confidence</p>
                    </div>
                  )}
                </div>
              )}

              {/* Key market levels */}
              {advice.key_levels_today && Object.keys(advice.key_levels_today).length > 0 && (
                <div className="bg-dark-800 border border-dark-600 rounded-xl p-3">
                  <p className="text-xs font-bold text-gray-400 mb-2">KEY LEVELS TODAY</p>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(advice.key_levels_today).map(([sym, levels]) => (
                      <div key={sym} className="text-xs">
                        <span className="font-bold text-white">{sym}</span>
                        <span className="text-green-400 ml-1">S:{levels.support}</span>
                        <span className="text-red-400 ml-1">R:{levels.resistance}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Trade recommendations */}
              {(advice.top_trades ?? []).length > 0 ? (
                <div className="space-y-3">
                  <p className="text-sm font-bold text-gray-300">
                    🎯 Top {advice.top_trades.length} Trade Recommendations
                  </p>
                  {advice.top_trades.map((trade, i) => (
                    <TradeCard key={i} trade={trade} onAddToWatchlist={onAddToWatchlist} />
                  ))}
                </div>
              ) : (
                advice.overall_stance === 'stay_out' && (
                  <div className="bg-red-900/20 border border-red-800 rounded-xl p-5 text-center">
                    <p className="text-4xl mb-2">⛔</p>
                    <p className="text-red-400 font-bold text-lg">AI Recommends: STAY OUT TODAY</p>
                    <p className="text-red-300/70 text-sm mt-1">{advice.risk_warning}</p>
                  </div>
                )
              )}

              {/* Symbols to avoid */}
              {(advice.symbols_to_avoid ?? []).length > 0 && (
                <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
                  <p className="text-xs font-bold text-red-400 mb-2">⚠️ AVOID TODAY</p>
                  <div className="flex flex-wrap gap-2">
                    {advice.symbols_to_avoid.map(sym => (
                      <div key={sym} className="bg-red-900/30 border border-red-800/50 rounded-lg px-2 py-1">
                        <span className="text-sm font-bold text-red-300">{sym}</span>
                        {advice.avoid_reasons?.[sym] && (
                          <span className="text-xs text-red-400/70 ml-1">— {advice.avoid_reasons[sym]}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Insider signals */}
              {(advice.insider_signals ?? []).length > 0 && (
                <div className="bg-purple-900/20 border border-purple-800/50 rounded-xl p-4">
                  <p className="text-xs font-bold text-purple-400 mb-2">🔍 SMART MONEY SIGNALS</p>
                  {advice.insider_signals.map((signal, i) => (
                    <p key={i} className="text-sm text-purple-200 mb-1">• {signal}</p>
                  ))}
                </div>
              )}

              {/* Risk warning */}
              {advice.risk_warning && (
                <div className="bg-yellow-900/20 border border-yellow-800/50 rounded-xl p-3 flex gap-2">
                  <AlertTriangle size={16} className="text-yellow-400 flex-shrink-0 mt-0.5" />
                  <p className="text-sm text-yellow-200">{advice.risk_warning}</p>
                </div>
              )}
            </>
          )}
        </>
      )}

      {tab === 'unusual' && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500">
            Stocks with volume 2.5× above average — potential smart money activity
          </p>
          {unusual.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Zap size={32} className="mx-auto mb-2 opacity-40" />
              <p>No unusual volume detected. Start bot to monitor.</p>
            </div>
          ) : (
            unusual.map((a, i) => (
              <div key={i} className="bg-dark-800 border border-purple-800/40 rounded-xl p-3 flex items-center gap-3">
                <Zap size={16} className="text-purple-400" />
                <div className="flex-1">
                  <span className="font-bold text-white">{a.symbol}</span>
                  <span className="text-xs text-gray-400 ml-2">
                    Volume {a.volume_ratio?.toFixed(1)}× normal
                  </span>
                </div>
                <div className="text-right">
                  <span className={`text-sm font-bold ${a.signal==='BUY'?'text-green-400':a.signal==='SELL'?'text-red-400':'text-gray-400'}`}>
                    {a.signal}
                  </span>
                  <span className="text-xs text-gray-500 ml-1">{(a.confidence*100).toFixed(0)}%</span>
                </div>
                <span className="text-sm font-mono text-white">${a.price?.toFixed(2)}</span>
                {onAddToWatchlist && (
                  <button
                    onClick={() => onAddToWatchlist(a.symbol)}
                    className="text-xs text-brand-500 bg-dark-600 hover:bg-dark-500 px-2 py-1 rounded transition-colors"
                  >
                    +WL
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

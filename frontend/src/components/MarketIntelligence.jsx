import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { Shield, TrendingUp, AlertTriangle, CheckCircle, XCircle, RefreshCw, Brain } from 'lucide-react'

const REGIME_CONFIG = {
  trending_up:   { color:'text-green-400',  bg:'bg-green-900/20  border-green-800',  icon:'📈', label:'Trending Up'   },
  trending_down: { color:'text-red-400',    bg:'bg-red-900/20    border-red-800',    icon:'📉', label:'Trending Down' },
  choppy:        { color:'text-yellow-400', bg:'bg-yellow-900/20 border-yellow-800', icon:'〰️', label:'Choppy'        },
  breakout:      { color:'text-brand-500',  bg:'bg-teal-900/20   border-teal-800',   icon:'🚀', label:'Breakout'      },
  volatile:      { color:'text-orange-400', bg:'bg-orange-900/20 border-orange-800', icon:'⚡', label:'Volatile'      },
  low_vol:       { color:'text-blue-400',   bg:'bg-blue-900/20   border-blue-800',   icon:'😴', label:'Low Vol'       },
  neutral:       { color:'text-gray-400',   bg:'bg-dark-700      border-dark-600',   icon:'➡️', label:'Neutral'       },
}

const SETUP_COLORS = {
  momentum_breakout: 'text-green-400',
  pullback_long:     'text-blue-400',
  vwap_reclaim:      'text-brand-500',
  mean_reversion:    'text-purple-400',
  range_scalp:       'text-yellow-400',
  peak_bounce:       'text-orange-400',
  no_trade:          'text-gray-500',
}

function QualityBar({ value }) {
  const color = value >= 70 ? '#00d4aa' : value >= 50 ? '#f59e0b' : '#ef4444'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-dark-600 rounded-full h-2">
        <div className="h-2 rounded-full transition-all" style={{ width:`${Math.min(value,100)}%`, background:color }}/>
      </div>
      <span className="text-xs font-bold w-8" style={{color}}>{value?.toFixed(0)}</span>
    </div>
  )
}

export default function MarketIntelligence() {
  const [regime,   setRegime]   = useState(null)
  const [symbol,   setSymbol]   = useState('AAPL')
  const [setup,    setSetup]    = useState(null)
  const [rules,    setRules]    = useState(null)
  const [loading,  setLoading]  = useState('')
  const [tab,      setTab]      = useState('regime')

  useEffect(() => { loadRegime() }, [])

  async function loadRegime() {
    setLoading('regime')
    try {
      const r = await api.get('/regime')
      setRegime(r.data)
    } catch {}
    finally { setLoading('') }
  }

  async function analyzeSymbol() {
    if (!symbol) return
    setLoading('setup')
    try {
      const [s, r] = await Promise.all([
        api.get(`/setup/${symbol.toUpperCase()}`).then(x => x.data),
        api.post(`/rules/check/${symbol.toUpperCase()}`).then(x => x.data),
      ])
      setSetup(s)
      setRules(r)
      setTab('setup')
    } catch(e) {
      alert(e.response?.data?.detail ?? e.message)
    } finally { setLoading('') }
  }

  const rc = regime ? (REGIME_CONFIG[regime.regime] ?? REGIME_CONFIG.neutral) : null
  const advice = regime?.trade_advice ?? {}

  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
        <h2 className="font-black text-white text-lg flex items-center gap-2 mb-1">
          <Brain size={18} className="text-brand-500"/> Market Intelligence
        </h2>
        <p className="text-xs text-gray-400">
          Professional-grade regime detection, setup classification, and hard rules validation before any trade.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2">
        {[
          { id: 'regime', label: '🌡️ Market Regime' },
          { id: 'setup',  label: '🎯 Setup Analysis' },
          { id: 'rules',  label: '🛡️ Rules Check'   },
          { id: 'guide',  label: '📖 Strategy Guide' },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
              tab===t.id ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}>{t.label}</button>
        ))}
        <button onClick={loadRegime} disabled={loading==='regime'}
          className="ml-auto text-xs bg-dark-700 text-gray-400 px-3 py-2 rounded-lg hover:bg-dark-600">
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''}/>
        </button>
      </div>

      {/* ── Regime ───────────────────────────────────────────────────────────── */}
      {tab === 'regime' && (
        <div className="space-y-4">
          {!regime ? (
            <div className="text-center py-12 text-gray-500">
              <p>Start the bot to detect market regime</p>
            </div>
          ) : (
            <>
              {/* Current regime */}
              <div className={`p-5 rounded-xl border ${rc?.bg}`}>
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-3xl">{rc?.icon}</span>
                  <div>
                    <p className={`text-xl font-black ${rc?.color}`}>{rc?.label}</p>
                    <p className="text-sm text-gray-300">{regime.description}</p>
                  </div>
                  <div className="ml-auto text-right">
                    <p className={`text-lg font-bold ${rc?.color}`}>{(regime.confidence*100).toFixed(0)}%</p>
                    <p className="text-xs text-gray-500">confidence</p>
                  </div>
                </div>

                {/* Trade advice */}
                <div className="grid grid-cols-3 gap-2 mt-3">
                  {[
                    { label:'Position Size', value:`${(advice.size_mult*100).toFixed(0)}% of normal` },
                    { label:'Stop Width',    value:`${(advice.stop_mult*100).toFixed(0)}% of ATR`    },
                    { label:'Min R:R',       value:`${advice.min_rr}:1`                              },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-dark-700/60 rounded-lg p-2.5 text-center">
                      <p className="text-xs text-gray-400">{label}</p>
                      <p className="text-sm font-bold text-white">{value}</p>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-400 mt-2">{advice.note}</p>
              </div>

              {/* Recommended strategies */}
              <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
                <p className="text-sm font-bold text-gray-300 mb-3">✅ Best Strategies for Today</p>
                <div className="flex flex-wrap gap-2">
                  {(regime.strategies ?? []).map(s => (
                    <span key={s} className="bg-brand-500/20 border border-brand-500/40 text-brand-400 text-xs px-3 py-1.5 rounded-lg font-medium capitalize">
                      {s.replace(/_/g,' ')}
                    </span>
                  ))}
                </div>
              </div>

              {/* Metrics */}
              <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
                <p className="text-sm font-bold text-gray-300 mb-3">📊 SPY Market Metrics</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {regime.metrics && Object.entries({
                    'Trend Strength': regime.metrics.trend_strength,
                    'ATR %':          `${regime.metrics.atr_pct}%`,
                    'Range %':        `${regime.metrics.range_pct}%`,
                    'Volume Ratio':   `${regime.metrics.volume_ratio}×`,
                    '5-Day ROC':      `${regime.metrics.roc_5day}%`,
                    'SPY Price':      `$${regime.metrics.current_price}`,
                    'EMA 9':          `$${regime.metrics.ema9}`,
                    'EMA 21':         `$${regime.metrics.ema21}`,
                  }).map(([k, v]) => (
                    <div key={k} className="bg-dark-700 rounded-lg p-2.5 text-center">
                      <p className="text-xs text-gray-500">{k}</p>
                      <p className="text-sm font-bold text-white">{v}</p>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Setup Analysis ────────────────────────────────────────────────────── */}
      {tab === 'setup' && (
        <div className="space-y-4">
          <div className="flex gap-2">
            <input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())}
              placeholder="Symbol e.g. AAPL"
              className="flex-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500 font-mono uppercase"/>
            <button onClick={analyzeSymbol} disabled={loading==='setup' || !symbol}
              className="px-5 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold text-sm rounded-xl disabled:opacity-50 transition-colors">
              {loading==='setup' ? '⟳ Analyzing…' : '🔬 Analyze'}
            </button>
          </div>

          {setup && (
            <div className="space-y-4">
              {/* Setup type */}
              <div className={`p-4 rounded-xl border ${
                setup.tradeable ? 'bg-green-900/10 border-green-800' : 'bg-dark-800 border-dark-600'
              }`}>
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <span className={`text-lg font-black capitalize ${SETUP_COLORS[setup.setup_type] ?? 'text-white'}`}>
                      {setup.setup_type?.replace(/_/g,' ') ?? 'No Setup'}
                    </span>
                    {setup.tradeable && <span className="ml-2 text-xs bg-green-800 text-green-300 px-2 py-0.5 rounded-full">TRADEABLE</span>}
                  </div>
                  <span className={`text-xl font-black ${setup.quality>=70?'text-green-400':setup.quality>=50?'text-yellow-400':'text-red-400'}`}>
                    {setup.quality?.toFixed(0)}/100
                  </span>
                </div>
                <p className="text-sm text-gray-300">{setup.description}</p>
                <QualityBar value={setup.quality}/>
              </div>

              {/* Rules */}
              {setup.tradeable && (
                <div className="bg-dark-800 border border-dark-600 rounded-xl p-4 space-y-2">
                  {[
                    { label:'Entry',  value: setup.entry_rule,  icon:'▶' },
                    { label:'Stop',   value: setup.stop_rule,   icon:'🛑' },
                    { label:'Target', value: setup.target_rule, icon:'🎯' },
                  ].map(({ label, value, icon }) => (
                    <div key={label} className="text-sm">
                      <span className="text-gray-500 text-xs">{icon} {label}: </span>
                      <span className="text-gray-200">{value}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Quality issues */}
              {(setup.quality_issues ?? []).length > 0 && (
                <div className="bg-yellow-900/20 border border-yellow-800/50 rounded-xl p-3">
                  <p className="text-xs font-bold text-yellow-400 mb-1">⚠️ Issues</p>
                  {setup.quality_issues.map((i, idx) => (
                    <p key={idx} className="text-xs text-yellow-200">• {i}</p>
                  ))}
                </div>
              )}

              {/* VWAP info */}
              {setup.vwap_info && (
                <div className="bg-dark-800 border border-dark-600 rounded-xl p-3 flex gap-4 text-xs">
                  <span className="text-gray-400">VWAP: <strong className="text-white">${setup.vwap_info.vwap?.toFixed(2)}</strong></span>
                  <span className={setup.vwap_info.above_vwap ? 'text-green-400' : 'text-red-400'}>
                    {setup.vwap_info.above_vwap ? '▲ Above VWAP' : '▼ Below VWAP'} ({setup.vwap_info.distance_pct?.toFixed(2)}%)
                  </span>
                  {setup.vwap_info.reclaim && <span className="text-brand-500 font-bold">🔄 RECLAIM</span>}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Rules Check ───────────────────────────────────────────────────────── */}
      {tab === 'rules' && (
        <div className="space-y-4">
          {!rules ? (
            <div className="text-center py-8 text-gray-500">
              <p>Analyze a symbol first to see rule results</p>
            </div>
          ) : (
            <>
              {/* Overall result */}
              <div className={`p-4 rounded-xl border ${
                rules.passed ? 'bg-green-900/20 border-green-800' : 'bg-red-900/20 border-red-800'
              }`}>
                <p className={`text-lg font-black ${rules.passed ? 'text-green-400' : 'text-red-400'}`}>
                  {rules.summary}
                </p>
              </div>

              {/* Position sizing (risk-first) */}
              {rules.sizing && (
                <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
                  <p className="text-sm font-bold text-gray-300 mb-3">📐 Risk-First Position Sizing</p>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                    {[
                      ['Shares',         rules.sizing.shares],
                      ['Entry',          `$${rules.sizing.entry}`],
                      ['Stop Loss',      `$${rules.sizing.stop_loss}`],
                      ['Take Profit',    `$${rules.sizing.take_profit}`],
                      ['Risk ($)',       `$${rules.sizing.risk_dollars}`],
                      ['Risk (%)',       `${rules.sizing.risk_pct}%`],
                      ['Reward ($)',     `$${rules.sizing.reward_dollars}`],
                      ['Actual R:R',    `${rules.sizing.actual_rr}:1`],
                      ['Position Value',`$${rules.sizing.position_value}`],
                      ['Slippage Est.', `$${rules.sizing.slippage_est}`],
                      ['Net Reward',    `$${rules.sizing.net_reward}`],
                      ['Sizing Method', rules.sizing.sizing_method],
                    ].map(([k, v]) => (
                      <div key={k} className="bg-dark-700 rounded-lg p-2">
                        <p className="text-gray-500">{k}</p>
                        <p className="font-bold text-white">{v}</p>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    ℹ️ Sizing based on 1% capital risk per trade — NOT profit target. This is safer and more professional.
                  </p>
                </div>
              )}

              {/* Individual rules */}
              <div className="bg-dark-800 border border-dark-600 rounded-xl overflow-hidden">
                <p className="text-sm font-bold text-gray-300 px-4 py-3 border-b border-dark-600">All Rules</p>
                <div className="divide-y divide-dark-700">
                  {(rules.rules ?? []).map((rule, i) => (
                    <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                      {rule.passed
                        ? <CheckCircle size={14} className="text-green-400 flex-shrink-0"/>
                        : <XCircle    size={14} className="text-red-400 flex-shrink-0"/>
                      }
                      <div className="flex-1">
                        <span className="text-sm text-white font-medium">{rule.rule}</span>
                        {!rule.critical && <span className="text-xs text-gray-600 ml-1">(advisory)</span>}
                        <p className="text-xs text-gray-500">{rule.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Strategy Guide ────────────────────────────────────────────────────── */}
      {tab === 'guide' && (
        <div className="space-y-4 text-sm">
          {[
            {
              title: '📈 Momentum Breakout',
              color: 'border-green-800/50',
              conditions: ['Price breaks 20-bar high', 'Volume ≥ 2× average', 'Above VWAP', '5-min uptrend'],
              entry:  'Buy on close above breakout — not before',
              stop:   'Below breakout level or 1.5× ATR',
              target: '2-3× ATR above entry',
              avoid:  'Chasing after extended move, low volume, below VWAP',
            },
            {
              title: '🔄 VWAP Reclaim',
              color: 'border-brand-500/50',
              conditions: ['Price was below VWAP', 'Price crosses back above', 'Volume confirms', 'Not overbought (RSI<65)'],
              entry:  'First candle close above VWAP',
              stop:   'Back below VWAP — no second chances',
              target: 'Prior high or 2× ATR above',
              avoid:  'Multiple failed reclaim attempts, low volume',
            },
            {
              title: '↩️ Pullback Long',
              color: 'border-blue-800/50',
              conditions: ['Uptrend (EMA9>EMA21>EMA50)', 'Pulled back to VWAP or EMA', 'RSI 30-45', 'MACD not deeply negative'],
              entry:  'First green candle after pullback',
              stop:   'Below swing low or VWAP',
              target: 'Prior high or measured move',
              avoid:  'Downtrending stocks, below VWAP, RSI<30',
            },
            {
              title: '🔀 Mean Reversion',
              color: 'border-purple-800/50',
              conditions: ['RSI < 25 or > 75', 'At Bollinger Band extreme', 'Volume confirming', 'No strong trend'],
              entry:  'Wait for first reversal candle — confirmation required',
              stop:   'Tight — below/above reversal candle',
              target: 'VWAP or mid-Bollinger — take quick profits',
              avoid:  'Trending stocks (mean reversion fails in trends)',
            },
          ].map(s => (
            <div key={s.title} className={`bg-dark-800 border ${s.color} rounded-xl p-4 space-y-3`}>
              <h3 className="font-bold text-white">{s.title}</h3>
              <div>
                <p className="text-xs text-gray-400 font-bold mb-1">ENTRY CONDITIONS (ALL required)</p>
                {s.conditions.map((c,i) => <p key={i} className="text-xs text-gray-300">✓ {c}</p>)}
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div className="bg-dark-700 p-2 rounded">
                  <p className="text-gray-500">Entry</p><p className="text-white">{s.entry}</p>
                </div>
                <div className="bg-dark-700 p-2 rounded">
                  <p className="text-gray-500">Stop</p><p className="text-red-300">{s.stop}</p>
                </div>
                <div className="bg-dark-700 p-2 rounded">
                  <p className="text-gray-500">Target</p><p className="text-green-300">{s.target}</p>
                </div>
              </div>
              <p className="text-xs text-yellow-300">⚠️ Avoid: {s.avoid}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

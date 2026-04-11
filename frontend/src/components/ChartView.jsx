import { useEffect, useRef, useState } from 'react'
import { createChart } from 'lightweight-charts'
import { getChart } from '../services/api'

const TIMEFRAMES = ['1Min', '5Min', '15Min', '1Hour']
const WATCHLIST  = ['AAPL','MSFT','NVDA','TSLA','AMD','SPY','QQQ','AMZN','META','GOOGL']

export default function ChartView({ signals }) {
  const chartRef  = useRef(null)
  const chartInst = useRef(null)
  const candleSer = useRef(null)
  const [symbol, setSymbol] = useState('AAPL')
  const [tf, setTf]         = useState('5Min')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!chartRef.current) return

    const chart = createChart(chartRef.current, {
      layout:     { background: { color: '#111827' }, textColor: '#9ca3af' },
      grid:       { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
      crosshair:  { mode: 1 },
      rightPriceScale: { borderColor: '#374151' },
      timeScale:  { borderColor: '#374151', timeVisible: true, secondsVisible: false },
      width:  chartRef.current.clientWidth,
      height: 380,
    })

    const series = chart.addCandlestickSeries({
      upColor:        '#00d4aa',
      downColor:      '#ef4444',
      borderUpColor:  '#00d4aa',
      borderDownColor:'#ef4444',
      wickUpColor:    '#00d4aa',
      wickDownColor:  '#ef4444',
    })

    chartInst.current = chart
    candleSer.current = series

    const ro = new ResizeObserver(() => {
      if (chartRef.current) chart.applyOptions({ width: chartRef.current.clientWidth })
    })
    ro.observe(chartRef.current)

    return () => { ro.disconnect(); chart.remove() }
  }, [])

  useEffect(() => {
    loadData()
  }, [symbol, tf])

  async function loadData() {
    if (!candleSer.current) return
    setLoading(true)
    try {
      const bars = await getChart(symbol, tf)
      if (!bars.length) return
      const candles = bars.map(b => ({
        time:  Math.floor(new Date(b.timestamp).getTime() / 1000),
        open:  b.open, high: b.high, low: b.low, close: b.close,
      })).sort((a, b) => a.time - b.time)
      candleSer.current.setData(candles)
      chartInst.current?.timeScale().fitContent()

      // Draw signal markers
      const sigForSymbol = (signals ?? []).find(s => s.symbol === symbol)
      if (sigForSymbol && sigForSymbol.signal !== 'HOLD') {
        const last = candles[candles.length - 1]
        candleSer.current.setMarkers([{
          time:     last.time,
          position: sigForSymbol.signal === 'BUY' ? 'belowBar' : 'aboveBar',
          color:    sigForSymbol.signal === 'BUY' ? '#00d4aa' : '#ef4444',
          shape:    sigForSymbol.signal === 'BUY' ? 'arrowUp'  : 'arrowDown',
          text:     `${sigForSymbol.signal} ${(sigForSymbol.confidence * 100).toFixed(0)}%`,
        }])
      }
    } catch (e) {
      console.error('Chart load error:', e)
    } finally {
      setLoading(false)
    }
  }

  const currentSig = (signals ?? []).find(s => s.symbol === symbol)

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap gap-2 items-center">
        {/* Symbol picker */}
        <div className="flex flex-wrap gap-1">
          {WATCHLIST.map(sym => (
            <button
              key={sym}
              onClick={() => setSymbol(sym)}
              className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                symbol === sym
                  ? 'bg-brand-500 text-dark-900'
                  : 'bg-dark-700 text-gray-300 hover:bg-dark-600'
              }`}
            >
              {sym}
            </button>
          ))}
        </div>
        {/* Timeframe */}
        <div className="flex gap-1 ml-auto">
          {TIMEFRAMES.map(t => (
            <button
              key={t}
              onClick={() => setTf(t)}
              className={`px-2 py-1 rounded text-xs transition-colors ${
                tf === t ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
              }`}
            >
              {t}
            </button>
          ))}
          <button
            onClick={loadData}
            className="px-2 py-1 rounded text-xs bg-dark-700 text-gray-400 hover:bg-dark-600"
          >
            ↻
          </button>
        </div>
      </div>

      {/* Signal badge */}
      {currentSig && currentSig.signal !== 'HOLD' && (
        <div className={`flex items-center gap-3 p-3 rounded-lg border ${
          currentSig.signal === 'BUY'
            ? 'bg-green-900/30 border-green-800 text-green-300'
            : 'bg-red-900/30 border-red-800 text-red-300'
        }`}>
          <span className="text-lg font-bold">{currentSig.signal === 'BUY' ? '▲' : '▼'} {currentSig.signal}</span>
          <div className="text-sm">
            <span className="font-semibold">{(currentSig.confidence * 100).toFixed(0)}% confidence</span>
            {' · '}
            <span className="text-xs opacity-75">{(currentSig.reasons ?? []).join(' · ')}</span>
          </div>
          <div className="ml-auto text-xs opacity-60">
            RSI {currentSig.rsi?.toFixed(0)} · Vol {currentSig.volume_ratio?.toFixed(1)}×
          </div>
        </div>
      )}

      {/* Chart */}
      <div className="relative bg-dark-800 border border-dark-600 rounded-xl overflow-hidden">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-dark-800/70 z-10">
            <span className="text-brand-500 text-sm animate-pulse">Loading…</span>
          </div>
        )}
        <div ref={chartRef} className="w-full" />
      </div>

      {/* Indicator summary */}
      {currentSig && (
        <div className="grid grid-cols-4 gap-2">
          {[
            { label: 'RSI',     value: currentSig.rsi?.toFixed(1) ?? '—' },
            { label: 'Vol Ratio', value: `${currentSig.volume_ratio?.toFixed(2) ?? '—'}×` },
            { label: 'ATR',     value: currentSig.atr?.toFixed(3) ?? '—' },
            { label: 'ML',      value: currentSig.ml_trained ? 'Active' : 'Training' },
          ].map(({ label, value }) => (
            <div key={label} className="bg-dark-800 border border-dark-600 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500">{label}</p>
              <p className="text-sm font-bold text-white">{value}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

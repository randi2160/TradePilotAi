export default function Signals({ signals = [] }) {
  if (!signals.length) {
    return (
      <div className="text-center py-16 text-gray-500">
        <p className="text-4xl mb-3">🤖</p>
        <p>Start the bot to see live AI signals.</p>
      </div>
    )
  }

  const sorted = [...signals].sort((a, b) => {
    const order = { BUY: 0, SELL: 1, HOLD: 2, WAIT: 3 }
    return (order[a.signal] ?? 9) - (order[b.signal] ?? 9) || b.confidence - a.confidence
  })

  return (
    <div className="space-y-4">
      <p className="text-xs text-gray-500">
        Refreshes every 30 seconds · {signals.length} symbols scanned
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {sorted.map(sig => {
          const isBuy  = sig.signal === 'BUY'
          const isSell = sig.signal === 'SELL'
          const isHold = sig.signal === 'HOLD' || sig.signal === 'WAIT'

          return (
            <div
              key={sig.symbol}
              className={`p-4 rounded-xl border transition-all ${
                isBuy  ? 'bg-green-900/15 border-green-800/50' :
                isSell ? 'bg-red-900/15 border-red-800/50'    :
                         'bg-dark-800 border-dark-600'
              }`}
            >
              {/* Header */}
              <div className="flex justify-between items-center mb-2">
                <span className="font-bold text-white text-lg">{sig.symbol}</span>
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-bold px-2 py-1 rounded-full ${
                    isBuy  ? 'bg-green-800 text-green-300' :
                    isSell ? 'bg-red-800 text-red-300'     :
                             'bg-dark-600 text-gray-400'
                  }`}>
                    {isBuy ? '▲ ' : isSell ? '▼ ' : '— '}{sig.signal}
                  </span>
                  <span className={`text-xs font-mono ${
                    sig.confidence > 0.75 ? 'text-yellow-400' : 'text-gray-400'
                  }`}>
                    {(sig.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Confidence bar */}
              <div className="w-full bg-dark-700 rounded-full h-1.5 mb-3">
                <div
                  className={`h-1.5 rounded-full transition-all duration-500 ${
                    isBuy ? 'bg-green-400' : isSell ? 'bg-red-400' : 'bg-gray-500'
                  }`}
                  style={{ width: `${(sig.confidence * 100).toFixed(0)}%` }}
                />
              </div>

              {/* Indicators row */}
              <div className="flex gap-3 text-xs text-gray-400 mb-2">
                {sig.rsi != null && (
                  <span className={sig.rsi < 30 ? 'text-green-400' : sig.rsi > 70 ? 'text-red-400' : ''}>
                    RSI {sig.rsi?.toFixed(0)}
                  </span>
                )}
                {sig.volume_ratio != null && (
                  <span className={sig.volume_ratio > 1.5 ? 'text-yellow-400' : ''}>
                    Vol {sig.volume_ratio?.toFixed(1)}×
                  </span>
                )}
                {sig.atr != null && <span>ATR {sig.atr?.toFixed(3)}</span>}
                {sig.price != null && <span className="ml-auto text-white font-mono">${sig.price?.toFixed(2)}</span>}
              </div>

              {/* Reasons */}
              {(sig.reasons ?? []).length > 0 && (
                <p className="text-xs text-gray-500 truncate">
                  {sig.reasons.join(' · ')}
                </p>
              )}

              {/* Model breakdown */}
              {sig.breakdown && (
                <div className="flex gap-2 mt-2">
                  {Object.entries(sig.breakdown).map(([model, val]) => (
                    <span key={model} className="text-xs bg-dark-700 px-2 py-0.5 rounded text-gray-400">
                      {model}: <span className="text-white">{typeof val === 'number' ? `${(val*100).toFixed(0)}%` : val}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

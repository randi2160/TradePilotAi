import { useEffect, useState } from 'react'
import { getMarketNews, getSymbolNews, addSymbol } from '../services/api'

const SENTIMENT_COLORS = {
  bullish: { bg: 'bg-green-900/30', border: 'border-green-800/50', text: 'text-green-400', dot: 'bg-green-400' },
  bearish: { bg: 'bg-red-900/30',   border: 'border-red-800/50',   text: 'text-red-400',   dot: 'bg-red-400'   },
  neutral: { bg: 'bg-dark-700',     border: 'border-dark-600',     text: 'text-gray-400',  dot: 'bg-gray-500'  },
}

function SymbolTag({ sym }) {
  const [added, setAdded] = useState(false)

  async function handleAdd(e) {
    e.preventDefault()
    e.stopPropagation()
    try {
      await addSymbol(sym)
      setAdded(true)
      setTimeout(() => setAdded(false), 3000)
    } catch {}
  }

  return (
    <div className="flex items-center gap-0.5 bg-dark-600 rounded overflow-hidden">
      <span className="text-xs text-gray-300 px-1.5 py-0.5">${sym}</span>
      <button
        onClick={handleAdd}
        title={added ? `${sym} added!` : `Add ${sym} to watchlist`}
        className={`text-xs px-1.5 py-0.5 transition-colors border-l border-dark-500 ${
          added
            ? 'text-green-400 bg-green-900/30'
            : 'text-gray-500 hover:text-brand-500 hover:bg-dark-500'
        }`}
      >
        {added ? '✓' : '+'}
      </button>
    </div>
  )
}

function NewsCard({ article }) {
  const s    = SENTIMENT_COLORS[article.sentiment] ?? SENTIMENT_COLORS.neutral
  const time = article.published
    ? new Date(article.published).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})
    : ''
  const score = Math.abs(article.score ?? 0)

  return (
    <a
      href={article.url || '#'}
      target="_blank"
      rel="noopener noreferrer"
      className={`block p-3 rounded-xl border ${s.bg} ${s.border} hover:opacity-80 transition-opacity`}
    >
      <div className="flex items-start gap-2">
        <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${s.dot}`} />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-white font-medium leading-snug line-clamp-2">
            {article.headline}
          </p>
          {article.summary && (
            <p className="text-xs text-gray-400 mt-1 line-clamp-1">{article.summary}</p>
          )}
          <div className="flex items-center gap-2 mt-1.5">
            <span className={`text-xs font-semibold capitalize ${s.text}`}>
              {article.sentiment}
            </span>
            {score > 0 && (
              <div className="flex-1 bg-dark-600 rounded-full h-1 max-w-[60px]">
                <div
                  className={`h-1 rounded-full ${s.dot}`}
                  style={{ width: `${Math.min(score * 100, 100)}%` }}
                />
              </div>
            )}
            <span className="text-xs text-gray-500 ml-auto">{article.source}</span>
            {time && <span className="text-xs text-gray-600">{time}</span>}
          </div>
          {(article.symbols ?? []).length > 0 && (
            <div className="flex gap-1 mt-1.5 flex-wrap">
              <span className="text-xs text-gray-500 self-center">+ Add to WL:</span>
              {article.symbols.slice(0,5).map(sym => (
                <SymbolTag key={sym} sym={sym} />
              ))}
            </div>
          )}
        </div>
      </div>
    </a>
  )
}

export default function NewsPanel({ watchlist = [] }) {
  const [news,    setNews]    = useState([])
  const [symbol,  setSymbol]  = useState('market')
  const [loading, setLoading] = useState(false)

  useEffect(() => { loadNews() }, [symbol])
  useEffect(() => {
    const iv = setInterval(loadNews, 120000)  // refresh every 2 min
    return () => clearInterval(iv)
  }, [symbol])

  async function loadNews() {
    setLoading(true)
    try {
      const data = symbol === 'market'
        ? await getMarketNews(20)
        : await getSymbolNews(symbol, 10)
      setNews(Array.isArray(data) ? data : [])
    } catch {
      setNews([])
    } finally {
      setLoading(false)
    }
  }

  const bullish = news.filter(n => n.sentiment === 'bullish').length
  const bearish = news.filter(n => n.sentiment === 'bearish').length
  const overallSentiment = bullish > bearish ? 'bullish' : bearish > bullish ? 'bearish' : 'neutral'

  return (
    <div className="space-y-4">
      {/* Symbol selector */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setSymbol('market')}
          className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
            symbol === 'market' ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
          }`}
        >
          🌐 Market
        </button>
        {watchlist.slice(0, 12).map(sym => (
          <button
            key={sym}
            onClick={() => setSymbol(sym)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              symbol === sym ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}
          >
            {sym}
          </button>
        ))}
        <button
          onClick={loadNews}
          disabled={loading}
          className="ml-auto px-3 py-1 rounded-lg text-xs bg-dark-700 text-gray-400 hover:bg-dark-600"
        >
          {loading ? '⟳' : '↻'} Refresh
        </button>
      </div>

      {/* Overall sentiment bar */}
      {news.length > 0 && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-3 flex items-center gap-3">
          <span className="text-xs text-gray-400">Sentiment:</span>
          <div className="flex-1 flex rounded-full overflow-hidden h-2">
            <div className="bg-green-400 h-2 transition-all" style={{width:`${(bullish/news.length*100).toFixed(0)}%`}}/>
            <div className="bg-gray-600 h-2 transition-all" style={{width:`${((news.length-bullish-bearish)/news.length*100).toFixed(0)}%`}}/>
            <div className="bg-red-400 h-2 transition-all" style={{width:`${(bearish/news.length*100).toFixed(0)}%`}}/>
          </div>
          <span className={`text-xs font-bold capitalize ${
            overallSentiment==='bullish'?'text-green-400':overallSentiment==='bearish'?'text-red-400':'text-gray-400'
          }`}>
            {overallSentiment}
          </span>
          <span className="text-xs text-gray-500">{news.length} articles</span>
        </div>
      )}

      {/* Articles */}
      {news.length === 0 && !loading ? (
        <div className="text-center py-12 text-gray-500">
          <p className="text-3xl mb-2">📰</p>
          <p>No news found. Start the bot or check your API keys.</p>
        </div>
      ) : (
        <div className="space-y-2 max-h-[560px] overflow-y-auto pr-1">
          {news.map((article, i) => <NewsCard key={i} article={article} />)}
        </div>
      )}
    </div>
  )
}

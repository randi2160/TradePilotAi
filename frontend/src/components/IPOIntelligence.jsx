import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { Bell, ExternalLink, RefreshCw, TrendingUp, Calendar, Star } from 'lucide-react'

const HYPE_STARS = (score) => '⭐'.repeat(Math.min(score, 5))

const SECTOR_COLORS = {
  'AI/Tech':   'bg-purple-900/30 text-purple-400 border-purple-800/40',
  'Fintech':   'bg-blue-900/30   text-blue-400   border-blue-800/40',
  'Space/Tech':'bg-indigo-900/30 text-indigo-400  border-indigo-800/40',
  'Social':    'bg-pink-900/30   text-pink-400    border-pink-800/40',
  'Retail':    'bg-orange-900/30 text-orange-400  border-orange-800/40',
  'default':   'bg-dark-700      text-gray-400    border-dark-600',
}

function sectorColor(sector) {
  return SECTOR_COLORS[sector] ?? SECTOR_COLORS.default
}

function DaysChip({ days }) {
  if (days === null || days === undefined) return null
  if (days < 0)  return <span className="text-xs bg-dark-600 text-gray-500 px-2 py-0.5 rounded-full">Past</span>
  if (days === 0) return <span className="text-xs bg-green-900/40 text-green-400 border border-green-800/40 px-2 py-0.5 rounded-full font-bold animate-pulse">TODAY</span>
  if (days <= 7)  return <span className="text-xs bg-yellow-900/40 text-yellow-400 border border-yellow-800/40 px-2 py-0.5 rounded-full font-bold">In {days}d</span>
  return <span className="text-xs bg-dark-700 text-gray-400 border border-dark-600 px-2 py-0.5 rounded-full">In {days}d</span>
}

function IPOCard({ ipo }) {
  const hasSymbol = ipo.symbol && ipo.symbol !== 'N/A'
  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-4 hover:border-dark-500 transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-white">{ipo.name}</span>
            {hasSymbol && (
              <span className="text-xs bg-brand-500/20 text-brand-400 border border-brand-500/30 px-1.5 py-0.5 rounded font-mono font-bold">
                ${ipo.symbol}
              </span>
            )}
            {ipo.sector && (
              <span className={`text-xs px-1.5 py-0.5 rounded-full border ${sectorColor(ipo.sector)}`}>
                {ipo.sector}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 mt-1 flex-wrap">
            {ipo.date && (
              <span className="text-xs text-gray-500 flex items-center gap-1">
                <Calendar size={10}/> {ipo.date}
              </span>
            )}
            {ipo.exchange && (
              <span className="text-xs text-gray-500">{ipo.exchange}</span>
            )}
            {(ipo.price_low || ipo.price_high) && (
              <span className="text-xs text-gray-400">
                💰 ${ipo.price_low}{ipo.price_high ? ` – $${ipo.price_high}` : ''}
              </span>
            )}
          </div>
          {ipo.notes && (
            <p className="text-xs text-gray-500 mt-1">{ipo.notes}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 flex-shrink-0">
          <DaysChip days={ipo.days_until}/>
          {ipo.hype_score > 0 && (
            <span className="text-xs" title={`Hype score: ${ipo.hype_score}/5`}>
              {HYPE_STARS(ipo.hype_score)}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

function NewsCard({ article }) {
  const ago = () => {
    const mins = Math.floor((Date.now() - new Date(article.published)) / 60000)
    if (mins < 60)   return `${mins}m ago`
    if (mins < 1440) return `${Math.floor(mins/60)}h ago`
    return `${Math.floor(mins/1440)}d ago`
  }
  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-3 hover:border-dark-500 transition-colors">
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white leading-snug">{article.title}</p>
          {article.summary && (
            <p className="text-xs text-gray-400 mt-1 line-clamp-2">{article.summary}</p>
          )}
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-xs text-gray-600">{article.source}</span>
            <span className="text-xs text-gray-600">·</span>
            <span className="text-xs text-gray-600">{ago()}</span>
            {article.symbols?.length > 0 && (
              <span className="text-xs text-brand-500">{article.symbols.join(', ')}</span>
            )}
          </div>
        </div>
        {article.url && article.url !== 'https://reuters.com' && (
          <a href={article.url} target="_blank" rel="noopener noreferrer"
            className="flex-shrink-0 text-gray-600 hover:text-brand-400 transition-colors">
            <ExternalLink size={14}/>
          </a>
        )}
      </div>
    </div>
  )
}

export default function IPOIntelligence() {
  const [tab,      setTab]      = useState('upcoming')
  const [calendar, setCalendar] = useState(null)
  const [news,     setNews]     = useState([])
  const [preIpo,   setPreIpo]   = useState([])
  const [loading,  setLoading]  = useState(true)
  const [checking, setChecking] = useState({})

  useEffect(() => { loadAll() }, [])

  async function loadAll() {
    setLoading(true)
    try {
      const [calRes, newsRes] = await Promise.allSettled([
        api.get('/ipo/calendar').then(r => r.data),
        api.get('/ipo/news').then(r => r.data),
      ])
      if (calRes.status  === 'fulfilled') setCalendar(calRes.value)
      if (newsRes.status === 'fulfilled') setNews(newsRes.value)
      setPreIpo(calRes.status === 'fulfilled' ? calRes.value.pre_ipo ?? [] : [])
    } catch {}
    finally { setLoading(false) }
  }

  async function checkSymbol(name) {
    setChecking(c => ({ ...c, [name]: true }))
    try {
      const r = await api.get(`/ipo/check/${encodeURIComponent(name)}`)
      if (r.data.listed) {
        alert(`🎉 ${name} is now trading as $${r.data.symbol}!`)
      } else {
        alert(`${name} is not yet listed on exchanges`)
      }
    } catch {}
    finally { setChecking(c => ({ ...c, [name]: false })) }
  }

  const upcoming = calendar?.upcoming ?? []
  const recent   = calendar?.recent   ?? []

  const TABS = [
    { id:'upcoming', label:`📅 Upcoming (${upcoming.length})`   },
    { id:'preipo',   label:`🔮 Pre-IPO Watch (${preIpo.length})` },
    { id:'recent',   label:`📊 Recent (${recent.length})`       },
    { id:'news',     label:`📰 IPO News (${news.length})`       },
  ]

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="bg-dark-800 border border-dark-600 rounded-2xl p-5">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h2 className="font-black text-white text-lg flex items-center gap-2">
              🚀 IPO Intelligence
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Track upcoming IPOs, pre-IPO companies, and be first to know when they list
            </p>
          </div>
          <button onClick={loadAll} disabled={loading}
            className="p-2 bg-dark-700 rounded-lg hover:bg-dark-600 transition-colors">
            <RefreshCw size={14} className={`text-gray-400 ${loading ? 'animate-spin' : ''}`}/>
          </button>
        </div>

        {/* Quick stats */}
        {calendar && (
          <div className="grid grid-cols-3 gap-3 mt-3">
            <div className="bg-dark-700 rounded-xl p-2.5 text-center">
              <p className="text-lg font-black text-brand-500">{upcoming.length}</p>
              <p className="text-xs text-gray-500">Upcoming</p>
            </div>
            <div className="bg-dark-700 rounded-xl p-2.5 text-center">
              <p className="text-lg font-black text-yellow-400">{preIpo.length}</p>
              <p className="text-xs text-gray-500">Pre-IPO Watch</p>
            </div>
            <div className="bg-dark-700 rounded-xl p-2.5 text-center">
              <p className="text-lg font-black text-green-400">{recent.length}</p>
              <p className="text-xs text-gray-500">Recent IPOs</p>
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex gap-2 flex-wrap">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
              tab === t.id ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}>{t.label}</button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-12 text-gray-500">
          <RefreshCw size={24} className="animate-spin mx-auto mb-2"/>
          <p>Loading IPO data…</p>
        </div>
      ) : (
        <>
          {/* Upcoming IPOs */}
          {tab === 'upcoming' && (
            <div className="space-y-3">
              {upcoming.length === 0 ? (
                <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-2xl text-gray-500">
                  <p className="text-3xl mb-2">📅</p>
                  <p>No upcoming IPOs found — check back soon</p>
                </div>
              ) : upcoming.map((ipo, i) => (
                <IPOCard key={i} ipo={ipo}/>
              ))}
            </div>
          )}

          {/* Pre-IPO Watch */}
          {tab === 'preipo' && (
            <div className="space-y-3">
              <div className="bg-yellow-900/20 border border-yellow-800/40 rounded-xl p-3">
                <p className="text-xs text-yellow-400">
                  🔮 These companies don't have ticker symbols yet. We'll alert you the moment they start trading.
                  Click "Check Now" to see if any have recently listed.
                </p>
              </div>
              {preIpo.map((company, i) => (
                <div key={i} className="bg-dark-800 border border-dark-600 rounded-xl p-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-brand-500/20 flex items-center justify-center text-brand-400 font-black text-sm flex-shrink-0">
                      {company.name.slice(0,2).toUpperCase()}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <p className="font-bold text-white">{company.name}</p>
                        <span className={`text-xs px-1.5 py-0.5 rounded-full border ${sectorColor(company.sector)}`}>
                          {company.sector}
                        </span>
                        <span className="ml-auto text-xs bg-dark-600 text-gray-500 px-2 py-0.5 rounded-full">No symbol yet</span>
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5">{company.notes}</p>
                    </div>
                    <button onClick={() => checkSymbol(company.name)}
                      disabled={checking[company.name]}
                      className="text-xs bg-brand-500/20 hover:bg-brand-500/40 text-brand-400 border border-brand-500/30 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50 flex-shrink-0">
                      {checking[company.name] ? '⟳' : 'Check Now'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Recent IPOs */}
          {tab === 'recent' && (
            <div className="space-y-3">
              {recent.length === 0 ? (
                <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-2xl text-gray-500">
                  <p className="text-3xl mb-2">📊</p>
                  <p>No recent IPOs in the database yet</p>
                </div>
              ) : recent.map((ipo, i) => (
                <IPOCard key={i} ipo={ipo}/>
              ))}
            </div>
          )}

          {/* IPO News */}
          {tab === 'news' && (
            <div className="space-y-3">
              {news.length === 0 ? (
                <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-2xl text-gray-500">
                  <p className="text-3xl mb-2">📰</p>
                  <p>No IPO news found</p>
                </div>
              ) : news.map((article, i) => (
                <NewsCard key={i} article={article}/>
              ))}
            </div>
          )}
        </>
      )}

      {/* Disclaimer */}
      <div className="text-center text-xs text-gray-600 pb-2">
        IPO data sourced from public calendars. Dates and prices are estimates and subject to change.
        Not financial advice.
      </div>
    </div>
  )
}

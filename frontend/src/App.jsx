import { useState, useEffect, useRef, lazy, Suspense } from 'react'
import { AuthProvider, useAuth, api } from './hooks/useAuth'
import { useWebSocket }               from './hooks/useWebSocket'
import { getTrades, addSymbol, getDashboardToday } from './services/api'
import { Search } from 'lucide-react'
// Eager — needed on first render
import LoginPage            from './components/LoginPage'
import Dashboard            from './components/Dashboard'
import LiveTicker           from './components/LiveTicker'
import AlertBell, { AIRefreshBadge } from './components/AlertBell'
// Lazy — loaded on tab click
const ChartView            = lazy(() => import('./components/ChartView'))
const BotControls          = lazy(() => import('./components/BotControls'))
const TradeLog             = lazy(() => import('./components/TradeLog'))
const Signals              = lazy(() => import('./components/Signals'))
const PortfolioChart       = lazy(() => import('./components/PortfolioChart'))
const NewsPanel            = lazy(() => import('./components/NewsPanel'))
const MarketScanner        = lazy(() => import('./components/MarketScanner'))
const Settings             = lazy(() => import('./components/Settings'))
const AIAdvisor            = lazy(() => import('./components/AIAdvisor'))
const AutoManualToggle     = lazy(() => import('./components/AutoManualToggle'))
const UserProfile          = lazy(() => import('./components/UserProfile'))
const ManualTrade          = lazy(() => import('./components/ManualTrade'))
const Performance          = lazy(() => import('./components/Performance'))
const PeakBounce           = lazy(() => import('./components/PeakBounce'))
const DualEngineDashboard  = lazy(() => import('./components/DualEngineDashboard'))
const GoalSetting          = lazy(() => import('./components/GoalSetting'))
const DailyReport          = lazy(() => import('./components/DailyReport'))
const PnLHistory           = lazy(() => import('./components/PnLHistory'))
const MarketIntelligence   = lazy(() => import('./components/MarketIntelligence'))
const BrokerManager        = lazy(() => import('./components/BrokerManager'))
const ActivityLog          = lazy(() => import('./components/ActivityLog'))
const SocialFeed           = lazy(() => import('./components/SocialFeed'))
const CopyTrading          = lazy(() => import('./components/CopyTrading'))
const IPOIntelligence      = lazy(() => import('./components/IPOIntelligence'))
const AdminPanel           = lazy(() => import('./components/AdminPanel'))
const SafetyControls       = lazy(() => import('./components/SafetyControls'))
const ConsentFlow          = lazy(() => import('./components/ConsentFlow'))
const SymbolPage           = lazy(() => import('./components/SymbolPage'))
const StockBoard           = lazy(() => import('./components/StockBoard'))
const BillingTab           = lazy(() => import('./components/BillingTab'))
const DailyAdvisor         = lazy(() => import('./components/DailyAdvisor'))
const AlpacaAccountPanel   = lazy(() => import('./components/AlpacaAccountPanel'))
const CryptoBounceAnalysis = lazy(() => import('./components/CryptoBounceAnalysis'))
// DailyPicksMini needs a separate lazy chunk since it's a named export
const DailyPicksMini       = lazy(() => import('./components/DailyAdvisor').then(m => ({ default: m.DailyPicksMini })))

const TABS = [
  { id: 'dashboard',   label: '📊', full: 'Dashboard'    },
  { id: 'daily',       label: '🎯', full: 'Daily Advisor' },
  { id: 'ai',          label: '🧠', full: 'AI Advisor'    },
  { id: 'social',      label: '👥', full: 'Social'        },
  { id: 'copy',        label: '📋', full: 'Copy Trading'  },
  { id: 'ipo',         label: '🚀', full: 'IPO Watch'     },
  { id: 'portfolio',   label: '💰', full: 'Portfolio'     },
  { id: 'goals',       label: '🎯', full: 'Goals'         },
  { id: 'report',      label: '📄', full: 'Daily Report'  },
  { id: 'history',     label: '📈', full: 'P&L History'   },
  { id: 'activity',    label: '📡', full: 'Activity'      },
  { id: 'intel',       label: '🔬', full: 'Intelligence'  },
  { id: 'performance', label: '🏆', full: 'Performance'   },
  { id: 'bounce',      label: '📉', full: 'Peak Bounce'   },
  { id: 'crypto-bounce', label: '🔄', full: 'Crypto Bounce' },
  { id: 'dual',        label: '⚡', full: 'Dual Engine'   },
  { id: 'chart',       label: '📈', full: 'Charts'        },
  { id: 'scanner',     label: '🔍', full: 'Scanner'       },
  { id: 'news',        label: '📰', full: 'News'          },
  { id: 'signals',     label: '🤖', full: 'Signals'       },
  { id: 'trades',      label: '📋', full: 'Trades'        },
  { id: 'manual',      label: '✋', full: 'Manual Trade'  },
  { id: 'mode',        label: '🔀', full: 'Auto/Manual'   },
  { id: 'bot',         label: '⚙️', full: 'Bot'           },
  { id: 'safety',      label: '🛡️', full: 'Safety'        },
  { id: 'broker',      label: '🔌', full: 'My Broker'     },
  { id: 'settings',    label: '🛠️', full: 'Settings'      },
  { id: 'profile',     label: '👤', full: 'Profile'       },
  { id: 'billing',     label: '💳', full: 'Billing'       },
  { id: 'admin',       label: '🛡️', full: 'Admin'         },
]

function TradingApp() {
  const { user, token, loading } = useAuth()
  const { data, connected }      = useWebSocket(token)
  const [tab,          setTab]          = useState('dashboard')
  const [needsConsent, setNeedsConsent] = useState(null)
  const [trades,       setTrades]       = useState([])
  const [activeSymbol, setActiveSymbol] = useState(null)
  const [boardSymbol,  setBoardSymbol]  = useState(null)
  // Persistent daily P&L — survives backend restart because it reads from the
  // `daily_pnl` table rather than the bot's in-memory tracker.
  const [dayPnl,       setDayPnl]       = useState(null)
  // Global search
  const [searchQuery,  setSearchQuery]  = useState('')
  const [searchOpen,   setSearchOpen]   = useState(false)
  const searchRef = useRef(null)

  function handleSearchSubmit(e) {
    e.preventDefault()
    const sym = searchQuery.trim().toUpperCase().replace('$', '')
    if (!sym) return
    // Open symbol page + auto-add to watchlist
    addSymbol(sym).catch(() => {})
    setActiveSymbol(sym)
    setSearchQuery('')
    setSearchOpen(false)
  }

  // Close search on click outside
  useEffect(() => {
    function handleClickOutside(e) {
      if (searchRef.current && !searchRef.current.contains(e.target)) setSearchOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  useEffect(() => {
    const handler = (e) => setTab(e.detail)
    window.addEventListener('navigate', handler)
    const symHandler = (e) => setActiveSymbol(e.detail)
    window.addEventListener('openSymbol', symHandler)
    const boardHandler = (e) => { setBoardSymbol(e.detail); setActiveSymbol(null) }
    window.addEventListener('openSymbolFullPage', boardHandler)
    return () => {
      window.removeEventListener('navigate', handler)
      window.removeEventListener('openSymbol', symHandler)
      window.removeEventListener('openSymbolFullPage', boardHandler)
    }
  }, [])

  useEffect(() => {
    if (!token) return
    getTrades().then(setTrades).catch(() => {})
    const iv = setInterval(() => getTrades().then(setTrades).catch(() => {}), 10000)
    return () => clearInterval(iv)
  }, [token])

  // Poll today's persisted P&L — independent of whether the bot is running.
  useEffect(() => {
    if (!token) return
    const load = () => getDashboardToday().then(setDayPnl).catch(() => {})
    load()
    const iv = setInterval(load, 5000)
    return () => clearInterval(iv)
  }, [token])

  // Compliance check — gate the dashboard behind required consents.
  //
  // Admin users (platform owners) bypass the flow — they wrote the docs,
  // forcing them to click through in dev is wasted friction. Every other
  // user has to accept risk_disclosure + terms_of_service + auto_trading
  // before the dashboard renders.
  //
  // If the backend route fails for any reason we fail OPEN (let them in)
  // rather than locking everyone out of their own data. The trade-off is
  // conscious: availability > strict compliance on a transient error.
  useEffect(() => {
    if (!user) return
    if (user.is_admin) {
      setNeedsConsent(false)
      return
    }
    api.get('/compliance/status')
      .then(r => setNeedsConsent(!r.data?.onboarding_complete))
      .catch(() => setNeedsConsent(false)) // if route fails, don't block dashboard
  }, [user?.id, user?.is_admin])

  if (loading) return (
    <div className="min-h-screen bg-dark-900 flex items-center justify-center">
      <div className="text-center">
        <img src="/logo-mark.png" alt="Morviq AI" className="w-16 h-16 mx-auto mb-3 animate-pulse object-contain"/>
        <p className="text-gray-400">Loading Morviq AI…</p>
      </div>
    </div>
  )

  if (!user) return <LoginPage />

  if (needsConsent === null) return (
    <div className="min-h-screen bg-dark-900 flex items-center justify-center">
      <div className="animate-spin w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full"/>
    </div>
  )

  if (needsConsent) return (
    <Suspense fallback={<div className="min-h-screen bg-dark-900 flex items-center justify-center"><div className="animate-spin w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full"/></div>}>
      <ConsentFlow user={user} onComplete={() => setNeedsConsent(false)}/>
    </Suspense>
  )

  // Full-page stock board — takes over entire screen
  if (boardSymbol) return (
    <Suspense fallback={<div className="min-h-screen bg-dark-900 flex items-center justify-center"><div className="animate-spin w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full"/></div>}>
      <StockBoard
        symbol={boardSymbol}
        currentUserId={user?.id}
        onBack={() => setBoardSymbol(null)}
      />
    </Suspense>
  )

  const pnl         = data?.total_pnl ?? data?.realized_pnl ?? 0
  const cryptoPnl   = data?.crypto_pnl ?? 0
  const running     = data?.bot_status === 'running'
  const capital     = user?.capital ?? data?.settings?.capital ?? 5000
  const watchlist   = data?.settings?.watchlist ?? []
  const signals     = data?.signals ?? []
  const pending     = data?.pending_trades ?? []
  const tradingMode = data?.trading_mode ?? 'auto'
  // Prefer persisted DailyPnL values so the header survives a backend restart.
  // Falls back to WebSocket tracker if DB snapshot hasn't loaded yet.
  const realizedToday   = parseFloat(dayPnl?.realized_pnl   ?? data?.realized_pnl ?? 0) || 0
  const unrealizedToday = parseFloat(dayPnl?.unrealized_pnl ?? 0) || 0
  const totalToday      = parseFloat(dayPnl?.total_pnl      ?? (realizedToday + unrealizedToday)) || 0
  const equity          = parseFloat(dayPnl?.ending_equity  ?? (capital + pnl)) || (capital + pnl)

  async function handleAddToWatchlist(symbol) {
    try { await addSymbol(symbol) } catch {}
  }

  return (
    <div className="min-h-screen bg-dark-900 text-white flex flex-col">

      {/* Header */}
      <header className="bg-dark-800 border-b border-dark-600 px-4 py-2.5 flex items-center gap-3 flex-shrink-0">
        <img src="/logo-mark.png" alt="Morviq AI" className="w-10 h-10 flex-shrink-0 object-contain"/>
        <div className="hidden sm:block">
          <img src="/logo.png" alt="Morviq AI — AI That Trades. Wealth That Grows." className="h-10 w-auto object-contain"/>
        </div>

        {/* Global symbol search */}
        <div ref={searchRef} className="relative">
          <form onSubmit={handleSearchSubmit} className="flex items-center">
            <div className={`flex items-center bg-dark-700 border rounded-lg transition-all ${searchOpen ? 'border-brand-500 w-44 sm:w-56' : 'border-dark-600 w-9 sm:w-44'}`}>
              <button type="button" onClick={() => { setSearchOpen(true); setTimeout(() => searchRef.current?.querySelector('input')?.focus(), 50) }}
                className="flex-shrink-0 w-9 h-8 flex items-center justify-center text-gray-400 hover:text-brand-400">
                <Search size={15}/>
              </button>
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
                onFocus={() => setSearchOpen(true)}
                placeholder="Ticker…"
                maxLength={10}
                className={`bg-transparent text-sm text-white placeholder-gray-500 outline-none pr-2 py-1 ${searchOpen ? 'w-full' : 'hidden sm:block w-full'}`}
              />
            </div>
          </form>
        </div>

        {/* Today settled (realized) — persists across restart via DailyPnL table */}
        <div title="Realized P&L — settled closed trades today"
          className={`px-2.5 py-1 rounded-full text-xs font-bold flex items-center gap-1 ${realizedToday >= 0 ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
          <span className="text-[10px] opacity-70 uppercase tracking-wide hidden sm:inline">Today</span>
          <span>{realizedToday >= 0 ? '+' : ''}${realizedToday.toFixed(2)}</span>
          {cryptoPnl !== 0 && (
            <span className="text-[10px] ml-1 opacity-70">
              (₿{cryptoPnl >= 0 ? '+' : ''}{cryptoPnl.toFixed(2)})
            </span>
          )}
        </div>
        {/* Unrealized (open positions floating) — only show when non-zero */}
        {unrealizedToday !== 0 && (
          <div title="Unrealized P&L \u2014 open positions, not yet closed"
            className={`px-2.5 py-1 rounded-full text-xs font-bold flex items-center gap-1 border ${unrealizedToday >= 0 ? 'bg-green-900/20 text-green-400 border-green-800/40' : 'bg-red-900/20 text-red-400 border-red-800/40'}`}>
            <span className="text-[10px] opacity-70 uppercase tracking-wide hidden sm:inline">Unreal</span>
            <span>{unrealizedToday >= 0 ? '+' : ''}${unrealizedToday.toFixed(2)}</span>
          </div>
        )}
        <div className="hidden md:flex items-center gap-1 bg-dark-700 px-3 py-1 rounded-full text-xs text-gray-300"
          title="Current portfolio equity (from Alpaca)">
          💼 ${equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}
        </div>
        <div className={`hidden sm:flex items-center gap-1 px-2 py-1 rounded-full text-xs font-bold ${tradingMode === 'auto' ? 'bg-brand-500/20 text-brand-400 border border-brand-500/40' : 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/40'}`}>
          {tradingMode === 'auto' ? '🤖 AUTO' : '👤 MANUAL'}
        </div>
        {pending.length > 0 && (
          <button onClick={() => setTab('mode')} className="flex items-center gap-1 bg-yellow-500 text-dark-900 text-xs font-bold px-2 py-1 rounded-full animate-pulse">
            ⚡ {pending.length} pending
          </button>
        )}
        <AlertBell userTier={user?.is_admin ? 'admin' : (user?.subscription_tier || 'free')}/>
        <button onClick={() => setTab('profile')} className="ml-auto w-8 h-8 rounded-full bg-brand-500 flex items-center justify-center text-dark-900 text-xs font-black hover:bg-brand-400 transition-colors">
          {user.avatar_initials ?? user.email.slice(0,2).toUpperCase()}
        </button>
        <AIRefreshBadge tier={user?.is_admin ? 'admin' : (user?.subscription_tier || 'free')} compact={true}/>
        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full ${!connected ? 'bg-red-500' : running ? 'bg-green-400 animate-pulse' : 'bg-yellow-400'}`}/>
          <span className="text-xs text-gray-400 hidden sm:block">
            {!connected ? 'Offline' : running ? `LIVE · ${(data?.mode ?? '').toUpperCase()}` : 'Idle'}
          </span>
        </div>
        {data?.mode === 'live' && (
          <span className="text-xs px-2 py-1 rounded font-bold bg-red-900 text-red-300 animate-pulse">⚠️ LIVE $</span>
        )}
      </header>

      {/* Progress bar */}
      {data && (
        <div className="bg-dark-800 border-b border-dark-600 px-4 py-1.5">
          <div className="flex items-center gap-3 max-w-screen-xl mx-auto">
            <span className="text-xs text-gray-500 hidden sm:block">Target</span>
            <div className="flex-1 bg-dark-700 rounded-full h-1.5 overflow-hidden">
              <div className="h-1.5 rounded-full transition-all duration-700" style={{ width: `${Math.min(data.progress_pct ?? 0, 100)}%`, background: (data.progress_pct ?? 0) >= 100 ? 'linear-gradient(90deg,#00d4aa,#00b894)' : 'linear-gradient(90deg,#6366f1,#00d4aa)' }}/>
            </div>
            <span className="text-xs font-mono text-gray-300 whitespace-nowrap">
              ${(data.realized_pnl ?? 0).toFixed(2)} / ${user?.daily_target_max ?? 250}
            </span>
          </div>
        </div>
      )}

      {/* Live Ticker */}
      <LiveTicker watchlist={watchlist.length ? watchlist : []} />

      {/* Tabs */}
      <nav className="bg-dark-800 border-b border-dark-600 overflow-x-auto flex-shrink-0">
        <div className="flex min-w-max px-2">
          {TABS.filter(t => t.id !== 'admin' || user.is_admin).map(t => {
            let badge = null
            if (t.id === 'trades'  && trades.length > 0)  badge = trades.length
            if (t.id === 'signals' && signals.filter(s => s.signal !== 'HOLD').length > 0) badge = signals.filter(s => s.signal !== 'HOLD').length
            if (t.id === 'mode'    && pending.length > 0)  badge = `${pending.length}!`
            return (
              <button key={t.id} onClick={() => setTab(t.id)}
                className={`flex items-center gap-1 px-3 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${tab === t.id ? 'border-brand-500 text-brand-500' : 'border-transparent text-gray-400 hover:text-gray-200'}`}>
                <span>{t.label}</span>
                <span className="hidden sm:inline">{t.full}</span>
                {badge != null && (
                  <span className={`text-xs px-1.5 rounded-full font-bold ml-0.5 ${String(badge).includes('!') ? 'bg-yellow-500 text-dark-900' : 'bg-brand-500 text-dark-900'}`}>{badge}</span>
                )}
              </button>
            )
          })}
        </div>
      </nav>

      {/* Content */}
      <main className="flex-1 max-w-screen-xl w-full mx-auto p-4 md:p-6 overflow-auto">
       <Suspense fallback={<div className="flex items-center justify-center py-20"><div className="animate-spin w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full"/></div>}>
        {tab === 'dashboard'   && (
          <div className="space-y-5">
            {/* Chart full-width on top */}
            <Suspense fallback={<div className="h-48 bg-dark-800 rounded-2xl animate-pulse"/>}>
              <PortfolioChart capital={capital}/>
            </Suspense>

            {/* Alpaca account mirror + Daily picks, side by side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <Suspense fallback={<div className="h-32 bg-dark-800 rounded-2xl animate-pulse"/>}>
                <AlpacaAccountPanel/>
              </Suspense>
              <div className="bg-dark-800 border border-dark-600 rounded-2xl p-4">
                <Suspense fallback={<div className="h-24 animate-pulse"/>}>
                  <DailyPicksMini onNavigate={setTab}/>
                </Suspense>
              </div>
            </div>

            {/* Main dashboard stats, engines, signals, positions */}
            <Dashboard data={data}/>
          </div>
        )}
        {tab === 'daily'       && <DailyAdvisor/>}
        {tab === 'ai'          && <AIAdvisor           onAddToWatchlist={handleAddToWatchlist}/>}
        {tab === 'social'      && <SocialFeed           currentUserId={user?.id}/>}
        {tab === 'copy'        && <CopyTrading/>}
        {tab === 'ipo'         && <IPOIntelligence/>}
        {tab === 'admin'       && user.is_admin && <AdminPanel/>}
        {tab === 'safety'      && <SafetyControls botStatus={data?.bot_status ?? 'stopped'} onStatusChange={() => {}}/>}
        {tab === 'portfolio'   && <PortfolioChart       capital={capital}/>}
        {tab === 'goals'       && <GoalSetting          capital={capital}/>}
        {tab === 'report'      && <DailyReport/>}
        {tab === 'history'     && <PnLHistory/>}
        {tab === 'activity'    && <ActivityLog/>}
        {tab === 'intel'       && <MarketIntelligence/>}
        {tab === 'performance' && <Performance/>}
        {tab === 'bounce'      && <PeakBounce           capital={capital}/>}
        {tab === 'crypto-bounce' && <CryptoBounceAnalysis />}
        {tab === 'dual'        && <DualEngineDashboard  capital={capital}/>}
        {tab === 'chart'       && <ChartView            signals={signals}/>}
        {tab === 'scanner'     && <MarketScanner        onAddToWatchlist={handleAddToWatchlist}/>}
        {tab === 'news'        && <NewsPanel            watchlist={watchlist}/>}
        {tab === 'signals'     && <Signals              signals={signals}/>}
        {tab === 'trades'      && <TradeLog             trades={trades}/>}
        {tab === 'manual'      && <ManualTrade          capital={capital} onTrade={() => getTrades().then(setTrades)}/>}
        {tab === 'mode'        && <AutoManualToggle     data={data}/>}
        {tab === 'bot'         && <BotControls          data={data} user={user}/>}
        {tab === 'broker'      && <BrokerManager/>}
        {tab === 'settings'    && <Settings/>}
        {tab === 'profile'     && <UserProfile/>}
        {tab === 'billing'     && <BillingTab/>}
       </Suspense>
      </main>

      <footer className="text-center py-2 text-xs text-gray-700 border-t border-dark-800">
        Morviq AI v4 · Secured · PostgreSQL · GPT-4 · Not financial advice
      </footer>

      {/* Symbol Board Overlay */}
      {activeSymbol && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
          onClick={e => e.target === e.currentTarget && setActiveSymbol(null)}>
          <div className="w-full max-w-2xl h-[85vh] flex flex-col">
            <SymbolPage
              symbol={activeSymbol}
              currentUserId={user?.id}
              onClose={() => setActiveSymbol(null)}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <TradingApp />
    </AuthProvider>
  )
}
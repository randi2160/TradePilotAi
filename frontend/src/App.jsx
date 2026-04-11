import { useState, useEffect } from 'react'
import { AuthProvider, useAuth } from './hooks/useAuth'
import { useWebSocket }          from './hooks/useWebSocket'
import { getTrades, addSymbol }  from './services/api'

import LoginPage       from './components/LoginPage'
import Dashboard       from './components/Dashboard'
import ChartView       from './components/ChartView'
import BotControls     from './components/BotControls'
import TradeLog        from './components/TradeLog'
import Signals         from './components/Signals'
import PortfolioChart  from './components/PortfolioChart'
import NewsPanel       from './components/NewsPanel'
import MarketScanner   from './components/MarketScanner'
import Settings        from './components/Settings'
import AIAdvisor       from './components/AIAdvisor'
import AutoManualToggle from './components/AutoManualToggle'
import UserProfile     from './components/UserProfile'
import ManualTrade     from './components/ManualTrade'
import Performance     from './components/Performance'
import PeakBounce           from './components/PeakBounce'
import DualEngineDashboard  from './components/DualEngineDashboard'
import GoalSetting          from './components/GoalSetting'
import DailyReport          from './components/DailyReport'
import MarketIntelligence   from './components/MarketIntelligence'
import LiveTicker           from './components/LiveTicker'
import BrokerManager        from './components/BrokerManager'
import ActivityLog          from './components/ActivityLog'

const TABS = [
  { id: 'dashboard',   label: '📊', full: 'Dashboard'   },
  { id: 'ai',          label: '🧠', full: 'AI Advisor'   },
  { id: 'portfolio',   label: '💰', full: 'Portfolio'    },
  { id: 'goals',       label: '🎯', full: 'Goals'        },
  { id: 'report',      label: '📄', full: 'Daily Report' },
  { id: 'activity',    label: '📡', full: 'Activity Log' },
  { id: 'intel',       label: '🔬', full: 'Intelligence' },
  { id: 'performance', label: '🏆', full: 'Performance'  },
  { id: 'bounce',      label: '📉', full: 'Peak Bounce'  },
  { id: 'dual',        label: '⚡', full: 'Dual Engine'  },
  { id: 'chart',       label: '📈', full: 'Charts'       },
  { id: 'scanner',     label: '🔍', full: 'Scanner'      },
  { id: 'news',        label: '📰', full: 'News'         },
  { id: 'signals',     label: '🤖', full: 'Signals'      },
  { id: 'trades',      label: '📋', full: 'Trades'       },
  { id: 'manual',      label: '✋', full: 'Manual Trade' },
  { id: 'mode',        label: '⚡', full: 'Auto/Manual'  },
  { id: 'bot',         label: '⚙️', full: 'Bot'          },
  { id: 'broker',      label: '🔌', full: 'My Broker'    },
  { id: 'settings',    label: '🛠️', full: 'Settings'     },
  { id: 'profile',     label: '👤', full: 'Profile'      },
]

function TradingApp() {
  const { user, token, loading } = useAuth()
  const { data, connected }      = useWebSocket(token)
  const [tab,    setTab]         = useState('dashboard')
  const [trades, setTrades]      = useState([])

  useEffect(() => {
    const handler = (e) => setTab(e.detail)
    window.addEventListener('navigate', handler)
    return () => window.removeEventListener('navigate', handler)
  }, [])

  useEffect(() => {
    if (!token) return
    getTrades().then(setTrades).catch(() => {})
    const iv = setInterval(() => getTrades().then(setTrades).catch(() => {}), 10000)
    return () => clearInterval(iv)
  }, [token])

  if (loading) {
    return (
      <div className="min-h-screen bg-dark-900 flex items-center justify-center">
        <div className="text-center">
          <div className="text-4xl mb-3 animate-pulse">📈</div>
          <p className="text-gray-400">Loading AutoTrader Pro…</p>
        </div>
      </div>
    )
  }

  if (!user) return <LoginPage />

  const pnl         = data?.total_pnl ?? data?.realized_pnl ?? 0
  const running     = data?.bot_status === 'running'
  const capital     = user?.capital ?? data?.settings?.capital ?? 5000
  const watchlist   = data?.settings?.watchlist ?? []
  const signals     = data?.signals ?? []
  const pending     = data?.pending_trades ?? []
  const tradingMode = data?.trading_mode ?? 'auto'
  const equity      = capital + pnl

  async function handleAddToWatchlist(symbol) {
    try { await addSymbol(symbol) } catch {}
  }

  return (
    <div className="min-h-screen bg-dark-900 text-white flex flex-col">

      {/* Header */}
      <header className="bg-dark-800 border-b border-dark-600 px-4 py-2.5 flex items-center gap-3 flex-shrink-0">
        <span className="text-xl">📈</span>
        <div className="hidden sm:block">
          <h1 className="font-black text-white leading-none text-sm">AutoTrader Pro</h1>
          <p className="text-xs text-gray-500">GPT-4 · AI · Alpaca · PostgreSQL</p>
        </div>
        <div className={`px-3 py-1 rounded-full text-sm font-bold ${pnl >= 0 ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
          {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} today
        </div>
        <div className="hidden md:flex items-center gap-1 bg-dark-700 px-3 py-1 rounded-full text-xs text-gray-300">
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
        <button onClick={() => setTab('profile')} className="ml-auto w-8 h-8 rounded-full bg-brand-500 flex items-center justify-center text-dark-900 text-xs font-black hover:bg-brand-400 transition-colors">
          {user.avatar_initials ?? user.email.slice(0,2).toUpperCase()}
        </button>
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
          {TABS.map(t => {
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
        {tab === 'dashboard'   && <div className="space-y-5"><PortfolioChart capital={capital}/><Dashboard data={data}/></div>}
        {tab === 'ai'          && <AIAdvisor           onAddToWatchlist={handleAddToWatchlist}/>}
        {tab === 'portfolio'   && <PortfolioChart       capital={capital}/>}
        {tab === 'goals'       && <GoalSetting          capital={capital}/>}
        {tab === 'report'      && <DailyReport/>}
        {tab === 'activity'    && <ActivityLog/>}
        {tab === 'intel'       && <MarketIntelligence/>}
        {tab === 'performance' && <Performance/>}
        {tab === 'bounce'      && <PeakBounce           capital={capital}/>}
        {tab === 'dual'        && <DualEngineDashboard  capital={capital}/>}
        {tab === 'chart'       && <ChartView            signals={signals}/>}
        {tab === 'scanner'     && <MarketScanner        onAddToWatchlist={handleAddToWatchlist}/>}
        {tab === 'news'        && <NewsPanel            watchlist={watchlist}/>}
        {tab === 'signals'     && <Signals              signals={signals}/>}
        {tab === 'trades'      && <TradeLog             trades={trades}/>}
        {tab === 'manual'      && <ManualTrade          capital={capital} onTrade={() => getTrades().then(setTrades)}/>}
        {tab === 'mode'        && <AutoManualToggle     data={data}/>}
        {tab === 'bot'         && <BotControls          data={data}/>}
        {tab === 'broker'      && <BrokerManager/>}
        {tab === 'settings'    && <Settings/>}
        {tab === 'profile'     && <UserProfile/>}
      </main>

      <footer className="text-center py-2 text-xs text-gray-700 border-t border-dark-800">
        AutoTrader Pro v4 · Secured · PostgreSQL · GPT-4 · Not financial advice
      </footer>
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

import { useState, useEffect, useCallback } from 'react'
import { api } from '../hooks/useAuth'
import { Bell, X, TrendingUp, TrendingDown, AlertTriangle, CheckCircle, Clock, Zap, ChevronRight } from 'lucide-react'

const ALERT_CONFIG = {
  BUY_SIGNAL:  { icon: TrendingUp,    color: 'text-green-400',  bg: 'bg-green-900/20  border-green-700/50',  label: '🟢 Buy Signal'   },
  SELL_SIGNAL: { icon: TrendingDown,  color: 'text-red-400',    bg: 'bg-red-900/20    border-red-700/50',    label: '🔴 Sell Signal'  },
  STOP_HIT:    { icon: AlertTriangle, color: 'text-red-400',    bg: 'bg-red-900/30    border-red-700/60',    label: '⛔ Stop Alert'   },
  TARGET_HIT:  { icon: CheckCircle,   color: 'text-green-400',  bg: 'bg-green-900/30  border-green-700/60',  label: '✅ Target Hit'   },
  VOLUME:      { icon: Zap,           color: 'text-yellow-400', bg: 'bg-yellow-900/20 border-yellow-700/50', label: '⚡ Volume Spike' },
}

function timeAgo(iso) {
  if (!iso) return ''
  const mins = Math.floor((Date.now() - new Date(iso)) / 60000)
  if (mins < 1)    return 'just now'
  if (mins < 60)   return `${mins}m ago`
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`
  return new Date(iso).toLocaleDateString()
}

function AlertCard({ alert, onRead, onSymbolClick }) {
  const cfg  = ALERT_CONFIG[alert.alert_type] || ALERT_CONFIG.BUY_SIGNAL
  const Icon = cfg.icon
  return (
    <div onClick={() => { onRead(alert.id); onSymbolClick?.(alert.symbol) }}
      className={`p-3.5 border rounded-xl cursor-pointer transition-all hover:opacity-90 ${cfg.bg} ${alert.is_read ? 'opacity-60' : ''}`}>
      <div className="flex items-start gap-3">
        <div className={`w-2 h-2 rounded-full flex-shrink-0 mt-1.5 ${alert.is_read ? 'bg-transparent' : 'bg-brand-500'}`}/>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-xs font-black ${cfg.color}`}>{cfg.label}</span>
            <span className="text-sm font-black text-white">${alert.symbol}</span>
            {alert.confidence && <span className="text-xs text-gray-500">{alert.confidence}% conf</span>}
            <span className="text-xs text-gray-600 ml-auto flex-shrink-0">{timeAgo(alert.timestamp)}</span>
          </div>
          {(alert.entry || alert.exit || alert.stop) && (
            <div className="flex gap-2 mt-1.5 flex-wrap">
              {alert.entry && <span className="text-xs px-2 py-0.5 bg-dark-900/50 rounded font-mono">Entry <span className="text-brand-400 font-bold">${alert.entry}</span></span>}
              {alert.exit  && <span className="text-xs px-2 py-0.5 bg-dark-900/50 rounded font-mono">Target <span className="text-green-400 font-bold">${alert.exit}</span></span>}
              {alert.stop  && <span className="text-xs px-2 py-0.5 bg-dark-900/50 rounded font-mono">Stop <span className="text-red-400 font-bold">${alert.stop}</span></span>}
              {alert.risk_reward && <span className="text-xs text-gray-500 self-center">R:R 1:{parseFloat(alert.risk_reward).toFixed(1)}</span>}
            </div>
          )}
          {alert.reasoning && <p className="text-xs text-gray-400 mt-1 leading-relaxed line-clamp-2">{alert.reasoning}</p>}
        </div>
        <ChevronRight size={14} className="text-gray-600 flex-shrink-0 mt-0.5"/>
      </div>
    </div>
  )
}

export function SymbolAlertView({ symbol, onClose }) {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    api.get(`/alerts/symbol/${symbol}`)
      .then(r => setAlerts(r.data.alerts || []))
      .catch(() => {}).finally(() => setLoading(false))
  }, [symbol])
  const buys  = alerts.filter(a => a.alert_type === 'BUY_SIGNAL')
  const sells = alerts.filter(a => a.alert_type === 'SELL_SIGNAL')
  return (
    <div className="bg-dark-800 border border-dark-600 rounded-2xl overflow-hidden">
      <div className="bg-dark-900 border-b border-dark-700 px-4 py-3 flex items-center gap-3">
        <Bell size={16} className="text-brand-400"/>
        <div className="flex-1">
          <div className="text-sm font-black text-white">${symbol} — Today's Alerts</div>
          <div className="text-xs text-gray-500">{alerts.length} signals · {buys.length} buy · {sells.length} sell</div>
        </div>
        {onClose && <button onClick={onClose} className="p-1 text-gray-500 hover:text-white"><X size={14}/></button>}
      </div>
      {alerts.length > 0 && (
        <div className="grid grid-cols-3 gap-px bg-dark-700 border-b border-dark-700">
          {[
            { label: 'Buy Signals',     val: buys.length,    color: 'text-green-400' },
            { label: 'Sell Signals',    val: sells.length,   color: 'text-red-400'   },
            { label: 'Avg Confidence',  val: Math.round(alerts.reduce((s,a) => s+(a.confidence||0), 0)/alerts.length)+'%', color: 'text-brand-400' },
          ].map(({ label, val, color }) => (
            <div key={label} className="bg-dark-800 p-3 text-center">
              <div className="text-xs text-gray-500">{label}</div>
              <div className={`text-lg font-black ${color}`}>{val}</div>
            </div>
          ))}
        </div>
      )}
      <div className="p-3 max-h-80 overflow-y-auto space-y-2">
        {loading && <div className="text-center py-8 text-gray-600 text-sm">Loading…</div>}
        {!loading && alerts.length === 0 && (
          <div className="text-center py-8 text-gray-600">
            <Bell size={24} className="mx-auto mb-2 opacity-30"/>
            <p className="text-sm">No alerts for ${symbol} today</p>
            <p className="text-xs mt-1">Run AI analysis to generate signals</p>
          </div>
        )}
        {alerts.map((a, i) => <AlertCard key={i} alert={a} onRead={() => {}} onSymbolClick={() => {}}/>)}
      </div>
    </div>
  )
}

export function AIRefreshBadge({ tier, compact = false }) {
  const config = {
    free:       { label: '15 min delay',  color: 'text-gray-400',    bg: 'bg-dark-700 border-dark-600',           icon: Clock },
    subscriber: { label: '1 min refresh', color: 'text-brand-400',   bg: 'bg-brand-500/10 border-brand-500/30',  icon: Zap   },
    pro:        { label: 'Real-time',      color: 'text-green-400',   bg: 'bg-green-900/20 border-green-800/40',  icon: Zap   },
    admin:      { label: 'Real-time',      color: 'text-yellow-400',  bg: 'bg-yellow-900/20 border-yellow-800/40',icon: Zap   },
  }
  const cfg  = config[tier] || config.free
  const Icon = cfg.icon
  if (compact) return (
    <span className={`inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded border ${cfg.bg} ${cfg.color}`}>
      <Icon size={10}/> {cfg.label}
    </span>
  )
  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl border text-xs ${cfg.bg} ${cfg.color}`}>
      <Icon size={12}/>
      <span className="font-medium">AI: {cfg.label}</span>
      {tier === 'free' && (
        <button onClick={() => window.dispatchEvent(new CustomEvent('navigate', { detail: 'billing' }))}
          className="ml-1 text-brand-400 hover:text-brand-300 font-bold underline">
          Upgrade ↗
        </button>
      )}
    </div>
  )
}

export default function AlertBell({ userTier = 'free' }) {
  const [open,    setOpen]    = useState(false)
  const [unread,  setUnread]  = useState(0)
  const [alerts,  setAlerts]  = useState([])
  const [loading, setLoading] = useState(false)
  const [filter,  setFilter]  = useState('all')

  const loadCount = useCallback(async () => {
    try { const r = await api.get('/alerts/count'); setUnread(r.data.unread || 0) } catch {}
  }, [])

  const loadAlerts = useCallback(async () => {
    setLoading(true)
    try { const r = await api.get('/alerts?limit=30'); setAlerts(r.data.alerts || []); setUnread(r.data.unread || 0) }
    catch {} finally { setLoading(false) }
  }, [])

  useEffect(() => { loadCount(); const iv = setInterval(loadCount, 30000); return () => clearInterval(iv) }, [loadCount])
  useEffect(() => { if (open) loadAlerts() }, [open, loadAlerts])

  async function handleRead(id) {
    try { await api.post(`/alerts/read/${id}`); setAlerts(a => a.map(x => x.id===id?{...x,is_read:true}:x)); setUnread(u => Math.max(0,u-1)) } catch {}
  }
  async function markAllRead() {
    try { await api.post('/alerts/read'); setAlerts(a => a.map(x=>({...x,is_read:true}))); setUnread(0) } catch {}
  }
  function handleSymbolClick(symbol) { setOpen(false); window.dispatchEvent(new CustomEvent('openSymbol', { detail: symbol })) }

  const filtered = filter === 'unread' ? alerts.filter(a => !a.is_read) : alerts
  const buys     = alerts.filter(a => a.alert_type==='BUY_SIGNAL'  && !a.is_read).length
  const sells    = alerts.filter(a => a.alert_type==='SELL_SIGNAL' && !a.is_read).length

  return (
    <div className="relative">
      <button onClick={() => setOpen(o => !o)}
        className={`relative flex items-center justify-center w-9 h-9 rounded-xl border transition-all ${
          open ? 'bg-brand-500/20 border-brand-500/40 text-brand-400' : 'bg-dark-700 border-dark-600 text-gray-400 hover:text-white hover:border-dark-500'
        }`}>
        <Bell size={16}/>
        {unread > 0 && (
          <div className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] bg-red-500 text-white text-xs font-black rounded-full flex items-center justify-center px-1 shadow-lg">
            {unread > 99 ? '99+' : unread}
          </div>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 w-96 bg-dark-800 border border-dark-600 rounded-2xl shadow-2xl z-50 overflow-hidden" style={{maxHeight:'80vh'}}>
          <div className="bg-dark-900 border-b border-dark-700 px-4 py-3">
            <div className="flex items-center gap-2">
              <Bell size={15} className="text-brand-400"/>
              <span className="text-sm font-black text-white">Trading Alerts</span>
              {unread > 0 && <span className="text-xs bg-red-900/40 text-red-400 border border-red-800/40 px-1.5 py-0.5 rounded-full font-bold">{unread} new</span>}
              <div className="ml-auto flex items-center gap-2">
                {unread > 0 && <button onClick={markAllRead} className="text-xs text-gray-500 hover:text-brand-400">Mark all read</button>}
                <button onClick={() => setOpen(false)} className="text-gray-500 hover:text-white"><X size={14}/></button>
              </div>
            </div>
            {(buys > 0 || sells > 0) && (
              <div className="flex gap-2 mt-2">
                {buys  > 0 && <span className="text-xs px-2 py-0.5 bg-green-900/20 text-green-400 border border-green-800/40 rounded-full font-bold">🟢 {buys} buy</span>}
                {sells > 0 && <span className="text-xs px-2 py-0.5 bg-red-900/20   text-red-400   border border-red-800/40   rounded-full font-bold">🔴 {sells} sell</span>}
              </div>
            )}
            <div className="flex gap-1 mt-2">
              {['all','unread'].map(f => (
                <button key={f} onClick={() => setFilter(f)}
                  className={`text-xs px-2.5 py-1 rounded-lg transition-colors ${filter===f?'bg-brand-500 text-dark-900 font-bold':'text-gray-500 hover:text-white'}`}>
                  {f==='all'?`All (${alerts.length})`:`Unread (${unread})`}
                </button>
              ))}
            </div>
          </div>

          {userTier === 'free' && (
            <div className="px-4 py-2.5 bg-dark-700/50 border-b border-dark-700 flex items-center gap-2">
              <Clock size={12} className="text-gray-500 flex-shrink-0"/>
              <span className="text-xs text-gray-500 flex-1">Alerts update every 15 min on Free plan</span>
              <button onClick={() => { setOpen(false); window.dispatchEvent(new CustomEvent('navigate',{detail:'billing'})) }}
                className="text-xs text-brand-400 font-bold hover:text-brand-300 flex-shrink-0">Get real-time ↗</button>
            </div>
          )}

          <div className="overflow-y-auto p-3 space-y-2" style={{maxHeight:'55vh'}}>
            {loading && <div className="text-center py-8 text-gray-600 text-sm">Loading alerts…</div>}
            {!loading && filtered.length === 0 && (
              <div className="text-center py-10 text-gray-600">
                <Bell size={28} className="mx-auto mb-2 opacity-30"/>
                <p className="text-sm font-medium">{filter==='unread'?'All caught up!':'No alerts yet'}</p>
                <p className="text-xs mt-1 text-gray-700">Run AI analysis on symbols you're watching</p>
              </div>
            )}
            {filtered.map((alert, i) => (
              <AlertCard key={i} alert={alert} onRead={handleRead} onSymbolClick={handleSymbolClick}/>
            ))}
          </div>

          <div className="border-t border-dark-700 px-4 py-2.5 bg-dark-900/50 text-center">
            <p className="text-xs text-gray-600">Click any alert to open its symbol board</p>
          </div>
        </div>
      )}
      {open && <div className="fixed inset-0 z-40" onClick={() => setOpen(false)}/>}
    </div>
  )
}

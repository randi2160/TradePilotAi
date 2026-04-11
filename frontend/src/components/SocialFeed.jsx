import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { Heart, MessageCircle, Copy, TrendingUp, TrendingDown, Users, RefreshCw, Bell } from 'lucide-react'

const ACTION_CONFIG = {
  BUY:        { color:'text-green-400', bg:'bg-green-900/30 border-green-800', icon:'▲', label:'BUY'        },
  SELL:       { color:'text-red-400',   bg:'bg-red-900/30   border-red-800',   icon:'▼', label:'SOLD'       },
  TARGET_HIT: { color:'text-brand-500', bg:'bg-teal-900/30  border-teal-800',  icon:'🎯',label:'TARGET HIT' },
  STOP_HIT:   { color:'text-orange-400',bg:'bg-orange-900/30 border-orange-800',icon:'🛑',label:'STOP HIT'  },
  CLOSED:     { color:'text-gray-400',  bg:'bg-dark-700      border-dark-600',  icon:'■', label:'CLOSED'     },
}

function BroadcastCard({ b, onLike, onFollow, isFollowing, currentUserId }) {
  const [showComments, setShowComments] = useState(false)
  const [comments,     setComments]     = useState([])
  const [newComment,   setNewComment]   = useState('')
  const [posting,      setPosting]      = useState(false)
  const ac = ACTION_CONFIG[b.action] ?? ACTION_CONFIG.CLOSED

  const trader = b.trader ?? {}
  const isMe   = trader.id === currentUserId || b.trader_id === currentUserId

  async function loadComments() {
    try {
      const r = await api.get(`/social/broadcast/${b.id}/comments`)
      setComments(r.data)
    } catch {}
  }

  async function submitComment() {
    if (!newComment.trim()) return
    setPosting(true)
    try {
      await api.post(`/social/broadcast/${b.id}/comment`, { content: newComment })
      setNewComment('')
      loadComments()
    } catch {}
    finally { setPosting(false) }
  }

  return (
    <div className={`rounded-xl border p-4 space-y-3 ${ac.bg}`}>
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-full bg-brand-500/30 flex items-center justify-center text-brand-400 font-black text-sm flex-shrink-0">
          {(typeof trader === 'string' ? trader : trader.display_name ?? 'T').slice(0,2).toUpperCase()}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-bold text-white text-sm">
              {typeof trader === 'string' ? trader : trader.display_name ?? `Trader #${b.trader_id}`}
            </span>
            {trader.is_copyable && (
              <span className="text-xs bg-brand-500/20 text-brand-400 border border-brand-500/40 px-1.5 py-0.5 rounded-full">
                ✓ Copyable
              </span>
            )}
            {trader.win_rate > 0 && (
              <span className="text-xs text-gray-500">{trader.win_rate?.toFixed(0)}% WR</span>
            )}
          </div>
          <p className="text-xs text-gray-500">
            {new Date(b.created_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}
            {' · '}{trader.total_trades ?? 0} trades
          </p>
        </div>
        {!isMe && (
          <button onClick={() => onFollow(b.trader_id ?? trader.id)}
            className={`text-xs px-3 py-1.5 rounded-lg font-bold transition-colors ${
              isFollowing
                ? 'bg-dark-600 text-gray-400 hover:bg-red-900/30 hover:text-red-400'
                : 'bg-brand-500/20 text-brand-400 border border-brand-500/40 hover:bg-brand-500/40'
            }`}>
            {isFollowing ? 'Following' : '+ Follow'}
          </button>
        )}
      </div>

      {/* Trade card */}
      <div className="bg-dark-800/60 rounded-xl p-3">
        <div className="flex items-center gap-3 mb-2">
          <span className="font-black text-white text-xl">{b.symbol}</span>
          <span className={`text-sm font-black px-2 py-0.5 rounded ${ac.color}`}>
            {ac.icon} {ac.label}
          </span>
          {b.qty > 0 && <span className="text-xs text-gray-400">{b.qty} shares</span>}
        </div>

        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="bg-dark-700 rounded-lg p-2">
            <p className="text-gray-500">Price</p>
            <p className="font-bold text-white">${b.price?.toFixed(2)}</p>
          </div>
          {b.stop_loss && (
            <div className="bg-dark-700 rounded-lg p-2">
              <p className="text-gray-500">Stop Loss</p>
              <p className="font-bold text-red-400">${b.stop_loss?.toFixed(2)}</p>
            </div>
          )}
          {b.take_profit && (
            <div className="bg-dark-700 rounded-lg p-2">
              <p className="text-gray-500">Target</p>
              <p className="font-bold text-green-400">${b.take_profit?.toFixed(2)}</p>
            </div>
          )}
          {b.confidence > 0 && (
            <div className="bg-dark-700 rounded-lg p-2">
              <p className="text-gray-500">Confidence</p>
              <p className="font-bold text-brand-500">{(b.confidence * 100).toFixed(0)}%</p>
            </div>
          )}
          {b.pnl !== null && b.pnl !== undefined && (
            <div className={`rounded-lg p-2 ${b.pnl >= 0 ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
              <p className="text-gray-500">P&L</p>
              <p className={`font-bold ${b.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {b.pnl >= 0 ? '+' : ''}${b.pnl?.toFixed(2)}
              </p>
            </div>
          )}
        </div>

        {b.reasoning && (
          <p className="text-xs text-gray-400 mt-2">
            🤖 {b.reasoning}
          </p>
        )}
      </div>

      {/* Manual copy prompt */}
      {b.action === 'BUY' && !isMe && b.stop_loss && (
        <div className="bg-dark-700 rounded-lg px-3 py-2 flex items-center gap-2 text-xs">
          <Copy size={12} className="text-gray-400"/>
          <span className="text-gray-400">Copy manually:</span>
          <span className="text-white font-mono">
            BUY {b.symbol} @ ${b.price?.toFixed(2)} · SL ${b.stop_loss?.toFixed(2)} · TP ${b.take_profit?.toFixed(2)}
          </span>
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-4">
        <button onClick={() => onLike(b.id)}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-red-400 transition-colors">
          <Heart size={14}/>
          <span>{b.likes}</span>
        </button>
        <button onClick={() => { setShowComments(s => !s); if (!showComments) loadComments() }}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-brand-400 transition-colors">
          <MessageCircle size={14}/>
          <span>{b.comments_count ?? 0}</span>
        </button>
        {b.copies_count > 0 && (
          <span className="flex items-center gap-1 text-xs text-gray-500">
            <Copy size={12}/> {b.copies_count} copied
          </span>
        )}
        <span className="text-xs text-gray-600 ml-auto">{b.setup_type?.replace(/_/g,' ')}</span>
      </div>

      {/* Comments */}
      {showComments && (
        <div className="space-y-2 pt-2 border-t border-dark-600">
          {comments.map((c, i) => (
            <div key={i} className="flex gap-2 text-xs">
              <span className="font-bold text-gray-300 flex-shrink-0">{c.display_name}</span>
              <span className="text-gray-400">{c.content}</span>
              <span className="text-gray-600 ml-auto flex-shrink-0">{c.created_at?.slice(11,16)}</span>
            </div>
          ))}
          <div className="flex gap-2 mt-2">
            <input value={newComment} onChange={e => setNewComment(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && submitComment()}
              placeholder="Add a comment..."
              className="flex-1 bg-dark-700 border border-dark-600 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-brand-500"/>
            <button onClick={submitComment} disabled={posting}
              className="px-3 py-1.5 bg-brand-500 hover:bg-brand-600 text-dark-900 text-xs font-bold rounded-lg">
              Post
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function SocialFeed({ currentUserId }) {
  const [feed,       setFeed]       = useState([])
  const [following,  setFollowing]  = useState(new Set())
  const [tab,        setTab]        = useState('feed')
  const [myProfile,  setMyProfile]  = useState(null)
  const [traders,    setTraders]    = useState([])
  const [notifCount, setNotifCount] = useState(0)
  const [loading,    setLoading]    = useState(false)
  const [filterSym,  setFilterSym]  = useState('')

  useEffect(() => { loadAll() }, [tab])
  useEffect(() => {
    const iv = setInterval(() => { if (tab === 'feed') loadFeed() }, 15000)
    return () => clearInterval(iv)
  }, [tab])

  async function loadAll() {
    setLoading(true)
    try {
      await Promise.all([
        loadFeed(),
        loadProfile(),
        loadFollowing(),
        loadNotifCount(),
        tab === 'traders' && loadTraders(),
      ].filter(Boolean))
    } finally { setLoading(false) }
  }

  async function loadFeed() {
    try {
      const sym = filterSym ? `?symbol=${filterSym}` : ''
      const r   = await api.get(`/social/feed${sym}`)
      setFeed(r.data)
    } catch {
      // Fallback to public feed
      try {
        const r = await api.get('/social/feed/public')
        setFeed(r.data)
      } catch {}
    }
  }

  async function loadProfile() {
    try {
      const r = await api.get('/social/profile/me')
      setMyProfile(r.data)
    } catch {}
  }

  async function loadFollowing() {
    try {
      const r = await api.get('/social/following')
      setFollowing(new Set(r.data.map(f => f.leader_id)))
    } catch {}
  }

  async function loadTraders() {
    try {
      const r = await api.get('/social/traders')
      setTraders(r.data)
    } catch {}
  }

  async function loadNotifCount() {
    try {
      const r = await api.get('/social/notifications')
      setNotifCount(r.data.filter(n => !n.is_read).length)
    } catch {}
  }

  async function handleLike(broadcastId) {
    try { await api.post(`/social/broadcast/${broadcastId}/like`) } catch {}
  }

  async function handleFollow(leaderId) {
    if (!leaderId) return
    try {
      if (following.has(leaderId)) {
        await api.delete(`/social/follow/${leaderId}`)
        setFollowing(f => { const n = new Set(f); n.delete(leaderId); return n })
      } else {
        await api.post(`/social/follow/${leaderId}`)
        setFollowing(f => new Set([...f, leaderId]))
      }
    } catch {}
  }

  return (
    <div className="space-y-5">

      {/* Tabs */}
      <div className="flex gap-2 flex-wrap">
        {[
          { id:'feed',    label:'📡 Live Feed'    },
          { id:'my',      label:'📋 My Trades'    },
          { id:'traders', label:'👥 Traders'      },
          { id:'profile', label:'👤 My Profile'   },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
              tab===t.id ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}>{t.label}</button>
        ))}
        {notifCount > 0 && (
          <button onClick={async () => { setTab('feed'); await api.post('/social/notifications/read'); setNotifCount(0) }}
            className="flex items-center gap-1 px-3 py-2 bg-yellow-900/40 text-yellow-400 border border-yellow-700 rounded-lg text-xs">
            <Bell size={12}/> {notifCount} new
          </button>
        )}
        <button onClick={loadAll} disabled={loading}
          className="ml-auto p-2 bg-dark-700 rounded-lg hover:bg-dark-600 transition-colors">
          <RefreshCw size={14} className={`text-gray-400 ${loading?'animate-spin':''}`}/>
        </button>
      </div>

      {/* ── Live Feed ─────────────────────────────────────────────────────────── */}
      {tab === 'feed' && (
        <div className="space-y-4">
          {/* Symbol filter */}
          <div className="flex gap-2">
            <input value={filterSym} onChange={e => setFilterSym(e.target.value.toUpperCase())}
              placeholder="Filter by symbol e.g. NVDA"
              className="flex-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2 text-white text-sm font-mono uppercase focus:outline-none focus:border-brand-500"/>
            {filterSym && <button onClick={() => { setFilterSym(''); loadFeed() }}
              className="px-3 text-gray-400 hover:text-white">✕</button>}
          </div>

          {feed.length === 0 ? (
            <div className="text-center py-16 bg-dark-800 border border-dark-600 rounded-xl">
              <p className="text-4xl mb-3">📡</p>
              <p className="font-bold text-white mb-1">No broadcasts yet</p>
              <p className="text-sm text-gray-400">Follow traders or make trades to see activity here</p>
            </div>
          ) : (
            feed.map(b => (
              <BroadcastCard
                key={b.id}
                b={b}
                onLike={handleLike}
                onFollow={handleFollow}
                isFollowing={following.has(b.trader_id ?? b.trader?.id)}
                currentUserId={currentUserId}
              />
            ))
          )}
        </div>
      )}

      {/* ── My Broadcasts ─────────────────────────────────────────────────────── */}
      {tab === 'my' && (
        <div className="space-y-4">
          <MyBroadcasts currentUserId={currentUserId}/>
        </div>
      )}

      {/* ── Traders Leaderboard ───────────────────────────────────────────────── */}
      {tab === 'traders' && (
        <div className="space-y-3">
          <p className="text-sm text-gray-400">Top traders by performance — follow to see their trades in your feed</p>
          {traders.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Users size={32} className="mx-auto mb-2 opacity-40"/>
              <p>No public traders yet — be the first!</p>
            </div>
          ) : traders.map((t, i) => (
            <div key={t.user_id} className="flex items-center gap-3 bg-dark-800 border border-dark-600 rounded-xl p-3">
              <span className="text-gray-500 w-6 text-center font-bold">#{i+1}</span>
              <div className="flex-1">
                <p className="font-bold text-white">{t.display_name}</p>
                <div className="flex gap-3 text-xs text-gray-500">
                  <span>{t.total_trades} trades</span>
                  <span>+${t.total_pnl?.toFixed(0)}</span>
                  <span>{t.followers} followers</span>
                  {t.is_copyable && <span className="text-brand-500">✓ Copyable</span>}
                </div>
              </div>
              <div className="text-right">
                <p className={`font-black text-lg ${t.win_rate >= 60 ? 'text-green-400' : 'text-yellow-400'}`}>
                  {t.win_rate?.toFixed(0)}%
                </p>
                <p className="text-xs text-gray-500">win rate</p>
              </div>
              <button onClick={() => handleFollow(t.user_id)}
                className={`text-xs px-3 py-1.5 rounded-lg font-bold transition-colors ${
                  following.has(t.user_id)
                    ? 'bg-dark-600 text-gray-400'
                    : 'bg-brand-500/20 text-brand-400 border border-brand-500/40'
                }`}>
                {following.has(t.user_id) ? 'Following' : '+ Follow'}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── My Profile ────────────────────────────────────────────────────────── */}
      {tab === 'profile' && myProfile && (
        <MyProfileEditor profile={myProfile} onUpdate={loadProfile}/>
      )}
    </div>
  )
}

function MyBroadcasts({ currentUserId }) {
  const [broadcasts, setBroadcasts] = useState([])
  useEffect(() => {
    api.get('/social/feed/my-broadcasts').then(r => setBroadcasts(r.data)).catch(() => {})
  }, [])

  if (broadcasts.length === 0) return (
    <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-xl text-gray-500">
      <p className="text-3xl mb-2">📋</p>
      <p>No broadcasts yet — execute trades to auto-post here</p>
    </div>
  )

  return broadcasts.map(b => {
    const ac = ACTION_CONFIG[b.action] ?? ACTION_CONFIG.CLOSED
    return (
      <div key={b.id} className={`rounded-xl border p-4 ${ac.bg}`}>
        <div className="flex items-center gap-3 mb-2">
          <span className="font-black text-white text-lg">{b.symbol}</span>
          <span className={`text-sm font-bold ${ac.color}`}>{ac.icon} {ac.label}</span>
          {b.pnl !== null && b.pnl !== undefined && (
            <span className={`text-sm font-bold ml-auto ${b.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {b.pnl >= 0 ? '+' : ''}${b.pnl?.toFixed(2)}
            </span>
          )}
        </div>
        <div className="flex gap-4 text-xs text-gray-400">
          <span>${b.price?.toFixed(2)}</span>
          {b.stop_loss   && <span>SL ${b.stop_loss?.toFixed(2)}</span>}
          {b.take_profit && <span>TP ${b.take_profit?.toFixed(2)}</span>}
          <span className="ml-auto">❤️ {b.likes}  💬 {b.copies_count} copied</span>
        </div>
        <p className="text-xs text-gray-600 mt-1">{new Date(b.created_at).toLocaleString()}</p>
      </div>
    )
  })
}

function MyProfileEditor({ profile, onUpdate }) {
  const [displayName, setDisplayName] = useState(profile.display_name ?? '')
  const [bio,         setBio]         = useState(profile.bio ?? '')
  const [isPublic,    setIsPublic]    = useState(profile.is_public ?? true)
  const [saving,      setSaving]      = useState(false)
  const [msg,         setMsg]         = useState('')

  async function save() {
    setSaving(true)
    try {
      await api.put('/social/profile/me', { display_name: displayName, bio, is_public: isPublic })
      setMsg('✅ Profile updated!')
      onUpdate()
    } catch { setMsg('❌ Failed to save') }
    finally { setSaving(false); setTimeout(() => setMsg(''), 3000) }
  }

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-5">
      <h3 className="font-bold text-white">My Trader Profile</h3>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 text-center text-xs">
        {[
          { label:'Win Rate',   value:`${profile.stats?.win_rate?.toFixed(0) ?? 0}%`, color: profile.stats?.win_rate >= 60 ? 'text-green-400' : 'text-yellow-400' },
          { label:'Trades',     value: profile.stats?.total_trades ?? 0,              color:'text-white'   },
          { label:'Total P&L',  value:`$${profile.stats?.total_pnl?.toFixed(0) ?? 0}`, color:'text-green-400' },
          { label:'Followers',  value: profile.stats?.followers ?? 0,                color:'text-white'   },
          { label:'Days Active',value: profile.stats?.days_tracked ?? 0,             color:'text-white'   },
          { label:'Copyable',   value: profile.is_copyable ? '✅ Yes' : '❌ No',      color: profile.is_copyable ? 'text-green-400' : 'text-gray-500' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-dark-700 rounded-lg p-2.5">
            <p className="text-gray-500">{label}</p>
            <p className={`font-bold ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      {!profile.is_copyable && (
        <p className="text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-800/40 rounded-lg p-2.5">
          ⚠️ To become copyable: need 30+ days of history and 60%+ win rate
        </p>
      )}

      <div className="space-y-3">
        <div>
          <label className="text-xs text-gray-400">Display Name</label>
          <input value={displayName} onChange={e => setDisplayName(e.target.value)}
            className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500"/>
        </div>
        <div>
          <label className="text-xs text-gray-400">Bio</label>
          <textarea value={bio} onChange={e => setBio(e.target.value)} rows={3}
            placeholder="Tell other traders about your strategy..."
            className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500 resize-none"/>
        </div>
        <label className="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" checked={isPublic} onChange={e => setIsPublic(e.target.checked)}
            className="w-4 h-4"/>
          <div>
            <p className="text-sm text-white">Public Profile</p>
            <p className="text-xs text-gray-400">Allow other traders to see your broadcasts and follow you</p>
          </div>
        </label>
      </div>

      {msg && <p className="text-sm text-center">{msg}</p>}

      <button onClick={save} disabled={saving}
        className="w-full py-3 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl transition-colors disabled:opacity-50">
        {saving ? 'Saving…' : 'Save Profile'}
      </button>
    </div>
  )
}

import { useState, useEffect, useRef } from 'react'
import { api } from '../hooks/useAuth'
import { Heart, MessageCircle, Copy, Users, RefreshCw, Bell, TrendingUp, TrendingDown, Shield, Plus, X, Send } from 'lucide-react'
import { openSymbolBoard, parseSymbolsInText } from '../utils/symbolUtils'

// ── Constants ────────────────────────────────────────────────────────────────

const ACTION_CONFIG = {
  BUY:        { color:'text-green-400',  bg:'bg-green-900/20  border-green-800/50',  icon:'▲', label:'BUY'        },
  SELL:       { color:'text-red-400',    bg:'bg-red-900/20    border-red-800/50',    icon:'▼', label:'SOLD'       },
  TARGET_HIT: { color:'text-brand-500',  bg:'bg-teal-900/20   border-teal-800/50',   icon:'🎯',label:'TARGET HIT' },
  STOP_HIT:   { color:'text-orange-400', bg:'bg-orange-900/20 border-orange-800/50', icon:'🛑',label:'STOP HIT'   },
  CLOSED:     { color:'text-gray-400',   bg:'bg-dark-800      border-dark-600',      icon:'■', label:'CLOSED'     },
}

const TIERS = {
  free:       { label:'Free',       color:'text-gray-400',  features:['Follow traders','15-min delayed feed','Manual copy'] },
  subscriber: { label:'Subscriber', color:'text-brand-500', features:['Real-time feed','Auto-copy 2 leaders','Create groups'] },
  pro:        { label:'Pro',        color:'text-yellow-400', features:['Auto-copy 10 leaders','Unlimited groups','Analytics'] },
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Avatar({ name, size = 'sm' }) {
  const initials = (name ?? 'U').slice(0,2).toUpperCase()
  const sz = size === 'lg' ? 'w-12 h-12 text-base' : 'w-8 h-8 text-xs'
  return (
    <div className={`${sz} rounded-full bg-brand-500/30 flex items-center justify-center text-brand-400 font-black flex-shrink-0`}>
      {initials}
    </div>
  )
}

function BroadcastCard({ b, myId, following, onLike, onFollow, onCopy }) {
  const [showComments, setShowComments] = useState(false)
  const [comments,     setComments]     = useState([])
  const [newComment,   setNewComment]   = useState('')
  const [posting,      setPosting]      = useState(false)
  const [liked,        setLiked]        = useState(false)
  const [likeCount,    setLikeCount]    = useState(b.likes ?? 0)

  const ac      = ACTION_CONFIG[b.action] ?? ACTION_CONFIG.CLOSED
  const trader  = b.trader ?? {}
  const name    = typeof trader === 'string' ? trader : trader.display_name ?? `Trader #${b.trader_id}`
  const isMe    = (b.trader_id ?? trader.id) === myId
  const leaderId= b.trader_id ?? trader.id
  const isFollowing = following.has(leaderId)

  async function toggleLike() {
    try {
      await api.post(`/social/broadcast/${b.id}/like`)
      setLiked(l => !l)
      setLikeCount(c => liked ? c - 1 : c + 1)
    } catch {}
  }

  async function loadComments() {
    try { const r = await api.get(`/social/broadcast/${b.id}/comments`); setComments(r.data) } catch {}
  }

  async function postComment() {
    if (!newComment.trim()) return
    setPosting(true)
    try {
      await api.post(`/social/broadcast/${b.id}/comment`, { content: newComment })
      setNewComment('')
      loadComments()
    } catch {} finally { setPosting(false) }
  }

  const timeAgo = (iso) => {
    const mins = Math.floor((Date.now() - new Date(iso)) / 60000)
    if (mins < 1)  return 'just now'
    if (mins < 60) return `${mins}m ago`
    if (mins < 1440) return `${Math.floor(mins/60)}h ago`
    return `${Math.floor(mins/1440)}d ago`
  }

  return (
    <div className={`rounded-xl border p-4 space-y-3 transition-all hover:border-opacity-70 ${ac.bg}`}>
      {/* Header */}
      <div className="flex items-center gap-3">
        <Avatar name={name}/>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-white text-sm">{name}</span>
            {trader.is_copyable && (
              <span className="text-xs bg-brand-500/20 text-brand-400 border border-brand-500/30 px-1.5 py-0.5 rounded-full">✓ Copyable</span>
            )}
            {trader.win_rate > 0 && (
              <span className="text-xs text-gray-500">{trader.win_rate?.toFixed(0)}% WR · {trader.total_trades} trades</span>
            )}
          </div>
          <p className="text-xs text-gray-500">{timeAgo(b.created_at)}</p>
        </div>
        {!isMe && (
          <button onClick={() => onFollow(leaderId)}
            className={`text-xs px-3 py-1.5 rounded-lg font-bold transition-all ${
              isFollowing
                ? 'bg-dark-600 text-gray-400 hover:bg-red-900/20 hover:text-red-400'
                : 'bg-brand-500/20 text-brand-400 border border-brand-500/30 hover:bg-brand-500/30'
            }`}>
            {isFollowing ? 'Following' : '+ Follow'}
          </button>
        )}
      </div>

      {/* Trade card */}
      <div className="bg-dark-900/50 rounded-xl p-3 space-y-2">
        <div className="flex items-center gap-3">
          <button onClick={() => openSymbolBoard(b.symbol)}
            className="font-black text-white text-2xl hover:text-brand-400 transition-colors cursor-pointer">
            ${b.symbol}
          </button>
          <span className={`text-sm font-black ${ac.color}`}>{ac.icon} {ac.label}</span>
          {b.qty > 0 && <span className="text-xs text-gray-400">{b.qty} shares</span>}
          {b.pnl !== null && b.pnl !== undefined && (
            <span className={`ml-auto font-black text-lg ${b.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {b.pnl >= 0 ? '+' : ''}${b.pnl?.toFixed(2)}
            </span>
          )}
        </div>

        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="bg-dark-800/80 rounded-lg p-2 text-center">
            <p className="text-gray-500 mb-0.5">Price</p>
            <p className="font-bold text-white">${b.price?.toFixed(2)}</p>
          </div>
          {b.stop_loss && (
            <div className="bg-dark-800/80 rounded-lg p-2 text-center">
              <p className="text-gray-500 mb-0.5">Stop Loss</p>
              <p className="font-bold text-red-400">${b.stop_loss?.toFixed(2)}</p>
            </div>
          )}
          {b.take_profit && (
            <div className="bg-dark-800/80 rounded-lg p-2 text-center">
              <p className="text-gray-500 mb-0.5">Target</p>
              <p className="font-bold text-green-400">${b.take_profit?.toFixed(2)}</p>
            </div>
          )}
          {b.confidence > 0 && (
            <div className="bg-dark-800/80 rounded-lg p-2 text-center">
              <p className="text-gray-500 mb-0.5">AI Conf</p>
              <p className="font-bold text-brand-500">{(b.confidence*100).toFixed(0)}%</p>
            </div>
          )}
        </div>

        {b.reasoning && (
          <p className="text-xs text-gray-400 flex items-start gap-1">
            <span>🤖</span><span>{b.reasoning}</span>
          </p>
        )}

        {/* Manual copy prompt */}
        {b.action === 'BUY' && !isMe && b.stop_loss && (
          <button onClick={() => onCopy(b)}
            className="w-full flex items-center justify-center gap-2 text-xs bg-dark-700 hover:bg-dark-600 text-gray-300 hover:text-white py-2 rounded-lg transition-colors border border-dark-600">
            <Copy size={12}/> Copy this trade manually
          </button>
        )}
      </div>

      {/* Actions bar */}
      <div className="flex items-center gap-4 pt-1">
        <button onClick={toggleLike}
          className={`flex items-center gap-1.5 text-xs transition-colors ${liked ? 'text-red-400' : 'text-gray-400 hover:text-red-400'}`}>
          <Heart size={14} fill={liked ? 'currentColor' : 'none'}/> {likeCount}
        </button>
        <button onClick={() => { setShowComments(s => !s); if (!showComments) loadComments() }}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-brand-400 transition-colors">
          <MessageCircle size={14}/> {b.comments_count ?? 0}
        </button>
        {b.copies_count > 0 && (
          <span className="flex items-center gap-1 text-xs text-gray-600">
            <Copy size={12}/> {b.copies_count} copied
          </span>
        )}
        {b.setup_type && (
          <span className="ml-auto text-xs text-gray-600 capitalize">{b.setup_type.replace(/_/g,' ')}</span>
        )}
      </div>

      {/* Comments */}
      {showComments && (
        <div className="space-y-2 pt-2 border-t border-dark-700">
          {comments.map((c, i) => (
            <div key={i} className="flex gap-2 text-xs">
              <span className="font-bold text-gray-300 flex-shrink-0">{c.display_name}</span>
              <span className="text-gray-400 flex-1">{c.content}</span>
              <span className="text-gray-600 flex-shrink-0">{c.created_at?.slice(11,16)}</span>
            </div>
          ))}
          <div className="flex gap-2">
            <input value={newComment} onChange={e => setNewComment(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && postComment()}
              placeholder="Add a comment…" maxLength={500}
              className="flex-1 bg-dark-700 border border-dark-600 rounded-lg px-3 py-1.5 text-xs text-white focus:outline-none focus:border-brand-500"/>
            <button onClick={postComment} disabled={posting || !newComment.trim()}
              className="px-3 py-1.5 bg-brand-500 hover:bg-brand-600 text-dark-900 text-xs font-bold rounded-lg disabled:opacity-50">
              <Send size={12}/>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function CopyModal({ trade, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="bg-dark-800 border border-dark-600 rounded-2xl p-6 max-w-sm w-full space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-white">📋 Manual Copy Guide</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-white"><X size={18}/></button>
        </div>
        <div className="bg-dark-700 rounded-xl p-4 space-y-2 text-sm">
          <div className="flex justify-between"><span className="text-gray-400">Symbol</span><span className="font-bold text-white">{trade.symbol}</span></div>
          <div className="flex justify-between"><span className="text-gray-400">Action</span><span className="font-bold text-green-400">BUY</span></div>
          <div className="flex justify-between"><span className="text-gray-400">Entry ~</span><span className="font-bold text-white">${trade.price?.toFixed(2)}</span></div>
          {trade.stop_loss   && <div className="flex justify-between"><span className="text-gray-400">Stop Loss</span><span className="font-bold text-red-400">${trade.stop_loss?.toFixed(2)}</span></div>}
          {trade.take_profit && <div className="flex justify-between"><span className="text-gray-400">Take Profit</span><span className="font-bold text-green-400">${trade.take_profit?.toFixed(2)}</span></div>}
          {trade.confidence  && <div className="flex justify-between"><span className="text-gray-400">AI Confidence</span><span className="font-bold text-brand-500">{(trade.confidence*100).toFixed(0)}%</span></div>}
        </div>
        {trade.reasoning && <p className="text-xs text-gray-400">📊 {trade.reasoning}</p>}
        <p className="text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-800/40 rounded-lg p-3">
          ⚠️ This is a manual copy. You are responsible for all trades. This is not financial advice.
        </p>
        <button onClick={onClose} className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl">
          Got it — I'll place this manually
        </button>
      </div>
    </div>
  )
}

function GroupModal({ onClose, onCreated }) {
  const [name, setName]   = useState('')
  const [desc, setDesc]   = useState('')
  const [cat,  setCat]    = useState('general')
  const [pub,  setPub]    = useState(true)
  const [rules,setRules]  = useState('Be respectful. No spam. No pump & dump language.')
  const [saving,setSaving]= useState(false)
  const [err,  setErr]    = useState('')

  async function create() {
    if (!name.trim()) { setErr('Group name required'); return }
    setSaving(true)
    try {
      const r = await api.post('/social/groups', { name, description: desc, category: cat, is_public: pub, rules })
      onCreated(r.data)
      onClose()
    } catch(e) { setErr(e.response?.data?.detail ?? 'Failed to create group') }
    finally { setSaving(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="bg-dark-800 border border-dark-600 rounded-2xl p-6 max-w-md w-full space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-bold text-white">🏘️ Create Trading Group</h3>
          <button onClick={onClose}><X size={18} className="text-gray-500"/></button>
        </div>
        {err && <p className="text-xs text-red-400 bg-red-900/20 p-2 rounded-lg">{err}</p>}
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-400">Group Name *</label>
            <input value={name} onChange={e => setName(e.target.value)} maxLength={50}
              placeholder="e.g. Momentum Traders Club"
              className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500"/>
          </div>
          <div>
            <label className="text-xs text-gray-400">Description</label>
            <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={2} maxLength={300}
              placeholder="What is this group about?"
              className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500 resize-none"/>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400">Category</label>
              <select value={cat} onChange={e => setCat(e.target.value)}
                className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-xl px-3 py-2.5 text-white text-sm focus:outline-none">
                {['general','momentum','swing','options','crypto','forex'].map(c => (
                  <option key={c} value={c} className="capitalize">{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400">Visibility</label>
              <select value={pub} onChange={e => setPub(e.target.value === 'true')}
                className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-xl px-3 py-2.5 text-white text-sm focus:outline-none">
                <option value="true">Public</option>
                <option value="false">Private</option>
              </select>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400">Group Rules</label>
            <textarea value={rules} onChange={e => setRules(e.target.value)} rows={2}
              className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500 resize-none"/>
          </div>
        </div>
        <button onClick={create} disabled={saving}
          className="w-full py-3 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl disabled:opacity-50">
          {saving ? 'Creating…' : '🏘️ Create Group'}
        </button>
      </div>
    </div>
  )
}

function SymbolChat({ symbol, onClose }) {
  const [msgs,     setMsgs]    = useState([])
  const [content,  setContent] = useState('')
  const [sentiment,setSentiment]=useState('neutral')
  const [posting,  setPosting] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    load()
    const iv = setInterval(load, 8000)
    return () => clearInterval(iv)
  }, [symbol])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior:'smooth' }) }, [msgs])

  async function load() {
    try { const r = await api.get(`/social/chat/${symbol}?limit=50`); setMsgs(r.data.reverse()) } catch {}
  }

  async function post() {
    if (!content.trim()) return
    setPosting(true)
    try {
      const r = await api.post(`/social/chat/${symbol}`, { content, sentiment })
      if (r.data.error) { alert(r.data.error); return }
      if (r.data.warning) alert(`⚠️ Warning: ${r.data.warning}`)
      setContent('')
      load()
    } catch {} finally { setPosting(false) }
  }

  const sentBg = { bullish:'bg-green-900/30 text-green-400', bearish:'bg-red-900/30 text-red-400', neutral:'bg-dark-600 text-gray-400' }

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-2xl overflow-hidden flex flex-col h-96">
      <div className="flex items-center justify-between px-4 py-3 border-b border-dark-600">
        <p className="font-bold text-white">${symbol} Chat</p>
        {onClose && <button onClick={onClose}><X size={16} className="text-gray-400"/></button>}
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-2">
        {msgs.length === 0 && <p className="text-center text-gray-500 text-sm py-8">No messages yet — start the conversation!</p>}
        {msgs.map((m, i) => (
          <div key={i} className="flex gap-2">
            <Avatar name={m.display_name} size="sm"/>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-xs font-bold text-gray-300">{m.display_name}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded capitalize ${sentBg[m.sentiment] ?? sentBg.neutral}`}>{m.sentiment}</span>
                <span className="text-xs text-gray-600 ml-auto">{m.created_at?.slice(11,16)}</span>
              </div>
              <p className="text-sm text-gray-300">{m.content}</p>
            </div>
          </div>
        ))}
        <div ref={bottomRef}/>
      </div>
      <div className="border-t border-dark-600 p-3 space-y-2">
        <div className="flex gap-1">
          {['bullish','neutral','bearish'].map(s => (
            <button key={s} onClick={() => setSentiment(s)}
              className={`flex-1 text-xs py-1 rounded font-medium capitalize transition-colors ${
                sentiment === s ? sentBg[s] : 'bg-dark-700 text-gray-500'
              }`}>{s}</button>
          ))}
        </div>
        <div className="flex gap-2">
          <input value={content} onChange={e => setContent(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && post()}
            placeholder={`What do you think about $${symbol}?`} maxLength={500}
            className="flex-1 bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"/>
          <button onClick={post} disabled={posting || !content.trim()}
            className="px-3 bg-brand-500 hover:bg-brand-600 text-dark-900 rounded-lg disabled:opacity-50">
            <Send size={14}/>
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function SocialFeed({ currentUserId }) {
  const [tab,        setTab]        = useState('feed')
  const [feed,       setFeed]       = useState([])
  const [following,  setFollowing]  = useState(new Set())
  const [myProfile,  setMyProfile]  = useState(null)
  const [traders,    setTraders]    = useState([])
  const [groups,     setGroups]     = useState([])
  const [notifs,     setNotifs]     = useState([])
  const [unread,     setUnread]     = useState(0)
  const [myBroadcasts, setMyBroadcasts] = useState([])
  const [loading,    setLoading]    = useState(false)
  const [filterSym,  setFilterSym]  = useState('')
  const [copyTrade,  setCopyTrade]  = useState(null)
  const [showCreateGroup, setShowCreateGroup] = useState(false)
  const [chatSymbol, setChatSymbol] = useState(null)
  const [editProfile,setEditProfile]= useState(false)
  const [profileForm,setProfileForm]= useState({ display_name:'', bio:'', is_public:true })
  const [savingProfile,setSavingProfile]=useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => { loadAll() }, [])
  useEffect(() => { if (tab === 'feed') loadFeed() }, [tab, filterSym])
  useEffect(() => { if (tab === 'traders') loadTraders() }, [tab])
  useEffect(() => { if (tab === 'groups') loadGroups() }, [tab])
  useEffect(() => { if (tab === 'my') loadMyBroadcasts() }, [tab])
  useEffect(() => { if (tab === 'notifications') loadNotifs() }, [tab])

  // Auto-refresh feed every 15s
  useEffect(() => {
    const iv = setInterval(() => { if (tab === 'feed') loadFeed() }, 15000)
    return () => clearInterval(iv)
  }, [tab, filterSym])

  async function loadAll() {
    await Promise.allSettled([loadFeed(), loadProfile(), loadFollowing(), loadUnread()])
  }

  async function loadFeed() {
    setLoading(true)
    try {
      const sym = filterSym ? `?symbol=${filterSym}` : ''
      const r   = await api.get(`/social/feed${sym}`)
      setFeed(r.data)
    } catch {
      try { const r = await api.get('/social/feed/public'); setFeed(r.data) } catch {}
    } finally { setLoading(false) }
  }

  async function loadProfile() {
    try {
      const r = await api.get('/social/profile/me')
      setMyProfile(r.data)
      setProfileForm({ display_name: r.data.display_name ?? '', bio: r.data.bio ?? '', is_public: r.data.is_public ?? true })
    } catch {}
  }

  async function loadFollowing() {
    try { const r = await api.get('/social/following'); setFollowing(new Set(r.data.map(f => f.leader_id))) } catch {}
  }

  async function loadTraders() {
    try { const r = await api.get('/social/traders'); setTraders(r.data) } catch {}
  }

  async function loadGroups() {
    try { const r = await api.get('/social/groups?limit=30'); setGroups(r.data) } catch {}
  }

  async function loadMyBroadcasts() {
    try { const r = await api.get('/social/feed/my-broadcasts'); setMyBroadcasts(r.data) } catch {}
  }

  async function loadNotifs() {
    try { const r = await api.get('/social/notifications'); setNotifs(r.data) } catch {}
  }

  async function loadUnread() {
    try { const r = await api.get('/social/notifications'); setUnread(r.data.filter(n => !n.is_read).length) } catch {}
  }

  async function markRead() {
    try { await api.post('/social/notifications/read'); setUnread(0) } catch {}
  }

  function flash(m) { setMsg(m); setTimeout(() => setMsg(''), 4000) }

  async function handleFollow(leaderId) {
    if (!leaderId) return
    try {
      if (following.has(leaderId)) {
        await api.delete(`/social/follow/${leaderId}`)
        setFollowing(f => { const n = new Set(f); n.delete(leaderId); return n })
        flash('Unfollowed')
      } else {
        await api.post(`/social/follow/${leaderId}`)
        setFollowing(f => new Set([...f, leaderId]))
        flash('✅ Following! Their trades will appear in your feed')
      }
    } catch(e) { flash('❌ ' + (e.response?.data?.detail ?? e.message)) }
  }

  async function joinGroup(id) {
    try {
      const r = await api.post(`/social/groups/${id}/join`)
      if (r.data.status === 'already_member') {
        flash('ℹ️ You are already a member of this group')
      } else {
        flash(`✅ Joined ${r.data.group || 'group'}!`)
      }
      loadGroups()
    } catch(e) {
      const msg = e.response?.data?.detail ?? e.message ?? 'Failed to join'
      flash('❌ ' + msg)
      console.error('Join group error:', e.response?.data || e)
    }
  }

  async function saveProfile() {
    setSavingProfile(true)
    try {
      await api.put('/social/profile/me', profileForm)
      flash('✅ Profile updated')
      loadProfile()
      setEditProfile(false)
    } catch { flash('❌ Failed to save') }
    finally { setSavingProfile(false) }
  }

  const TABS = [
    { id:'feed',          label:'📡 Live Feed'     },
    { id:'my',            label:'📋 My Trades'     },
    { id:'traders',       label:'👥 Traders'       },
    { id:'groups',        label:'🏘️ Groups'         },
    { id:'profile',       label:'👤 My Profile'    },
    { id:'notifications', label:`🔔 ${unread > 0 ? `(${unread})` : ''}` },
  ]

  return (
    <div className="space-y-4 max-w-3xl">

      {/* Modals */}
      {copyTrade       && <CopyModal trade={copyTrade} onClose={() => setCopyTrade(null)}/>}
      {showCreateGroup && <GroupModal onClose={() => setShowCreateGroup(false)} onCreated={() => { loadGroups(); flash('✅ Group created!') }}/>}

      {/* Flash message */}
      {msg && <div className="p-3 bg-dark-700 border border-dark-600 rounded-xl text-sm text-center">{msg}</div>}

      {/* Tabs */}
      <div className="flex gap-2 flex-wrap">
        {TABS.map(t => (
          <button key={t.id} onClick={() => { setTab(t.id); if (t.id === 'notifications') markRead() }}
            className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
              tab===t.id ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}>{t.label}</button>
        ))}
        <button onClick={() => { setLoading(true); loadAll().finally(() => setLoading(false)) }}
          className="ml-auto p-2 bg-dark-700 rounded-lg hover:bg-dark-600">
          <RefreshCw size={14} className={`text-gray-400 ${loading ? 'animate-spin' : ''}`}/>
        </button>
      </div>

      {/* ── LIVE FEED ──────────────────────────────────────────────────────── */}
      {tab === 'feed' && (
        <div className="space-y-4">
          {/* Symbol filter + chat */}
          <div className="flex gap-2">
            <input value={filterSym} onChange={e => setFilterSym(e.target.value.toUpperCase())}
              placeholder="Filter by symbol e.g. NVDA"
              className="flex-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2 text-white text-sm font-mono uppercase focus:outline-none focus:border-brand-500"/>
            {filterSym && (
              <>
                <button onClick={() => setChatSymbol(filterSym)}
                  className="px-3 py-2 bg-dark-700 text-gray-400 hover:text-white rounded-xl border border-dark-600 text-xs">
                  💬 Chat
                </button>
                <button onClick={() => setFilterSym('')} className="px-3 py-2 bg-dark-700 text-gray-400 rounded-xl">✕</button>
              </>
            )}
          </div>

          {/* Symbol chat popup */}
          {chatSymbol && (
            <SymbolChat symbol={chatSymbol} onClose={() => setChatSymbol(null)}/>
          )}

          {feed.length === 0 ? (
            <div className="text-center py-16 bg-dark-800 border border-dark-600 rounded-2xl">
              <p className="text-4xl mb-3">📡</p>
              <p className="font-bold text-white mb-1">No broadcasts yet</p>
              <p className="text-sm text-gray-400 mb-4">Follow traders or run the bot to see live trades here</p>
              <button onClick={() => setTab('traders')} className="px-4 py-2 bg-brand-500 text-dark-900 font-bold rounded-xl text-sm">
                Find Traders to Follow →
              </button>
            </div>
          ) : (
            feed.map(b => (
              <BroadcastCard key={b.id} b={b} myId={currentUserId}
                following={following} onLike={() => {}} onFollow={handleFollow} onCopy={setCopyTrade}/>
            ))
          )}
        </div>
      )}

      {/* ── MY BROADCASTS ──────────────────────────────────────────────────── */}
      {tab === 'my' && (
        <div className="space-y-3">
          <p className="text-sm text-gray-400">Every trade your bot executes is automatically broadcast here</p>
          {myBroadcasts.length === 0 ? (
            <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-2xl text-gray-500">
              <p className="text-3xl mb-2">📋</p>
              <p>No broadcasts yet — start the bot to auto-post trades</p>
            </div>
          ) : myBroadcasts.map(b => {
            const ac = ACTION_CONFIG[b.action] ?? ACTION_CONFIG.CLOSED
            return (
              <div key={b.id} className={`rounded-xl border p-4 ${ac.bg}`}>
                <div className="flex items-center gap-3 mb-2">
                  <span className="font-black text-white text-xl">{b.symbol}</span>
                  <span className={`text-sm font-bold ${ac.color}`}>{ac.icon} {ac.label}</span>
                  {b.pnl !== null && b.pnl !== undefined && (
                    <span className={`ml-auto font-black text-lg ${b.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {b.pnl >= 0 ? '+' : ''}${b.pnl?.toFixed(2)}
                    </span>
                  )}
                </div>
                <div className="flex gap-4 text-xs text-gray-400">
                  <span>@ ${b.price?.toFixed(2)}</span>
                  {b.stop_loss   && <span>SL ${b.stop_loss?.toFixed(2)}</span>}
                  {b.take_profit && <span>TP ${b.take_profit?.toFixed(2)}</span>}
                  {b.confidence  && <span>Conf {(b.confidence*100).toFixed(0)}%</span>}
                  <span className="ml-auto">❤️ {b.likes}  💬 {b.comments_count ?? 0}  📋 {b.copies_count ?? 0}</span>
                </div>
                <p className="text-xs text-gray-600 mt-1">{new Date(b.created_at).toLocaleString()}</p>
              </div>
            )
          })}
        </div>
      )}

      {/* ── TRADERS LEADERBOARD ────────────────────────────────────────────── */}
      {tab === 'traders' && (
        <div className="space-y-3">
          <p className="text-sm text-gray-400">Follow traders to see their bot trades in your live feed in real-time</p>
          {traders.length === 0 ? (
            <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-2xl text-gray-500">
              <Users size={32} className="mx-auto mb-2 opacity-40"/>
              <p>No public traders yet — make your profile public to appear here</p>
            </div>
          ) : traders.map((t, i) => (
            <div key={t.user_id} className="flex items-center gap-3 bg-dark-800 border border-dark-600 rounded-xl p-4">
              <span className="text-gray-600 w-6 font-bold text-center">#{i+1}</span>
              <Avatar name={t.display_name}/>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-bold text-white">{t.display_name}</p>
                  {t.is_copyable && <span className="text-xs bg-brand-500/20 text-brand-400 border border-brand-500/30 px-1.5 py-0.5 rounded-full">✓ Copyable</span>}
                </div>
                <div className="flex gap-3 text-xs text-gray-500 mt-0.5">
                  <span>{t.total_trades} trades</span>
                  <span className={t.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}>
                    {t.total_pnl >= 0 ? '+' : ''}${t.total_pnl?.toFixed(0)}
                  </span>
                  <span>{t.followers} followers</span>
                  <span>{t.days_tracked}d tracked</span>
                </div>
              </div>
              <div className="text-right mr-3">
                <p className={`font-black text-xl ${t.win_rate >= 60 ? 'text-green-400' : t.win_rate >= 50 ? 'text-yellow-400' : 'text-red-400'}`}>
                  {t.win_rate?.toFixed(0)}%
                </p>
                <p className="text-xs text-gray-500">win rate</p>
              </div>
              <button onClick={() => handleFollow(t.user_id)}
                className={`text-xs px-3 py-2 rounded-lg font-bold transition-all ${
                  following.has(t.user_id)
                    ? 'bg-dark-600 text-gray-400 hover:bg-red-900/20 hover:text-red-400'
                    : 'bg-brand-500/20 text-brand-400 border border-brand-500/30 hover:bg-brand-500/30'
                }`}>
                {following.has(t.user_id) ? 'Following' : '+ Follow'}
              </button>
            </div>
          ))}
        </div>
      )}

      {/* ── GROUPS ──────────────────────────────────────────────────────────── */}
      {tab === 'groups' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-400">Join trading groups to share strategies and discuss setups</p>
            <button onClick={() => setShowCreateGroup(true)}
              className="flex items-center gap-1.5 text-xs bg-brand-500/20 text-brand-400 border border-brand-500/30 px-3 py-2 rounded-lg hover:bg-brand-500/30">
              <Plus size={12}/> Create Group
            </button>
          </div>
          {groups.length === 0 ? (
            <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-2xl text-gray-500">
              <p className="text-3xl mb-2">🏘️</p>
              <p>No groups yet — create the first one!</p>
            </div>
          ) : groups.map(g => (
            <div key={g.id} className="bg-dark-800 border border-dark-600 rounded-xl p-4 flex items-center gap-4">
              <div className="w-10 h-10 rounded-xl bg-dark-700 flex items-center justify-center text-xl flex-shrink-0">
                {g.category === 'momentum' ? '⚡' : g.category === 'swing' ? '📈' : g.category === 'options' ? '🎯' : g.category === 'crypto' ? '₿' : '🏘️'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <p className="font-bold text-white">{g.name}</p>
                  <span className="text-xs bg-dark-700 text-gray-400 px-1.5 py-0.5 rounded capitalize">{g.category}</span>
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{g.description || 'No description'}</p>
                <p className="text-xs text-gray-600 mt-0.5">👥 {g.members} members</p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => joinGroup(g.id)}
                  className="text-xs px-3 py-2 bg-brand-500/20 text-brand-400 border border-brand-500/30 hover:bg-brand-500/30 rounded-lg font-bold transition-all">
                  Join
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── MY PROFILE ──────────────────────────────────────────────────────── */}
      {tab === 'profile' && myProfile && (
        <div className="space-y-4">
          {/* Stats */}
          <div className="bg-dark-800 border border-dark-600 rounded-2xl p-5">
            <div className="flex items-center gap-4 mb-4">
              <Avatar name={myProfile.display_name} size="lg"/>
              <div>
                <h3 className="font-black text-white text-lg">{myProfile.display_name}</h3>
                <p className="text-xs text-gray-400">{myProfile.bio || 'No bio yet'}</p>
                <div className="flex gap-2 mt-1">
                  <span className={`text-xs px-2 py-0.5 rounded-full border ${TIERS[myProfile.subscription]?.color ?? 'text-gray-400'} bg-dark-700 border-dark-600`}>
                    {TIERS[myProfile.subscription]?.label ?? 'Free'}
                  </span>
                  {myProfile.is_public ? (
                    <span className="text-xs text-green-400">🌐 Public</span>
                  ) : (
                    <span className="text-xs text-gray-500">🔒 Private</span>
                  )}
                </div>
              </div>
              <button onClick={() => setEditProfile(e => !e)}
                className="ml-auto text-xs bg-dark-700 hover:bg-dark-600 text-gray-400 px-3 py-1.5 rounded-lg">
                {editProfile ? 'Cancel' : '✏️ Edit'}
              </button>
            </div>

            {/* Stats grid */}
            <div className="grid grid-cols-3 gap-2 text-center text-xs">
              {[
                { label:'Win Rate',   value:`${myProfile.stats?.win_rate?.toFixed(0) ?? 0}%`, color: (myProfile.stats?.win_rate ?? 0) >= 60 ? 'text-green-400' : 'text-yellow-400' },
                { label:'Trades',     value: myProfile.stats?.total_trades ?? 0,              color:'text-white' },
                { label:'Total P&L',  value:`$${myProfile.stats?.total_pnl?.toFixed(0) ?? 0}`, color:'text-green-400' },
                { label:'Followers',  value: myProfile.stats?.followers ?? 0,                 color:'text-white' },
                { label:'Days Active',value: myProfile.stats?.days_tracked ?? 0,              color:'text-white' },
                { label:'Copyable',   value: myProfile.is_copyable ? '✅ Yes' : '❌ No',       color: myProfile.is_copyable ? 'text-green-400' : 'text-gray-500' },
              ].map(({ label, value, color }) => (
                <div key={label} className="bg-dark-700 rounded-xl p-2.5">
                  <p className="text-gray-500">{label}</p>
                  <p className={`font-bold ${color}`}>{value}</p>
                </div>
              ))}
            </div>

            {!myProfile.is_copyable && (
              <p className="text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-800/40 rounded-lg p-2.5 mt-3">
                ⚠️ To become copyable by others: need 30+ days of history and 60%+ win rate
              </p>
            )}
          </div>

          {/* Edit form */}
          {editProfile && (
            <div className="bg-dark-800 border border-dark-600 rounded-2xl p-5 space-y-3">
              <h4 className="font-bold text-white">Edit Profile</h4>
              <div>
                <label className="text-xs text-gray-400">Display Name</label>
                <input value={profileForm.display_name} onChange={e => setProfileForm(p => ({...p, display_name: e.target.value}))}
                  maxLength={50}
                  className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500"/>
              </div>
              <div>
                <label className="text-xs text-gray-400">Bio</label>
                <textarea value={profileForm.bio} onChange={e => setProfileForm(p => ({...p, bio: e.target.value}))}
                  rows={2} maxLength={300}
                  placeholder="Tell other traders about your strategy…"
                  className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-xl px-4 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500 resize-none"/>
              </div>
              <label className="flex items-center gap-3 cursor-pointer">
                <input type="checkbox" checked={profileForm.is_public}
                  onChange={e => setProfileForm(p => ({...p, is_public: e.target.checked}))}
                  className="w-4 h-4"/>
                <div>
                  <p className="text-sm text-white">Public Profile</p>
                  <p className="text-xs text-gray-500">Allow others to see your trades and follow you</p>
                </div>
              </label>
              <button onClick={saveProfile} disabled={savingProfile}
                className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl disabled:opacity-50">
                {savingProfile ? 'Saving…' : 'Save Profile'}
              </button>
            </div>
          )}

          {/* Subscription tiers */}
          <div className="bg-dark-800 border border-dark-600 rounded-2xl p-5">
            <h4 className="font-bold text-white mb-3">Subscription Tiers</h4>
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(TIERS).map(([key, tier]) => (
                <div key={key} className={`rounded-xl border p-3 text-center ${
                  myProfile.subscription === key ? 'border-brand-500 bg-brand-500/10' : 'border-dark-600 bg-dark-700'
                }`}>
                  <p className={`font-bold text-sm mb-2 ${tier.color}`}>{tier.label}</p>
                  {tier.features.map((f, i) => <p key={i} className="text-xs text-gray-500 mb-1">{f}</p>)}
                  {myProfile.subscription === key && <p className="text-xs text-brand-500 font-bold mt-2">✓ Current</p>}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── NOTIFICATIONS ───────────────────────────────────────────────────── */}
      {tab === 'notifications' && (
        <div className="space-y-2">
          {notifs.length === 0 ? (
            <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-2xl text-gray-500">
              <Bell size={32} className="mx-auto mb-2 opacity-40"/>
              <p>No notifications yet</p>
            </div>
          ) : notifs.map((n, i) => (
            <div key={i} className={`flex gap-3 p-3 rounded-xl border transition-colors ${
              n.is_read ? 'bg-dark-800 border-dark-600' : 'bg-dark-700 border-brand-500/30'
            }`}>
              <div className="text-xl flex-shrink-0">
                {n.type === 'trade_broadcast' ? '📡' : n.type === 'follow' ? '👥' : n.type === 'ban' ? '🚫' : '🔔'}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-bold text-white">{n.title}</p>
                <p className="text-xs text-gray-400">{n.body}</p>
                <p className="text-xs text-gray-600 mt-0.5">{new Date(n.created_at).toLocaleString()}</p>
              </div>
              {!n.is_read && <div className="w-2 h-2 rounded-full bg-brand-500 flex-shrink-0 mt-1.5"/>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

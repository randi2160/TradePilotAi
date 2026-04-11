import { useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { User, Shield, Bell, Key, LogOut, Save, TrendingUp } from 'lucide-react'

export default function UserProfile() {
  const { user, updateProfile, logout } = useAuth()
  const [tab,    setTab]    = useState('profile')
  const [saving, setSaving] = useState(false)
  const [msg,    setMsg]    = useState('')

  const [form, setForm] = useState({
    full_name:        user?.full_name        ?? '',
    phone:            user?.phone            ?? '',
    capital:          user?.capital          ?? 5000,
    daily_target_min: user?.daily_target_min ?? 100,
    daily_target_max: user?.daily_target_max ?? 250,
    max_daily_loss:   user?.max_daily_loss   ?? 150,
    risk_profile:     user?.risk_profile     ?? 'moderate',
    email_alerts:     user?.email_alerts     ?? true,
    alpaca_key:       '',
    alpaca_secret:    '',
    alpaca_mode:      user?.alpaca_mode      ?? 'paper',
  })

  function set(field) {
    return e => setForm(f => ({ ...f, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))
  }

  function flash(text) { setMsg(text); setTimeout(() => setMsg(''), 3000) }

  async function save() {
    setSaving(true)
    try {
      const payload = { ...form }
      if (!payload.alpaca_key)    delete payload.alpaca_key
      if (!payload.alpaca_secret) delete payload.alpaca_secret
      payload.capital          = parseFloat(payload.capital)
      payload.daily_target_min = parseFloat(payload.daily_target_min)
      payload.daily_target_max = parseFloat(payload.daily_target_max)
      payload.max_daily_loss   = parseFloat(payload.max_daily_loss)
      await updateProfile(payload)
      flash('✅ Profile saved!')
    } catch(e) {
      flash(`❌ ${e.response?.data?.detail ?? e.message}`)
    } finally { setSaving(false) }
  }

  const TABS = [
    { id: 'profile',  label: '👤 Profile',  icon: User   },
    { id: 'trading',  label: '📈 Trading',  icon: TrendingUp },
    { id: 'security', label: '🔐 Security', icon: Shield  },
    { id: 'alerts',   label: '🔔 Alerts',   icon: Bell    },
  ]

  return (
    <div className="max-w-2xl space-y-5">

      {/* Header */}
      <div className="flex items-center gap-4">
        <div className="w-14 h-14 rounded-full bg-brand-500 flex items-center justify-center text-dark-900 text-xl font-black">
          {user?.avatar_initials ?? user?.email?.slice(0,2).toUpperCase()}
        </div>
        <div>
          <h2 className="text-white font-bold text-lg">{user?.full_name || 'Trader'}</h2>
          <p className="text-gray-400 text-sm">{user?.email}</p>
          <p className="text-xs text-gray-500">Member since {new Date(user?.created_at).toLocaleDateString()}</p>
        </div>
        <button onClick={logout}
          className="ml-auto flex items-center gap-1.5 text-xs text-red-400 bg-red-900/20 hover:bg-red-900/40 border border-red-800/50 px-3 py-2 rounded-lg transition-colors">
          <LogOut size={13}/> Sign Out
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-dark-800 border border-dark-600 rounded-xl p-1">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex-1 py-2 rounded-lg text-xs font-medium transition-all ${
              tab === t.id ? 'bg-brand-500 text-dark-900' : 'text-gray-400 hover:text-white'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {msg && <div className="p-3 bg-dark-700 rounded-lg text-sm text-center">{msg}</div>}

      {/* ── Profile ───────────────────────────────────────────────────────────── */}
      {tab === 'profile' && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
          <h3 className="font-bold text-white">Personal Information</h3>
          {[
            { label: 'Full Name', field: 'full_name', type: 'text', ph: 'Your name' },
            { label: 'Phone',     field: 'phone',     type: 'tel',  ph: '+1 (555) 000-0000' },
          ].map(({ label, field, type, ph }) => (
            <div key={field}>
              <label className="block text-xs text-gray-400 mb-1">{label}</label>
              <input type={type} value={form[field]} onChange={set(field)} placeholder={ph}
                className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500"/>
            </div>
          ))}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Email (read-only)</label>
            <input type="email" value={user?.email ?? ''} readOnly
              className="w-full bg-dark-600 border border-dark-600 rounded-xl px-4 py-3 text-gray-400 text-sm cursor-not-allowed"/>
          </div>
        </div>
      )}

      {/* ── Trading ───────────────────────────────────────────────────────────── */}
      {tab === 'trading' && (
        <div className="space-y-4">
          <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
            <h3 className="font-bold text-white">Capital & Targets</h3>
            {[
              { label: 'Trading Capital ($)', field: 'capital',          min: 100 },
              { label: 'Min Daily Target ($)', field: 'daily_target_min', min: 10  },
              { label: 'Max Daily Target ($)', field: 'daily_target_max', min: 10  },
              { label: 'Max Daily Loss ($)',   field: 'max_daily_loss',   min: 10  },
            ].map(({ label, field, min }) => (
              <div key={field}>
                <label className="block text-xs text-gray-400 mb-1">{label}</label>
                <input type="number" value={form[field]} onChange={set(field)} min={min} step="10"
                  className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500"/>
              </div>
            ))}
            <div>
              <label className="block text-xs text-gray-400 mb-1">Risk Profile</label>
              <select value={form.risk_profile} onChange={set('risk_profile')}
                className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500">
                <option value="conservative">Conservative</option>
                <option value="moderate">Moderate</option>
                <option value="aggressive">Aggressive</option>
              </select>
            </div>
          </div>

          <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
            <h3 className="font-bold text-white">Alpaca API Keys</h3>
            <p className="text-xs text-gray-500">
              {user?.has_alpaca_keys ? '✅ Keys configured' : '❌ No keys set — using defaults from .env'}
            </p>
            {[
              { label: 'API Key ID',   field: 'alpaca_key',    ph: 'PKXXXXXXXXXX' },
              { label: 'Secret Key',   field: 'alpaca_secret', ph: '••••••••••••' },
            ].map(({ label, field, ph }) => (
              <div key={field}>
                <label className="block text-xs text-gray-400 mb-1">{label}</label>
                <input type="password" value={form[field]} onChange={set(field)} placeholder={ph}
                  className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500"/>
              </div>
            ))}
            <div>
              <label className="block text-xs text-gray-400 mb-1">Mode</label>
              <select value={form.alpaca_mode} onChange={set('alpaca_mode')}
                className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500">
                <option value="paper">Paper (fake money — safe)</option>
                <option value="live">Live (real money — caution!)</option>
              </select>
            </div>
          </div>
        </div>
      )}

      {/* ── Security ──────────────────────────────────────────────────────────── */}
      {tab === 'security' && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
          <h3 className="font-bold text-white">Security</h3>
          <div className="space-y-2 text-sm">
            {[
              ['JWT Authentication', '✅ Active'],
              ['Session Duration',   '24 hours'],
              ['Password',          '✅ Bcrypt hashed'],
              ['API Keys',          user?.has_alpaca_keys ? '✅ Stored encrypted' : 'Not set'],
              ['Last Login',        user?.last_login ? new Date(user.last_login).toLocaleString() : 'Just now'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between py-2 border-b border-dark-600">
                <span className="text-gray-400">{k}</span>
                <span className="text-white font-medium">{v}</span>
              </div>
            ))}
          </div>
          <div className="bg-yellow-900/20 border border-yellow-800/40 rounded-lg p-3 text-xs text-yellow-300">
            ⚠️ Never share your API keys. Use paper mode while testing.
          </div>
        </div>
      )}

      {/* ── Alerts ────────────────────────────────────────────────────────────── */}
      {tab === 'alerts' && (
        <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
          <h3 className="font-bold text-white">Email Alerts</h3>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-white">Enable Email Alerts</p>
              <p className="text-xs text-gray-400">Trade fills, daily target, stop losses</p>
            </div>
            <button onClick={() => setForm(f => ({ ...f, email_alerts: !f.email_alerts }))}
              className={`w-12 h-6 rounded-full transition-colors ${form.email_alerts ? 'bg-brand-500' : 'bg-dark-600'}`}>
              <div className={`w-5 h-5 bg-white rounded-full transition-transform mx-0.5 ${form.email_alerts ? 'translate-x-6' : 'translate-x-0'}`}/>
            </button>
          </div>
          <p className="text-xs text-gray-500">
            Sending to: <span className="text-white">{user?.email}</span>
          </p>
          <div className="bg-dark-700 rounded-lg p-3 text-xs text-gray-400 space-y-1">
            <p>📧 Trade opened → instant email</p>
            <p>📧 Trade closed with P&L → instant email</p>
            <p>📧 Daily target hit → instant email</p>
            <p>📧 Stop loss triggered → instant email</p>
            <p>📧 Daily summary → 4 PM ET every trading day</p>
          </div>
        </div>
      )}

      {/* Save button */}
      <button onClick={save} disabled={saving}
        className="w-full flex items-center justify-center gap-2 bg-brand-500 hover:bg-brand-600 text-dark-900 font-black py-3.5 rounded-xl transition-colors disabled:opacity-50">
        <Save size={16}/>
        {saving ? 'Saving…' : 'Save Changes'}
      </button>
    </div>
  )
}

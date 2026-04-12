import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../hooks/useAuth'
import {
  Shield, Users, FileText, Settings, Activity, AlertTriangle,
  CheckCircle, XCircle, RefreshCw, Search, ChevronDown, ChevronUp,
  Power, Edit, Eye, Download, ToggleLeft, ToggleRight, Save, Plus
} from 'lucide-react'

// ── Helpers ───────────────────────────────────────────────────────────────────

const SEV_COLOR = {
  info:     'text-blue-400   bg-blue-900/20   border-blue-800/40',
  warning:  'text-yellow-400 bg-yellow-900/20 border-yellow-800/40',
  critical: 'text-red-400    bg-red-900/20    border-red-800/40',
}

const EVENT_ICON = {
  'user.':     '👤',
  'legal.':    '📋',
  'trading.':  '📈',
  'copy.':     '📋',
  'security.': '🔒',
  'admin.':    '⚙️',
  'account.':  '👤',
}

function eventIcon(type) {
  for (const [prefix, icon] of Object.entries(EVENT_ICON)) {
    if (type.startsWith(prefix)) return icon
  }
  return '📌'
}

function timeAgo(iso) {
  if (!iso) return ''
  const mins = Math.floor((Date.now() - new Date(iso)) / 60000)
  if (mins < 1)    return 'just now'
  if (mins < 60)   return `${mins}m ago`
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`
  return new Date(iso).toLocaleDateString()
}

function formatDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false,
  })
}

function Card({ children, className = '' }) {
  return (
    <div className={`bg-dark-800 border border-dark-600 rounded-xl p-4 ${className}`}>
      {children}
    </div>
  )
}

function StatBox({ label, value, color = 'text-white', sub }) {
  return (
    <div className="bg-dark-700 border border-dark-600 rounded-xl p-4 text-center">
      <div className={`text-2xl font-black ${color} leading-none`}>{value}</div>
      <div className="text-xs text-gray-500 mt-1">{label}</div>
      {sub && <div className="text-xs text-gray-600 mt-0.5">{sub}</div>}
    </div>
  )
}

// ── Tab: Dashboard ────────────────────────────────────────────────────────────

function DashboardTab() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [killActive, setKillActive] = useState(false)
  const [killing, setKilling] = useState(false)

  useEffect(() => { load() }, [])

  async function load() {
    setLoading(true)
    try { const r = await api.get('/admin/dashboard'); setData(r.data) }
    catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  async function toggleKill() {
    if (!window.confirm(killActive
      ? 'Resume all trading? Users bots will be able to trade again.'
      : '⚠️ HALT ALL TRADING? This stops every user bot immediately. Are you sure?'
    )) return
    setKilling(true)
    try {
      const endpoint = killActive ? '/admin/kill-switch/release' : '/admin/kill-switch'
      await api.post(endpoint)
      setKillActive(k => !k)
      load()
    } catch (e) { alert('Failed: ' + e.message) }
    finally { setKilling(false) }
  }

  if (loading) return <div className="text-center py-12 text-gray-500"><RefreshCw size={24} className="animate-spin mx-auto mb-2"/>Loading dashboard…</div>
  if (!data) return <div className="text-center py-12 text-red-400">Failed to load — check if you are an admin</div>

  return (
    <div className="space-y-5">

      {/* Kill Switch */}
      <div className={`rounded-xl border p-4 flex items-center gap-4 ${
        killActive ? 'bg-red-900/20 border-red-600' : 'bg-dark-800 border-dark-600'
      }`}>
        <Power size={22} className={killActive ? 'text-red-400' : 'text-gray-400'}/>
        <div className="flex-1">
          <div className={`font-bold ${killActive ? 'text-red-400' : 'text-white'}`}>
            {killActive ? '🛑 ALL TRADING HALTED' : 'Global Kill Switch'}
          </div>
          <div className="text-xs text-gray-500">
            {killActive ? 'Click to resume all user bots' : 'Emergency halt — stops ALL trading across every user instantly'}
          </div>
        </div>
        <button onClick={toggleKill} disabled={killing}
          className={`px-4 py-2 rounded-lg font-bold text-sm transition-all disabled:opacity-50 ${
            killActive
              ? 'bg-green-900/30 text-green-400 border border-green-700 hover:bg-green-900/50'
              : 'bg-red-900/30 text-red-400 border border-red-700 hover:bg-red-900/50'
          }`}>
          {killing ? 'Processing…' : killActive ? '▶ Resume Trading' : '⏹ Halt All Trading'}
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <StatBox label="Total Users" value={data.users?.total} color="text-brand-500"/>
        <StatBox label="Active Users" value={data.users?.active} color="text-green-400"/>
        <StatBox label="Live Mode Users" value={data.users?.live ?? 0} color="text-yellow-400"/>
        <StatBox label="Total Trades" value={data.trades?.total}/>
        <StatBox label="Trades Today" value={data.trades?.today} color="text-brand-500"/>
        <StatBox label="Platform Status" value="Online" color="text-green-400"/>
      </div>

      {/* Recent Alerts */}
      <Card>
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle size={16} className="text-yellow-400"/>
          <span className="font-bold text-white text-sm">Recent Alerts</span>
        </div>
        {!data.recent_alerts?.length ? (
          <p className="text-sm text-gray-500 text-center py-4">No recent alerts — all clear</p>
        ) : (
          <div className="space-y-2">
            {data.recent_alerts.map((a, i) => (
              <div key={i} className={`flex items-start gap-3 p-2.5 rounded-lg border text-xs ${SEV_COLOR[a.severity] ?? SEV_COLOR.info}`}>
                <span>{eventIcon(a.event)}</span>
                <div className="flex-1">
                  <div className="font-bold">{a.event}</div>
                  <div className="opacity-70">User #{a.user_id} · {a.ip}</div>
                </div>
                <div className="opacity-60 flex-shrink-0">{timeAgo(a.timestamp)}</div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

// ── Tab: Users ────────────────────────────────────────────────────────────────

function UsersTab() {
  const [users, setUsers]     = useState([])
  const [total, setTotal]     = useState(0)
  const [search, setSearch]   = useState('')
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [audit, setAudit]     = useState([])
  const [consents, setConsents] = useState([])
  const [msg, setMsg]         = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const r = await api.get(`/admin/users?search=${search}&limit=50`)
      setUsers(r.data.users)
      setTotal(r.data.total)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [search])

  useEffect(() => { load() }, [load])

  async function loadUser(u) {
    setSelected(u)
    const [aRes, cRes] = await Promise.allSettled([
      api.get(`/admin/users/${u.id}/audit?limit=30`),
      api.get(`/admin/users/${u.id}/consents`),
    ])
    if (aRes.status === 'fulfilled') setAudit(aRes.value.data)
    if (cRes.status === 'fulfilled') setConsents(cRes.value.data)
  }

  async function action(userId, act) {
    try {
      await api.post(`/admin/users/${userId}/action`, { action: act })
      setMsg(`✅ Action "${act}" applied`)
      load()
      setTimeout(() => setMsg(''), 3000)
    } catch (e) { setMsg('❌ ' + (e.response?.data?.detail ?? e.message)) }
  }

  return (
    <div className="space-y-4">
      {msg && <div className="p-3 bg-dark-700 border border-dark-600 rounded-xl text-sm text-center">{msg}</div>}

      {/* Search */}
      <div className="flex gap-3">
        <div className="flex-1 relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"/>
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search by email…"
            className="w-full bg-dark-700 border border-dark-600 rounded-xl pl-9 pr-4 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500"/>
        </div>
        <button onClick={load} className="px-3 py-2 bg-dark-700 rounded-xl border border-dark-600 hover:bg-dark-600">
          <RefreshCw size={14} className={`text-gray-400 ${loading ? 'animate-spin' : ''}`}/>
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* User List */}
        <div className="space-y-2">
          <div className="text-xs text-gray-500">{total} users total</div>
          {users.map(u => (
            <div key={u.id}
              onClick={() => loadUser(u)}
              className={`p-3 rounded-xl border cursor-pointer transition-colors ${
                selected?.id === u.id
                  ? 'bg-brand-500/10 border-brand-500/40'
                  : 'bg-dark-800 border-dark-600 hover:border-dark-500'
              }`}>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-dark-600 flex items-center justify-center text-xs font-bold text-gray-300">
                  {u.email.slice(0, 2).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-bold text-white truncate">{u.email}</div>
                  <div className="text-xs text-gray-500">{u.full_name || 'No name'} · ${u.capital}</div>
                </div>
                <div className="flex gap-1">
                  {u.is_admin && <span className="text-xs bg-yellow-900/30 text-yellow-400 px-1.5 py-0.5 rounded">Admin</span>}
                  {u.live_mode && <span className="text-xs bg-red-900/30 text-red-400 px-1.5 py-0.5 rounded">Live</span>}
                  <span className={`text-xs px-1.5 py-0.5 rounded ${u.is_active ? 'bg-green-900/30 text-green-400' : 'bg-dark-600 text-gray-500'}`}>
                    {u.is_active ? 'Active' : 'Suspended'}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* User Detail */}
        {selected ? (
          <div className="space-y-3">
            <Card>
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-full bg-brand-500/30 flex items-center justify-center font-bold text-brand-400">
                  {selected.email.slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <div className="font-bold text-white">{selected.email}</div>
                  <div className="text-xs text-gray-500">ID #{selected.id} · {selected.subscription}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                {[
                  ['Capital',    `$${selected.capital}`],
                  ['Status',     selected.is_active ? '✅ Active' : '🚫 Suspended'],
                  ['Admin',      selected.is_admin ? '✅ Yes' : 'No'],
                  ['Live Mode',  selected.live_mode ? '🔴 On' : 'Off'],
                  ['Last Login', selected.last_login ? timeAgo(selected.last_login) : 'Never'],
                  ['Registered', selected.created_at ? new Date(selected.created_at).toLocaleDateString() : 'Unknown'],
                ].map(([k, v]) => (
                  <div key={k} className="bg-dark-700 rounded-lg p-2">
                    <div className="text-gray-500">{k}</div>
                    <div className="text-white font-medium mt-0.5">{v}</div>
                  </div>
                ))}
              </div>

              <div className="flex gap-2 flex-wrap">
                {selected.is_active
                  ? <button onClick={() => action(selected.id, 'suspend')}
                      className="text-xs px-3 py-1.5 bg-red-900/20 text-red-400 border border-red-800/40 rounded-lg hover:bg-red-900/40">
                      Suspend
                    </button>
                  : <button onClick={() => action(selected.id, 'unsuspend')}
                      className="text-xs px-3 py-1.5 bg-green-900/20 text-green-400 border border-green-800/40 rounded-lg hover:bg-green-900/40">
                      Unsuspend
                    </button>
                }
                {!selected.is_admin && (
                  <button onClick={() => action(selected.id, 'make_admin')}
                    className="text-xs px-3 py-1.5 bg-yellow-900/20 text-yellow-400 border border-yellow-800/40 rounded-lg hover:bg-yellow-900/40">
                    Make Admin
                  </button>
                )}
              </div>
            </Card>

            {/* Consents */}
            {consents.length > 0 && (
              <Card>
                <div className="text-xs font-bold text-green-400 mb-2">✅ Legal Consents on Record</div>
                {consents.map((c, i) => (
                  <div key={i} className="text-xs border-b border-dark-600 pb-2 mb-2 last:border-0 last:mb-0 last:pb-0">
                    <div className="flex justify-between">
                      <span className="font-bold text-white">{c.consent_type}</span>
                      <span className="text-gray-500">v{c.doc_version}</span>
                    </div>
                    <div className="text-gray-500">IP: {c.ip} · {timeAgo(c.timestamp)}</div>
                    <div className="text-gray-600 font-mono truncate">sig: {c.sig_hash?.slice(0, 20)}…</div>
                  </div>
                ))}
              </Card>
            )}

            {/* Audit Trail */}
            {audit.length > 0 && (
              <Card>
                <div className="text-xs font-bold text-brand-500 mb-2">Audit Trail</div>
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {audit.map((a, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs py-1 border-b border-dark-700 last:border-0">
                      <span>{eventIcon(a.event)}</span>
                      <span className="text-gray-400 flex-1">{a.event}</span>
                      <span className="text-gray-600">{timeAgo(a.timestamp)}</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center h-48 text-gray-600 text-sm">
            Select a user to view details
          </div>
        )}
      </div>
    </div>
  )
}

// ── Tab: Audit Logs ───────────────────────────────────────────────────────────

function AuditTab() {
  const [logs,      setLogs]      = useState([])
  const [total,     setTotal]     = useState(0)
  const [severity,  setSeverity]  = useState('')
  const [loading,   setLoading]   = useState(true)
  const [verified,  setVerified]  = useState(null)
  const [verifying, setVerifying] = useState(false)
  const [selected,  setSelected]  = useState(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => { load() }, [severity])

  async function load() {
    setLoading(true)
    try {
      const r = await api.get(`/admin/audit-logs?limit=100&severity=${severity}`)
      setLogs(r.data.logs)
      setTotal(r.data.total)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  async function verify() {
    setVerifying(true)
    try { const r = await api.get('/admin/audit-logs/verify'); setVerified(r.data) }
    catch (e) { console.error(e) }
    finally { setVerifying(false) }
  }

  function exportTxt() {
    const lines = logs.map(l =>
      `[${l.timestamp}] [${l.severity.toUpperCase()}] ${l.event}\n` +
      `  User: ${l.user_email || 'N/A'} (#${l.user_id || 'N/A'}) | IP: ${l.ip || 'N/A'}\n` +
      `  Payload: ${JSON.stringify(l.payload || {})}\n` +
      `  Hash: ${l.hash}\n` +
      `  Prev:  ${l.prev_hash}\n` +
      `${'─'.repeat(80)}`
    ).join('\n')

    const header = `MORVIQ AI — AUDIT LOG EXPORT\nExported: ${new Date().toISOString()}\nTotal entries: ${total}\nShowing: ${logs.length}\n${'═'.repeat(80)}\n\n`
    const blob = new Blob([header + lines], { type: 'text/plain' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `morviq-audit-${new Date().toISOString().slice(0,10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  function exportCsv() {
    const header = 'timestamp,severity,event,user_id,user_email,ip,payload,hash,prev_hash\n'
    const rows   = logs.map(l =>
      [l.timestamp, l.severity, l.event, l.user_id || '', l.user_email || '',
       l.ip || '', JSON.stringify(l.payload || {}).replace(/"/g, '""'),
       l.hash, l.prev_hash
      ].map(v => `"${v}"`).join(',')
    ).join('\n')
    const blob = new Blob([header + rows], { type: 'text/csv' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `morviq-audit-${new Date().toISOString().slice(0,10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  function exportPdf() {
    const win = window.open('', '_blank')
    const rows = logs.map(l => `
      <tr style="border-bottom:1px solid #e5e7eb">
        <td style="padding:6px 8px;font-size:11px;white-space:nowrap">${new Date(l.timestamp).toLocaleString()}</td>
        <td style="padding:6px 8px">
          <span style="background:${l.severity==='critical'?'#fee2e2':l.severity==='warning'?'#fef9c3':'#dbeafe'};
            color:${l.severity==='critical'?'#991b1b':l.severity==='warning'?'#854d0e':'#1e40af'};
            padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600">
            ${l.severity.toUpperCase()}
          </span>
        </td>
        <td style="padding:6px 8px;font-size:11px;font-weight:600">${l.event}</td>
        <td style="padding:6px 8px;font-size:11px">${l.user_email || l.user_id || '—'}</td>
        <td style="padding:6px 8px;font-size:10px;color:#6b7280">${l.ip || '—'}</td>
        <td style="padding:6px 8px;font-size:10px;font-family:monospace;color:#6b7280">${l.hash?.slice(0,12)}…</td>
      </tr>`
    ).join('')

    win.document.write(`<!DOCTYPE html><html><head>
      <title>Morviq AI — Audit Log Export</title>
      <style>
        body{font-family:Arial,sans-serif;margin:0;padding:20px;color:#111}
        h1{font-size:18px;margin-bottom:4px}
        .meta{color:#666;font-size:12px;margin-bottom:20px}
        table{width:100%;border-collapse:collapse;font-size:12px}
        th{background:#f9fafb;padding:8px;text-align:left;font-size:11px;color:#374151;border-bottom:2px solid #e5e7eb}
        tr:nth-child(even){background:#f9fafb}
        @media print{.no-print{display:none}}
      </style>
    </head><body>
      <div style="display:flex;justify-content:space-between;align-items:start">
        <div>
          <h1>🛡️ Morviq AI — Audit Log Export</h1>
          <div class="meta">Exported: ${new Date().toLocaleString()} · Total shown: ${logs.length} of ${total} entries · Chain status: ${verified?.intact ? '✅ Verified intact' : '⚠️ Not verified'}</div>
        </div>
        <button class="no-print" onclick="window.print()" style="padding:8px 16px;background:#1d4ed8;color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px">🖨️ Print / Save PDF</button>
      </div>
      <table>
        <thead><tr>
          <th>Timestamp</th><th>Severity</th><th>Event</th><th>User</th><th>IP</th><th>Hash</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <div style="margin-top:20px;padding:12px;background:#f9fafb;border:1px solid #e5e7eb;border-radius:6px;font-size:11px;color:#6b7280">
        This audit log is hash-chained. Each entry's hash includes the previous entry's hash, making tampering detectable.
        Document generated by Morviq AI Compliance System on ${new Date().toISOString()}.
      </div>
    </body></html>`)
    win.document.close()
  }

  return (
    <div className="space-y-4">

      {/* Toolbar */}
      <div className="flex gap-2 items-center flex-wrap">
        <select value={severity} onChange={e => setSeverity(e.target.value)}
          className="bg-dark-700 border border-dark-600 rounded-xl px-3 py-2 text-sm text-white focus:outline-none">
          <option value="">All Severities</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="critical">Critical</option>
        </select>
        <button onClick={load} className="px-3 py-2 bg-dark-700 rounded-xl border border-dark-600 hover:bg-dark-600">
          <RefreshCw size={14} className={`text-gray-400 ${loading ? 'animate-spin' : ''}`}/>
        </button>
        <div className="ml-auto flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500">{total} total events</span>
          <button onClick={verify} disabled={verifying}
            className="flex items-center gap-1.5 text-xs px-3 py-2 bg-dark-700 hover:bg-dark-600 text-gray-400 border border-dark-600 rounded-xl">
            <Shield size={12}/> {verifying ? 'Verifying…' : 'Verify Chain'}
          </button>
          {/* Export buttons */}
          <button onClick={exportTxt}
            className="flex items-center gap-1.5 text-xs px-3 py-2 bg-dark-700 hover:bg-dark-600 text-gray-400 border border-dark-600 rounded-xl">
            <Download size={12}/> TXT
          </button>
          <button onClick={exportCsv}
            className="flex items-center gap-1.5 text-xs px-3 py-2 bg-dark-700 hover:bg-dark-600 text-gray-400 border border-dark-600 rounded-xl">
            <Download size={12}/> CSV
          </button>
          <button onClick={exportPdf}
            className="flex items-center gap-1.5 text-xs px-3 py-2 bg-brand-500/20 hover:bg-brand-500/30 text-brand-400 border border-brand-500/30 rounded-xl font-bold">
            <Download size={12}/> PDF
          </button>
        </div>
      </div>

      {/* Chain Verification */}
      {verified && (
        <div className={`p-3 rounded-xl border text-sm flex items-center gap-3 ${
          verified.intact ? 'bg-green-900/20 border-green-800/40 text-green-400' : 'bg-red-900/20 border-red-800/40 text-red-400'
        }`}>
          {verified.intact ? <CheckCircle size={16}/> : <XCircle size={16}/>}
          <div>
            {verified.intact
              ? `✅ Chain intact — ${verified.checked} entries verified, no tampering detected`
              : `❌ Chain BROKEN at entry #${verified.broken_at} — possible tampering!`}
          </div>
          <span className="ml-auto text-xs opacity-60">{timeAgo(verified.verified_at)}</span>
        </div>
      )}

      {/* Split view: list + detail */}
      <div className={`grid gap-4 ${selected ? 'grid-cols-2' : 'grid-cols-1'}`}>
        {/* Log list */}
        <div className="space-y-1.5 max-h-[600px] overflow-y-auto">
          {logs.map((l, i) => (
            <div key={i}
              onClick={() => setSelected(selected?.id === l.id ? null : l)}
              className={`flex items-start gap-3 p-3 rounded-xl border text-xs cursor-pointer transition-all ${
                selected?.id === l.id
                  ? 'ring-1 ring-brand-500 ' + (SEV_COLOR[l.severity] ?? SEV_COLOR.info)
                  : (SEV_COLOR[l.severity] ?? SEV_COLOR.info) + ' hover:opacity-80'
              }`}>
              <span className="text-base flex-shrink-0">{eventIcon(l.event)}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold">{l.event}</span>
                  {l.user_email && <span className="opacity-60 truncate">{l.user_email}</span>}
                </div>
                <div className="opacity-50 mt-0.5 truncate">{l.ip} · <span className="font-mono">{formatDateTime(l.timestamp)}</span></div>
              </div>
              <span className={`px-1.5 py-0.5 rounded font-bold flex-shrink-0 ${SEV_COLOR[l.severity]}`}>
                {l.severity}
              </span>
            </div>
          ))}
          {!loading && logs.length === 0 && (
            <div className="text-center py-12 text-gray-500">No audit logs found</div>
          )}
        </div>

        {/* Individual log detail */}
        {selected && (
          <div className="bg-dark-800 border border-dark-600 rounded-xl p-4 space-y-3 self-start sticky top-0">
            <div className="flex items-center justify-between">
              <span className="font-bold text-white text-sm">Log Detail</span>
              <button onClick={() => setSelected(null)} className="text-gray-500 hover:text-white text-xs">✕ Close</button>
            </div>

            <div className={`p-2.5 rounded-lg border text-xs font-bold ${SEV_COLOR[selected.severity]}`}>
              {eventIcon(selected.event)} {selected.event}
            </div>

            <div className="space-y-2 text-xs">
              {[
                ['Timestamp',  formatDateTime(selected.timestamp)],
                ['Severity',   selected.severity],
                ['User ID',    selected.user_id || '—'],
                ['Email',      selected.user_email || '—'],
                ['IP Address', selected.ip || '—'],
              ].map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <span className="text-gray-500 w-24 flex-shrink-0">{k}</span>
                  <span className="text-white font-medium">{v}</span>
                </div>
              ))}
            </div>

            {/* Payload */}
            {Object.keys(selected.payload || {}).length > 0 && (
              <div>
                <div className="text-xs text-gray-500 mb-1">Payload</div>
                <pre className="bg-dark-700 rounded-lg p-3 text-xs text-gray-300 overflow-auto max-h-32 font-mono whitespace-pre-wrap">
                  {JSON.stringify(selected.payload, null, 2)}
                </pre>
              </div>
            )}

            {/* Hash chain */}
            <div className="border-t border-dark-600 pt-3 space-y-1">
              <div className="text-xs text-gray-500 mb-1">Hash Chain (tamper-proof)</div>
              <div className="text-xs font-mono">
                <div className="text-gray-600">prev: <span className="text-gray-400">{selected.prev_hash?.slice(0,32)}…</span></div>
                <div className="text-green-400">this: <span>{selected.hash?.slice(0,32)}…</span></div>
              </div>
            </div>

            {/* Export single entry */}
            <button
              onClick={() => {
                const text = `MORVIQ AI — AUDIT LOG ENTRY\n${'═'.repeat(40)}\nEvent:     ${selected.event}\nTimestamp: ${selected.timestamp}\nSeverity:  ${selected.severity}\nUser:      ${selected.user_email || selected.user_id || 'N/A'}\nIP:        ${selected.ip || 'N/A'}\nPayload:   ${JSON.stringify(selected.payload || {}, null, 2)}\n\nHash Chain:\n  Prev: ${selected.prev_hash}\n  This: ${selected.hash}\n`
                const blob = new Blob([text], { type: 'text/plain' })
                const url  = URL.createObjectURL(blob)
                const a    = document.createElement('a')
                a.href     = url
                a.download = `audit-entry-${selected.id}.txt`
                a.click()
                URL.revokeObjectURL(url)
              }}
              className="w-full text-xs py-2 bg-dark-700 hover:bg-dark-600 text-gray-400 border border-dark-600 rounded-lg flex items-center justify-center gap-1.5">
              <Download size={11}/> Export This Entry
            </button>
          </div>
        )}
      </div>
    </div>
  )
}


// ── Tab: Legal Documents ──────────────────────────────────────────────────────

const DOC_TYPES = [
  { value: 'tos',              label: 'Terms of Service',          badge: 'Consent Flow',  color: 'text-brand-400'  },
  { value: 'risk',             label: 'Risk Disclosure',           badge: 'Consent Flow',  color: 'text-red-400'    },
  { value: 'auto_trading',     label: 'Auto-Trading Authorization', badge: 'Consent Flow',  color: 'text-yellow-400' },
  { value: 'privacy',          label: 'Privacy Policy',            badge: 'Legal',         color: 'text-blue-400'   },
  { value: 'cookies',          label: 'Cookie Policy',             badge: 'Legal',         color: 'text-gray-400'   },
  { value: 'about',            label: 'About Us',                  badge: 'Content',       color: 'text-green-400'  },
  { value: 'suitability',      label: 'Suitability Questions',     badge: 'Consent Flow',  color: 'text-purple-400' },
  { value: 'disclaimer',       label: 'Trading Disclaimer',        badge: 'Legal',         color: 'text-red-400'    },
]

const CONSENT_FLOW_DOCS = ['tos', 'risk', 'auto_trading', 'suitability']

function RichEditor({ value, onChange }) {
  const editorRef  = useRef(null)
  const quillRef   = useRef(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    // Load Quill CSS
    if (!document.getElementById('quill-css')) {
      const link = document.createElement('link')
      link.id   = 'quill-css'
      link.rel  = 'stylesheet'
      link.href = 'https://cdnjs.cloudflare.com/ajax/libs/quill/1.3.7/quill.snow.min.css'
      document.head.appendChild(link)
    }
    // Load Quill JS
    if (window.Quill) { initQuill(); return }
    const script   = document.createElement('script')
    script.src     = 'https://cdnjs.cloudflare.com/ajax/libs/quill/1.3.7/quill.min.js'
    script.onload  = initQuill
    document.head.appendChild(script)

    function initQuill() {
      if (!editorRef.current || quillRef.current) return
      quillRef.current = new window.Quill(editorRef.current, {
        theme: 'snow',
        modules: {
          toolbar: [
            [{ header: [1, 2, 3, false] }],
            ['bold', 'italic', 'underline', 'strike'],
            [{ color: [] }, { background: [] }],
            [{ list: 'ordered' }, { list: 'bullet' }],
            [{ indent: '-1' }, { indent: '+1' }],
            [{ align: [] }],
            ['link', 'image'],
            ['blockquote', 'code-block'],
            ['clean'],
          ],
        },
        placeholder: 'Write your legal document here…',
      })

      // Set initial content
      if (value) quillRef.current.root.innerHTML = value

      // Listen for changes
      quillRef.current.on('text-change', () => {
        onChange(quillRef.current.root.innerHTML)
      })

      setReady(true)
    }

    return () => { quillRef.current = null }
  }, [])

  // Sync external value changes (e.g. loading existing doc)
  useEffect(() => {
    if (quillRef.current && value !== quillRef.current.root.innerHTML) {
      quillRef.current.root.innerHTML = value || ''
    }
  }, [value])

  return (
    <div>
      <style>{`
        .ql-toolbar { background:#1a2740; border:1px solid #374151; border-radius:10px 10px 0 0; }
        .ql-container { background:#111d33; border:1px solid #374151; border-top:none; border-radius:0 0 10px 10px; min-height:320px; font-size:14px; }
        .ql-editor { color:#e5e7eb; min-height:300px; }
        .ql-editor.ql-blank::before { color:#6b7280; }
        .ql-stroke { stroke:#9ca3af !important; }
        .ql-fill { fill:#9ca3af !important; }
        .ql-picker-label { color:#9ca3af !important; }
        .ql-picker-options { background:#1a2740; border-color:#374151; }
        .ql-picker-item { color:#e5e7eb; }
        .ql-toolbar button:hover .ql-stroke, .ql-toolbar button.ql-active .ql-stroke { stroke:#00C896 !important; }
        .ql-toolbar button:hover .ql-fill, .ql-toolbar button.ql-active .ql-fill { fill:#00C896 !important; }
        .ql-snow .ql-tooltip { background:#1a2740; border-color:#374151; color:#e5e7eb; }
        .ql-snow .ql-tooltip input { background:#111d33; border-color:#374151; color:#e5e7eb; }
        .ql-editor h1,.ql-editor h2,.ql-editor h3 { color:#fff; }
        .ql-editor a { color:#00C896; }
        .ql-editor blockquote { border-left:3px solid #374151; color:#9ca3af; }
      `}</style>
      <div ref={editorRef}/>
      {!ready && (
        <div className="text-xs text-gray-500 text-center py-4">Loading editor…</div>
      )}
    </div>
  )
}

function LegalTab() {
  const [docs, setDocs]       = useState([])
  const [editing, setEditing] = useState(null)
  const [form, setForm]       = useState({
    doc_type: 'tos', title: '', content: '',
    show_in_footer: false, show_in_nav: false, show_in_signup: false, footer_order: 0
  })
  const [saving, setSaving]   = useState(false)
  const [msg, setMsg]         = useState('')

  useEffect(() => { load() }, [])

  async function load() {
    try { const r = await api.get('/admin/legal'); setDocs(r.data) } catch (e) { console.error(e) }
  }

  function startEdit(doc) {
    setEditing(doc.id)
    setForm({
      doc_type:       doc.doc_type,
      title:          doc.title,
      content:        doc.content,
      show_in_footer: doc.show_in_footer || false,
      show_in_nav:    doc.show_in_nav    || false,
      show_in_signup: doc.show_in_signup || false,
      footer_order:   doc.footer_order   || 0,
    })
  }

  function startNew() {
    setEditing('new')
    setForm({ doc_type: 'tos', title: '', content: '', show_in_footer: false, show_in_nav: false, show_in_signup: false, footer_order: 0 })
  }

  async function save() {
    if (!form.title.trim() || !form.content.trim()) {
      setMsg('❌ Title and content are required')
      return
    }
    setSaving(true)
    try {
      await api.post('/admin/legal', form)
      setMsg('✅ Document published — new version is live')
      setEditing(null)
      load()
    } catch (e) { setMsg('❌ ' + (e.response?.data?.detail ?? e.message)) }
    finally { setSaving(false); setTimeout(() => setMsg(''), 4000) }
  }

  // Group by doc_type, show only active
  const active = docs.filter(d => d.is_active)
  const history = docs.filter(d => !d.is_active)

  return (
    <div className="space-y-4">
      {msg && <div className="p-3 bg-dark-700 border border-dark-600 rounded-xl text-sm text-center">{msg}</div>}

      {editing ? (
        /* Editor */
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-white">{editing === 'new' ? '+ New Document' : 'Edit Document'}</h3>
            <button onClick={() => setEditing(null)} className="text-xs text-gray-500 hover:text-white">Cancel</button>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-400">Document Type</label>
              <select value={form.doc_type} onChange={e => setForm(f => ({...f, doc_type: e.target.value}))}
                className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-xl px-3 py-2.5 text-white text-sm focus:outline-none">
                {DOC_TYPES.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400">Title</label>
              <input value={form.title} onChange={e => setForm(f => ({...f, title: e.target.value}))}
                className="w-full mt-1 bg-dark-700 border border-dark-600 rounded-xl px-3 py-2.5 text-white text-sm focus:outline-none focus:border-brand-500"/>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-400 mb-1 block">Content — Rich Text Editor</label>
            <RichEditor
              value={form.content}
              onChange={content => setForm(f => ({...f, content}))}
            />
            <div className="mt-1 flex items-center gap-2">
              <button
                onClick={() => {
                  const win = window.open('', '_blank')
                  win.document.write(`<html><head><title>Preview</title></head><body style="font-family:sans-serif;padding:2rem;max-width:800px;margin:0 auto">${form.content}</body></html>`)
                  win.document.close()
                }}
                className="text-xs text-brand-400 hover:underline flex items-center gap-1"
              >
                <Eye size={11}/> Preview in new tab
              </button>
              <span className="text-xs text-gray-600">· Supports headings, bold, italic, lists, links, images</span>
            </div>
          </div>
          <div className="bg-dark-700 border border-dark-600 rounded-xl p-4 space-y-3">
            <div className="text-xs font-bold text-white mb-2">📍 Visibility — Where should this document appear?</div>
            <div className="grid grid-cols-3 gap-3">
              <label className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                form.show_in_footer ? 'bg-brand-500/10 border-brand-500/40' : 'bg-dark-800 border-dark-600 hover:border-dark-500'
              }`}>
                <input type="checkbox" checked={form.show_in_footer}
                  onChange={e => setForm(f => ({...f, show_in_footer: e.target.checked}))}
                  className="mt-0.5 w-4 h-4 flex-shrink-0"/>
                <div>
                  <div className="text-sm font-bold text-white">Footer</div>
                  <div className="text-xs text-gray-500 mt-0.5">Link appears in site footer for all users</div>
                </div>
              </label>
              <label className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                form.show_in_nav ? 'bg-brand-500/10 border-brand-500/40' : 'bg-dark-800 border-dark-600 hover:border-dark-500'
              }`}>
                <input type="checkbox" checked={form.show_in_nav}
                  onChange={e => setForm(f => ({...f, show_in_nav: e.target.checked}))}
                  className="mt-0.5 w-4 h-4 flex-shrink-0"/>
                <div>
                  <div className="text-sm font-bold text-white">Navigation</div>
                  <div className="text-xs text-gray-500 mt-0.5">Link appears in top navigation bar</div>
                </div>
              </label>
              <label className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                form.show_in_signup ? 'bg-brand-500/10 border-brand-500/40' : 'bg-dark-800 border-dark-600 hover:border-dark-500'
              }`}>
                <input type="checkbox" checked={form.show_in_signup}
                  onChange={e => setForm(f => ({...f, show_in_signup: e.target.checked}))}
                  className="mt-0.5 w-4 h-4 flex-shrink-0"/>
                <div>
                  <div className="text-sm font-bold text-white">Signup Flow</div>
                  <div className="text-xs text-gray-500 mt-0.5">Required reading during registration</div>
                </div>
              </label>
            </div>
            {form.show_in_footer && (
              <div className="flex items-center gap-3">
                <label className="text-xs text-gray-400 flex-shrink-0">Footer order:</label>
                <input type="number" value={form.footer_order} min={0} max={20}
                  onChange={e => setForm(f => ({...f, footer_order: parseInt(e.target.value) || 0}))}
                  className="w-20 bg-dark-800 border border-dark-600 rounded-lg px-2 py-1 text-white text-sm"/>
                <span className="text-xs text-gray-500">Lower = appears first in footer</span>
              </div>
            )}
            {!form.show_in_footer && !form.show_in_nav && !form.show_in_signup && (
              <div className="text-xs text-yellow-400 bg-yellow-900/20 border border-yellow-800/40 rounded-lg p-2">
                ⚠️ No visibility selected — document will be hidden (useful for internal drafts or signup-only docs)
              </div>
            )}
          </div>
          <button onClick={save} disabled={saving}
            className="flex items-center gap-2 px-5 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl text-sm disabled:opacity-50">
            <Save size={14}/> {saving ? 'Publishing…' : 'Publish New Version'}
          </button>
        </div>
      ) : (
        /* Doc List */
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-white">Legal Documents</h3>
            <button onClick={startNew}
              className="flex items-center gap-1.5 text-xs px-3 py-2 bg-brand-500/20 text-brand-400 border border-brand-500/30 rounded-lg hover:bg-brand-500/30">
              <Plus size={12}/> New Document
            </button>
          </div>

          {/* Consent Flow Status */}
          <div className="bg-dark-700 border border-dark-600 rounded-xl p-3">
            <div className="text-xs font-bold text-white mb-2">
              📋 Consent Flow Documents — Users must read these during signup
            </div>
            <div className="grid grid-cols-2 gap-2">
              {CONSENT_FLOW_DOCS.map(dt => {
                const doc = active.find(d => d.doc_type === dt)
                const type = DOC_TYPES.find(t => t.value === dt)
                return (
                  <div key={dt} className={`flex items-center gap-2 p-2 rounded-lg border text-xs ${
                    doc ? 'bg-green-900/10 border-green-800/30' : 'bg-red-900/10 border-red-800/30'
                  }`}>
                    <span className={doc ? 'text-green-400' : 'text-red-400'}>{doc ? '✅' : '❌'}</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-bold text-white truncate">{type?.label}</div>
                      {doc ? (
                        <div className="text-gray-500 truncate">v{doc.version} · {timeAgo(doc.updated_at)}</div>
                      ) : (
                        <div className="text-red-400">Missing — users will see hardcoded text</div>
                      )}
                    </div>
                    {!doc && (
                      <button onClick={() => { startNew(); setForm(f => ({...f, doc_type: dt})) }}
                        className="text-xs px-1.5 py-0.5 bg-red-900/30 text-red-400 border border-red-800/40 rounded hover:bg-red-900/50 flex-shrink-0">
                        Add
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {active.map(d => (
            <Card key={d.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="font-bold text-white">{d.title}</span>
                    <span className="text-xs bg-green-900/30 text-green-400 px-1.5 py-0.5 rounded">Active</span>
                    <span className="text-xs text-gray-600">v{d.version}</span>
                    {CONSENT_FLOW_DOCS.includes(d.doc_type) && (
                      <span className="text-xs bg-brand-500/20 text-brand-400 border border-brand-500/30 px-1.5 py-0.5 rounded">📋 Consent Flow</span>
                    )}
                    {d.show_in_footer && <span className="text-xs bg-blue-900/30 text-blue-400 border border-blue-800/40 px-1.5 py-0.5 rounded">📍 Footer</span>}
                    {d.show_in_nav    && <span className="text-xs bg-purple-900/30 text-purple-400 border border-purple-800/40 px-1.5 py-0.5 rounded">🔗 Nav</span>}
                    {d.show_in_signup && <span className="text-xs bg-yellow-900/30 text-yellow-400 border border-yellow-800/40 px-1.5 py-0.5 rounded">📋 Signup</span>}
                    {!d.show_in_footer && !d.show_in_nav && !d.show_in_signup && !CONSENT_FLOW_DOCS.includes(d.doc_type) && (
                      <span className="text-xs bg-dark-700 text-gray-500 px-1.5 py-0.5 rounded">Hidden</span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500">
                    <span className={DOC_TYPES.find(t => t.value === d.doc_type)?.color || 'text-gray-400'}>
                      {DOC_TYPES.find(t => t.value === d.doc_type)?.label}
                    </span>
                    {' · '}Hash: <span className="font-mono">{d.content_hash?.slice(0, 16)}…</span>
                    {' · '}Updated: <span className="font-mono">{formatDateTime(d.updated_at)}</span>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => startEdit(d)}
                    className="text-xs px-3 py-1.5 bg-dark-700 hover:bg-dark-600 text-gray-400 hover:text-white border border-dark-600 rounded-lg flex items-center gap-1">
                    <Edit size={11}/> Edit
                  </button>
                </div>
              </div>
            </Card>
          ))}

          {active.length === 0 && (
            <div className="text-center py-8 text-gray-500 text-sm">
              No legal documents yet — click "New Document" to create your first
            </div>
          )}

          {history.length > 0 && (
            <div>
              <div className="text-xs text-gray-600 mb-2">Version History ({history.length} old versions kept for legal record)</div>
              {history.slice(0, 5).map(d => (
                <div key={d.id} className="flex items-center gap-3 py-2 border-b border-dark-700 last:border-0 text-xs">
                  <span className="text-gray-600">{d.doc_type}</span>
                  <span className="text-gray-500 flex-1">{d.title}</span>
                  <span className="text-gray-600">v{d.version}</span>
                  <span className="text-gray-600">{timeAgo(d.updated_at)}</span>
                  <span className="bg-dark-600 text-gray-500 px-1.5 py-0.5 rounded">Archived</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Tab: Platform Settings ────────────────────────────────────────────────────

const DEFAULT_SETTINGS = [
  { key: 'company_name',       value: 'Morviq AI',          desc: 'Company name',         public: true },
  { key: 'support_email',      value: 'hello@morviqai.com', desc: 'Support email',         public: true },
  { key: 'tos_version',        value: '2026-04-11',         desc: 'Current ToS version',   public: true },
  { key: 'max_daily_loss_default', value: '150',             desc: 'Default max daily loss ($)', public: false },
  { key: 'global_trading_halted', value: 'false',           desc: 'Emergency kill switch', public: false },
  { key: 'copy_min_days',      value: '30',                 desc: 'Min days to be copyable', public: false },
  { key: 'copy_min_winrate',   value: '60',                 desc: 'Min win rate % to be copyable', public: false },
  { key: 'maintenance_mode',   value: 'false',              desc: 'Show maintenance page',  public: false },
]

function SettingsTab() {
  const [settings, setSettings] = useState({})
  const [edits, setEdits]       = useState({})
  const [saving, setSaving]     = useState({})
  const [msg, setMsg]           = useState('')

  useEffect(() => { load() }, [])

  async function load() {
    try {
      const r = await api.get('/admin/settings')
      setSettings(r.data)
      // Seed any missing defaults
      const missing = DEFAULT_SETTINGS.filter(d => !r.data[d.key])
      if (missing.length) {
        for (const m of missing) {
          await api.put(`/admin/settings/${m.key}`, {
            value: m.value, description: m.desc, is_public: m.public
          })
        }
        const r2 = await api.get('/admin/settings')
        setSettings(r2.data)
      }
    } catch (e) { console.error(e) }
  }

  async function save(key) {
    const val = edits[key]
    if (val === undefined) return
    setSaving(s => ({...s, [key]: true}))
    try {
      const current = settings[key] || {}
      await api.put(`/admin/settings/${key}`, {
        value:       val,
        description: current.description,
        is_public:   current.is_public ?? false,
      })
      setMsg(`✅ "${key}" saved`)
      setEdits(e => { const n = {...e}; delete n[key]; return n })
      load()
    } catch (e) { setMsg('❌ ' + e.message) }
    finally {
      setSaving(s => ({...s, [key]: false}))
      setTimeout(() => setMsg(''), 3000)
    }
  }

  const rows = DEFAULT_SETTINGS.map(d => ({
    ...d,
    current: settings[d.key]?.value ?? d.value,
    desc:    settings[d.key]?.description ?? d.desc,
    public:  settings[d.key]?.is_public ?? d.public,
  }))

  return (
    <div className="space-y-4">
      {msg && <div className="p-3 bg-dark-700 border border-dark-600 rounded-xl text-sm text-center">{msg}</div>}
      <Card>
        <div className="space-y-3">
          {rows.map(row => (
            <div key={row.key} className="flex items-center gap-3 py-3 border-b border-dark-700 last:border-0">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-white font-mono">{row.key}</span>
                  {row.public && <span className="text-xs bg-blue-900/30 text-blue-400 px-1.5 py-0.5 rounded">Public</span>}
                </div>
                <div className="text-xs text-gray-500 mt-0.5">{row.desc}</div>
              </div>
              <input
                value={edits[row.key] ?? row.current}
                onChange={e => setEdits(ed => ({...ed, [row.key]: e.target.value}))}
                className="w-48 bg-dark-700 border border-dark-600 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
              />
              {edits[row.key] !== undefined && (
                <button onClick={() => save(row.key)} disabled={saving[row.key]}
                  className="px-3 py-2 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl text-xs disabled:opacity-50">
                  {saving[row.key] ? '…' : <Save size={12}/>}
                </button>
              )}
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

// ── Main Admin Panel ──────────────────────────────────────────────────────────

const TABS = [
  { id: 'dashboard', label: 'Dashboard',  icon: Activity },
  { id: 'users',     label: 'Users',      icon: Users },
  { id: 'audit',     label: 'Audit Log',  icon: Shield },
  { id: 'legal',     label: 'Legal Docs', icon: FileText },
  { id: 'settings',  label: 'Settings',   icon: Settings },
]

export default function AdminPanel() {
  const [tab, setTab] = useState('dashboard')
  const [me, setMe]   = useState(null)

  useEffect(() => {
    api.get('/auth/profile').then(r => setMe(r.data)).catch(() => {})
  }, [])

  if (me && !me.is_admin) {
    return (
      <div className="flex items-center justify-center py-24 flex-col gap-4">
        <Shield size={48} className="text-red-400"/>
        <h2 className="text-xl font-bold text-white">Admin Access Required</h2>
        <p className="text-gray-500 text-sm">Your account does not have admin privileges.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3 pb-3 border-b border-dark-600">
        <div className="w-10 h-10 rounded-xl bg-brand-500/20 flex items-center justify-center">
          <Shield size={20} className="text-brand-500"/>
        </div>
        <div>
          <h2 className="font-black text-white text-lg">Morviq AI — Admin Panel</h2>
          <p className="text-xs text-gray-500">Compliance · Legal · User Management · Platform Settings</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 flex-wrap">
        {TABS.map(t => {
          const Icon = t.icon
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                tab === t.id
                  ? 'bg-brand-500 text-dark-900'
                  : 'bg-dark-700 text-gray-400 hover:bg-dark-600 hover:text-white'
              }`}>
              <Icon size={13}/> {t.label}
            </button>
          )
        })}
      </div>

      {/* Tab Content */}
      {tab === 'dashboard' && <DashboardTab/>}
      {tab === 'users'     && <UsersTab/>}
      {tab === 'audit'     && <AuditTab/>}
      {tab === 'legal'     && <LegalTab/>}
      {tab === 'settings'  && <SettingsTab/>}
    </div>
  )
}
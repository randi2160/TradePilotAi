import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { Shield, Zap, AlertTriangle, CheckCircle, ExternalLink, RefreshCw, Wifi, WifiOff } from 'lucide-react'

const BROKER_ICONS = {
  alpaca_paper: '📄',
  alpaca_live:  '🦙',
  ibkr:         '🏦',
  tradier:      '📈',
}

const BROKER_STEPS = {
  alpaca_paper: [
    '1. Sign up free at alpaca.markets',
    '2. Go to Paper Trading → Your API Keys',
    '3. Generate API Key + Secret',
    '4. Paste both keys below',
  ],
  alpaca_live: [
    '1. Sign up at alpaca.markets',
    '2. Complete identity verification (KYC)',
    '3. Fund your account via bank transfer',
    '4. Go to Live Trading → Your API Keys',
    '5. Generate API Key + Secret',
    '6. Paste both keys below',
  ],
  ibkr: [
    '1. Open account at interactivebrokers.com',
    '2. Download TWS or IB Gateway',
    '3. Enable API connections in TWS settings',
    '4. Note your port (7497 for live, 7496 for paper)',
    '5. Enter connection details below',
  ],
  tradier: [
    '1. Open account at brokerage.tradier.com',
    '2. Go to Profile → API Access',
    '3. Generate an Access Token',
    '4. Find your Account ID in Account Summary',
    '5. Paste both below',
  ],
}

function StatBox({ label, value, color = 'text-white', sub }) {
  return (
    <div className="bg-dark-700 rounded-xl p-3 text-center">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className={`text-lg font-black ${color}`}>{value}</p>
      {sub && <p className="text-xs text-gray-600 mt-0.5">{sub}</p>}
    </div>
  )
}

export default function BrokerManager() {
  const [supported,  setSupported]  = useState({})
  const [status,     setStatus]     = useState(null)
  const [account,    setAccount]    = useState(null)
  const [tab,        setTab]        = useState('overview')
  const [selected,   setSelected]   = useState(null)
  const [creds,      setCreds]      = useState({})
  const [connecting, setConnecting] = useState(false)
  const [testing,    setTesting]    = useState(false)
  const [liveChecks, setLiveChecks] = useState({ risk: false, real: false })
  const [msg,        setMsg]        = useState({ text:'', type:'' })

  useEffect(() => { loadAll() }, [])

  async function loadAll() {
    try {
      const [sup, stat] = await Promise.all([
        api.get('/broker/supported').then(r => r.data),
        api.get('/broker/status').then(r => r.data),
      ])
      setSupported(sup)
      setStatus(stat)
      setSelected(stat.broker_type)
      if (stat.connected) loadAccount()
    } catch {}
  }

  async function loadAccount() {
    try {
      const r = await api.get('/broker/account')
      setAccount(r.data)
    } catch {}
  }

  function flash(text, type = 'info') {
    setMsg({ text, type })
    setTimeout(() => setMsg({ text:'', type:'' }), 5000)
  }

  async function connect() {
    if (!selected || !creds || Object.keys(creds).length === 0) {
      flash('Fill in all credential fields', 'error'); return
    }
    setConnecting(true)
    try {
      const r = await api.post('/broker/connect', {
        broker_type:  selected,
        credentials:  creds,
      })
      flash(r.data.message, 'success')
      await loadAll()
      setTab('overview')
    } catch(e) {
      flash(e.response?.data?.detail ?? e.message, 'error')
    } finally { setConnecting(false) }
  }

  async function disconnect() {
    if (!confirm('Disconnect your broker? The bot will stop trading.')) return
    try {
      await api.delete('/broker/disconnect')
      flash('Broker disconnected', 'info')
      setAccount(null)
      loadAll()
    } catch {}
  }

  async function testConnection() {
    setTesting(true)
    try {
      const r = await api.get('/broker/test')
      flash(r.data.message, r.data.status === 'ok' ? 'success' : 'error')
    } catch(e) { flash(e.message, 'error') }
    finally { setTesting(false) }
  }

  async function enableLiveMode() {
    if (!liveChecks.risk || !liveChecks.real) {
      flash('Check both confirmation boxes first', 'error'); return
    }
    try {
      const r = await api.post('/broker/live-mode', {
        enable:        true,
        confirm_risk:  true,
        confirm_real:  true,
      })
      flash(r.data.message, 'warning')
      loadAll()
    } catch(e) { flash(e.response?.data?.detail ?? e.message, 'error') }
  }

  async function disableLiveMode() {
    try {
      await api.post('/broker/live-mode', { enable: false, confirm_risk: false, confirm_real: false })
      flash('Live trading disabled — safe mode on', 'success')
      loadAll()
    } catch {}
  }

  const broker = supported[selected] ?? {}
  const acct   = account?.account ?? {}
  const equity = parseFloat(acct.equity ?? 0)
  const cash   = parseFloat(acct.cash   ?? 0)
  const bp     = parseFloat(acct.buying_power ?? cash)

  const msgColors = {
    success: 'bg-green-900/30 border-green-700 text-green-300',
    error:   'bg-red-900/30 border-red-700 text-red-300',
    warning: 'bg-yellow-900/30 border-yellow-700 text-yellow-300',
    info:    'bg-dark-700 border-dark-600 text-gray-300',
  }

  return (
    <div className="space-y-5 max-w-3xl">

      {/* Tabs */}
      <div className="flex gap-2">
        {[
          { id: 'overview', label: '📊 Account Overview' },
          { id: 'connect',  label: '🔌 Connect Broker'   },
          { id: 'live',     label: '⚡ Live Mode'         },
          { id: 'transfer', label: '💸 Funding'           },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
              tab===t.id ? 'bg-brand-500 text-dark-900' : 'bg-dark-700 text-gray-400 hover:bg-dark-600'
            }`}>{t.label}</button>
        ))}
      </div>

      {msg.text && (
        <div className={`p-3 rounded-xl border text-sm ${msgColors[msg.type] ?? msgColors.info}`}>
          {msg.text}
        </div>
      )}

      {/* ── Overview ─────────────────────────────────────────────────────────── */}
      {tab === 'overview' && (
        <div className="space-y-4">
          {/* Connection status banner */}
          <div className={`p-4 rounded-xl border flex items-center gap-3 ${
            status?.connected
              ? 'bg-green-900/20 border-green-800'
              : 'bg-dark-800 border-dark-600'
          }`}>
            {status?.connected
              ? <Wifi size={20} className="text-green-400"/>
              : <WifiOff size={20} className="text-gray-500"/>
            }
            <div className="flex-1">
              <p className="font-bold text-white">
                {status?.connected ? status.broker_name : 'No broker connected'}
              </p>
              <p className="text-xs text-gray-400">
                {status?.connected
                  ? status.using_env_keys
                    ? `✅ Using API keys from .env file · ${status.env_mode?.toUpperCase() ?? 'PAPER'} mode`
                    : `${status.live_mode ? '⚡ LIVE TRADING' : '📄 Paper Trading'} · ${status.broker_type}`
                  : 'Connect a broker or add keys to your .env file'
                }
              </p>
            </div>
            <div className="flex gap-2">
              {status?.connected && (
                <>
                  <button onClick={testConnection} disabled={testing}
                    className="text-xs px-3 py-1.5 bg-dark-700 hover:bg-dark-600 text-gray-300 rounded-lg transition-colors">
                    <RefreshCw size={12} className={testing ? 'animate-spin inline mr-1' : 'inline mr-1'}/>
                    Test
                  </button>
                  <button onClick={() => loadAccount()}
                    className="text-xs px-3 py-1.5 bg-dark-700 hover:bg-dark-600 text-gray-300 rounded-lg transition-colors">
                    ↻ Refresh
                  </button>
                </>
              )}
              {!status?.connected && (
                <button onClick={() => setTab('connect')}
                  className="text-xs px-4 py-1.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-lg">
                  Connect →
                </button>
              )}
            </div>
          </div>

          {/* Live mode warning */}
          {status?.live_mode && (
            <div className="p-3 bg-red-900/30 border border-red-700 rounded-xl flex items-center gap-3">
              <AlertTriangle size={16} className="text-red-400 flex-shrink-0"/>
              <p className="text-sm text-red-300 flex-1">
                <strong>LIVE TRADING ACTIVE</strong> — Real money is at risk. Bot is executing real trades.
              </p>
              <button onClick={disableLiveMode}
                className="text-xs bg-red-800 hover:bg-red-700 text-white px-3 py-1.5 rounded-lg font-bold">
                Disable
              </button>
            </div>
          )}

          {/* Account stats */}
          {account ? (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3">
                <StatBox label="Account Value"  value={`$${equity.toLocaleString('en-US',{minimumFractionDigits:2})}`} color="text-green-400"/>
                <StatBox label="Cash Available" value={`$${cash.toLocaleString('en-US',{minimumFractionDigits:2})}`}/>
                <StatBox label="Buying Power"   value={`$${bp.toLocaleString('en-US',{minimumFractionDigits:2})}`} color="text-brand-500"/>
              </div>

              {/* Open positions */}
              {(account.positions ?? []).length > 0 && (
                <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
                  <p className="text-sm font-bold text-gray-300 mb-3">📂 Open Positions</p>
                  <div className="space-y-2">
                    {account.positions.map((p, i) => (
                      <div key={i} className="flex items-center justify-between bg-dark-700 rounded-lg px-3 py-2.5">
                        <div>
                          <span className="font-bold text-white">{p.symbol}</span>
                          <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${
                            p.side==='long' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
                          }`}>{p.side?.toUpperCase()} × {p.qty}</span>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-bold text-white">${p.current_price?.toFixed(2)}</p>
                          <p className={`text-xs ${(p.unrealized_pnl??0)>=0?'text-green-400':'text-red-400'}`}>
                            {(p.unrealized_pnl??0)>=0?'+':''}${p.unrealized_pnl?.toFixed(2)}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recent orders */}
              {(account.orders ?? []).length > 0 && (
                <div className="bg-dark-800 border border-dark-600 rounded-xl p-4">
                  <p className="text-sm font-bold text-gray-300 mb-3">📋 Recent Orders</p>
                  <div className="space-y-1">
                    {account.orders.slice(0,5).map((o, i) => (
                      <div key={i} className="flex items-center gap-3 text-xs text-gray-300 py-1.5 border-b border-dark-700 last:border-0">
                        <span className="font-bold text-white w-14">{o.symbol}</span>
                        <span className={`px-1.5 py-0.5 rounded ${
                          o.side==='buy' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
                        }`}>{o.side?.toUpperCase()}</span>
                        <span>{o.qty} shares</span>
                        <span className="ml-auto text-gray-500">{o.status}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <button onClick={disconnect}
                className="w-full py-2.5 bg-dark-700 hover:bg-red-900/30 text-gray-400 hover:text-red-400 text-sm rounded-xl transition-colors border border-dark-600 hover:border-red-800">
                Disconnect Broker
              </button>
            </div>
          ) : status?.connected ? (
            <div className="text-center py-8 text-gray-500">
              <p>Loading account data…</p>
              <button onClick={loadAccount} className="mt-2 text-xs text-brand-500">Retry</button>
            </div>
          ) : (
            <div className="text-center py-12 bg-dark-800 border border-dark-600 rounded-xl">
              <p className="text-4xl mb-3">🔌</p>
              <p className="font-bold text-white mb-1">No Broker Connected</p>
              <p className="text-sm text-gray-400 mb-4">Connect your own broker account to start trading</p>
              <button onClick={() => setTab('connect')}
                className="px-6 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl">
                Connect a Broker →
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Connect ──────────────────────────────────────────────────────────── */}
      {tab === 'connect' && (
        <div className="space-y-5">
          <div className="bg-dark-800 border border-brand-500/30 rounded-xl p-4">
            <p className="text-xs text-brand-500 font-bold mb-1">ℹ️ How it works</p>
            <p className="text-xs text-gray-400">
              You connect YOUR broker account using API keys. AutoTrader Pro is a software platform —
              we never hold your money or execute trades in our name. All trades go directly from
              our system to your personal broker account. <strong className="text-white">Use at your own risk.</strong>
            </p>
          </div>

          {/* Broker selector */}
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(supported).map(([key, b]) => (
              <button key={key} onClick={() => { setSelected(key); setCreds({}) }}
                className={`p-4 rounded-xl border text-left transition-all ${
                  selected===key ? 'border-brand-500 bg-brand-500/10' : 'border-dark-600 hover:border-dark-500 bg-dark-800'
                }`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xl">{BROKER_ICONS[key]}</span>
                  <span className="font-bold text-white text-sm">{b.name}</span>
                  {b.live && <span className="text-xs bg-red-900/40 text-red-400 px-1.5 py-0.5 rounded">LIVE</span>}
                </div>
                <p className="text-xs text-gray-400">{b.description}</p>
                <div className="flex gap-2 mt-2">
                  <span className="text-xs text-gray-500">Commission: {b.commission}</span>
                  <span className="text-xs text-gray-500">Min: {b.min_account}</span>
                </div>
              </button>
            ))}
          </div>

          {/* Selected broker details */}
          {selected && supported[selected] && (
            <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-white">{BROKER_ICONS[selected]} {supported[selected].name}</h3>
                  {supported[selected].note && (
                    <p className="text-xs text-yellow-400 mt-0.5">⚠️ {supported[selected].note}</p>
                  )}
                </div>
                <a href={supported[selected].signup_url} target="_blank" rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-brand-500 hover:underline">
                  Open Account <ExternalLink size={10}/>
                </a>
              </div>

              {/* Setup steps */}
              <div className="bg-dark-700 rounded-xl p-3">
                <p className="text-xs font-bold text-gray-400 mb-2">Setup Steps:</p>
                {(BROKER_STEPS[selected] ?? []).map((s, i) => (
                  <p key={i} className="text-xs text-gray-300 py-0.5">{s}</p>
                ))}
              </div>

              {/* Credential fields */}
              <div className="space-y-3">
                <p className="text-xs font-bold text-gray-300">Your API Credentials</p>
                {(supported[selected].fields ?? []).map(field => (
                  <div key={field}>
                    <label className="block text-xs text-gray-400 mb-1 capitalize">
                      {field.replace(/_/g,' ')}
                    </label>
                    <input
                      type={field.includes('secret') || field.includes('token') ? 'password' : 'text'}
                      value={creds[field] ?? ''}
                      onChange={e => setCreds(c => ({...c, [field]: e.target.value}))}
                      placeholder={`Enter your ${field.replace(/_/g,' ')}`}
                      className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-2.5 text-white text-sm font-mono focus:outline-none focus:border-brand-500"
                    />
                  </div>
                ))}
              </div>

              <button onClick={connect} disabled={connecting}
                className="w-full py-3 bg-brand-500 hover:bg-brand-600 text-dark-900 font-black rounded-xl transition-colors disabled:opacity-50">
                {connecting ? '⟳ Connecting & Verifying...' : '🔌 Connect & Verify'}
              </button>
              <p className="text-xs text-gray-600 text-center">
                Your credentials are stored securely and only used to execute trades on your account.
              </p>
            </div>
          )}
        </div>
      )}

      {/* ── Live Mode ────────────────────────────────────────────────────────── */}
      {tab === 'live' && (
        <div className="space-y-4">
          {status?.live_mode ? (
            <div className="space-y-4">
              <div className="p-5 bg-red-900/20 border border-red-700 rounded-xl text-center">
                <p className="text-3xl mb-2">⚡</p>
                <p className="text-xl font-black text-red-400">LIVE TRADING ACTIVE</p>
                <p className="text-sm text-gray-300 mt-2">Real money is at risk. Bot is executing real trades on your account.</p>
              </div>
              <button onClick={disableLiveMode}
                className="w-full py-3 bg-dark-700 hover:bg-dark-600 text-gray-300 font-bold rounded-xl border border-dark-600">
                🔒 Switch to Paper Mode (Safe)
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Checklist */}
              <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-3">
                <h3 className="font-bold text-white">Before enabling live trading</h3>

                {[
                  { id:'broker',    label:'Live broker connected', check: status?.connected && !status?.broker_type?.includes('paper') },
                  { id:'capital',   label:'Account has sufficient funds', check: equity > 0 },
                  { id:'paper',     label:'Tested strategy in paper mode first', check: null },
                  { id:'limits',    label:'Daily loss limits configured', check: true },
                ].map(item => (
                  <div key={item.id} className="flex items-center gap-3">
                    {item.check === true  ? <CheckCircle size={16} className="text-green-400"/> :
                     item.check === false ? <AlertTriangle size={16} className="text-red-400"/> :
                     <div className="w-4 h-4 rounded-full border-2 border-gray-600"/>}
                    <span className={`text-sm ${item.check === true ? 'text-gray-300' : item.check === false ? 'text-red-300' : 'text-gray-500'}`}>
                      {item.label}
                    </span>
                  </div>
                ))}
              </div>

              {/* Risk confirmations */}
              <div className="bg-yellow-900/20 border border-yellow-700 rounded-xl p-4 space-y-3">
                <p className="text-sm font-bold text-yellow-400">⚠️ You must confirm both statements:</p>

                {[
                  { key:'risk',  text:'I understand that automated trading carries significant financial risk and I may lose all invested capital' },
                  { key:'real',  text:'I understand that real money will be used, AutoTrader Pro is a software tool only, and I am solely responsible for all trading losses' },
                ].map(item => (
                  <label key={item.key} className="flex items-start gap-3 cursor-pointer">
                    <input type="checkbox"
                      checked={liveChecks[item.key]}
                      onChange={e => setLiveChecks(c => ({...c, [item.key]: e.target.checked}))}
                      className="mt-0.5 w-4 h-4 flex-shrink-0"/>
                    <span className="text-xs text-yellow-200">{item.text}</span>
                  </label>
                ))}
              </div>

              <button
                onClick={enableLiveMode}
                disabled={!liveChecks.risk || !liveChecks.real || !status?.connected}
                className="w-full py-3 bg-red-700 hover:bg-red-600 text-white font-black rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                ⚡ Enable Live Trading
              </button>

              {(!status?.connected || status?.broker_type?.includes('paper')) && (
                <p className="text-xs text-red-400 text-center">
                  Connect a live broker account first (alpaca_live, tradier, or ibkr)
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Funding ──────────────────────────────────────────────────────────── */}
      {tab === 'transfer' && (
        <div className="space-y-4">
          <div className="bg-dark-800 border border-dark-600 rounded-xl p-5">
            <h3 className="font-bold text-white mb-3">💸 Account Funding</h3>
            <p className="text-sm text-gray-400 mb-4">
              All deposits and withdrawals are handled directly by your broker.
              AutoTrader Pro never touches your money.
            </p>

            {status?.broker_type === 'alpaca_live' || status?.broker_type === 'alpaca_paper' ? (
              <div className="space-y-3">
                <a href="https://app.alpaca.markets/dashboard/overview/transfers"
                   target="_blank" rel="noopener noreferrer"
                  className="flex items-center justify-between p-4 bg-dark-700 hover:bg-dark-600 rounded-xl transition-colors border border-dark-600">
                  <div>
                    <p className="font-bold text-white">Deposit Funds (ACH)</p>
                    <p className="text-xs text-gray-400">Link your bank account and transfer funds</p>
                  </div>
                  <ExternalLink size={16} className="text-brand-500"/>
                </a>
                <a href="https://app.alpaca.markets/dashboard/overview/transfers"
                   target="_blank" rel="noopener noreferrer"
                  className="flex items-center justify-between p-4 bg-dark-700 hover:bg-dark-600 rounded-xl transition-colors border border-dark-600">
                  <div>
                    <p className="font-bold text-white">Withdraw Funds</p>
                    <p className="text-xs text-gray-400">Transfer money back to your bank</p>
                  </div>
                  <ExternalLink size={16} className="text-brand-500"/>
                </a>
                <a href="https://app.alpaca.markets/dashboard/overview"
                   target="_blank" rel="noopener noreferrer"
                  className="flex items-center justify-between p-4 bg-dark-700 hover:bg-dark-600 rounded-xl transition-colors border border-dark-600">
                  <div>
                    <p className="font-bold text-white">Open Alpaca Dashboard</p>
                    <p className="text-xs text-gray-400">View full account, statements, documents</p>
                  </div>
                  <ExternalLink size={16} className="text-brand-500"/>
                </a>
              </div>
            ) : status?.connected ? (
              <div className="p-4 bg-dark-700 rounded-xl">
                <p className="text-sm text-gray-300">
                  Please manage your deposits and withdrawals directly through your broker's platform.
                </p>
                {supported[status?.broker_type]?.signup_url && (
                  <a href={supported[status?.broker_type]?.signup_url}
                     target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 mt-3 text-brand-500 text-sm hover:underline">
                    Open {status?.broker_name} <ExternalLink size={12}/>
                  </a>
                )}
              </div>
            ) : (
              <p className="text-gray-500 text-sm">Connect a broker first to manage funding.</p>
            )}
          </div>

          {/* Account summary if available */}
          {acct.equity > 0 && (
            <div className="grid grid-cols-3 gap-3">
              <StatBox label="Account Value"  value={`$${equity.toLocaleString('en-US',{minimumFractionDigits:2})}`} color="text-green-400"/>
              <StatBox label="Cash"           value={`$${cash.toLocaleString('en-US',{minimumFractionDigits:2})}`}/>
              <StatBox label="Buying Power"   value={`$${bp.toLocaleString('en-US',{minimumFractionDigits:2})}`} color="text-brand-500"/>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import { CheckCircle, XCircle, Zap, Crown, Star, ExternalLink, RefreshCw } from 'lucide-react'

const TIER_STYLE = {
  free:       { color: 'text-gray-400',   border: 'border-dark-600',          bg: 'bg-dark-700'           },
  subscriber: { color: 'text-brand-400',  border: 'border-brand-500/40',      bg: 'bg-brand-500/10'       },
  pro:        { color: 'text-yellow-400', border: 'border-yellow-500/40',     bg: 'bg-yellow-500/10'      },
}

const TIER_ICON = {
  free:       <Star size={18}/>,
  subscriber: <Zap size={18}/>,
  pro:        <Crown size={18}/>,
}

function PlanCard({ plan, current, onUpgrade, loading }) {
  const isCurrentPlan = current?.tier === plan.tier
  const style         = TIER_STYLE[plan.tier] || TIER_STYLE.free
  const isPopular     = plan.tier === 'subscriber'

  return (
    <div className={`relative rounded-2xl border-2 p-6 flex flex-col gap-4 transition-all ${
      isCurrentPlan ? style.border + ' ' + style.bg : 'border-dark-600 bg-dark-800'
    } ${isPopular && !isCurrentPlan ? 'ring-1 ring-brand-500/30' : ''}`}>

      {isPopular && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-brand-500 text-dark-900 text-xs font-black px-4 py-1 rounded-full">
          MOST POPULAR
        </div>
      )}

      {isCurrentPlan && (
        <div className={`absolute -top-3 right-4 text-xs font-black px-3 py-1 rounded-full ${style.bg} ${style.color} border ${style.border}`}>
          YOUR PLAN
        </div>
      )}

      <div className="flex items-center gap-3">
        <div className={`${style.color}`}>{TIER_ICON[plan.tier]}</div>
        <div>
          <div className={`text-lg font-black ${style.color}`}>{plan.name}</div>
          <div className="text-2xl font-black text-white">
            {plan.price === 0 ? 'Free' : `$${plan.price}`}
            {plan.price > 0 && <span className="text-sm font-normal text-gray-500">/month</span>}
          </div>
        </div>
      </div>

      <ul className="space-y-2 flex-1">
        {plan.features.map((f, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-gray-400">
            <CheckCircle size={14} className="text-green-400 flex-shrink-0 mt-0.5"/>
            {f}
          </li>
        ))}
      </ul>

      {isCurrentPlan ? (
        <div className={`text-center text-sm font-bold ${style.color} py-2`}>
          ✓ Active Plan
        </div>
      ) : plan.price === 0 ? (
        <div className="text-center text-sm text-gray-600 py-2">Default — no action needed</div>
      ) : (
        <button
          onClick={() => onUpgrade(plan.tier)}
          disabled={loading}
          className={`w-full py-3 rounded-xl font-bold text-sm transition-all disabled:opacity-50 ${
            isPopular
              ? 'bg-brand-500 hover:bg-brand-600 text-dark-900'
              : 'bg-yellow-500 hover:bg-yellow-600 text-dark-900'
          }`}
        >
          {loading ? 'Redirecting…' : `Upgrade to ${plan.name}`}
        </button>
      )}
    </div>
  )
}

export default function BillingTab() {
  const [status,  setStatus]  = useState(null)
  const [plans,   setPlans]   = useState([])
  const [loading, setLoading] = useState(true)
  const [upgrading, setUpgrading] = useState(false)
  const [msg,     setMsg]     = useState('')

  useEffect(() => {
    load()
  }, [])

  async function load() {
    setLoading(true)
    try {
      const [statusRes, plansRes] = await Promise.all([
        api.get('/billing/status'),
        api.get('/billing/plans'),
      ])
      setStatus(statusRes.data)
      setPlans(plansRes.data)
    } catch (e) {
      setMsg('Failed to load billing info: ' + (e.response?.data?.detail || e.message))
    } finally { setLoading(false) }
  }

  async function handleUpgrade(tier) {
    setUpgrading(true)
    try {
      const r = await api.post('/billing/checkout', {
        tier,
        success_url: window.location.origin + '/dashboard?tab=billing&success=1',
        cancel_url:  window.location.origin + '/dashboard?tab=billing',
      })
      window.location.href = r.data.checkout_url
    } catch (e) {
      setMsg('Checkout failed: ' + (e.response?.data?.detail || e.message))
      setUpgrading(false)
    }
  }

  async function handlePortal() {
    setUpgrading(true)
    try {
      const r = await api.post('/billing/portal')
      window.location.href = r.data.portal_url
    } catch (e) {
      setMsg('Portal failed: ' + (e.response?.data?.detail || e.message))
      setUpgrading(false)
    }
  }

  // Check for success redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('success') === '1') {
      setMsg('✅ Subscription activated! Welcome to your new plan.')
      window.history.replaceState({}, '', window.location.pathname)
      setTimeout(load, 2000)
    }
  }, [])

  if (loading) return (
    <div className="flex items-center justify-center py-16">
      <RefreshCw size={24} className="animate-spin text-brand-500"/>
    </div>
  )

  const tier  = status?.tier || 'free'
  const style = TIER_STYLE[tier] || TIER_STYLE.free

  return (
    <div className="space-y-6 max-w-4xl mx-auto">

      {msg && (
        <div className={`p-4 rounded-xl border text-sm flex items-center gap-2 ${
          msg.startsWith('✅')
            ? 'bg-green-900/20 border-green-800/40 text-green-400'
            : 'bg-red-900/20 border-red-800/40 text-red-400'
        }`}>
          {msg}
          <button onClick={() => setMsg('')} className="ml-auto text-gray-500 hover:text-white">✕</button>
        </div>
      )}

      {/* Current plan summary */}
      <div className={`rounded-2xl border p-5 ${style.border} ${style.bg}`}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className={style.color}>{TIER_ICON[tier]}</div>
            <div>
              <div className="text-xs text-gray-500">Current Plan</div>
              <div className={`text-xl font-black ${style.color}`}>{status?.plan_name || 'Free'}</div>
            </div>
          </div>

          <div className="flex gap-3">
            {status?.subscription_id && (
              <button onClick={handlePortal} disabled={upgrading}
                className="flex items-center gap-1.5 text-xs px-4 py-2 bg-dark-700 hover:bg-dark-600 text-gray-400 hover:text-white border border-dark-600 rounded-xl transition-all disabled:opacity-50">
                <ExternalLink size={12}/> Manage Billing
              </button>
            )}
            <button onClick={load}
              className="p-2 bg-dark-700 rounded-xl border border-dark-600 hover:bg-dark-600">
              <RefreshCw size={13} className="text-gray-500"/>
            </button>
          </div>
        </div>

        {status?.current_period_end && (
          <div className="mt-3 text-xs text-gray-500">
            {status.cancel_at_period_end
              ? `⚠️ Cancels on ${new Date(status.current_period_end).toLocaleDateString()}`
              : `Renews ${new Date(status.current_period_end).toLocaleDateString()}`
            }
          </div>
        )}

        {/* Feature limits */}
        {status?.limits && (
          <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
            {[
              { label: 'Live Trading',   val: status.limits.live_trading ? '✅ Yes' : '❌ No',     color: status.limits.live_trading ? 'text-green-400' : 'text-red-400' },
              { label: 'Copy Leaders',   val: status.limits.copy_leaders === 999 ? 'Unlimited' : status.limits.copy_leaders || 0, color: 'text-white' },
              { label: 'Groups',         val: status.limits.groups === 999 ? 'Unlimited' : status.limits.groups,  color: 'text-white' },
              { label: 'AI Analyses/day',val: status.limits.ai_analyses === 999 ? 'Unlimited' : status.limits.ai_analyses, color: 'text-white' },
            ].map(({ label, val, color }) => (
              <div key={label} className="bg-dark-800/60 rounded-xl p-2.5 text-center border border-dark-700">
                <div className="text-xs text-gray-500">{label}</div>
                <div className={`text-sm font-bold mt-0.5 ${color}`}>{val}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Plan cards */}
      <div>
        <h3 className="text-sm font-bold text-white mb-4">Available Plans</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {plans.map(plan => (
            <PlanCard
              key={plan.tier}
              plan={plan}
              current={status}
              onUpgrade={handleUpgrade}
              loading={upgrading}
            />
          ))}
        </div>
      </div>

      {/* FAQ */}
      <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-3">
        <div className="text-sm font-bold text-white">Billing FAQ</div>
        {[
          { q: 'Can I cancel anytime?',            a: 'Yes. Cancel from the "Manage Billing" portal. Your plan stays active until the end of the paid period.' },
          { q: 'Do you offer refunds?',             a: 'No refunds for partial months. Cancel before your next billing date to avoid the next charge.' },
          { q: 'Is my payment info secure?',        a: 'Yes. All payments are processed by Stripe — we never see or store your card details.' },
          { q: 'Can I upgrade mid-month?',          a: 'Yes. You\'ll be prorated for the remainder of the month.' },
          { q: 'What happens if I miss payment?',   a: 'After a 3-day grace period, your account downgrades to the Free plan automatically.' },
        ].map(({ q, a }) => (
          <div key={q} className="border-t border-dark-700 pt-3 first:border-0 first:pt-0">
            <div className="text-xs font-bold text-white mb-0.5">{q}</div>
            <div className="text-xs text-gray-500 leading-relaxed">{a}</div>
          </div>
        ))}
      </div>

      <p className="text-xs text-gray-600 text-center">
        Morviq AI is a software platform. Subscriptions do not guarantee trading profits.
        Trading involves risk of loss. <span className="text-brand-400">Not financial advice.</span>
      </p>
    </div>
  )
}

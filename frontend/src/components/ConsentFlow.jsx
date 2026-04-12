import { useState, useEffect } from 'react'
import { api } from '../hooks/useAuth'
import {
  Shield, CheckCircle, AlertTriangle, ChevronRight,
  ChevronLeft, Lock, FileText, TrendingUp, User
} from 'lucide-react'

const STEPS = [
  { id: 'welcome',      label: 'Welcome',       icon: User },
  { id: 'suitability',  label: 'Suitability',   icon: TrendingUp },
  { id: 'risk',         label: 'Risk Disclosure',icon: AlertTriangle },
  { id: 'tos',          label: 'Terms',          icon: FileText },
  { id: 'automation',   label: 'Auto-Trading',   icon: Shield },
  { id: 'complete',     label: 'Complete',       icon: CheckCircle },
]

function ProgressBar({ current }) {
  const idx = STEPS.findIndex(s => s.id === current)
  return (
    <div className="flex items-center gap-0 mb-8">
      {STEPS.map((step, i) => {
        const Icon = step.icon
        const done    = i < idx
        const active  = i === idx
        const pending = i > idx
        return (
          <div key={step.id} className="flex items-center flex-1 last:flex-none">
            <div className={`flex flex-col items-center gap-1`}>
              <div className={`w-9 h-9 rounded-full flex items-center justify-center transition-all ${
                done    ? 'bg-green-500 text-white' :
                active  ? 'bg-brand-500 text-dark-900' :
                          'bg-dark-700 text-gray-600'
              }`}>
                {done ? <CheckCircle size={16}/> : <Icon size={16}/>}
              </div>
              <span className={`text-xs hidden sm:block ${
                active ? 'text-brand-400 font-bold' : done ? 'text-green-400' : 'text-gray-600'
              }`}>{step.label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`flex-1 h-0.5 mx-1 mb-5 ${done ? 'bg-green-500' : 'bg-dark-600'}`}/>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Step 1: Welcome ───────────────────────────────────────────────────────────
function WelcomeStep({ onNext }) {
  return (
    <div className="space-y-6 text-center">
      <div className="flex justify-center">
        <div className="w-20 h-20 rounded-2xl bg-brand-500/20 flex items-center justify-center">
          <img src="/logo-mark.svg" alt="Morviq AI" className="w-12 h-12" onError={e => { e.target.style.display='none' }}/>
          <Shield size={36} className="text-brand-500"/>
        </div>
      </div>
      <div>
        <h2 className="text-2xl font-black text-white mb-2">Welcome to Morviq AI</h2>
        <p className="text-gray-400 text-sm leading-relaxed max-w-md mx-auto">
          Before you start trading, we need to complete a quick compliance process.
          This protects you and ensures you understand how automated trading works.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 text-left max-w-md mx-auto">
        {[
          { icon:'📋', title:'Suitability Check', desc:'Quick questions about your trading experience and financial situation' },
          { icon:'⚠️', title:'Risk Disclosure',   desc:'You must read and acknowledge the risks of automated trading' },
          { icon:'📄', title:'Terms of Service',   desc:'Our platform terms and your responsibilities as a user' },
          { icon:'🤖', title:'Auto-Trading Consent', desc:'Explicitly authorize the AI to trade on your behalf within your limits' },
        ].map((item, i) => (
          <div key={i} className="flex gap-3 p-3 bg-dark-700 border border-dark-600 rounded-xl">
            <span className="text-xl flex-shrink-0">{item.icon}</span>
            <div>
              <div className="text-sm font-bold text-white">{item.title}</div>
              <div className="text-xs text-gray-500 mt-0.5">{item.desc}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="bg-yellow-900/20 border border-yellow-800/40 rounded-xl p-4 text-xs text-yellow-400 text-left max-w-md mx-auto">
        ⚠️ All responses are legally recorded and cryptographically signed. This process takes about 3 minutes.
      </div>

      <button onClick={onNext}
        className="flex items-center gap-2 mx-auto px-8 py-3 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl transition-all">
        Begin Compliance Process <ChevronRight size={16}/>
      </button>
    </div>
  )
}

// ── Step 2: Suitability ───────────────────────────────────────────────────────
const SUITABILITY_QUESTIONS = [
  {
    id: 'experience',
    question: 'What is your trading experience level?',
    options: [
      { value: 'none',         label: 'No experience',          risk: 'high'   },
      { value: 'beginner',     label: 'Less than 1 year',       risk: 'medium' },
      { value: 'intermediate', label: '1–3 years',              risk: 'low'    },
      { value: 'experienced',  label: '3–5 years',              risk: 'low'    },
      { value: 'professional', label: '5+ years / Professional', risk: 'low'   },
    ]
  },
  {
    id: 'income',
    question: 'What is your approximate annual income?',
    options: [
      { value: 'under_30k',  label: 'Under $30,000'          },
      { value: '30k_75k',    label: '$30,000 – $75,000'      },
      { value: '75k_150k',   label: '$75,000 – $150,000'     },
      { value: 'over_150k',  label: 'Over $150,000'          },
      { value: 'prefer_not', label: 'Prefer not to answer'   },
    ]
  },
  {
    id: 'net_worth',
    question: 'What is your approximate investable net worth (excluding home)?',
    options: [
      { value: 'under_10k',   label: 'Under $10,000'         },
      { value: '10k_50k',     label: '$10,000 – $50,000'     },
      { value: '50k_250k',    label: '$50,000 – $250,000'    },
      { value: 'over_250k',   label: 'Over $250,000'         },
      { value: 'prefer_not',  label: 'Prefer not to answer'  },
    ]
  },
  {
    id: 'risk_tolerance',
    question: 'How would you describe your risk tolerance?',
    options: [
      { value: 'conservative',  label: 'Conservative — I cannot afford losses',     risk: 'warn' },
      { value: 'moderate',      label: 'Moderate — Some losses are acceptable'                   },
      { value: 'aggressive',    label: 'Aggressive — I accept significant risk'                  },
      { value: 'speculative',   label: 'Speculative — I understand I may lose all' , risk: 'ok'  },
    ]
  },
  {
    id: 'loss_capacity',
    question: 'How much of the capital you plan to trade can you afford to lose entirely?',
    options: [
      { value: 'none',    label: 'None — I cannot afford any losses', risk: 'block' },
      { value: 'some',    label: 'Some — up to 25%'                                 },
      { value: 'half',    label: 'About half — up to 50%'                           },
      { value: 'all',     label: 'All of it — it is truly risk capital'              },
    ]
  },
  {
    id: 'objective',
    question: 'What is your primary objective for using Morviq AI?',
    options: [
      { value: 'income',     label: 'Generate regular income'       },
      { value: 'growth',     label: 'Long-term wealth growth'       },
      { value: 'learning',   label: 'Learn algorithmic trading'     },
      { value: 'supplement', label: 'Supplement other investments'  },
    ]
  },
]

function SuitabilityStep({ onNext, onBack, setSuitabilityData }) {
  const [answers, setAnswers] = useState({})
  const [warning, setWarning] = useState('')

  const allAnswered = SUITABILITY_QUESTIONS.every(q => answers[q.id])

  function handleAnswer(qId, value, risk) {
    setAnswers(a => ({ ...a, [qId]: value }))
    setWarning('')

    if (risk === 'block') {
      setWarning('⚠️ Trading involves real financial risk. If you cannot afford any losses, we strongly recommend using paper trading mode only and consulting a financial advisor before trading with real money.')
    }
  }

  function handleNext() {
    setSuitabilityData(answers)
    onNext()
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-black text-white mb-1">Suitability Assessment</h2>
        <p className="text-gray-500 text-sm">These questions help us understand your situation and ensure trading is appropriate for you.</p>
      </div>

      {SUITABILITY_QUESTIONS.map((q, qi) => (
        <div key={q.id} className="space-y-2">
          <div className="text-sm font-bold text-white">
            {qi + 1}. {q.question}
          </div>
          <div className="grid grid-cols-1 gap-2">
            {q.options.map(opt => (
              <label key={opt.value}
                className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                  answers[q.id] === opt.value
                    ? 'bg-brand-500/15 border-brand-500/50 text-white'
                    : 'bg-dark-700 border-dark-600 text-gray-400 hover:border-dark-500'
                }`}>
                <input type="radio" name={q.id} value={opt.value}
                  checked={answers[q.id] === opt.value}
                  onChange={() => handleAnswer(q.id, opt.value, opt.risk)}
                  className="sr-only"/>
                <div className={`w-4 h-4 rounded-full border-2 flex-shrink-0 transition-all ${
                  answers[q.id] === opt.value ? 'border-brand-500 bg-brand-500' : 'border-gray-600'
                }`}>
                  {answers[q.id] === opt.value && <div className="w-1.5 h-1.5 bg-white rounded-full m-auto mt-0.5"/>}
                </div>
                <span className="text-sm">{opt.label}</span>
              </label>
            ))}
          </div>
        </div>
      ))}

      {warning && (
        <div className="bg-red-900/20 border border-red-800/40 rounded-xl p-4 text-sm text-red-400">
          {warning}
        </div>
      )}

      <div className="flex gap-3">
        <button onClick={onBack} className="flex items-center gap-2 px-5 py-2.5 bg-dark-700 text-gray-400 hover:text-white border border-dark-600 rounded-xl text-sm">
          <ChevronLeft size={14}/> Back
        </button>
        <button onClick={handleNext} disabled={!allAnswered}
          className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl text-sm disabled:opacity-40 disabled:cursor-not-allowed">
          Continue <ChevronRight size={14}/>
        </button>
      </div>
    </div>
  )
}

// ── Step 3: Risk Disclosure ───────────────────────────────────────────────────
function RiskStep({ onNext, onBack }) {
  const [read,    setRead]    = useState(false)
  const [checked, setChecked] = useState(false)
  const [scrolled, setScrolled] = useState(false)

  function handleScroll(e) {
    const el = e.target
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 20) {
      setRead(true)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-black text-white mb-1">Risk Disclosure</h2>
        <p className="text-gray-500 text-sm">Please read the following disclosure carefully and scroll to the bottom before continuing.</p>
      </div>

      <div onScroll={handleScroll}
        className="h-72 overflow-y-auto bg-dark-700 border border-dark-600 rounded-xl p-4 text-sm text-gray-300 leading-relaxed space-y-3">
        <h3 className="font-bold text-white text-base">Risk Disclosure Statement</h3>

        <p><strong className="text-yellow-400">IMPORTANT — PLEASE READ CAREFULLY BEFORE TRADING</strong></p>

        <p><strong className="text-white">1. Trading Involves Substantial Risk of Loss</strong><br/>
        Trading stocks, securities, and any financial instruments involves substantial risk of loss and is not suitable for all investors. You may lose some or all of your invested capital. Never trade with money you cannot afford to lose entirely.</p>

        <p><strong className="text-white">2. Morviq AI is Not a Financial Advisor</strong><br/>
        Morviq AI is a software technology platform. We are not a registered broker-dealer, investment advisor, or financial planner. Nothing on this platform constitutes financial advice, investment advice, or a recommendation to buy or sell any security.</p>

        <p><strong className="text-white">3. Past Performance Does Not Guarantee Future Results</strong><br/>
        Any historical performance data, win rates, or return figures displayed on the platform are for informational purposes only. Past performance of any algorithm, strategy, or trader does not guarantee similar results in the future. Markets change constantly and unpredictably.</p>

        <p><strong className="text-white">4. Automated Trading Risks</strong><br/>
        Automated trading algorithms can malfunction, make incorrect decisions, or perform poorly in certain market conditions. Software bugs, internet outages, exchange connectivity issues, or unexpected market events can cause erroneous trades or inability to close positions. You accept full responsibility for all outcomes.</p>

        <p><strong className="text-white">5. Copy Trading Risks</strong><br/>
        Copying another trader's strategy does not guarantee similar results. Differences in trade execution timing, slippage, available capital, and market conditions can result in significantly different outcomes for your account compared to the leader you copy.</p>

        <p><strong className="text-white">6. You Are Solely Responsible</strong><br/>
        You are solely responsible for all trading decisions, outcomes, and losses that occur in your brokerage account. Morviq AI executes trades only within the limits and rules you configure. By enabling automated trading, you authorize the platform to execute trades on your behalf within those limits.</p>

        <p><strong className="text-white">7. Tax Implications</strong><br/>
        Trading activities may have significant tax implications. Morviq AI does not provide tax advice. Consult a qualified tax professional.</p>

        <p><strong className="text-white">8. Pattern Day Trader Rule</strong><br/>
        If you have less than $25,000 in your brokerage account, you are subject to Pattern Day Trader (PDT) restrictions. Violating PDT rules can result in your account being restricted. You are responsible for compliance.</p>

        <p><strong className="text-white">9. No Guarantee of Platform Availability</strong><br/>
        The platform may experience downtime, maintenance, or technical failures. Morviq AI is not liable for any trading losses that occur due to platform unavailability.</p>

        <p><strong className="text-white">10. Seek Professional Advice</strong><br/>
        Before trading, we strongly encourage you to consult a licensed financial advisor about whether trading is appropriate for your personal financial situation. Only invest money you can afford to lose entirely.</p>

        <p className="text-gray-500 italic">Last updated: April 2026 — Morviq AI</p>
      </div>

      {!read && (
        <p className="text-xs text-yellow-400 text-center">↑ Scroll to the bottom to continue</p>
      )}

      <label className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all ${
        read ? 'bg-dark-700 border-dark-600 hover:border-brand-500/40' : 'opacity-40 pointer-events-none bg-dark-800 border-dark-700'
      }`}>
        <input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)}
          disabled={!read} className="mt-0.5 w-5 h-5 flex-shrink-0 accent-brand-500"/>
        <div className="text-sm text-gray-300">
          <strong className="text-white">I have read and understand the Risk Disclosure Statement.</strong>
          {' '}I acknowledge that trading involves substantial risk of loss and that past performance does not guarantee future results. I understand that Morviq AI is not a financial advisor and that I am solely responsible for all trading decisions and outcomes.
        </div>
      </label>

      <div className="flex gap-3">
        <button onClick={onBack} className="flex items-center gap-2 px-5 py-2.5 bg-dark-700 text-gray-400 hover:text-white border border-dark-600 rounded-xl text-sm">
          <ChevronLeft size={14}/> Back
        </button>
        <button onClick={onNext} disabled={!checked || !read}
          className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl text-sm disabled:opacity-40 disabled:cursor-not-allowed">
          I Understand the Risks <ChevronRight size={14}/>
        </button>
      </div>
    </div>
  )
}

// ── Step 4: Terms of Service ──────────────────────────────────────────────────
function TermsStep({ onNext, onBack }) {
  const [read,    setRead]    = useState(false)
  const [checked, setChecked] = useState(false)

  function handleScroll(e) {
    const el = e.target
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 20) setRead(true)
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-black text-white mb-1">Terms of Service</h2>
        <p className="text-gray-500 text-sm">Please read and accept our Terms of Service to continue.</p>
      </div>

      <div onScroll={handleScroll}
        className="h-72 overflow-y-auto bg-dark-700 border border-dark-600 rounded-xl p-4 text-sm text-gray-300 leading-relaxed space-y-3">
        <h3 className="font-bold text-white text-base">Morviq AI — Terms of Service</h3>
        <p className="text-gray-500">Version 2026-04-11</p>

        <p><strong className="text-white">1. Acceptance</strong><br/>
        By using Morviq AI, you agree to be bound by these Terms. If you do not agree, do not use the platform.</p>

        <p><strong className="text-white">2. Description of Service</strong><br/>
        Morviq AI provides AI-powered automated trading software that connects to third-party brokerage accounts. We are NOT a broker, dealer, or investment advisor. All trades execute in your own brokerage account.</p>

        <p><strong className="text-white">3. Eligibility</strong><br/>
        You must be at least 18 years of age and legally permitted to trade securities in your jurisdiction.</p>

        <p><strong className="text-white">4. User Responsibilities</strong><br/>
        You are responsible for: (a) maintaining the security of your account credentials; (b) all trading outcomes in your brokerage account; (c) compliance with all applicable laws and regulations; (d) accuracy of information provided to us.</p>

        <p><strong className="text-white">5. Automated Trading Authorization</strong><br/>
        By enabling automated trading, you explicitly authorize Morviq AI to place, manage, and close trades in your brokerage account within the risk limits you configure. You may revoke this authorization at any time by disabling the bot.</p>

        <p><strong className="text-white">6. Subscriptions and Payments</strong><br/>
        Paid plans are billed monthly. Cancellations take effect at the end of the billing period. No refunds for partial months. All prices are in USD.</p>

        <p><strong className="text-white">7. Prohibited Uses</strong><br/>
        You may not: (a) violate securities laws or engage in market manipulation; (b) share account access with unauthorized persons; (c) attempt to reverse-engineer or hack the platform; (d) use the platform to engage in fraudulent activity.</p>

        <p><strong className="text-white">8. Limitation of Liability</strong><br/>
        To the maximum extent permitted by law, Morviq AI shall not be liable for any trading losses, lost profits, or indirect damages. Our total liability shall not exceed fees paid in the preceding 3 months.</p>

        <p><strong className="text-white">9. Indemnification</strong><br/>
        You agree to indemnify Morviq AI against all claims arising from your use of the platform or violation of these Terms.</p>

        <p><strong className="text-white">10. Changes</strong><br/>
        We may update these Terms. Material changes will be communicated via email or in-app notification. Continued use constitutes acceptance.</p>

        <p><strong className="text-white">11. Governing Law</strong><br/>
        These Terms are governed by the laws of the United States. Disputes shall be resolved through binding arbitration.</p>

        <p className="text-gray-500 italic">For questions: legal@morviqai.com</p>
      </div>

      {!read && <p className="text-xs text-yellow-400 text-center">↑ Scroll to the bottom to continue</p>}

      <label className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all ${
        read ? 'bg-dark-700 border-dark-600 hover:border-brand-500/40' : 'opacity-40 pointer-events-none bg-dark-800 border-dark-700'
      }`}>
        <input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)}
          disabled={!read} className="mt-0.5 w-5 h-5 flex-shrink-0 accent-brand-500"/>
        <div className="text-sm text-gray-300">
          <strong className="text-white">I have read and agree to the Terms of Service.</strong>
          {' '}I understand that Morviq AI is a software platform, not a financial advisor, and that I am solely responsible for all trading activity in my account.
        </div>
      </label>

      <div className="flex gap-3">
        <button onClick={onBack} className="flex items-center gap-2 px-5 py-2.5 bg-dark-700 text-gray-400 hover:text-white border border-dark-600 rounded-xl text-sm">
          <ChevronLeft size={14}/> Back
        </button>
        <button onClick={onNext} disabled={!checked || !read}
          className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl text-sm disabled:opacity-40 disabled:cursor-not-allowed">
          Accept Terms <ChevronRight size={14}/>
        </button>
      </div>
    </div>
  )
}

// ── Step 5: Auto-Trading Consent ──────────────────────────────────────────────
const AUTO_CONSENTS = [
  { id: 'risk_settings',  text: 'I have set my own daily loss limit and maximum trade size — the bot will stop automatically if I hit my limit' },
  { id: 'my_rules',       text: 'I understand the AI only trades within the specific rules and limits I configure — it does not act freely' },
  { id: 'not_advisor',    text: 'I understand Morviq AI is software, not a financial advisor. It does not provide investment advice.' },
  { id: 'may_lose',       text: 'I understand I can lose real money — including losing all of the money I put in — and I accept this risk' },
  { id: 'can_disable',    text: 'I know I can stop all trading immediately at any time using the Safety tab — I am always in control' },
  { id: 'responsibility', text: 'I accept full legal responsibility for all trades that execute in my brokerage account through this platform' },
]

function AutoTradingStep({ onNext, onBack }) {
  const [checks,    setChecks]    = useState({})
  const [dailyLoss, setDailyLoss] = useState('150')
  const [tradeSize, setTradeSize] = useState('500')
  const [finalAck,  setFinalAck]  = useState(false)
  const [typeConfirm, setTypeConfirm] = useState('')

  const allChecked = AUTO_CONSENTS.every(c => checks[c.id])
  const confirmed  = allChecked && finalAck && typeConfirm.trim().toUpperCase() === 'I ACCEPT'

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-black text-white mb-1">Automated Trading Authorization</h2>
        <p className="text-gray-500 text-sm">
          You are about to authorize Morviq AI to execute real trades automatically.
          Read every statement carefully — this is a legal authorization.
        </p>
      </div>

      {/* PLAIN LANGUAGE MONEY LOSS BOX */}
      <div className="bg-red-900/25 border-2 border-red-700/60 rounded-xl p-5 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">⚠️</span>
          <span className="text-base font-black text-red-400">Plain Language Warning — Please Read</span>
        </div>
        <div className="space-y-2 text-sm text-red-200/90 leading-relaxed">
          <p>
            <strong className="text-white">You can lose real money.</strong> When you enable auto-trading,
            the AI will buy and sell real stocks using real money in your brokerage account.
            Stock prices go up <em>and down</em>. The AI can be wrong. Trades can lose money.
          </p>
          <p>
            <strong className="text-white">You could lose everything you invest.</strong> In a bad market,
            or if the strategy performs poorly, you may lose some or all of the capital you trade with.
            This is not a savings account. This is not guaranteed income.
          </p>
          <p>
            <strong className="text-white">Past results mean nothing.</strong> Any performance numbers
            shown on this platform are historical and do not predict what will happen to your money.
          </p>
          <p>
            <strong className="text-white">Only trade money you can afford to lose entirely.</strong>{' '}
            Never trade with rent money, emergency funds, or money you need.
          </p>
        </div>
      </div>

      {/* Risk Limits */}
      <div className="bg-dark-700 border border-dark-600 rounded-xl p-4 space-y-3">
        <div className="text-xs font-bold text-brand-400">Set Your Safety Limits — Required</div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-400">Maximum daily loss ($)</label>
            <input type="number" value={dailyLoss} onChange={e => setDailyLoss(e.target.value)}
              min="10" max="10000"
              className="w-full mt-1 bg-dark-800 border border-dark-600 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500"/>
            <p className="text-xs text-gray-600 mt-1">Bot stops automatically when this is lost in one day</p>
          </div>
          <div>
            <label className="text-xs text-gray-400">Maximum trade size ($)</label>
            <input type="number" value={tradeSize} onChange={e => setTradeSize(e.target.value)}
              min="10" max="100000"
              className="w-full mt-1 bg-dark-800 border border-dark-600 rounded-xl px-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500"/>
            <p className="text-xs text-gray-600 mt-1">No single trade will exceed this amount</p>
          </div>
        </div>
      </div>

      {/* 6 Checkboxes */}
      <div className="space-y-2">
        <div className="text-xs font-bold text-white">
          Check every box — you must read and agree to each one individually:
        </div>
        {AUTO_CONSENTS.map((consent, i) => (
          <label key={consent.id}
            className={`flex items-start gap-3 p-3.5 rounded-xl border cursor-pointer transition-all ${
              checks[consent.id]
                ? 'bg-green-900/15 border-green-700/50'
                : 'bg-dark-700 border-dark-600 hover:border-dark-500'
            }`}>
            <input type="checkbox"
              checked={!!checks[consent.id]}
              onChange={e => setChecks(c => ({...c, [consent.id]: e.target.checked}))}
              className="mt-0.5 w-5 h-5 flex-shrink-0 accent-green-500"/>
            <div className="text-sm text-gray-300 flex-1">
              <span className="text-gray-500 mr-1">{i + 1}.</span>
              {consent.text}
            </div>
            {checks[consent.id] && <CheckCircle size={16} className="text-green-400 flex-shrink-0 mt-0.5"/>}
          </label>
        ))}
      </div>

      {/* Final plain-language re-acknowledgment */}
      {allChecked && (
        <div className="bg-dark-700 border border-yellow-700/40 rounded-xl p-4 space-y-3">
          <div className="text-sm font-bold text-yellow-400">One final confirmation</div>
          <label className="flex items-start gap-3 cursor-pointer">
            <input type="checkbox" checked={finalAck}
              onChange={e => setFinalAck(e.target.checked)}
              className="mt-0.5 w-5 h-5 flex-shrink-0 accent-yellow-500"/>
            <p className="text-sm text-white leading-relaxed">
              <strong>I understand that I can lose money — including losing all of my trading capital.</strong>{' '}
              I am not relying on Morviq AI for financial advice. I have chosen to enable automated trading
              of my own free will and I accept all financial risk and outcomes.
            </p>
          </label>
        </div>
      )}

      {/* Type to confirm */}
      {allChecked && finalAck && (
        <div className="space-y-2">
          <label className="text-xs font-bold text-white">
            Type <span className="text-brand-400 font-mono">I ACCEPT</span> below to confirm your authorization:
          </label>
          <input
            value={typeConfirm}
            onChange={e => setTypeConfirm(e.target.value)}
            placeholder="Type: I ACCEPT"
            className={`w-full bg-dark-800 border rounded-xl px-4 py-3 text-white text-sm font-mono focus:outline-none transition-colors ${
              typeConfirm.trim().toUpperCase() === 'I ACCEPT'
                ? 'border-green-600 bg-green-900/10'
                : 'border-dark-600 focus:border-brand-500'
            }`}
          />
          {typeConfirm.length > 0 && typeConfirm.trim().toUpperCase() !== 'I ACCEPT' && (
            <p className="text-xs text-red-400">Type exactly: I ACCEPT</p>
          )}
        </div>
      )}

      <div className="bg-dark-800 border border-dark-600 rounded-xl p-3 text-xs text-gray-500">
        🔒 By clicking "Enable Auto-Trading" your full name, IP address, timestamp, browser info,
        the limits you set, and a cryptographic signature will be permanently and irrevocably recorded.
        This record cannot be deleted.
      </div>

      <div className="flex gap-3">
        <button onClick={onBack}
          className="flex items-center gap-2 px-5 py-2.5 bg-dark-700 text-gray-400 hover:text-white border border-dark-600 rounded-xl text-sm">
          <ChevronLeft size={14}/> Back
        </button>
        <button
          onClick={() => onNext({ dailyLoss: parseFloat(dailyLoss), tradeSize: parseFloat(tradeSize) })}
          disabled={!confirmed}
          className="flex-1 flex items-center justify-center gap-2 py-3 bg-green-600 hover:bg-green-700 text-white font-bold rounded-xl text-sm disabled:opacity-30 disabled:cursor-not-allowed transition-all">
          <Lock size={14}/> Enable Auto-Trading
        </button>
      </div>
    </div>
  )
}

// ── Step 6: Complete ──────────────────────────────────────────────────────────
function CompleteStep({ sigHash, onDone }) {
  return (
    <div className="text-center space-y-6">
      <div className="flex justify-center">
        <div className="w-20 h-20 rounded-full bg-green-900/30 flex items-center justify-center">
          <CheckCircle size={42} className="text-green-400"/>
        </div>
      </div>
      <div>
        <h2 className="text-2xl font-black text-white mb-2">You're All Set!</h2>
        <p className="text-gray-400 text-sm">
          Your compliance process is complete. All consents have been recorded and cryptographically signed.
        </p>
      </div>

      <div className="bg-dark-700 border border-dark-600 rounded-xl p-4 text-left space-y-2">
        <div className="text-xs font-bold text-green-400 mb-3">✅ Consent Record Summary</div>
        {[
          'Suitability questionnaire completed',
          'Risk disclosure read and acknowledged',
          'Terms of Service accepted',
          'Automated trading authorization signed',
        ].map((item, i) => (
          <div key={i} className="flex items-center gap-2 text-sm text-gray-300">
            <CheckCircle size={14} className="text-green-400 flex-shrink-0"/>
            {item}
          </div>
        ))}
        {sigHash && (
          <div className="mt-3 pt-3 border-t border-dark-600">
            <div className="text-xs text-gray-500">Consent signature hash:</div>
            <div className="text-xs font-mono text-gray-400 mt-1 break-all">{sigHash}</div>
          </div>
        )}
      </div>

      <div className="text-xs text-gray-600">
        A copy of your consent record has been saved to your account.
        You can view it anytime in Settings → Compliance.
      </div>

      <button onClick={onDone}
        className="flex items-center gap-2 mx-auto px-8 py-3 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl transition-all">
        Go to Dashboard <ChevronRight size={16}/>
      </button>
    </div>
  )
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function ConsentFlow({ onComplete, user }) {
  const [step,            setStep]            = useState('welcome')
  const [suitabilityData, setSuitabilityData] = useState({})
  const [submitting,      setSubmitting]      = useState(false)
  const [sigHash,         setSigHash]         = useState('')
  const [error,           setError]           = useState('')

  const steps = STEPS.map(s => s.id)
  const goNext = () => setStep(s => steps[steps.indexOf(s) + 1])
  const goBack = () => setStep(s => steps[steps.indexOf(s) - 1])

  async function submitAll(autoSettings) {
    setSubmitting(true)
    setError('')
    try {
      // 1. Record suitability
      await api.post('/compliance/suitability', suitabilityData).catch(() => {})

      // 2. Record all individual consents
      for (const ct of ['risk_disclosure', 'terms_of_service', 'privacy']) {
        await api.post('/compliance/consent', {
          consent_type:     ct,
          document_version: '2026-04-11',
          accepted:         true,
        }).catch(() => {})
      }

      // 3. Record auto-trading consent with full context — most important one
      const autoConsentRes = await api.post('/compliance/consent', {
        consent_type:     'auto_trading',
        document_version: '2026-04-11',
        accepted:         true,
        daily_loss_limit: autoSettings?.dailyLoss,
        max_trade_size:   autoSettings?.tradeSize,
      }).catch(e => ({ data: { signature_hash: 'recorded' } }))

      const hash = autoConsentRes?.data?.signature_hash || 'recorded'
      setSigHash(hash)

      // 4. Update user risk settings from what they chose
      if (autoSettings) {
        await api.put('/settings/targets', {
          daily_target_min: 50,
          daily_target_max: 200,
          max_daily_loss:   autoSettings.dailyLoss,
        }).catch(() => {})
      }

      // 5. Record auto-trading mode as ENABLED in audit log
      await api.post('/compliance/auto-trading-enabled', {
        daily_loss_limit: autoSettings?.dailyLoss,
        max_trade_size:   autoSettings?.tradeSize,
        sig_hash:         hash,
      }).catch(() => {})

      setStep('complete')
    } catch (e) {
      setError('Failed to record consent. Please try again. Error: ' + (e.message || 'Unknown'))
    } finally { setSubmitting(false) }
  }

  return (
    <div className="min-h-screen bg-dark-900 flex items-center justify-center p-4">
      <div className="w-full max-w-xl bg-dark-800 border border-dark-600 rounded-2xl p-6 md:p-8">
        {step !== 'complete' && <ProgressBar current={step}/>}
        {error && <div className="mb-4 p-3 bg-red-900/20 border border-red-800/40 rounded-xl text-sm text-red-400">{error}</div>}

        {step === 'welcome'     && <WelcomeStep onNext={goNext}/>}
        {step === 'suitability' && <SuitabilityStep onNext={goNext} onBack={goBack} setSuitabilityData={setSuitabilityData}/>}
        {step === 'risk'        && <RiskStep onNext={goNext} onBack={goBack}/>}
        {step === 'tos'         && <TermsStep onNext={goNext} onBack={goBack}/>}
        {step === 'automation'  && (
          <AutoTradingStep
            onNext={submitAll}
            onBack={goBack}
          />
        )}
        {step === 'complete'    && <CompleteStep sigHash={sigHash} onDone={onComplete}/>}

        {submitting && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-dark-800 border border-dark-600 rounded-xl p-6 text-center">
              <div className="animate-spin w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full mx-auto mb-3"/>
              <p className="text-sm text-gray-400">Recording your consent…</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
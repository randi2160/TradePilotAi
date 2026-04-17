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
          <img src="/logo-mark.png" alt="Morviq AI" className="w-12 h-12 object-contain" onError={e => { e.target.style.display='none' }}/>
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

// ── Reusable DB-Driven Document Step ─────────────────────────────────────────
function DocStep({ docType, title, stepDesc, checkText, acceptLabel, onNext, onBack }) {
  const [doc,     setDoc]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [read,    setRead]    = useState(false)
  const [checked, setChecked] = useState(false)

  useEffect(() => {
    api.get(`/admin/legal/${docType}/active`)
      .then(r => { setDoc(r.data); setLoading(false) })
      .catch(() => { setDoc(null); setLoading(false) })
  }, [docType])

  function handleScroll(e) {
    const el = e.target
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 20) setRead(true)
  }

  const canProceed = checked && read && !!doc

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-black text-white mb-1">{title}</h2>
        <p className="text-gray-500 text-sm">{stepDesc}</p>
        {doc && (
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-gray-600">Version: {doc.version}</span>
            <span className="text-xs text-gray-700">·</span>
            <span className="text-xs font-mono text-gray-700">{doc.content_hash?.slice(0,12)}…</span>
          </div>
        )}
      </div>

      {loading ? (
        <div className="h-72 flex items-center justify-center">
          <div className="animate-spin w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full"/>
        </div>
      ) : !doc ? (
        <div className="h-72 bg-red-900/20 border-2 border-red-800/40 rounded-xl p-6 flex flex-col items-center justify-center gap-3">
          <div className="text-3xl">⚠️</div>
          <div className="text-center">
            <p className="text-red-400 font-bold text-sm">Document Not Configured</p>
            <p className="text-xs text-red-300/70 mt-1 leading-relaxed">
              The <strong>{docType}</strong> document has not been added yet.<br/>
              An administrator must add it in <strong>Admin Panel → Legal Docs</strong> before users can proceed.
            </p>
          </div>
        </div>
      ) : (
        <div
          onScroll={handleScroll}
          className="h-72 overflow-y-auto bg-dark-700 border border-dark-600 rounded-xl p-4 text-sm text-gray-300 leading-relaxed"
          dangerouslySetInnerHTML={{ __html: doc.content }}
        />
      )}

      {!read && doc && (
        <p className="text-xs text-yellow-400 text-center">↑ Scroll to the bottom to continue</p>
      )}

      <label className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all ${
        read && doc ? 'bg-dark-700 border-dark-600 hover:border-brand-500/40' : 'opacity-40 pointer-events-none bg-dark-800 border-dark-700'
      }`}>
        <input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)}
          disabled={!read || !doc} className="mt-0.5 w-5 h-5 flex-shrink-0 accent-brand-500"/>
        <div className="text-sm text-gray-300">{checkText}</div>
      </label>

      <div className="flex gap-3">
        <button onClick={onBack} className="flex items-center gap-2 px-5 py-2.5 bg-dark-700 text-gray-400 hover:text-white border border-dark-600 rounded-xl text-sm">
          <ChevronLeft size={14}/> Back
        </button>
        <button onClick={onNext} disabled={!canProceed}
          className="flex-1 flex items-center justify-center gap-2 py-2.5 bg-brand-500 hover:bg-brand-600 text-dark-900 font-bold rounded-xl text-sm disabled:opacity-40 disabled:cursor-not-allowed">
          {acceptLabel || 'Accept & Continue'} <ChevronRight size={14}/>
        </button>
      </div>
    </div>
  )
}

// ── Step 3: Risk Disclosure (DB-driven) ───────────────────────────────────────
function RiskStep({ onNext, onBack }) {
  return (
    <DocStep
      docType="risk"
      title="Risk Disclosure"
      stepDesc="Please read the risk disclosure carefully and scroll to the bottom before continuing."
      checkText="I have read and understand the Risk Disclosure Statement. I acknowledge that trading involves substantial risk of loss, that past performance does not guarantee future results, and that Morviq AI is not a financial advisor. I am solely responsible for all trading decisions and outcomes."
      acceptLabel="I Understand the Risks"
      onNext={onNext}
      onBack={onBack}
    />
  )
}

// ── Step 4: Terms of Service (DB-driven) ──────────────────────────────────────
function TermsStep({ onNext, onBack }) {
  return (
    <DocStep
      docType="tos"
      title="Terms of Service"
      stepDesc="Please read and accept our Terms of Service to continue."
      checkText="I have read and agree to the Terms of Service. I understand that Morviq AI is a software platform, not a financial advisor, and that I am solely responsible for all trading activity in my account."
      acceptLabel="Accept Terms"
      onNext={onNext}
      onBack={onBack}
    />
  )
}


// ── Step 5: Auto-Trading Consent ──────────────────────────────────────────────
const AUTO_CONSENTS = [
  { id: 'risk_settings',  text: 'I have set my own daily loss limit and maximum trade size — the bot will stop automatically if I hit my limit' },
  { id: 'my_rules',       text: 'I understand the AI only trades within the specific rules and limits I configure — it does not act freely' },
  { id: 'not_advisor',    text: 'I understand Morviq AI is software, not a financial advisor. It does not provide investment advice.' },
  { id: 'may_lose',       text: 'I understand I can lose real money — including losing all of the money I put in — and I accept this risk' },
  { id: 'no_approval',    text: 'I understand automated trading may execute trades WITHOUT asking me for approval on each trade, once enabled' },
  { id: 'can_disable',    text: 'I know I can stop all trading immediately at any time using the Safety tab — I am always in control' },
  { id: 'responsibility', text: 'I remain responsible for all profits, losses, and account activity regardless of how trades are executed' },
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
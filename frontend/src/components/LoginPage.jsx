import { useState } from 'react'
import { useAuth } from '../hooks/useAuth'
import { Eye, EyeOff, Loader } from 'lucide-react'

export default function LoginPage() {
  const { login, register } = useAuth()
  const [mode,    setMode]    = useState('login')   // login | register
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  const [showPw,  setShowPw]  = useState(false)

  const [form, setForm] = useState({
    email: '', password: '', full_name: '', phone: '',
  })

  function set(field) {
    return e => setForm(f => ({ ...f, [field]: e.target.value }))
  }

  async function submit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (mode === 'login') {
        await login(form.email, form.password)
      } else {
        if (form.password.length < 8) { setError('Password must be at least 8 characters'); return }
        await register(form.email, form.password, form.full_name, form.phone)
      }
    } catch (err) {
      setError(err.response?.data?.detail ?? err.message ?? 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-dark-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">

        {/* Logo */}
        <div className="text-center mb-8">
          <img src="/logo.png" alt="Morviq AI" className="w-80 mx-auto mb-4"/>
          <p className="text-gray-400 text-sm mt-1">AI-Powered Trading Platform</p>
        </div>

        {/* Card */}
        <div className="bg-dark-800 border border-dark-600 rounded-2xl p-8">

          {/* Tabs */}
          <div className="flex bg-dark-700 rounded-xl p-1 mb-6">
            {['login','register'].map(m => (
              <button
                key={m}
                onClick={() => { setMode(m); setError('') }}
                className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-all capitalize ${
                  mode === m ? 'bg-brand-500 text-dark-900' : 'text-gray-400 hover:text-white'
                }`}
              >
                {m === 'login' ? 'Sign In' : 'Create Account'}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-4">

            {mode === 'register' && (
              <div>
                <label className="block text-xs text-gray-400 mb-1">Full Name</label>
                <input
                  type="text" value={form.full_name} onChange={set('full_name')}
                  placeholder="Randy Smith"
                  className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500 placeholder-gray-600"
                />
              </div>
            )}

            <div>
              <label className="block text-xs text-gray-400 mb-1">Email Address</label>
              <input
                type="email" value={form.email} onChange={set('email')} required
                placeholder="you@example.com"
                className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500 placeholder-gray-600"
              />
            </div>

            <div>
              <label className="block text-xs text-gray-400 mb-1">Password</label>
              <div className="relative">
                <input
                  type={showPw ? 'text' : 'password'}
                  value={form.password} onChange={set('password')} required
                  placeholder={mode === 'register' ? 'Min 8 characters' : '••••••••'}
                  className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 pr-10 text-white text-sm focus:outline-none focus:border-brand-500 placeholder-gray-600"
                />
                <button type="button" onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white">
                  {showPw ? <EyeOff size={16}/> : <Eye size={16}/>}
                </button>
              </div>
            </div>

            {mode === 'register' && (
              <div>
                <label className="block text-xs text-gray-400 mb-1">Phone (optional, for future SMS)</label>
                <input
                  type="tel" value={form.phone} onChange={set('phone')}
                  placeholder="+1 (555) 000-0000"
                  className="w-full bg-dark-700 border border-dark-600 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-brand-500 placeholder-gray-600"
                />
              </div>
            )}

            {error && (
              <div className="bg-red-900/30 border border-red-800 rounded-xl p-3 text-red-400 text-sm">
                {error}
              </div>
            )}

            <button
              type="submit" disabled={loading}
              className="w-full bg-brand-500 hover:bg-brand-600 text-dark-900 font-black py-3.5 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading
                ? <><Loader size={16} className="animate-spin"/> Processing…</>
                : mode === 'login' ? 'Sign In' : 'Create Account'
              }
            </button>
          </form>

          {mode === 'login' && (
            <p className="text-center text-xs text-gray-500 mt-4">
              Don't have an account?{' '}
              <button onClick={() => setMode('register')} className="text-brand-500 hover:underline">
                Sign up free
              </button>
            </p>
          )}
        </div>

        <p className="text-center text-xs text-gray-600 mt-6">
          Morviq AI · Paper trading by default · Not financial advice
        </p>
      </div>
    </div>
  )
}

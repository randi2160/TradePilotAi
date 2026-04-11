import { createContext, useContext, useState, useEffect } from 'react'
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use(config => {
  const token = localStorage.getItem('at_token')
  if (token) {
    config.headers = config.headers ?? {}
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const stored = localStorage.getItem('at_token')
    if (stored) {
      // Add 5 second timeout so it never hangs forever
      const timer = setTimeout(() => setLoading(false), 5000)
      api.get('/auth/me')
        .then(r => { setUser(r.data); setLoading(false) })
        .catch(() => setLoading(false))
        .finally(() => clearTimeout(timer))
    } else {
      setLoading(false)
    }
  }, [])

  async function login(email, password) {
    const r = await api.post('/auth/login', { email, password })
    localStorage.setItem('at_token', r.data.access_token)
    setUser(r.data.user)
    return r.data
  }

  async function register(email, password, full_name = '', phone = '') {
    const r = await api.post('/auth/register', { email, password, full_name, phone })
    localStorage.setItem('at_token', r.data.access_token)
    setUser(r.data.user)
    return r.data
  }

  async function updateProfile(data) {
    const r = await api.put('/auth/profile', data)
    setUser(r.data.user)
    return r.data
  }

  function logout() {
    localStorage.removeItem('at_token')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, token: localStorage.getItem('at_token'), loading, login, register, logout, updateProfile }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() { return useContext(AuthContext) }
export { api }

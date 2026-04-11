import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../hooks/useAuth'
import SymbolPopup from './SymbolPopup'

function TickerItem({ symbol, data, isNew }) {
  const up = (data.change_pct ?? 0) >= 0
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 border-r border-dark-600 whitespace-nowrap select-none ${isNew ? 'bg-brand-500/20' : ''}`}>
      <span className="font-black text-white text-xs">{symbol}</span>
      <span className="text-xs font-mono text-gray-300">${(data.price ?? 0).toFixed(2)}</span>
      <span className={`text-xs font-bold ${up ? 'text-green-400' : 'text-red-400'}`}>
        {up ? '▲' : '▼'}{Math.abs(data.change_pct ?? 0).toFixed(2)}%
      </span>
    </span>
  )
}

export default function LiveTicker({ watchlist = [] }) {
  const [items,   setItems]   = useState([])
  const [newSyms, setNewSyms] = useState([])
  const [popup,   setPopup]   = useState(null)   // { symbol, x, y }
  const scrollRef = useRef(null)
  const posRef    = useRef(0)
  const animRef   = useRef(null)
  const pausedRef = useRef(false)
  const prevWL    = useRef([])

  // Detect newly added symbols — flash them
  useEffect(() => {
    const added = watchlist.filter(s => !prevWL.current.includes(s))
    if (added.length) { setNewSyms(added); setTimeout(() => setNewSyms([]), 4000) }
    prevWL.current = watchlist
  }, [watchlist.join(',')])

  const fetchAll = useCallback(async () => {
    try {
      const [tickerRes, scanRes] = await Promise.allSettled([
        api.get('/ticker'),
        api.get('/scanner/gainers?n=15'),
      ])
      const prices  = tickerRes.status === 'fulfilled' ? tickerRes.value.data  : {}
      const gainers = scanRes.status   === 'fulfilled' ? scanRes.value.data    : []

      const combined = {}
      for (const g of gainers)
        combined[g.symbol] = { price: g.price, change_pct: g.change_pct, volume: g.volume, is_mover: true }
      for (const [sym, d] of Object.entries(prices))
        combined[sym] = { ...(combined[sym] ?? {}), ...d, is_watchlist: true }

      const sorted = Object.entries(combined)
        .sort(([,a],[,b]) => {
          if (a.is_watchlist && !b.is_watchlist) return -1
          if (!a.is_watchlist && b.is_watchlist) return 1
          return (b.change_pct ?? 0) - (a.change_pct ?? 0)
        })
        .map(([sym, d]) => ({ sym, ...d }))

      setItems(sorted)
    } catch {}
  }, [])

  useEffect(() => {
    fetchAll()
    const iv = setInterval(fetchAll, 15000)
    return () => clearInterval(iv)
  }, [fetchAll, watchlist.join(',')])

  // Smooth scroll
  useEffect(() => {
    const el = scrollRef.current
    if (!el || items.length === 0) return
    let pos = posRef.current
    const tick = () => {
      if (!pausedRef.current) {
        const halfW = el.scrollWidth / 2
        pos = (pos + 0.6) % halfW
        posRef.current = pos
        el.style.transform = `translateX(-${pos}px)`
      }
      animRef.current = requestAnimationFrame(tick)
    }
    animRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(animRef.current)
  }, [items.length])

  function handleClick(e, sym) {
    e.stopPropagation()
    pausedRef.current = false
    if (popup?.symbol === sym) { setPopup(null); return }
    setPopup({ symbol: sym, x: Math.min(e.clientX - 180, window.innerWidth - 420), y: e.clientY + 12 })
  }

  if (items.length === 0) return null

  return (
    <div>
      {/* Symbol popup */}
      {popup && (
        <SymbolPopup
          symbol={popup.symbol}
          position={{ x: popup.x, y: popup.y }}
          onClose={() => setPopup(null)}
        />
      )}

      {/* Ticker bar */}
      <div
        className="bg-dark-900 border-b border-dark-700 overflow-hidden h-7 flex items-center relative cursor-pointer"
        onMouseEnter={() => { pausedRef.current = true  }}
        onMouseLeave={() => { pausedRef.current = false }}
        onClick={() => setPopup(null)}
      >
        <div className="absolute left-0 top-0 bottom-0 w-8 bg-gradient-to-r from-dark-900 to-transparent z-10 pointer-events-none"/>
        <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-dark-900 to-transparent z-10 pointer-events-none"/>

        <div ref={scrollRef} className="flex items-center will-change-transform">
          {[...items, ...items].map((item, i) => (
            <span key={`${item.sym}-${i}`}
              onClick={e => handleClick(e, item.sym)}
              className="hover:bg-dark-700/60 transition-colors rounded"
              title={`Click to see ${item.sym} details & chat`}>
              <TickerItem symbol={item.sym} data={item} isNew={newSyms.includes(item.sym)}/>
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

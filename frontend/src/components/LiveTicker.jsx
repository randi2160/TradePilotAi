import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../hooks/useAuth'
import SymbolPopup from './SymbolPopup'

const SECTIONS = [
  { key: 'watchlist', label: '📋 WATCHLIST', color: 'text-brand-500'  },
  { key: 'gainers',   label: '🔥 TOP GAINERS', color: 'text-green-400' },
  { key: 'active',   label: '⚡ MOST ACTIVE',  color: 'text-yellow-400' },
  { key: 'losers',   label: '📉 TOP LOSERS',   color: 'text-red-400'   },
]

function TickerItem({ symbol, data, isNew, onClick }) {
  const up = (data.change_pct ?? 0) >= 0
  return (
    <span
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3 border-r border-dark-600 whitespace-nowrap cursor-pointer hover:bg-dark-700/50 transition-colors ${isNew ? 'bg-brand-500/20' : ''}`}
    >
      <span className="font-black text-white text-xs">{symbol}</span>
      {data.price > 0 && (
        <span className="text-xs font-mono text-gray-300">${data.price.toFixed(2)}</span>
      )}
      <span className={`text-xs font-bold ${up ? 'text-green-400' : 'text-red-400'}`}>
        {up ? '▲' : '▼'}{Math.abs(data.change_pct ?? 0).toFixed(2)}%
      </span>
      {data.volume > 0 && data.is_active && (
        <span className="text-xs text-yellow-400">
          {data.volume > 1e6 ? `${(data.volume/1e6).toFixed(0)}M` : `${(data.volume/1e3).toFixed(0)}K`}
        </span>
      )}
    </span>
  )
}

function SectionLabel({ label, color }) {
  return (
    <span className={`inline-flex items-center px-3 border-r border-dark-500 whitespace-nowrap text-xs font-black ${color} bg-dark-800`}>
      {label}
    </span>
  )
}

export default function LiveTicker({ watchlist = [] }) {
  const [watchlistPrices, setWatchlistPrices] = useState({})
  const [gainers,   setGainers]   = useState([])
  const [losers,    setLosers]    = useState([])
  const [actives,   setActives]   = useState([])
  const [newSyms,   setNewSyms]   = useState([])
  const [popup,     setPopup]     = useState(null)
  const scrollRef = useRef(null)
  const posRef    = useRef(0)
  const animRef   = useRef(null)
  const pausedRef = useRef(false)
  const prevWL    = useRef([])

  // Detect newly added symbols
  useEffect(() => {
    const added = watchlist.filter(s => !prevWL.current.includes(s))
    if (added.length) { setNewSyms(added); setTimeout(() => setNewSyms([]), 4000) }
    prevWL.current = watchlist
  }, [watchlist.join(',')])

  const fetchAll = useCallback(async () => {
    try {
      const [tickerRes, scanRes] = await Promise.allSettled([
        api.get('/ticker'),
        api.get('/scanner/scan'),
      ])

      if (tickerRes.status === 'fulfilled') {
        setWatchlistPrices(tickerRes.value.data)
      }

      if (scanRes.status === 'fulfilled') {
        const scan = scanRes.value.data
        setGainers((scan.gainers  ?? []).slice(0, 8))
        setLosers( (scan.losers   ?? []).slice(0, 5))
        setActives((scan.most_active ?? []).slice(0, 8))
      }
    } catch {}
  }, [])

  useEffect(() => {
    fetchAll()
    const iv = setInterval(fetchAll, 20000)
    return () => clearInterval(iv)
  }, [fetchAll, watchlist.join(',')])

  // Build the full ticker content with section labels
  const buildItems = () => {
    const items = []

    // Watchlist section
    if (watchlist.length > 0) {
      items.push({ type: 'label', key: 'lbl-wl', label: '📋 MY WATCHLIST', color: 'text-brand-500' })
      watchlist.forEach(sym => {
        const d = watchlistPrices[sym]
        if (d) items.push({ type: 'item', sym, data: { ...d, is_watchlist: true } })
      })
    }

    // Top gainers section
    if (gainers.length > 0) {
      items.push({ type: 'label', key: 'lbl-gain', label: '🔥 TOP GAINERS', color: 'text-green-400' })
      gainers.forEach(g => {
        items.push({ type: 'item', sym: g.symbol, data: { price: g.price, change_pct: g.change_pct, volume: g.volume, is_gainer: true } })
      })
    }

    // Most active section
    if (actives.length > 0) {
      items.push({ type: 'label', key: 'lbl-act', label: '⚡ MOST ACTIVE', color: 'text-yellow-400' })
      actives.forEach(a => {
        items.push({ type: 'item', sym: a.symbol, data: { price: a.price, change_pct: a.change_pct, volume: a.volume, is_active: true } })
      })
    }

    // Top losers section
    if (losers.length > 0) {
      items.push({ type: 'label', key: 'lbl-lose', label: '📉 TOP LOSERS', color: 'text-red-400' })
      losers.forEach(l => {
        items.push({ type: 'item', sym: l.symbol, data: { price: l.price, change_pct: l.change_pct, volume: l.volume, is_loser: true } })
      })
    }

    return items
  }

  const items  = buildItems()
  const doubled = [...items, ...items]

  // Smooth scroll
  useEffect(() => {
    const el = scrollRef.current
    if (!el || items.length === 0) return
    let pos = posRef.current
    const tick = () => {
      if (!pausedRef.current) {
        const halfW = el.scrollWidth / 2
        pos = (pos + 0.5) % halfW
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
    window.dispatchEvent(new CustomEvent('openSymbol', { detail: sym }))
  }

  if (items.length === 0) return null

  return (
    <div>
      {popup && (
        <SymbolPopup symbol={popup.symbol} position={{ x: popup.x, y: popup.y }} onClose={() => setPopup(null)}/>
      )}
      <div
        className="bg-dark-900 border-b border-dark-700 overflow-hidden h-7 flex items-center relative"
        onMouseEnter={() => { pausedRef.current = true }}
        onMouseLeave={() => { pausedRef.current = false }}
        onClick={() => setPopup(null)}
      >
        <div className="absolute left-0 top-0 bottom-0 w-8 bg-gradient-to-r from-dark-900 to-transparent z-10 pointer-events-none"/>
        <div className="absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-dark-900 to-transparent z-10 pointer-events-none"/>

        <div ref={scrollRef} className="flex items-center will-change-transform">
          {doubled.map((item, i) => (
            item.type === 'label'
              ? <SectionLabel key={`${item.key}-${i}`} label={item.label} color={item.color}/>
              : <TickerItem
                  key={`${item.sym}-${i}`}
                  symbol={item.sym}
                  data={item.data}
                  isNew={newSyms.includes(item.sym)}
                  onClick={e => handleClick(e, item.sym)}
                />
          ))}
        </div>
      </div>
    </div>
  )
}
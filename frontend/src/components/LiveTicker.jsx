import { useState, useEffect, useRef } from 'react'
import { api } from '../hooks/useAuth'

function TickerItem({ symbol, data }) {
  const up  = data.change_pct >= 0
  return (
    <span className="inline-flex items-center gap-2 px-4 border-r border-dark-600 whitespace-nowrap">
      <span className="font-black text-white text-xs">{symbol}</span>
      <span className="text-xs font-mono">${data.price?.toFixed(2)}</span>
      <span className={`text-xs font-bold ${up ? 'text-green-400' : 'text-red-400'}`}>
        {up ? '▲' : '▼'}{Math.abs(data.change_pct).toFixed(2)}%
      </span>
    </span>
  )
}

export default function LiveTicker({ watchlist = [] }) {
  const [prices, setPrices]   = useState({})
  const [paused, setPaused]   = useState(false)
  const scrollRef = useRef(null)
  const animRef   = useRef(null)
  const posRef    = useRef(0)

  useEffect(() => {
    if (!watchlist.length) return
    fetchPrices()
    const iv = setInterval(fetchPrices, 15000)
    return () => clearInterval(iv)
  }, [watchlist.join(',')])

  async function fetchPrices() {
    try {
      const r = await api.get('/ticker')
      setPrices(r.data)
    } catch {}
  }

  // Smooth scroll animation
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return

    let pos = posRef.current
    const totalW = el.scrollWidth / 2

    function tick() {
      if (!paused) {
        pos += 0.5
        if (pos >= totalW) pos = 0
        posRef.current = pos
        el.style.transform = `translateX(-${pos}px)`
      }
      animRef.current = requestAnimationFrame(tick)
    }

    animRef.current = requestAnimationFrame(tick)
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current)
    }
  }, [paused, Object.keys(prices).length])

  const symbols  = watchlist.filter(s => prices[s])
  const noData   = symbols.length === 0

  if (noData) return null

  // Duplicate the list so scrolling loops seamlessly
  const items = [...symbols, ...symbols]

  return (
    <div
      className="bg-dark-800 border-b border-dark-600 overflow-hidden h-8 flex items-center cursor-pointer select-none relative"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      title="Hover to pause"
    >
      {/* Gradient fade edges */}
      <div className="absolute left-0 top-0 bottom-0 w-12 bg-gradient-to-r from-dark-800 to-transparent z-10 pointer-events-none"/>
      <div className="absolute right-0 top-0 bottom-0 w-12 bg-gradient-to-l from-dark-800 to-transparent z-10 pointer-events-none"/>

      <div
        ref={scrollRef}
        className="flex items-center will-change-transform"
        style={{ transform: 'translateX(0px)' }}
      >
        {items.map((sym, i) => (
          <TickerItem key={`${sym}-${i}`} symbol={sym} data={prices[sym] ?? {}} />
        ))}
      </div>
    </div>
  )
}

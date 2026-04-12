/**
 * openSymbolBoard(symbol)
 * Call this from anywhere to open the symbol board overlay.
 * Uses a custom DOM event so it works across any component.
 * 
 * Usage:
 *   import { openSymbolBoard, SymbolLink } from '../utils/symbolBoard'
 *   
 *   // Programmatic:
 *   openSymbolBoard('NVDA')
 * 
 *   // As a component:
 *   <SymbolLink symbol="NVDA" />
 */

export function openSymbolBoard(symbol) {
  if (!symbol) return
  const clean = symbol.replace('$', '').toUpperCase().trim()
  window.dispatchEvent(new CustomEvent('openSymbol', { detail: clean }))
}

/**
 * SymbolLink — clickable $SYMBOL chip
 * Renders as a styled badge that opens the symbol board on click.
 */
export function SymbolLink({ symbol, price, change, className = '' }) {
  if (!symbol) return null
  const clean  = symbol.replace('$', '').toUpperCase()
  const isUp   = change >= 0
  const color  = change === undefined
    ? 'text-brand-400 hover:text-brand-300 bg-brand-500/10 hover:bg-brand-500/20 border-brand-500/30'
    : isUp
    ? 'text-green-400 hover:text-green-300 bg-green-900/20 hover:bg-green-900/30 border-green-800/40'
    : 'text-red-400   hover:text-red-300   bg-red-900/20   hover:bg-red-900/30   border-red-800/40'

  return (
    <button
      onClick={() => openSymbolBoard(clean)}
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border text-xs font-bold transition-all ${color} ${className}`}
    >
      <span>${clean}</span>
      {price !== undefined && <span className="font-normal opacity-80">${Number(price).toFixed(2)}</span>}
      {change !== undefined && (
        <span>{isUp ? '▲' : '▼'}{Math.abs(change).toFixed(2)}%</span>
      )}
    </button>
  )
}

/**
 * parseSymbolsInText — finds $TICKER patterns in text and makes them clickable
 * Usage: parseSymbolsInText("I love $NVDA and $TSLA today!")
 * Returns: array of strings and SymbolLink elements
 */
export function parseSymbolsInText(text) {
  if (!text) return []
  const parts = text.split(/(\$[A-Z]{1,5})/g)
  return parts.map((part, i) => {
    if (/^\$[A-Z]{1,5}$/.test(part)) {
      return <SymbolLink key={i} symbol={part}/>
    }
    return part
  })
}

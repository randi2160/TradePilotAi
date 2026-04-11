import { useState, useRef, useEffect, useCallback } from 'react'
import { X, Minus, Maximize2, GripHorizontal } from 'lucide-react'

export default function FloatingPanel({
  id,
  title,
  icon = '📊',
  children,
  defaultPos = { x: 40, y: 100 },
  defaultSize = { w: 380, h: 'auto' },
  onClose,
  color = '#00d4aa',
  minW = 300,
  zIndex = 100,
  onFocus,
}) {
  const [pos,        setPos]        = useState(defaultPos)
  const [size,       setSize]       = useState(defaultSize)
  const [minimized,  setMinimized]  = useState(false)
  const [maximized,  setMaximized]  = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [prevState,  setPrevState]  = useState(null)

  const panelRef  = useRef(null)
  const dragStart = useRef(null)

  // ── Drag ──────────────────────────────────────────────────────────────────

  const onMouseDown = useCallback((e) => {
    if (maximized) return
    e.preventDefault()
    onFocus?.()
    dragStart.current = {
      mx: e.clientX,
      my: e.clientY,
      px: pos.x,
      py: pos.y,
    }
    setIsDragging(true)
  }, [pos, maximized, onFocus])

  useEffect(() => {
    if (!isDragging) return

    const onMove = (e) => {
      const d = dragStart.current
      setPos({
        x: Math.max(0, d.px + e.clientX - d.mx),
        y: Math.max(0, d.py + e.clientY - d.my),
      })
    }

    const onUp = () => setIsDragging(false)

    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup',   onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup',   onUp)
    }
  }, [isDragging])

  // ── Minimize / Maximize ───────────────────────────────────────────────────

  function toggleMinimize() {
    setMinimized(m => !m)
    setMaximized(false)
  }

  function toggleMaximize() {
    if (maximized) {
      setMaximized(false)
    } else {
      setPrevState({ pos, size })
      setMaximized(true)
    }
    setMinimized(false)
  }

  // Maximized style
  const maxStyle = maximized ? {
    position: 'fixed',
    top: 48, left: 0, right: 0, bottom: 0,
    width: '100vw',
    height: 'calc(100vh - 48px)',
    zIndex: 9999,
  } : {}

  // Normal style
  const panelStyle = maximized ? maxStyle : {
    position: 'fixed',
    left:     pos.x,
    top:      pos.y,
    width:    size.w,
    minWidth: minW,
    zIndex,
  }

  return (
    <div
      ref={panelRef}
      style={panelStyle}
      onMouseDown={onFocus}
      className="select-none"
    >
      <div className={`rounded-xl overflow-hidden shadow-2xl border ${
        isDragging ? 'shadow-brand-500/30' : 'shadow-black/50'
      }`}
        style={{ borderColor: `${color}40`, background: '#111827' }}
      >

        {/* ── Title bar ────────────────────────────────────────────────────── */}
        <div
          onMouseDown={onMouseDown}
          className={`flex items-center gap-2 px-3 py-2.5 border-b border-dark-600 ${
            maximized ? 'cursor-default' : 'cursor-grab active:cursor-grabbing'
          }`}
          style={{ background: `${color}18` }}
        >
          <GripHorizontal size={14} className="text-gray-600" />
          <span className="text-sm">{icon}</span>
          <span className="text-sm font-bold text-white flex-1">{title}</span>

          {/* Window controls */}
          <div className="flex gap-1">
            <button
              onMouseDown={e => e.stopPropagation()}
              onClick={toggleMinimize}
              className="w-5 h-5 rounded-full bg-yellow-500/80 hover:bg-yellow-400 flex items-center justify-center"
              title="Minimize"
            >
              <Minus size={10} className="text-yellow-900" />
            </button>
            <button
              onMouseDown={e => e.stopPropagation()}
              onClick={toggleMaximize}
              className="w-5 h-5 rounded-full bg-green-500/80 hover:bg-green-400 flex items-center justify-center"
              title="Maximize"
            >
              <Maximize2 size={8} className="text-green-900" />
            </button>
            {onClose && (
              <button
                onMouseDown={e => e.stopPropagation()}
                onClick={onClose}
                className="w-5 h-5 rounded-full bg-red-500/80 hover:bg-red-400 flex items-center justify-center"
                title="Close"
              >
                <X size={8} className="text-red-900" />
              </button>
            )}
          </div>
        </div>

        {/* ── Content ──────────────────────────────────────────────────────── */}
        {!minimized && (
          <div className={`overflow-auto ${maximized ? 'h-[calc(100vh-100px)]' : 'max-h-[600px]'}`}>
            {children}
          </div>
        )}

        {minimized && (
          <div className="px-3 py-1.5 text-xs text-gray-500">
            Click <span className="text-yellow-400">—</span> to restore
          </div>
        )}
      </div>
    </div>
  )
}

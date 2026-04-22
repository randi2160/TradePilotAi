import { useEffect, useState } from 'react'
import { Shield, Lock, Zap, AlertTriangle, TrendingUp, Save, Activity } from 'lucide-react'
import {
  getProtectionSettings,
  updateProtectionSettings,
  getProtectionStatus,
  forceHarvest,
  getLadderStatus,
  forceLadderTick,
} from '../services/api'

const TIER_COLORS = {
  tier9_moon:       'text-purple-400',
  tier8_rocket:     'text-fuchsia-400',
  tier7_runner:     'text-emerald-400',
  tier6_breakout:   'text-green-400',
  tier5_strong:     'text-lime-400',
  tier4_building:   'text-teal-400',
  tier3_early:      'text-yellow-400',
  tier2_starter:    'text-amber-400',
  tier1_breakeven:  'text-orange-400',
  tier0_early_be:   'text-orange-300',
  tier_inactive:    'text-gray-500',
}
const TIER_LABELS = {
  tier9_moon:       'Moon',
  tier8_rocket:     'Rocket',
  tier7_runner:     'Runner',
  tier6_breakout:   'Breakout',
  tier5_strong:     'Strong',
  tier4_building:   'Building',
  tier3_early:      'Early',
  tier2_starter:    'Starter',
  tier1_breakeven:  'Breakeven',
  tier0_early_be:   'Early BE',
  tier_inactive:    'Inactive',
}

function money(v, digits = 2) {
  const n = parseFloat(v) || 0
  return n.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

function pct(v) { return (parseFloat(v || 0) * 100).toFixed(1) }

export default function ProtectionSettings() {
  const [cfg,    setCfg]    = useState(null)
  const [status, setStatus] = useState(null)
  const [ladder, setLadder] = useState(null)
  const [msg,    setMsg]    = useState('')
  const [saving, setSaving] = useState(false)
  const [busy,   setBusy]   = useState(false)
  const [ladBusy, setLadBusy] = useState(false)

  // Local editable fields
  const [enabled,          setEnabled]          = useState(true)
  const [milestoneSize,    setMilestoneSize]    = useState(100)
  const [lockPct,          setLockPct]          = useState(70)   // stored as %, converted
  const [harvestPosPct,    setHarvestPosPct]    = useState(8)
  const [harvestCap,       setHarvestCap]       = useState(500)
  const [breachAction,     setBreachAction]     = useState('halt_close')

  // Ladder
  const [ladderEnabled,   setLadderEnabled]   = useState(true)
  const [scaleoutEnabled, setScaleoutEnabled] = useState(true)
  const [scaleoutFrac,    setScaleoutFrac]    = useState(25)      // stored as %, converted
  const [concentration,   setConcentration]   = useState(30)      // stored as %, converted
  const [timeDecayHours,  setTimeDecayHours]  = useState(4)
  const [milestonesStr,   setMilestonesStr]   = useState('5, 10, 15') // editable % CSV

  // Intra-milestone trailing harvest — protects partial gains between ladder steps
  const [intraLockPct,    setIntraLockPct]    = useState(30)      // % of intra-gain give-back, stored as %
  const [minIntraGain,    setMinIntraGain]    = useState(15)      // $ floor below which trigger doesn't arm

  // Recovery mode — tighter risk when equity < base
  const [recSizeMult,     setRecSizeMult]     = useState(60)      // % of normal size, stored as %
  const [recStopMult,     setRecStopMult]     = useState(75)      // % of normal stop distance, stored as %
  const [recConfBoost,    setRecConfBoost]    = useState(5)       // confidence boost pts (0-50), stored as pts
  const [recBudget,       setRecBudget]       = useState(20)      // $ per-trade further-drawdown cap

  useEffect(() => { load() }, [])
  useEffect(() => {
    const iv = setInterval(() => { loadStatus(); loadLadder() }, 15000)
    return () => clearInterval(iv)
  }, [])

  async function load() {
    try {
      const s = await getProtectionSettings()
      setCfg(s)
      setEnabled(!!s.enabled)
      setMilestoneSize(s.milestone_size)
      setLockPct(Math.round((s.lock_pct || 0) * 100))
      setHarvestPosPct(Math.round((s.harvest_position_pct || 0) * 100))
      setHarvestCap(s.harvest_portfolio_cap)
      setBreachAction(s.breach_action || 'halt_close')
      // Ladder
      setLadderEnabled(s.ladder_enabled !== false)
      setScaleoutEnabled(s.scaleout_enabled !== false)
      setScaleoutFrac(Math.round((s.scaleout_fraction || 0.25) * 100))
      setConcentration(Math.round((s.concentration_pct || 0.30) * 100))
      setTimeDecayHours(s.time_decay_hours ?? 4)
      const ms = Array.isArray(s.scaleout_milestones) && s.scaleout_milestones.length
        ? s.scaleout_milestones
        : [0.05, 0.10, 0.15]
      setMilestonesStr(ms.map(x => Math.round(x * 100)).join(', '))
      // Intra-milestone + recovery — new in the gain-preservation upgrade.
      // `?? default` because older DB rows won't have these columns until
      // migrate_ladder.py has run.
      setIntraLockPct(Math.round((s.intra_lock_pct ?? 0.30) * 100))
      setMinIntraGain(s.min_intra_gain ?? 15)
      setRecSizeMult(Math.round((s.recovery_size_mult ?? 0.60) * 100))
      setRecStopMult(Math.round((s.recovery_stop_mult ?? 0.75) * 100))
      setRecConfBoost(Math.round((s.recovery_conf_boost ?? 0.05) * 100))
      setRecBudget(s.recovery_budget ?? 20)
    } catch (e) {
      flash(`❌ Load failed: ${e.message}`)
    }
    loadStatus()
    loadLadder()
  }

  async function loadStatus() {
    try { setStatus(await getProtectionStatus()) } catch {}
  }

  async function loadLadder() {
    try { setLadder(await getLadderStatus()) } catch {}
  }

  function parseMilestones(str) {
    return (str || '')
      .split(',')
      .map(s => parseFloat(s.trim()))
      .filter(n => Number.isFinite(n) && n > 0 && n <= 100)
      .map(n => +(n / 100).toFixed(4))
  }

  function flash(text) {
    setMsg(text)
    setTimeout(() => setMsg(''), 3000)
  }

  async function save() {
    setSaving(true)
    try {
      const milestones = parseMilestones(milestonesStr)
      const updated = await updateProtectionSettings({
        enabled,
        milestone_size:         milestoneSize,
        lock_pct:               lockPct / 100,
        harvest_position_pct:   harvestPosPct / 100,
        harvest_portfolio_cap:  harvestCap,
        breach_action:          breachAction,
        // Ladder
        ladder_enabled:         ladderEnabled,
        scaleout_enabled:       scaleoutEnabled,
        scaleout_milestones:    milestones.length ? milestones : [0.05, 0.10, 0.15],
        scaleout_fraction:      scaleoutFrac / 100,
        concentration_pct:      concentration / 100,
        time_decay_hours:       parseFloat(timeDecayHours) || 0,
        // Intra-milestone trailing harvest
        intra_lock_pct:         intraLockPct / 100,
        min_intra_gain:         parseFloat(minIntraGain) || 0,
        // Recovery-mode tuning
        recovery_size_mult:     recSizeMult / 100,
        recovery_stop_mult:     recStopMult / 100,
        recovery_conf_boost:    recConfBoost / 100,
        recovery_budget:        parseFloat(recBudget) || 0,
      })
      setCfg(updated)
      flash('✅ Protection settings saved')
      loadStatus()
      loadLadder()
    } catch (e) {
      flash(`❌ ${e.response?.data?.detail ?? e.message}`)
    } finally { setSaving(false) }
  }

  async function handleHarvestNow() {
    setBusy(true)
    try {
      const r = await forceHarvest()
      const n = (r.harvested || []).length
      flash(n > 0 ? `🌾 Harvested ${n} position(s)` : 'No positions exceed thresholds')
    } catch (e) {
      flash(`❌ ${e.response?.data?.detail ?? e.message}`)
    } finally { setBusy(false) }
  }

  async function handleLadderTick() {
    setLadBusy(true)
    try {
      const r = await forceLadderTick()
      const n = (r.actions || []).length
      flash(n > 0 ? `🪜 Ladder: ${n} action(s) executed` : 'Ladder tick complete — no triggers')
      loadLadder()
    } catch (e) {
      flash(`❌ ${e.response?.data?.detail ?? e.message}`)
    } finally { setLadBusy(false) }
  }

  const floor       = status?.floor_value || cfg?.floor_value || 0
  const base        = status?.initial_capital || cfg?.initial_capital || 0
  const compound    = status?.current_compound || 0
  const unrealized  = status?.current_unrealized || 0
  const gainToNext  = status?.gain_to_next_milestone || 0
  const peak        = status?.peak_compound || 0
  const liveEq      = status?.live_equity
  const breached    = status?.breached
  const lockedGains = Math.max(0, floor - base)

  return (
    <div className="bg-dark-800 border border-dark-600 rounded-xl p-5 space-y-5">
      {msg && (
        <div className="bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-sm text-white">
          {msg}
        </div>
      )}

      {/* ── Header + status ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <Shield size={20} className="text-brand-400" />
        <div>
          <h3 className="text-white font-bold text-lg">Profit Protection</h3>
          <p className="text-xs text-gray-500">
            Locks in realized gains so you can't fall below your starting capital.
          </p>
        </div>
      </div>

      {/* Live status tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-dark-900 border border-dark-600 rounded-lg p-3">
          <p className="text-xs text-gray-500 flex items-center gap-1">
            <Lock size={11}/> Locked floor
          </p>
          <p className="text-xl font-bold text-brand-400">${money(floor, 0)}</p>
          <p className="text-xs text-gray-600">base ${money(base, 0)} + locked ${money(lockedGains, 0)}</p>
        </div>
        <div className="bg-dark-900 border border-dark-600 rounded-lg p-3">
          <p className="text-xs text-gray-500">Compound realized</p>
          <p className={`text-xl font-bold ${compound >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {compound >= 0 ? '+' : ''}${money(compound)}
          </p>
          <p className="text-xs text-gray-600">peak ${money(peak, 0)}</p>
        </div>
        <div className="bg-dark-900 border border-dark-600 rounded-lg p-3">
          <p className="text-xs text-gray-500">Floating (unrealized)</p>
          <p className={`text-xl font-bold ${unrealized >= 0 ? 'text-yellow-400' : 'text-red-400'}`}>
            {unrealized >= 0 ? '+' : ''}${money(unrealized)}
          </p>
          <p className="text-xs text-gray-600">not yet banked</p>
        </div>
        <div className="bg-dark-900 border border-dark-600 rounded-lg p-3">
          <p className="text-xs text-gray-500">Next ratchet in</p>
          <p className="text-xl font-bold text-white">
            ${money(gainToNext, 0)}
          </p>
          <p className="text-xs text-gray-600">of realized</p>
        </div>
      </div>

      {/* Breach banner */}
      {breached && (
        <div className="bg-red-500/10 border border-red-500/40 rounded-lg p-3 flex items-center gap-2">
          <AlertTriangle size={18} className="text-red-400 shrink-0"/>
          <div className="flex-1">
            <p className="text-sm font-bold text-red-300">
              Floor breached — equity ${money(liveEq)} &lt; floor ${money(floor)}
            </p>
            <p className="text-xs text-red-400/80">
              Breach action <span className="font-mono">{cfg?.breach_action}</span> was triggered.
            </p>
          </div>
        </div>
      )}

      {/* ── Settings form ───────────────────────────────────────────────── */}
      <div className="space-y-4 border-t border-dark-600 pt-4">
        {/* Enabled */}
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={enabled}
            onChange={e => setEnabled(e.target.checked)}
            className="w-4 h-4 accent-brand-500"
          />
          <div>
            <p className="text-sm text-white font-semibold">Enable protection</p>
            <p className="text-xs text-gray-500">
              When off, the bot will not ratchet the floor or halt on breach.
            </p>
          </div>
        </label>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Milestone size */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Milestone size
              <span className="ml-2 text-gray-600">(how often floor ratchets)</span>
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
              <input
                type="number" min="10" step="10"
                value={milestoneSize}
                onChange={e => setMilestoneSize(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-8 pr-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
            </div>
            <p className="text-xs text-gray-600 mt-1">
              Floor steps up every ${money(milestoneSize, 0)} of compound realized.
            </p>
          </div>

          {/* Lock % */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Lock-in %
              <span className="ml-2 text-gray-600">(portion of gains permanently saved)</span>
            </label>
            <div className="relative">
              <input
                type="number" min="0" max="100" step="5"
                value={lockPct}
                onChange={e => setLockPct(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-3 pr-8 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">%</span>
            </div>
            <p className="text-xs text-gray-600 mt-1">
              e.g. 70% = for every $100 booked, $70 is permanent.
            </p>
          </div>

          {/* Harvest position % */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Harvest threshold — per position
            </label>
            <div className="relative">
              <input
                type="number" min="0" max="200" step="1"
                value={harvestPosPct}
                onChange={e => setHarvestPosPct(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-3 pr-8 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">%</span>
            </div>
            <p className="text-xs text-gray-600 mt-1">
              Force-close any single winner above +{harvestPosPct}% unrealized.
            </p>
          </div>

          {/* Harvest portfolio cap */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Harvest threshold — portfolio cap
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
              <input
                type="number" min="0" step="50"
                value={harvestCap}
                onChange={e => setHarvestCap(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-8 pr-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
            </div>
            <p className="text-xs text-gray-600 mt-1">
              When total floating exceeds this, close the biggest winner to bank it.
            </p>
          </div>
        </div>

        {/* Breach action */}
        <div>
          <label className="block text-xs text-gray-400 mb-1">If floor is breached</label>
          <div className="grid grid-cols-3 gap-2">
            {[
              { v: 'halt_close', label: 'Halt + close all', sub: 'Safest' },
              { v: 'halt_only',  label: 'Halt new trades',   sub: 'Keep positions open' },
              { v: 'alert_only', label: 'Alert only',        sub: 'No auto-action' },
            ].map(opt => (
              <button
                key={opt.v}
                onClick={() => setBreachAction(opt.v)}
                className={`rounded-lg border text-left px-3 py-2 transition-colors ${
                  breachAction === opt.v
                    ? 'border-brand-500 bg-brand-500/10'
                    : 'border-dark-600 bg-dark-700 hover:bg-dark-600'
                }`}
              >
                <p className={`text-sm font-bold ${breachAction === opt.v ? 'text-brand-400' : 'text-white'}`}>
                  {opt.label}
                </p>
                <p className="text-xs text-gray-500">{opt.sub}</p>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Intra-milestone trailing harvest ────────────────────────────── */}
      <div className="space-y-4 border-t border-dark-600 pt-4">
        <div className="flex items-center gap-3">
          <TrendingUp size={18} className="text-brand-400" />
          <div>
            <h3 className="text-white font-bold text-base">Gain preservation — intra-milestone trigger</h3>
            <p className="text-xs text-gray-500">
              Locks partial progress between ladder steps. If equity climbs above floor
              and then pulls back by more than this percentage of the peak, positions close
              to bank realized gains before they evaporate.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Intra give-back % */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Giveback tolerance %
              <span className="ml-2 text-gray-600">(of intra-milestone gain)</span>
            </label>
            <div className="relative">
              <input
                type="number" min="5" max="95" step="5"
                value={intraLockPct}
                onChange={e => setIntraLockPct(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-3 pr-8 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">%</span>
            </div>
            <p className="text-xs text-gray-600 mt-1">
              Lock {100 - intraLockPct}% of every intra-milestone gain.
              Lower = tighter protection; higher = let winners breathe.
            </p>
          </div>

          {/* Minimum gain to arm */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Min gain to arm trigger
              <span className="ml-2 text-gray-600">(noise floor)</span>
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
              <input
                type="number" min="1" step="1"
                value={minIntraGain}
                onChange={e => setMinIntraGain(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-8 pr-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
            </div>
            <p className="text-xs text-gray-600 mt-1">
              Trigger won't fire until peak is more than ${money(minIntraGain, 0)} above floor.
            </p>
          </div>
        </div>
      </div>

      {/* ── Recovery mode — below sacred base ───────────────────────────── */}
      <div className="space-y-4 border-t border-dark-600 pt-4">
        <div className="flex items-center gap-3">
          <AlertTriangle size={18} className="text-yellow-400" />
          <div>
            <h3 className="text-white font-bold text-base">Recovery mode — when equity dips below base</h3>
            <p className="text-xs text-gray-500">
              If live equity falls below your starting capital, the bot keeps trading
              with much tighter risk so it can climb back. Normal halt is suspended only
              when no gains are locked above the base.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Size multiplier */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Position size ×
              <span className="ml-2 text-gray-600">(fraction of normal)</span>
            </label>
            <div className="relative">
              <input
                type="number" min="5" max="150" step="5"
                value={recSizeMult}
                onChange={e => setRecSizeMult(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-3 pr-8 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">%</span>
            </div>
            <p className="text-xs text-gray-600 mt-1">
              Shrinks dollar-risk per trade while in recovery.
            </p>
          </div>

          {/* Stop multiplier */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Stop distance ×
              <span className="ml-2 text-gray-600">(tighter = smaller)</span>
            </label>
            <div className="relative">
              <input
                type="number" min="25" max="200" step="5"
                value={recStopMult}
                onChange={e => setRecStopMult(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-3 pr-8 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">%</span>
            </div>
            <p className="text-xs text-gray-600 mt-1">
              Tighter stops cap each loss — 75% is a good default.
            </p>
          </div>

          {/* Confidence boost */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Confidence boost
              <span className="ml-2 text-gray-600">(extra pts over min)</span>
            </label>
            <div className="relative">
              <input
                type="number" min="0" max="50" step="1"
                value={recConfBoost}
                onChange={e => setRecConfBoost(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-3 pr-8 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">pts</span>
            </div>
            <p className="text-xs text-gray-600 mt-1">
              Only take higher-conviction trades while recovering.
            </p>
          </div>

          {/* Drawdown budget */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Per-trade drawdown cap
              <span className="ml-2 text-gray-600">($ risk vs equity)</span>
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
              <input
                type="number" min="1" step="1"
                value={recBudget}
                onChange={e => setRecBudget(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-8 pr-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
            </div>
            <p className="text-xs text-gray-600 mt-1">
              No trade may risk pushing equity more than ${money(recBudget, 0)} lower.
            </p>
          </div>
        </div>
      </div>

      {/* ── Ladder: per-position trail + partial scale-out ──────────────── */}
      <div className="space-y-4 border-t border-dark-600 pt-4">
        <div className="flex items-center gap-3">
          <Activity size={18} className="text-brand-400" />
          <div>
            <h3 className="text-white font-bold text-base">Ladder — per-position trail</h3>
            <p className="text-xs text-gray-500">
              Persistent peak tracking, tiered trailing stops, and partial scale-outs.
              Locks in each winner's gains without all-or-nothing closes.
            </p>
          </div>
        </div>

        {/* Ladder live tiles */}
        {ladder && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <div className="bg-dark-900 border border-dark-600 rounded-lg p-3">
              <p className="text-xs text-gray-500">Total unrealized</p>
              <p className={`text-xl font-bold ${((ladder.total_unrealized || 0) >= 0) ? 'text-yellow-400' : 'text-red-400'}`}>
                {(ladder.total_unrealized || 0) >= 0 ? '+' : ''}${money(ladder.total_unrealized)}
              </p>
            </div>
            <div className="bg-dark-900 border border-dark-600 rounded-lg p-3">
              <p className="text-xs text-gray-500 flex items-center gap-1">
                <Lock size={11}/> Protected by trails
              </p>
              <p className="text-xl font-bold text-brand-400">${money(ladder.total_protected)}</p>
            </div>
            <div className="bg-dark-900 border border-dark-600 rounded-lg p-3">
              <p className="text-xs text-gray-500">Protection ratio</p>
              <p className="text-xl font-bold text-white">
                {Math.round((ladder.protection_ratio || 0) * 100)}%
              </p>
              <p className="text-xs text-gray-600">of unrealized locked</p>
            </div>
          </div>
        )}

        {/* Ladder enable toggles */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="flex items-center gap-3 cursor-pointer bg-dark-900 border border-dark-600 rounded-lg p-3">
            <input
              type="checkbox"
              checked={ladderEnabled}
              onChange={e => setLadderEnabled(e.target.checked)}
              className="w-4 h-4 accent-brand-500"
            />
            <div>
              <p className="text-sm text-white font-semibold">Enable trailing stops</p>
              <p className="text-xs text-gray-500">
                Close a position when it gives back enough of its peak gain.
              </p>
            </div>
          </label>
          <label className="flex items-center gap-3 cursor-pointer bg-dark-900 border border-dark-600 rounded-lg p-3">
            <input
              type="checkbox"
              checked={scaleoutEnabled}
              onChange={e => setScaleoutEnabled(e.target.checked)}
              className="w-4 h-4 accent-brand-500"
            />
            <div>
              <p className="text-sm text-white font-semibold">Enable partial scale-outs</p>
              <p className="text-xs text-gray-500">
                Sell a slice of the original qty at each milestone, keep a runner.
              </p>
            </div>
          </label>
        </div>

        {/* Ladder numeric fields */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Scale-out milestones
              <span className="ml-2 text-gray-600">(% gain, comma-separated)</span>
            </label>
            <input
              type="text"
              value={milestonesStr}
              onChange={e => setMilestonesStr(e.target.value)}
              placeholder="5, 10, 15"
              className="w-full bg-dark-700 border border-dark-600 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
            />
            <p className="text-xs text-gray-600 mt-1">
              At each milestone, sell a fraction of original qty.
            </p>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Scale-out fraction
              <span className="ml-2 text-gray-600">(of original qty, per milestone)</span>
            </label>
            <div className="relative">
              <input
                type="number" min="1" max="100" step="5"
                value={scaleoutFrac}
                onChange={e => setScaleoutFrac(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-3 pr-8 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">%</span>
            </div>
            <p className="text-xs text-gray-600 mt-1">
              e.g. 25% × 3 milestones = 75% banked, 25% rides.
            </p>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Concentration guard
              <span className="ml-2 text-gray-600">(tighten trail if over)</span>
            </label>
            <div className="relative">
              <input
                type="number" min="5" max="100" step="1"
                value={concentration}
                onChange={e => setConcentration(parseFloat(e.target.value) || 0)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-3 pr-8 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">%</span>
            </div>
            <p className="text-xs text-gray-600 mt-1">
              If any single position exceeds {concentration}% of equity, tighten its trail.
            </p>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Time-decay guard
              <span className="ml-2 text-gray-600">(hours without new peak)</span>
            </label>
            <div className="relative">
              <input
                type="number" min="0" step="0.5"
                value={timeDecayHours}
                onChange={e => setTimeDecayHours(e.target.value)}
                className="w-full bg-dark-700 border border-dark-600 rounded-lg pl-3 pr-8 py-2 text-white text-sm focus:outline-none focus:border-brand-500"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">h</span>
            </div>
            <p className="text-xs text-gray-600 mt-1">
              No new peak for {timeDecayHours}h → bump down one tier to lock more.
            </p>
          </div>
        </div>

        {/* Per-position ladder table */}
        {ladder?.positions?.length > 0 && (
          <div className="overflow-x-auto border border-dark-600 rounded-lg">
            <table className="w-full text-sm">
              <thead className="bg-dark-900 text-xs text-gray-400 uppercase">
                <tr>
                  <th className="text-left px-3 py-2">Symbol</th>
                  <th className="text-right px-3 py-2">Now</th>
                  <th className="text-right px-3 py-2">Peak</th>
                  <th className="text-right px-3 py-2">Trail</th>
                  <th className="text-left  px-3 py-2">Tier</th>
                  <th className="text-right px-3 py-2">Hit</th>
                  <th className="text-right px-3 py-2">Protected</th>
                  <th className="text-right px-3 py-2">Unrealized</th>
                </tr>
              </thead>
              <tbody>
                {ladder.positions.map(p => (
                  <tr key={p.symbol} className="border-t border-dark-700">
                    <td className="px-3 py-2 text-white font-semibold">{p.symbol}</td>
                    <td className={`px-3 py-2 text-right ${(p.current_pct || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {((p.current_pct || 0) * 100).toFixed(2)}%
                    </td>
                    <td className="px-3 py-2 text-right text-yellow-400">
                      {((p.peak_pct || 0) * 100).toFixed(2)}%
                    </td>
                    <td className="px-3 py-2 text-right text-brand-400">
                      {p.trail_pct == null ? '—' : `${(p.trail_pct * 100).toFixed(2)}%`}
                    </td>
                    <td className={`px-3 py-2 ${TIER_COLORS[p.tier] || 'text-gray-400'}`}>
                      {TIER_LABELS[p.tier] || p.tier}
                      {p.tier_bumps > 0 && (
                        <span className="ml-1 text-xs text-orange-400">↓{p.tier_bumps}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-400">
                      {(p.levels_hit || []).length > 0
                        ? (p.levels_hit).map(x => `${Math.round(x * 100)}%`).join(', ')
                        : '—'}
                    </td>
                    <td className="px-3 py-2 text-right text-brand-400">${money(p.protected_usd)}</td>
                    <td className={`px-3 py-2 text-right ${(p.unrealized_usd || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {(p.unrealized_usd || 0) >= 0 ? '+' : ''}${money(p.unrealized_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Actions ─────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 border-t border-dark-600 pt-4 flex-wrap">
        <button
          onClick={save}
          disabled={saving}
          className="flex items-center gap-2 bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-dark-900 font-bold px-4 py-2 rounded-lg transition-colors"
        >
          <Save size={16}/> {saving ? 'Saving…' : 'Save settings'}
        </button>
        <button
          onClick={handleHarvestNow}
          disabled={busy}
          className="flex items-center gap-2 bg-dark-700 hover:bg-dark-600 disabled:opacity-50 text-white font-semibold px-4 py-2 rounded-lg transition-colors border border-dark-600"
          title="Force-close any positions that exceed the harvest thresholds right now"
        >
          <Zap size={16} className="text-yellow-400"/> {busy ? 'Working…' : 'Harvest now'}
        </button>
        <button
          onClick={handleLadderTick}
          disabled={ladBusy}
          className="flex items-center gap-2 bg-dark-700 hover:bg-dark-600 disabled:opacity-50 text-white font-semibold px-4 py-2 rounded-lg transition-colors border border-dark-600"
          title="Run one ladder tick now: update peaks, check trail exits, execute scale-outs"
        >
          <Activity size={16} className="text-brand-400"/> {ladBusy ? 'Working…' : 'Ladder tick'}
        </button>
      </div>
    </div>
  )
}

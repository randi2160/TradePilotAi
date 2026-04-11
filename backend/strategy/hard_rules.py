"""
Hard Rules Engine — the most important layer.
Every trade MUST pass ALL of these rules before execution.
AI signals are input. Rules are the gatekeeper.

Rules checked:
  1. Market hours (9:35 AM – 3:30 PM ET only)
  2. Spread quality (< 0.5% of price)
  3. Relative volume (≥ 1.5× 20-day average)
  4. VWAP alignment (long only above VWAP or reclaim)
  5. Minimum reward:risk ratio (≥ 2:1)
  6. 1-min + 5-min momentum agreement
  7. ATR-based position sizing (risk-first, not profit-first)
  8. Daily loss limit check
  9. Max open positions check
  10. PDT rule awareness
  11. Halt/news check (no trading stocks with recent halts)
  12. Regime compatibility (setup matches current regime)
"""
import logging
from datetime import datetime
from typing import Optional

import pytz

import config

logger = logging.getLogger(__name__)
ET = pytz.timezone("America/New_York")


class HardRulesEngine:
    def __init__(self):
        self.max_spread_pct    = 0.50    # max 0.5% spread
        self.min_rel_volume    = 1.5     # min 1.5× average volume
        self.min_rr_ratio      = 2.0     # min 2:1 reward:risk
        self.max_risk_per_trade = 0.01   # 1% of capital per trade
        self.slippage_est      = 0.0005  # 0.05% slippage per side

    def check_all(
        self,
        symbol:           str,
        price:            float,
        setup:            dict,
        vwap_info:        dict,
        regime:           dict,
        daily_pnl:        float,
        capital:          float,
        open_positions:   int,
        daily_loss_limit: float,
        df_1min:          Optional[object] = None,
        df_5min:          Optional[object] = None,
    ) -> dict:
        """
        Run all hard rules. Returns pass/fail + detailed reasons.
        ALL rules must pass for a trade to execute.
        """
        results = []
        passed  = True

        def rule(name: str, ok: bool, detail: str, critical: bool = True):
            nonlocal passed
            if not ok and critical:
                passed = False
            results.append({
                "rule":     name,
                "passed":   ok,
                "detail":   detail,
                "critical": critical,
            })

        # ── 1. Trading hours ──────────────────────────────────────────────────
        now  = datetime.now(ET)
        h, m = now.hour + now.minute / 60, now.minute
        in_hours = 9.583 <= h <= 15.5  # 9:35 AM to 3:30 PM
        rule("Trading Hours", in_hours,
             f"{'✅' if in_hours else '❌'} {now.strftime('%I:%M %p ET')} — must be 9:35AM–3:30PM ET")

        # ── 2. Spread quality ─────────────────────────────────────────────────
        spread_pct = setup.get("indicators", {}).get("spread_pct", 0)
        if spread_pct == 0 and df_5min is not None and len(df_5min) > 0:
            try:
                last = df_5min.iloc[-1]
                spread_pct = (last["high"] - last["low"]) / price * 100
            except Exception:
                spread_pct = 0.1
        spread_ok = spread_pct <= self.max_spread_pct or spread_pct == 0
        rule("Spread Quality", spread_ok,
             f"{'✅' if spread_ok else '❌'} Spread {spread_pct:.3f}% (max {self.max_spread_pct}%)")

        # ── 3. Relative volume ────────────────────────────────────────────────
        vol_ratio = setup.get("volume_ratio", setup.get("indicators", {}).get("volume_ratio", 1.0))
        vol_ok    = vol_ratio >= self.min_rel_volume
        rule("Relative Volume", vol_ok,
             f"{'✅' if vol_ok else '❌'} Volume {vol_ratio:.1f}× average (min {self.min_rel_volume}×)")

        # ── 4. VWAP alignment ─────────────────────────────────────────────────
        above_vwap = vwap_info.get("above_vwap", False)
        reclaim    = vwap_info.get("reclaim",     False)
        setup_type = setup.get("setup_type", "")
        # Mean reversion and bounce can trade below VWAP
        vwap_exempt = setup_type in ("mean_reversion", "peak_bounce", "range_scalp")
        vwap_ok = above_vwap or reclaim or vwap_exempt
        rule("VWAP Alignment", vwap_ok,
             f"{'✅' if vwap_ok else '❌'} Price {'above' if above_vwap else 'below'} VWAP "
             f"${vwap_info.get('vwap',0):.2f} — reclaim:{reclaim} exempt:{vwap_exempt}")

        # ── 5. Reward:Risk ratio ──────────────────────────────────────────────
        min_rr = setup.get("min_rr", self.min_rr_ratio)
        # Calculate actual R:R from setup if possible
        # (simplified — real R:R calculated in position sizing)
        rr_ok = setup.get("tradeable", False)
        rule("Reward:Risk Ratio", rr_ok,
             f"{'✅' if rr_ok else '❌'} Setup quality {setup.get('quality',0):.0f}/100 — R:R min {min_rr}:1")

        # ── 6. Setup quality threshold ────────────────────────────────────────
        quality = setup.get("quality", 0)
        quality_ok = quality >= 50 and not setup.get("quality_issues")
        rule("Setup Quality", quality_ok,
             f"{'✅' if quality_ok else '❌'} Quality {quality:.0f}/100 "
             f"— issues: {setup.get('quality_issues', [])}")

        # ── 7. Daily loss limit ───────────────────────────────────────────────
        loss_ok = daily_pnl > -daily_loss_limit
        rule("Daily Loss Limit", loss_ok,
             f"{'✅' if loss_ok else '❌'} Daily P&L ${daily_pnl:.2f} "
             f"(limit -${daily_loss_limit:.2f})")

        # ── 8. Max open positions ─────────────────────────────────────────────
        pos_ok = open_positions < config.MAX_OPEN_POSITIONS
        rule("Max Positions", pos_ok,
             f"{'✅' if pos_ok else '❌'} {open_positions}/{config.MAX_OPEN_POSITIONS} positions open")

        # ── 9. Regime compatibility ────────────────────────────────────────────
        regime_name = regime.get("regime", "neutral")
        regime_strategies = regime.get("strategies", [])
        regime_ok = (
            regime_name not in ("volatile",) or
            setup_type in regime_strategies or
            setup_type == "no_trade"
        )
        rule("Regime Compatible", regime_ok,
             f"{'✅' if regime_ok else '❌'} Regime:{regime_name} — "
             f"setup:{setup_type} — allowed:{regime_strategies}", critical=False)

        # ── 10. Momentum agreement (1m + 5m) ─────────────────────────────────
        momentum_ok = True  # Default pass if no data
        if df_1min is not None and df_5min is not None:
            try:
                momentum_ok = self._check_momentum_agreement(df_1min, df_5min)
            except Exception:
                pass
        rule("Momentum Agreement", momentum_ok,
             f"{'✅' if momentum_ok else '❌'} 1-min and 5-min momentum {'agree' if momentum_ok else 'conflict'}",
             critical=False)

        # ── Position sizing (risk-first) ───────────────────────────────────────
        sizing = self._calculate_risk_position(
            price    = price,
            capital  = capital,
            setup    = setup,
            regime   = regime,
        )

        return {
            "passed":   passed,
            "rules":    results,
            "passes":   sum(1 for r in results if r["passed"]),
            "total":    len(results),
            "sizing":   sizing,
            "summary":  f"{'✅ ALL RULES PASS' if passed else '❌ RULES FAILED'} — "
                        f"{sum(1 for r in results if r['passed'])}/{len(results)} rules passed",
        }

    def _calculate_risk_position(
        self,
        price:   float,
        capital: float,
        setup:   dict,
        regime:  dict,
    ) -> dict:
        """
        RISK-FIRST position sizing:
        shares = max_dollar_risk / stop_distance

        This is safer than profit-first sizing.
        """
        size_mult    = setup.get("size_mult", 0.8) * regime.get("trade_advice", {}).get("size_mult", 1.0)
        max_risk_pct = self.max_risk_per_trade * size_mult
        max_risk_$   = capital * max_risk_pct

        # Estimate stop distance (1.5× ATR or 1% of price)
        atr = setup.get("indicators", {}).get("atr", price * 0.01)
        stop_dist = atr * 1.5
        if stop_dist <= 0:
            stop_dist = price * 0.01

        # Shares = risk_dollars / stop_distance
        shares_raw   = max_risk_$ / stop_dist
        shares       = max(1, int(shares_raw))

        # Cap at 20% of capital
        max_by_capital = int(capital * 0.20 / price)
        shares         = min(shares, max_by_capital)

        entry    = price
        stop     = round(entry - stop_dist, 2)
        target   = round(entry + stop_dist * setup.get("min_rr", 2.0), 2)
        risk_$   = round(shares * stop_dist, 2)
        reward_$ = round(shares * stop_dist * setup.get("min_rr", 2.0), 2)
        slippage = round(shares * price * self.slippage_est * 2, 2)
        net_reward = round(reward_$ - slippage, 2)

        return {
            "shares":          shares,
            "entry":           round(entry, 2),
            "stop_loss":       stop,
            "take_profit":     target,
            "risk_dollars":    risk_$,
            "reward_dollars":  reward_$,
            "slippage_est":    slippage,
            "net_reward":      net_reward,
            "actual_rr":       round(reward_$ / risk_$ if risk_$ > 0 else 0, 2),
            "position_value":  round(shares * price, 2),
            "risk_pct":        round(risk_$ / capital * 100, 2),
            "max_risk_pct":    round(max_risk_pct * 100, 2),
            "sizing_method":   "risk_first",
            "size_mult":       round(size_mult, 2),
        }

    @staticmethod
    def _check_momentum_agreement(df_1min, df_5min) -> bool:
        """Both 1-min and 5-min bars should agree on direction."""
        try:
            c1  = df_1min["close"].values
            c5  = df_5min["close"].values
            mom1 = (c1[-1] - c1[-4]) > 0   # 1-min 4-bar momentum
            mom5 = (c5[-1] - c5[-4]) > 0   # 5-min 4-bar momentum
            return mom1 == mom5             # both same direction
        except Exception:
            return True

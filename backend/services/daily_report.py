"""
Daily Report — generates a comprehensive end-of-day summary
of everything that happened: scans, signals, entries, exits,
P&L breakdown, and comparison against daily target.
"""
import logging
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)


class DailyReporter:
    def __init__(self):
        self._events: list = []     # live event log
        self._trade_log: list = []  # detailed trade records

    # ── Event logging ─────────────────────────────────────────────────────────

    def log(self, event_type: str, symbol: str, msg: str, detail: dict = None):
        self._events.append({
            "type":      event_type,
            "symbol":    symbol,
            "msg":       msg,
            "detail":    detail or {},
            "time":      datetime.now().strftime("%H:%M:%S"),
            "timestamp": datetime.now().isoformat(),
        })
        self._events = self._events[-500:]

    def log_scan(self, symbol: str, signal: str, confidence: float, reasons: list):
        self.log("scan", symbol, f"{signal} signal detected",
                 {"confidence": confidence, "reasons": reasons})

    def log_entry(self, symbol: str, side: str, qty: int, price: float,
                  stop: float, target: float, confidence: float):
        self.log("entry", symbol, f"ENTERED {side} {qty}×{symbol}",
                 {"side": side, "qty": qty, "price": price,
                  "stop_loss": stop, "take_profit": target, "confidence": confidence,
                  "position_value": round(qty * price, 2)})

    def log_exit(self, symbol: str, side: str, qty: int,
                 entry: float, exit_price: float, pnl: float, reason: str):
        self.log("exit", symbol, f"EXITED {symbol} | {'+'if pnl>=0 else ''}${pnl:.2f}",
                 {"side": side, "qty": qty, "entry": entry, "exit": exit_price,
                  "pnl": round(pnl, 2), "reason": reason,
                  "pnl_pct": round((exit_price - entry) / entry * 100, 2) if entry > 0 else 0})

        self._trade_log.append({
            "symbol": symbol, "side": side, "qty": qty,
            "entry": entry, "exit": exit_price, "pnl": round(pnl, 2),
            "reason": reason, "time": datetime.now().strftime("%H:%M:%S"),
            "date": str(date.today()),
        })

    def log_skip(self, symbol: str, reason: str):
        self.log("skip", symbol, f"Skipped {symbol}", {"reason": reason})

    def log_blocked(self, symbol: str, reason: str):
        self.log("blocked", symbol, f"Trade blocked", {"reason": reason})

    # ── Report generation ─────────────────────────────────────────────────────

    def generate_report(
        self,
        tracker_stats: dict,
        positions:     list,
        signals:       list,
        goal_plan:     dict = None,
    ) -> dict:
        today_trades = [t for t in self._trade_log if t.get("date") == str(date.today())]

        wins    = [t for t in today_trades if t.get("pnl", 0) > 0]
        losses  = [t for t in today_trades if t.get("pnl", 0) < 0]
        total_pnl = sum(t.get("pnl", 0) for t in today_trades)

        # By symbol breakdown
        by_symbol = {}
        for t in today_trades:
            sym = t["symbol"]
            if sym not in by_symbol:
                by_symbol[sym] = {"symbol": sym, "trades": 0, "pnl": 0, "wins": 0}
            by_symbol[sym]["trades"] += 1
            by_symbol[sym]["pnl"]    += t.get("pnl", 0)
            if t.get("pnl", 0) > 0:
                by_symbol[sym]["wins"] += 1

        by_symbol_list = sorted(by_symbol.values(), key=lambda x: x["pnl"], reverse=True)

        # Signals summary
        buy_signals  = [s for s in signals if s.get("signal") == "BUY"]
        sell_signals = [s for s in signals if s.get("signal") == "SELL"]

        # Goal progress
        goal_info = {}
        if goal_plan:
            daily_target = goal_plan.get("daily_target", 0)
            goal_info = {
                "daily_target":    daily_target,
                "achieved":        total_pnl,
                "hit":             total_pnl >= goal_plan.get("daily_target_min", daily_target * 0.7),
                "pct_of_target":   round(total_pnl / daily_target * 100, 1) if daily_target > 0 else 0,
                "monthly_goal":    goal_plan.get("monthly_goal", 0),
                "monthly_remaining": goal_plan.get("remaining_goal", 0),
            }

        # Today's event summary
        scan_count   = sum(1 for e in self._events if e["type"] == "scan"  and e["time"][:2] == datetime.now().strftime("%H")[:2])
        entry_events = [e for e in self._events if e["type"] == "entry"]
        exit_events  = [e for e in self._events if e["type"] == "exit"]

        return {
            "date":            str(date.today()),
            "generated_at":    datetime.now().strftime("%I:%M %p ET"),
            "summary": {
                "total_pnl":       round(total_pnl, 2),
                "total_trades":    len(today_trades),
                "wins":            len(wins),
                "losses":          len(losses),
                "win_rate":        round(len(wins)/len(today_trades)*100,1) if today_trades else 0,
                "best_trade":      max((t["pnl"] for t in today_trades), default=0),
                "worst_trade":     min((t["pnl"] for t in today_trades), default=0),
                "avg_win":         round(sum(t["pnl"] for t in wins)/len(wins),2) if wins else 0,
                "avg_loss":        round(sum(t["pnl"] for t in losses)/len(losses),2) if losses else 0,
                "open_positions":  len(positions),
                "unrealized_pnl":  tracker_stats.get("unrealized_pnl", 0),
            },
            "goal_progress":   goal_info,
            "by_symbol":       by_symbol_list,
            "trades":          list(reversed(today_trades[-20:])),
            "signals_now": {
                "buy_count":   len(buy_signals),
                "sell_count":  len(sell_signals),
                "buy_symbols": [s["symbol"] for s in buy_signals],
                "sell_symbols":[s["symbol"] for s in sell_signals],
                "watching":    len(signals),
            },
            "activity": {
                "total_events": len(self._events),
                "entries_today": len(entry_events),
                "exits_today":   len(exit_events),
                "recent_events": list(reversed(self._events[-20:])),
            },
        }

    def get_events(self, limit: int = 50, event_type: str = None) -> list:
        events = self._events
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        return list(reversed(events[-limit:]))

    def reset_day(self):
        """Call at market open each day."""
        self._events = []
        logger.info("Daily reporter reset for new trading day")

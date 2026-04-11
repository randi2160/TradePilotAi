"""
Email alert service — SendGrid integration.
Sends trade alerts, daily summaries, and error notifications.
"""
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

SENDGRID_API_KEY  = os.getenv("SENDGRID_API_KEY", "")
ALERT_FROM_EMAIL  = os.getenv("ALERT_FROM_EMAIL", "alerts@autotrader.local")

try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    _SENDGRID_OK = True
except ImportError:
    _SENDGRID_OK = False


class AlertService:
    def __init__(self):
        self.enabled = bool(SENDGRID_API_KEY and _SENDGRID_OK)
        if not self.enabled:
            logger.warning("AlertService: SendGrid not configured — email alerts disabled")

    # ── Core send ─────────────────────────────────────────────────────────────

    async def send(self, to_email: str, subject: str, html_body: str) -> bool:
        if not self.enabled or not to_email:
            logger.info(f"[EMAIL SUPPRESSED] To: {to_email} | {subject}")
            return False
        try:
            msg = Mail(
                from_email    = ALERT_FROM_EMAIL,
                to_emails     = to_email,
                subject       = subject,
                html_content  = html_body,
            )
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            sg.send(msg)
            logger.info(f"Email sent → {to_email}: {subject}")
            return True
        except Exception as e:
            logger.error(f"SendGrid error: {e}")
            return False

    # ── Alert types ───────────────────────────────────────────────────────────

    async def trade_opened(self, to_email: str, trade: dict):
        emoji = "📈" if trade.get("side") == "BUY" else "📉"
        subject = f"{emoji} Trade Opened: {trade['side']} {trade['qty']}× {trade['symbol']}"
        html = self._template(
            title   = f"{emoji} Trade Opened",
            color   = "#00d4aa",
            rows    = [
                ("Symbol",         trade["symbol"]),
                ("Direction",      trade["side"]),
                ("Quantity",       str(trade["qty"])),
                ("Entry Price",    f"${trade.get('entry_price', 0):.2f}"),
                ("Position Value", f"${trade.get('position_value', 0):.2f}"),
                ("Stop Loss",      f"${trade.get('stop_loss', 0):.2f}"),
                ("Take Profit",    f"${trade.get('take_profit', 0):.2f}"),
                ("Risk",           f"${trade.get('risk_dollars', 0):.2f} ({trade.get('risk_pct', 0):.1f}%)"),
                ("AI Confidence",  f"{(trade.get('confidence', 0)*100):.0f}%"),
                ("Time",           datetime.now().strftime("%I:%M %p ET")),
            ],
            footer = "AutoTrader Pro — Paper Mode" if trade.get("mode") == "paper" else "⚠️ LIVE TRADE",
        )
        await self.send(to_email, subject, html)

    async def trade_closed(self, to_email: str, trade: dict):
        pnl   = trade.get("pnl", 0)
        net   = trade.get("net_pnl", pnl)
        emoji = "✅" if pnl >= 0 else "❌"
        subject = f"{emoji} Trade Closed: {trade['symbol']} | PnL: {'+'if pnl>=0 else ''}${pnl:.2f}"
        html = self._template(
            title = f"{emoji} Trade Closed",
            color = "#00d4aa" if pnl >= 0 else "#ef4444",
            rows  = [
                ("Symbol",      trade["symbol"]),
                ("Direction",   trade.get("side", "")),
                ("Entry",       f"${trade.get('entry_price', 0):.2f}"),
                ("Exit",        f"${trade.get('exit_price', 0):.2f}"),
                ("Quantity",    str(trade.get("qty", 0))),
                ("Gross P&L",   f"{'+'if pnl>=0 else ''}${pnl:.2f}"),
                ("Net P&L",     f"{'+'if net>=0 else ''}${net:.2f}"),
                ("P&L %",       f"{'+'if trade.get('pnl_pct',0)>=0 else ''}{trade.get('pnl_pct',0):.2f}%"),
                ("Time",        datetime.now().strftime("%I:%M %p ET")),
            ],
            footer = "Keep it up! 🚀" if pnl >= 0 else "Stay disciplined. Next trade awaits.",
        )
        await self.send(to_email, subject, html)

    async def daily_target_hit(self, to_email: str, pnl: float, target: float):
        subject = f"🎯 Daily Target Hit! +${pnl:.2f} / ${target:.0f} goal"
        html = self._template(
            title = "🎯 Daily Target Reached!",
            color = "#00d4aa",
            rows  = [
                ("Today's P&L",   f"+${pnl:.2f}"),
                ("Daily Target",  f"${target:.2f}"),
                ("Status",        "✅ BOT STOPPED FOR TODAY — gains locked in"),
                ("Time",          datetime.now().strftime("%I:%M %p ET")),
            ],
            footer = "Great day! Bot will resume tomorrow at market open.",
        )
        await self.send(to_email, subject, html)

    async def stop_loss_hit(self, to_email: str, symbol: str, pnl: float):
        subject = f"🛑 Stop Loss Hit: {symbol} | ${pnl:.2f}"
        html = self._template(
            title = "🛑 Stop Loss Triggered",
            color = "#ef4444",
            rows  = [
                ("Symbol",  symbol),
                ("Loss",    f"${pnl:.2f}"),
                ("Action",  "Position closed automatically"),
                ("Time",    datetime.now().strftime("%I:%M %p ET")),
            ],
            footer = "Risk management working correctly — loss was controlled.",
        )
        await self.send(to_email, subject, html)

    async def daily_loss_limit(self, to_email: str, pnl: float, limit: float):
        subject = f"⛔ Daily Loss Limit Hit — Bot Stopped (${pnl:.2f})"
        html = self._template(
            title = "⛔ Daily Loss Limit Reached",
            color = "#ef4444",
            rows  = [
                ("Today's Loss", f"${pnl:.2f}"),
                ("Loss Limit",   f"${limit:.2f}"),
                ("Status",       "BOT STOPPED — no more trades today"),
                ("Time",         datetime.now().strftime("%I:%M %p ET")),
            ],
            footer = "Capital protected. Review signals tomorrow.",
        )
        await self.send(to_email, subject, html)

    async def daily_summary(self, to_email: str, stats: dict):
        pnl      = stats.get("realized_pnl", 0)
        trades   = stats.get("trade_count", 0)
        win_rate = stats.get("win_rate", 0)
        subject  = f"📊 Daily Summary | {'+'if pnl>=0 else ''}${pnl:.2f} | {trades} trades"
        html = self._template(
            title = "📊 Today's Trading Summary",
            color = "#00d4aa" if pnl >= 0 else "#ef4444",
            rows  = [
                ("Date",         datetime.now().strftime("%B %d, %Y")),
                ("Total P&L",    f"{'+'if pnl>=0 else ''}${pnl:.2f}"),
                ("Trades",       str(trades)),
                ("Win Rate",     f"{win_rate}%"),
                ("Capital",      f"${stats.get('capital', 0):,.2f}"),
                ("Progress",     f"{stats.get('progress_pct', 0):.0f}% of daily target"),
            ],
            footer = "AutoTrader Pro — See full details at your dashboard.",
        )
        await self.send(to_email, subject, html)

    async def bot_error(self, to_email: str, error: str):
        subject = "⚠️ AutoTrader Bot Error — Action Required"
        html = self._template(
            title  = "⚠️ Bot Error Detected",
            color  = "#f59e0b",
            rows   = [("Error", error), ("Time", datetime.now().strftime("%I:%M %p ET"))],
            footer = "Check your dashboard and restart if needed.",
        )
        await self.send(to_email, subject, html)

    # ── HTML template ─────────────────────────────────────────────────────────

    @staticmethod
    def _template(title: str, color: str, rows: list, footer: str = "") -> str:
        rows_html = "".join(
            f"""<tr>
              <td style="padding:8px 12px;color:#9ca3af;font-size:13px;width:40%">{k}</td>
              <td style="padding:8px 12px;color:#ffffff;font-size:13px;font-weight:600">{v}</td>
            </tr>"""
            for k, v in rows
        )
        return f"""
        <div style="background:#0a0e1a;padding:32px;font-family:-apple-system,sans-serif;max-width:520px;margin:0 auto">
          <div style="background:{color};border-radius:12px;padding:3px;margin-bottom:24px">
            <div style="background:#111827;border-radius:10px;padding:24px">
              <h2 style="color:{color};margin:0 0 4px;font-size:20px">{title}</h2>
              <p style="color:#6b7280;font-size:12px;margin:0">AutoTrader Pro</p>
            </div>
          </div>
          <table style="width:100%;border-collapse:collapse;background:#111827;border-radius:12px;overflow:hidden">
            {rows_html}
          </table>
          <p style="color:#4b5563;font-size:12px;text-align:center;margin-top:20px">{footer}</p>
          <p style="color:#374151;font-size:11px;text-align:center">
            Not financial advice. Always trade responsibly.
          </p>
        </div>"""

"""
Social Trading Service — handles trade broadcasting, follow system,
symbol chat, moderation, and copy trade triggering.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from database.models import (
    TraderProfile, TradeBroadcast, Follow, BroadcastLike,
    BroadcastComment, SymbolChatMessage, Group, GroupMember,
    GroupPost, ModerationAction, CopyConfig, SocialNotification,
    User, Trade,
)

logger = logging.getLogger(__name__)

# ── Profanity filter ──────────────────────────────────────────────────────────
PROFANITY_WORDS = {
    "fuck","shit","ass","bitch","cunt","dick","pussy","bastard",
    "damn","hell","crap","piss","cock","whore","slut","retard",
    # pump/dump language
    "guaranteed","100x","pump","dump","moonshot","lambo","get rich",
    "insider","tip","sure thing","cant lose","guaranteed profit",
}

PUMP_DUMP_PATTERNS = [
    r'\b(guaranteed|sure|definite)\s+(profit|gain|return|win)',
    r'\b(100|1000)x\b',
    r'\bbuy\s+now\s+before',
    r'\binsider\s+(tip|info|knowledge)',
    r'\bcant?\s+lose\b',
]


def check_content(text: str, level: str = "medium") -> dict:
    """
    Returns: {clean: bool, flagged: bool, removed: bool, reason: str}
    """
    lower = text.lower()
    words = set(re.findall(r'\b\w+\b', lower))

    # Profanity check
    found_profanity = words & PROFANITY_WORDS
    if found_profanity:
        if level == "strict":
            return {"clean": False, "flagged": False, "removed": True,
                    "reason": f"Profanity detected: {', '.join(found_profanity)}"}
        else:
            return {"clean": False, "flagged": True, "removed": False,
                    "reason": f"Profanity detected: {', '.join(found_profanity)}"}

    # Pump/dump check (always flag these)
    for pattern in PUMP_DUMP_PATTERNS:
        if re.search(pattern, lower):
            return {"clean": False, "flagged": True, "removed": False,
                    "reason": "Possible pump/dump language — flagged for review"}

    # Spam: too many symbols or caps
    if len(re.findall(r'\$[A-Z]{1,5}', text)) > 5:
        return {"clean": False, "flagged": True, "removed": False,
                "reason": "Possible spam — too many ticker mentions"}

    return {"clean": True, "flagged": False, "removed": False, "reason": ""}


# ── Trader Profile ─────────────────────────────────────────────────────────────

class SocialService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_profile(self, user: User) -> TraderProfile:
        profile = self.db.query(TraderProfile).filter_by(user_id=user.id).first()
        if not profile:
            profile = TraderProfile(
                user_id      = user.id,
                display_name = user.full_name or user.email.split("@")[0],
                is_public    = True,
                subscription_tier = "free",
            )
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)
        return profile

    def update_profile_stats(self, user_id: int):
        """Recalculate win rate, total PnL etc from trades table."""
        trades = self.db.query(Trade).filter(
            Trade.user_id == user_id,
            Trade.status  == "closed",
        ).all()

        if not trades:
            return

        wins      = [t for t in trades if (t.pnl or 0) > 0]
        total_pnl = sum(t.pnl or 0 for t in trades)
        win_rate  = len(wins) / len(trades) * 100 if trades else 0

        profile = self.db.query(TraderProfile).filter_by(user_id=user_id).first()
        if profile:
            profile.total_trades = len(trades)
            profile.win_rate     = round(win_rate, 1)
            profile.total_pnl    = round(total_pnl, 2)
            profile.avg_profit   = round(total_pnl / len(trades), 2) if trades else 0
            profile.days_tracked = (datetime.utcnow() - profile.created_at).days
            # Enable copy if 30+ days and 60%+ win rate
            profile.is_copyable  = profile.days_tracked >= 30 and win_rate >= 60
            self.db.commit()

    # ── Trade Broadcasting ─────────────────────────────────────────────────────

    def broadcast_trade(
        self,
        user:       User,
        trade:      Trade,
        action:     str,
        reasoning:  str = "",
    ) -> TradeBroadcast:
        """Called automatically whenever a trade executes."""
        profile    = self.get_or_create_profile(user)
        visibility = "public" if profile.is_public else "followers"

        broadcast = TradeBroadcast(
            trader_id   = user.id,
            trade_id    = trade.id,
            symbol      = trade.symbol,
            action      = action,
            qty         = trade.qty,
            price       = trade.entry_price if action == "BUY" else (trade.exit_price or 0),
            stop_loss   = trade.stop_loss,
            take_profit = trade.take_profit,
            confidence  = trade.confidence or 0,
            setup_type  = getattr(trade, 'setup_type', ''),
            reasoning   = reasoning,
            visibility  = visibility,
        )

        # If closing trade, fill result
        if action in ("CLOSED", "STOP_HIT", "TARGET_HIT") and trade.pnl is not None:
            broadcast.pnl       = trade.pnl
            broadcast.pnl_pct   = trade.pnl_pct
            broadcast.is_winner = trade.pnl > 0

        self.db.add(broadcast)
        self.db.commit()
        self.db.refresh(broadcast)

        # Notify followers
        self._notify_followers(user.id, broadcast)

        # Trigger copy trading engine
        try:
            from services.copy_engine import CopyTradingEngine
            copy_engine = CopyTradingEngine(self.db)
            copy_engine.process_broadcast(broadcast, user)
        except Exception as e:
            logger.debug(f"Copy engine skipped: {e}")

        # Update profile stats
        self.update_profile_stats(user.id)

        logger.info(f"Broadcast: {user.email} {action} {trade.symbol} @ ${broadcast.price:.2f}")
        return broadcast

    def _notify_followers(self, leader_id: int, broadcast: TradeBroadcast):
        followers = self.db.query(Follow).filter_by(
            leader_id    = leader_id,
            notify_trades = True,
        ).all()

        action_text = {
            "BUY":        f"📈 entered LONG {broadcast.symbol}",
            "SELL":       f"📉 exited {broadcast.symbol}",
            "STOP_HIT":   f"🛑 stop loss hit on {broadcast.symbol}",
            "TARGET_HIT": f"🎯 hit target on {broadcast.symbol}!",
            "CLOSED":     f"■ closed position on {broadcast.symbol}",
        }.get(broadcast.action, f"traded {broadcast.symbol}")

        for follow in followers:
            notif = SocialNotification(
                user_id = follow.follower_id,
                type    = "trade_broadcast",
                title   = f"@{broadcast.trader_id} {action_text}",
                body    = f"${broadcast.price:.2f} · Conf: {broadcast.confidence:.0%}",
                data    = {"broadcast_id": broadcast.id, "symbol": broadcast.symbol},
            )
            self.db.add(notif)
        self.db.commit()

    # ── Feed ──────────────────────────────────────────────────────────────────

    def get_feed(
        self,
        user_id:  int,
        limit:    int = 30,
        offset:   int = 0,
        symbol:   Optional[str] = None,
    ) -> list:
        """Get social feed for a user — their follows + public broadcasts."""
        # Get who they follow
        following_ids = [
            f.leader_id for f in
            self.db.query(Follow).filter_by(follower_id=user_id).all()
        ]
        # Include themselves
        following_ids.append(user_id)

        q = self.db.query(TradeBroadcast).filter(
            TradeBroadcast.trader_id.in_(following_ids),
            TradeBroadcast.visibility.in_(["public", "followers"]),
        )
        if symbol:
            q = q.filter(TradeBroadcast.symbol == symbol.upper())

        broadcasts = q.order_by(TradeBroadcast.created_at.desc()).offset(offset).limit(limit).all()

        result = []
        for b in broadcasts:
            profile = self.db.query(TraderProfile).filter_by(user_id=b.trader_id).first()
            user    = self.db.query(User).filter_by(id=b.trader_id).first()
            result.append({
                "id":           b.id,
                "trader": {
                    "id":           b.trader_id,
                    "display_name": profile.display_name if profile else (user.email.split("@")[0] if user else "Unknown"),
                    "win_rate":     profile.win_rate     if profile else 0,
                    "total_trades": profile.total_trades if profile else 0,
                    "is_copyable":  profile.is_copyable  if profile else False,
                },
                "symbol":       b.symbol,
                "action":       b.action,
                "qty":          b.qty,
                "price":        b.price,
                "stop_loss":    b.stop_loss,
                "take_profit":  b.take_profit,
                "confidence":   b.confidence,
                "setup_type":   b.setup_type,
                "reasoning":    b.reasoning,
                "pnl":          b.pnl,
                "pnl_pct":      b.pnl_pct,
                "is_winner":    b.is_winner,
                "likes":        b.likes,
                "copies_count": b.copies_count,
                "comments_count": b.comments_count,
                "visibility":   b.visibility,
                "created_at":   b.created_at.isoformat(),
            })
        return result

    def get_public_feed(self, limit: int = 50, symbol: str = None) -> list:
        """Public feed — no auth required."""
        q = self.db.query(TradeBroadcast).filter_by(visibility="public")
        if symbol:
            q = q.filter(TradeBroadcast.symbol == symbol.upper())
        broadcasts = q.order_by(TradeBroadcast.created_at.desc()).limit(limit).all()
        result = []
        for b in broadcasts:
            profile = self.db.query(TraderProfile).filter_by(user_id=b.trader_id).first()
            user    = self.db.query(User).filter_by(id=b.trader_id).first()
            result.append({
                "id":       b.id,
                "trader":   profile.display_name if profile else (user.email.split("@")[0] if user else "Trader"),
                "trader_id": b.trader_id,
                "symbol":   b.symbol,
                "action":   b.action,
                "qty":      b.qty,
                "price":    b.price,
                "stop_loss": b.stop_loss,
                "take_profit": b.take_profit,
                "confidence": b.confidence,
                "reasoning": b.reasoning,
                "pnl":      b.pnl,
                "is_winner": b.is_winner,
                "likes":    b.likes,
                "copies_count": b.copies_count,
                "created_at": b.created_at.isoformat(),
            })
        return result

    # ── Follow ────────────────────────────────────────────────────────────────

    def follow(self, follower_id: int, leader_id: int) -> dict:
        if follower_id == leader_id:
            return {"error": "Cannot follow yourself"}
        existing = self.db.query(Follow).filter_by(
            follower_id=follower_id, leader_id=leader_id
        ).first()
        if existing:
            return {"status": "already_following"}

        follow = Follow(follower_id=follower_id, leader_id=leader_id)
        self.db.add(follow)

        # Update follower count
        profile = self.db.query(TraderProfile).filter_by(user_id=leader_id).first()
        if profile:
            profile.followers_count = self.db.query(Follow).filter_by(leader_id=leader_id).count() + 1

        self.db.commit()
        return {"status": "following"}

    def unfollow(self, follower_id: int, leader_id: int) -> dict:
        follow = self.db.query(Follow).filter_by(
            follower_id=follower_id, leader_id=leader_id
        ).first()
        if follow:
            self.db.delete(follow)
            profile = self.db.query(TraderProfile).filter_by(user_id=leader_id).first()
            if profile:
                profile.followers_count = max(0, profile.followers_count - 1)
            self.db.commit()
        return {"status": "unfollowed"}

    def is_following(self, follower_id: int, leader_id: int) -> bool:
        return bool(self.db.query(Follow).filter_by(
            follower_id=follower_id, leader_id=leader_id
        ).first())

    # ── Symbol Chat ───────────────────────────────────────────────────────────

    def post_symbol_chat(
        self,
        user_id:   int,
        symbol:    str,
        content:   str,
        sentiment: str = "neutral",
    ) -> dict:
        # Check moderation
        check = check_content(content, level="medium")
        if check["removed"]:
            return {"error": f"Post removed: {check['reason']}"}

        msg = SymbolChatMessage(
            symbol     = symbol.upper(),
            user_id    = user_id,
            content    = content[:500],   # max 500 chars
            sentiment  = sentiment,
            is_flagged = check["flagged"],
        )
        self.db.add(msg)

        if check["flagged"]:
            self._add_strike(user_id, None, check["reason"])

        self.db.commit()
        self.db.refresh(msg)
        return {
            "id":        msg.id,
            "content":   msg.content,
            "symbol":    msg.symbol,
            "sentiment": msg.sentiment,
            "flagged":   msg.is_flagged,
            "warning":   check["reason"] if check["flagged"] else None,
        }

    def get_symbol_chat(self, symbol: str, limit: int = 50) -> list:
        msgs = self.db.query(SymbolChatMessage).filter(
            SymbolChatMessage.symbol     == symbol.upper(),
            SymbolChatMessage.is_removed == False,
        ).order_by(SymbolChatMessage.created_at.desc()).limit(limit).all()

        result = []
        for m in msgs:
            user = self.db.query(User).filter_by(id=m.user_id).first()
            prof = self.db.query(TraderProfile).filter_by(user_id=m.user_id).first()
            result.append({
                "id":          m.id,
                "user_id":     m.user_id,
                "display_name": prof.display_name if prof else (user.email.split("@")[0] if user else "User"),
                "content":     m.content,
                "sentiment":   m.sentiment,
                "likes":       m.likes,
                "is_flagged":  m.is_flagged,
                "created_at":  m.created_at.isoformat(),
            })
        return result

    # ── Likes ─────────────────────────────────────────────────────────────────

    def like_broadcast(self, user_id: int, broadcast_id: int) -> dict:
        existing = self.db.query(BroadcastLike).filter_by(
            broadcast_id=broadcast_id, user_id=user_id
        ).first()
        broadcast = self.db.query(TradeBroadcast).filter_by(id=broadcast_id).first()
        if not broadcast:
            return {"error": "Not found"}

        if existing:
            self.db.delete(existing)
            broadcast.likes = max(0, broadcast.likes - 1)
            self.db.commit()
            return {"liked": False, "likes": broadcast.likes}

        like = BroadcastLike(broadcast_id=broadcast_id, user_id=user_id)
        self.db.add(like)
        broadcast.likes += 1
        self.db.commit()
        return {"liked": True, "likes": broadcast.likes}

    # ── Moderation ─────────────────────────────────────────────────────────────

    def _add_strike(self, user_id: int, group_id: Optional[int], reason: str):
        """Add a strike. 3 strikes = auto-ban from group."""
        if group_id:
            member = self.db.query(GroupMember).filter_by(
                group_id=group_id, user_id=user_id
            ).first()
            if member:
                member.strikes += 1
                if member.strikes >= 3:
                    member.is_banned = True
                    self._log_moderation(group_id, user_id, 0, "temp_ban", "3 strikes auto-ban", 72)
                self.db.commit()

    def _log_moderation(
        self,
        group_id: Optional[int],
        target_id: int,
        admin_id: int,
        action: str,
        reason: str,
        hours: Optional[int] = None,
    ):
        expires = datetime.utcnow() + timedelta(hours=hours) if hours else None
        mod = ModerationAction(
            group_id       = group_id,
            target_user_id = target_id,
            admin_id       = admin_id or target_id,
            action         = action,
            reason         = reason,
            duration_hours = hours,
            expires_at     = expires,
        )
        self.db.add(mod)
        self.db.commit()

    def ban_user(
        self,
        admin_id:   int,
        group_id:   int,
        target_id:  int,
        reason:     str,
        hours:      Optional[int] = None,  # None = permanent
    ) -> dict:
        member = self.db.query(GroupMember).filter_by(
            group_id=group_id, user_id=target_id
        ).first()
        if not member:
            return {"error": "User not in group"}

        member.is_banned = True
        self._log_moderation(group_id, target_id, admin_id,
                             "perm_ban" if not hours else "temp_ban", reason, hours)
        self.db.commit()

        # Notify banned user
        duration_text = f"{hours}h" if hours else "permanently"
        notif = SocialNotification(
            user_id = target_id,
            type    = "ban",
            title   = f"You have been {'temporarily ' if hours else ''}banned from a group",
            body    = f"Reason: {reason} · Duration: {duration_text}",
            data    = {"group_id": group_id, "duration_hours": hours},
        )
        self.db.add(notif)
        self.db.commit()
        return {"status": "banned", "duration": hours}

    def get_notifications(self, user_id: int, limit: int = 20) -> list:
        notifs = self.db.query(SocialNotification).filter_by(
            user_id=user_id
        ).order_by(SocialNotification.created_at.desc()).limit(limit).all()

        result = []
        for n in notifs:
            result.append({
                "id":         n.id,
                "type":       n.type,
                "title":      n.title,
                "body":       n.body,
                "data":       n.data,
                "is_read":    n.is_read,
                "created_at": n.created_at.isoformat(),
            })
        return result

    def mark_notifications_read(self, user_id: int):
        self.db.query(SocialNotification).filter_by(
            user_id=user_id, is_read=False
        ).update({"is_read": True})
        self.db.commit()

    # ── Groups ────────────────────────────────────────────────────────────────

    def create_group(
        self,
        creator_id:  int,
        name:        str,
        description: str,
        category:    str = "general",
        is_public:   bool = True,
        rules:       str = "Be respectful. No spam. No pump & dump.",
    ) -> dict:
        existing = self.db.query(Group).filter_by(name=name).first()
        if existing:
            return {"error": f"Group '{name}' already exists"}

        group = Group(
            name        = name,
            description = description,
            creator_id  = creator_id,
            category    = category,
            is_public   = is_public,
            rules       = rules,
        )
        self.db.add(group)
        self.db.flush()

        # Add creator as owner
        member = GroupMember(group_id=group.id, user_id=creator_id, role="owner")
        self.db.add(member)
        self.db.commit()
        self.db.refresh(group)
        return {"id": group.id, "name": group.name, "status": "created"}

    def get_traders(self, limit: int = 20, min_win_rate: float = 0) -> list:
        """Get leaderboard of public traders."""
        profiles = self.db.query(TraderProfile).filter(
            TraderProfile.is_public    == True,
            TraderProfile.total_trades >= 5,
            TraderProfile.win_rate     >= min_win_rate,
        ).order_by(TraderProfile.win_rate.desc()).limit(limit).all()

        result = []
        for p in profiles:
            user = self.db.query(User).filter_by(id=p.user_id).first()
            result.append({
                "user_id":       p.user_id,
                "display_name":  p.display_name or (user.email.split("@")[0] if user else "Trader"),
                "win_rate":      p.win_rate,
                "total_trades":  p.total_trades,
                "total_pnl":     p.total_pnl,
                "avg_profit":    p.avg_profit,
                "followers":     p.followers_count,
                "days_tracked":  p.days_tracked,
                "is_copyable":   p.is_copyable,
                "tier":          p.subscription_tier,
            })
        return result

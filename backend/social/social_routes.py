"""
Social Trading API routes — feed, follow, chat, groups, moderation.
Prefix: /api/social
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.auth              import get_current_user
from database.database      import get_db
from database.models        import User, TradeBroadcast, TraderProfile, Group, GroupMember
from services.social_service import SocialService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/social", tags=["Social Trading"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    bio:          Optional[str] = None
    is_public:    Optional[bool] = None

class ChatPost(BaseModel):
    content:   str = Field(..., min_length=1, max_length=500)
    sentiment: str = Field("neutral", pattern="^(bullish|bearish|neutral)$")

class GroupCreate(BaseModel):
    name:        str = Field(..., min_length=3, max_length=100)
    description: str = Field("", max_length=1000)
    category:    str = Field("general")
    is_public:   bool = True
    rules:       str = Field("Be respectful. No spam. No pump & dump.")

class BanBody(BaseModel):
    target_user_id: int
    reason:         str
    hours:          Optional[int] = None   # None = permanent

class CommentBody(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/profile/me", summary="Get my trader profile")
async def my_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = SocialService(db)
    profile = svc.get_or_create_profile(user)
    svc.update_profile_stats(user.id)
    return {
        "user_id":        profile.user_id,
        "display_name":   profile.display_name,
        "bio":            profile.bio,
        "is_public":      profile.is_public,
        "is_copyable":    profile.is_copyable,
        "subscription":   profile.subscription_tier,
        "stats": {
            "total_trades":   profile.total_trades,
            "win_rate":       profile.win_rate,
            "total_pnl":      profile.total_pnl,
            "avg_profit":     profile.avg_profit,
            "days_tracked":   profile.days_tracked,
            "followers":      profile.followers_count,
        },
    }

@router.put("/profile/me", summary="Update my trader profile")
async def update_profile(
    body: ProfileUpdate,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    svc     = SocialService(db)
    profile = svc.get_or_create_profile(user)
    if body.display_name is not None: profile.display_name = body.display_name[:50]
    if body.bio          is not None: profile.bio          = body.bio[:500]
    if body.is_public    is not None: profile.is_public    = body.is_public
    db.commit()
    return {"status": "updated"}

@router.get("/profile/{user_id}", summary="Get public trader profile")
async def get_profile(user_id: int, db: Session = Depends(get_db)):
    profile = db.query(TraderProfile).filter_by(user_id=user_id, is_public=True).first()
    if not profile:
        raise HTTPException(404, "Profile not found or private")
    user = db.query(User).filter_by(id=user_id).first()
    return {
        "user_id":      profile.user_id,
        "display_name": profile.display_name,
        "bio":          profile.bio,
        "is_copyable":  profile.is_copyable,
        "stats": {
            "total_trades":  profile.total_trades,
            "win_rate":      profile.win_rate,
            "total_pnl":     profile.total_pnl,
            "days_tracked":  profile.days_tracked,
            "followers":     profile.followers_count,
        },
    }

@router.get("/traders", summary="Leaderboard of public traders")
async def get_traders(
    min_win_rate: float = 0,
    limit:        int   = 20,
    db:           Session = Depends(get_db),
):
    svc = SocialService(db)
    return svc.get_traders(limit=limit, min_win_rate=min_win_rate)


# ── Feed ──────────────────────────────────────────────────────────────────────

@router.get("/feed", summary="Get social feed (broadcasts from followed traders)")
async def get_feed(
    symbol: Optional[str] = None,
    limit:  int  = 30,
    offset: int  = 0,
    user:   User = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    svc = SocialService(db)
    return svc.get_feed(user.id, limit=limit, offset=offset, symbol=symbol)

@router.get("/feed/public", summary="Public trade broadcasts — no auth required")
async def public_feed(
    symbol: Optional[str] = None,
    limit:  int = 50,
    db:     Session = Depends(get_db),
):
    svc = SocialService(db)
    return svc.get_public_feed(limit=limit, symbol=symbol)

@router.get("/feed/my-broadcasts", summary="My own broadcast history")
async def my_broadcasts(
    limit:  int  = 50,
    user:   User = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    broadcasts = db.query(TradeBroadcast).filter_by(
        trader_id=user.id
    ).order_by(TradeBroadcast.created_at.desc()).limit(limit).all()

    return [{
        "id":           b.id,
        "symbol":       b.symbol,
        "action":       b.action,
        "qty":          b.qty,
        "price":        b.price,
        "stop_loss":    b.stop_loss,
        "take_profit":  b.take_profit,
        "confidence":   b.confidence,
        "reasoning":    b.reasoning,
        "pnl":          b.pnl,
        "is_winner":    b.is_winner,
        "likes":        b.likes,
        "copies_count": b.copies_count,
        "created_at":   b.created_at.isoformat(),
    } for b in broadcasts]

@router.post("/broadcast/{broadcast_id}/like", summary="Like/unlike a broadcast")
async def like_broadcast(
    broadcast_id: int,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    svc = SocialService(db)
    return svc.like_broadcast(user.id, broadcast_id)

@router.post("/broadcast/{broadcast_id}/comment", summary="Comment on a broadcast")
async def add_comment(
    broadcast_id: int,
    body: CommentBody,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    from services.social_service import check_content, BroadcastComment
    check = check_content(body.content)
    if check["removed"]:
        raise HTTPException(400, f"Comment blocked: {check['reason']}")
    comment = BroadcastComment(
        broadcast_id = broadcast_id,
        user_id      = user.id,
        content      = body.content,
        is_flagged   = check["flagged"],
    )
    db.add(comment)
    b = db.query(TradeBroadcast).filter_by(id=broadcast_id).first()
    if b:
        b.comments_count += 1
    db.commit()
    return {"status": "posted", "flagged": check["flagged"], "warning": check["reason"] if check["flagged"] else None}

@router.get("/broadcast/{broadcast_id}/comments", summary="Get comments on a broadcast")
async def get_comments(broadcast_id: int, db: Session = Depends(get_db)):
    from database.models import BroadcastComment
    comments = db.query(BroadcastComment).filter_by(
        broadcast_id=broadcast_id, is_removed=False
    ).order_by(BroadcastComment.created_at.desc()).limit(50).all()
    result = []
    for c in comments:
        user = db.query(User).filter_by(id=c.user_id).first()
        prof = db.query(TraderProfile).filter_by(user_id=c.user_id).first()
        result.append({
            "id":           c.id,
            "display_name": prof.display_name if prof else (user.email.split("@")[0] if user else "User"),
            "content":      c.content,
            "is_flagged":   c.is_flagged,
            "created_at":   c.created_at.isoformat(),
        })
    return result


# ── Follow ────────────────────────────────────────────────────────────────────

@router.post("/follow/{leader_id}", summary="Follow a trader")
async def follow(
    leader_id: int,
    user:      User    = Depends(get_current_user),
    db:        Session = Depends(get_db),
):
    svc = SocialService(db)
    return svc.follow(user.id, leader_id)

@router.delete("/follow/{leader_id}", summary="Unfollow a trader")
async def unfollow(
    leader_id: int,
    user:      User    = Depends(get_current_user),
    db:        Session = Depends(get_db),
):
    svc = SocialService(db)
    return svc.unfollow(user.id, leader_id)

@router.get("/following", summary="List traders I follow")
async def get_following(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from database.models import Follow
    follows = db.query(Follow).filter_by(follower_id=user.id).all()
    result  = []
    for f in follows:
        prof = db.query(TraderProfile).filter_by(user_id=f.leader_id).first()
        u    = db.query(User).filter_by(id=f.leader_id).first()
        result.append({
            "leader_id":    f.leader_id,
            "display_name": prof.display_name if prof else (u.email.split("@")[0] if u else "Trader"),
            "win_rate":     prof.win_rate     if prof else 0,
            "total_trades": prof.total_trades if prof else 0,
            "is_copyable":  prof.is_copyable  if prof else False,
            "followed_at":  f.created_at.isoformat(),
        })
    return result


# ── Symbol Chat ───────────────────────────────────────────────────────────────

@router.get("/chat/{symbol}", summary="Get chat messages for a symbol")
async def get_chat(symbol: str, limit: int = 50, db: Session = Depends(get_db)):
    svc = SocialService(db)
    return svc.get_symbol_chat(symbol.upper(), limit=limit)

@router.post("/chat/{symbol}", summary="Post a message in symbol chat")
async def post_chat(
    symbol: str,
    body:   ChatPost,
    user:   User    = Depends(get_current_user),
    db:     Session = Depends(get_db),
):
    svc    = SocialService(db)
    result = svc.post_symbol_chat(user.id, symbol, body.content, body.sentiment)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


# ── Groups ────────────────────────────────────────────────────────────────────

@router.get("/groups", summary="List public groups")
async def list_groups(
    category: Optional[str] = None,
    limit:    int = 20,
    db:       Session = Depends(get_db),
):
    q = db.query(Group).filter_by(is_public=True)
    if category:
        q = q.filter(Group.category == category)
    groups = q.order_by(Group.member_count.desc()).limit(limit).all()
    return [{
        "id":          g.id,
        "name":        g.name,
        "description": g.description,
        "category":    g.category,
        "members":     g.member_count,
        "win_rate":    g.win_rate,
    } for g in groups]

@router.post("/groups", summary="Create a trading group")
async def create_group(
    body: GroupCreate,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    svc    = SocialService(db)
    result = svc.create_group(
        creator_id  = user.id,
        name        = body.name,
        description = body.description,
        category    = body.category,
        is_public   = body.is_public,
        rules       = body.rules,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

@router.post("/groups/{group_id}/join", summary="Join a group")
async def join_group(
    group_id: int,
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    group = db.query(Group).filter_by(id=group_id).first()
    if not group:
        raise HTTPException(404, "Group not found")
    existing = db.query(GroupMember).filter_by(group_id=group_id, user_id=user.id).first()
    if existing:
        return {"status": "already_member"}
    member = GroupMember(group_id=group_id, user_id=user.id, role="member")
    db.add(member)
    group.member_count += 1
    db.commit()
    return {"status": "joined", "group": group.name}

@router.get("/groups/{group_id}", summary="Get group details + recent posts")
async def get_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(Group).filter_by(id=group_id).first()
    if not group:
        raise HTTPException(404, "Group not found")
    posts = db.query(GroupPost).filter_by(
        group_id=group_id, is_removed=False
    ).order_by(GroupPost.created_at.desc()).limit(20).all()
    post_list = []
    for p in posts:
        u    = db.query(User).filter_by(id=p.user_id).first()
        prof = db.query(TraderProfile).filter_by(user_id=p.user_id).first()
        post_list.append({
            "id":           p.id,
            "display_name": prof.display_name if prof else (u.email.split("@")[0] if u else "User"),
            "content":      p.content,
            "symbol":       p.symbol,
            "sentiment":    p.sentiment,
            "is_pinned":    p.is_pinned,
            "likes":        p.likes,
            "created_at":   p.created_at.isoformat(),
        })
    return {
        "id":          group.id,
        "name":        group.name,
        "description": group.description,
        "category":    group.category,
        "rules":       group.rules,
        "members":     group.member_count,
        "is_public":   group.is_public,
        "posts":       post_list,
    }

@router.post("/groups/{group_id}/posts", summary="Post in a group")
async def group_post(
    group_id: int,
    body:     ChatPost,
    user:     User    = Depends(get_current_user),
    db:       Session = Depends(get_db),
):
    member = db.query(GroupMember).filter_by(
        group_id=group_id, user_id=user.id, is_banned=False
    ).first()
    if not member:
        raise HTTPException(403, "Join the group first to post")

    from services.social_service import check_content
    group = db.query(Group).filter_by(id=group_id).first()
    check = check_content(body.content, level=group.profanity_level if group else "medium")
    if check["removed"]:
        raise HTTPException(400, f"Post blocked: {check['reason']}")

    post = GroupPost(
        group_id   = group_id,
        user_id    = user.id,
        content    = body.content,
        sentiment  = body.sentiment,
        is_flagged = check["flagged"],
    )
    db.add(post)
    db.commit()
    return {"status": "posted", "flagged": check["flagged"]}


# ── Moderation ────────────────────────────────────────────────────────────────

@router.post("/groups/{group_id}/ban", summary="Ban a user from a group (admin only)")
async def ban_user(
    group_id: int,
    body:     BanBody,
    user:     User    = Depends(get_current_user),
    db:       Session = Depends(get_db),
):
    # Check admin
    member = db.query(GroupMember).filter_by(
        group_id=group_id, user_id=user.id
    ).first()
    if not member or member.role not in ("owner", "admin", "mod"):
        raise HTTPException(403, "Admin access required")

    svc = SocialService(db)
    return svc.ban_user(user.id, group_id, body.target_user_id, body.reason, body.hours)

@router.get("/groups/{group_id}/members", summary="List group members (admin view)")
async def group_members(
    group_id: int,
    user:     User    = Depends(get_current_user),
    db:       Session = Depends(get_db),
):
    member = db.query(GroupMember).filter_by(group_id=group_id, user_id=user.id).first()
    if not member or member.role not in ("owner", "admin", "mod"):
        raise HTTPException(403, "Admin access required")

    members = db.query(GroupMember).filter_by(group_id=group_id).all()
    result  = []
    for m in members:
        u    = db.query(User).filter_by(id=m.user_id).first()
        prof = db.query(TraderProfile).filter_by(user_id=m.user_id).first()
        result.append({
            "user_id":      m.user_id,
            "display_name": prof.display_name if prof else (u.email.split("@")[0] if u else "User"),
            "role":         m.role,
            "strikes":      m.strikes,
            "is_banned":    m.is_banned,
            "joined_at":    m.joined_at.isoformat(),
        })
    return result

@router.delete("/groups/{group_id}/posts/{post_id}", summary="Remove a post (admin only)")
async def remove_post(
    group_id: int,
    post_id:  int,
    user:     User    = Depends(get_current_user),
    db:       Session = Depends(get_db),
):
    member = db.query(GroupMember).filter_by(group_id=group_id, user_id=user.id).first()
    if not member or member.role not in ("owner", "admin", "mod"):
        raise HTTPException(403, "Admin access required")
    post = db.query(GroupPost).filter_by(id=post_id, group_id=group_id).first()
    if post:
        post.is_removed = True
        db.commit()
    return {"status": "removed"}


# ── Notifications ─────────────────────────────────────────────────────────────

@router.get("/notifications", summary="Get my notifications")
async def get_notifications(
    user: User    = Depends(get_current_user),
    db:   Session = Depends(get_db),
):
    svc = SocialService(db)
    return svc.get_notifications(user.id)

@router.post("/notifications/read", summary="Mark all notifications as read")
async def mark_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = SocialService(db)
    svc.mark_notifications_read(user.id)
    return {"status": "marked read"}

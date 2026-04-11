"""IPO Intelligence Routes — /api/ipo"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.auth         import get_current_user
from database.database import get_db
from database.models   import User
from services.ipo_service import IPOService
import config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ipo", tags=["IPO Intelligence"])

_svc = IPOService()


@router.get("/calendar", summary="Get upcoming IPO calendar")
async def get_ipo_calendar(user: User = Depends(get_current_user)):
    return await _svc.get_ipo_calendar()


@router.get("/news", summary="Get IPO-related news")
async def get_ipo_news(user: User = Depends(get_current_user)):
    return await _svc.get_ipo_news(
        alpaca_key    = config.ALPACA_API_KEY,
        alpaca_secret = config.ALPACA_SECRET_KEY,
    )


@router.get("/pre-ipo", summary="Get watched pre-IPO companies")
async def get_pre_ipo(user: User = Depends(get_current_user)):
    from services.ipo_service import WATCHED_PRE_IPO
    return WATCHED_PRE_IPO


@router.get("/check/{company_name}", summary="Check if pre-IPO company has a symbol yet")
async def check_symbol(company_name: str, user: User = Depends(get_current_user)):
    symbol = await _svc.check_symbol_available(
        company_name,
        alpaca_key = config.ALPACA_API_KEY,
    )
    return {
        "company": company_name,
        "symbol":  symbol,
        "listed":  symbol is not None,
        "message": f"🎉 {company_name} is now trading as ${symbol}!" if symbol else f"Not yet listed",
    }

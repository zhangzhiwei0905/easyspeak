"""WeChat login and JWT auth."""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.schemas.user import WxLoginRequest, WxLoginResponse
from app.config import get_settings
from jose import jwt

from datetime import datetime, timedelta, timezone

import httpx

router = APIRouter()
settings = get_settings()


async def get_current_user(
    authorization: str = Header(..., alias="Authorization"),
    db: Session = Depends(get_db),
) -> User:
    """Dependency: extract user from JWT token in Authorization header."""
    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        openid = payload.get("sub")
        if not openid:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.openid == openid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def create_token(openid: str) -> str:
    """Create JWT token for user."""
    payload = {
        "sub": openid,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@router.post("/login", response_model=WxLoginResponse)
async def wx_login(request: WxLoginRequest, db: Session = Depends(get_db)):
    """
    WeChat mini program login.
    Exchange code for openid via WeChat API, create user if new.
    """
    if not settings.WECHAT_APP_ID or not settings.WECHAT_APP_SECRET:
        # Dev mode: accept any code as openid for testing
        openid = f"dev_{request.code}"
    else:
        # Production: call WeChat API
        wx_url = "https://api.weixin.qq.com/sns/jscode2session"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                wx_url,
                params={
                    "appid": settings.WECHAT_APP_ID,
                    "secret": settings.WECHAT_APP_SECRET,
                    "js_code": request.code,
                    "grant_type": "authorization_code",
                },
            )
            data = resp.json()
            openid = data.get("openid")
            if not openid:
                raise HTTPException(
                    status_code=400,
                    detail=f"WeChat login failed: {data.get('errmsg', 'unknown error')}",
                )

    # Create or get user
    user = db.query(User).filter(User.openid == openid).first()
    is_new = user is None
    if is_new:
        user = User(openid=openid)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_token(openid)
    return WxLoginResponse(token=token, openid=openid, is_new_user=is_new)

"""Investment dashboard API — auth, investor accounts, admin panel."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.investment.registry import InvestmentAccount, get_investment_registry
from app.investment.yield_calc import period_days, period_rate_pct
from app.investment.tokens import create_token, verify_token
from app.investment.users import get_user_registry

router = APIRouter(prefix="/investment", tags=["investment"])


class RegisterBody(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=6, max_length=128)
    full_name: str = Field(default="", max_length=120)
    referral_code: str | None = Field(default=None, max_length=32)


class LoginBody(BaseModel):
    email: str = Field(..., min_length=5, max_length=120)
    password: str = Field(..., min_length=1, max_length=128)


class CashBody(BaseModel):
    amount: float = Field(..., gt=0, le=1_000_000)
    note: str | None = None


def _auth_user(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Login required")
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(401, "Invalid or expired session")
    users = get_user_registry()
    user = users.get(str(payload["sub"]))
    if user is None:
        raise HTTPException(401, "User not found")
    return {"user": user, "token_payload": payload}


def _require_admin(authorization: str | None) -> dict:
    ctx = _auth_user(authorization)
    if ctx["user"].role != "admin":
        raise HTTPException(403, "Admin access required")
    return ctx


def _resolve_investor_account(
    ctx: dict,
    x_jm_invest_id: str | None,
    x_jm_invest_token: str | None,
) -> InvestmentAccount:
    user = ctx["user"]
    reg = get_investment_registry()
    if user.role == "admin" and x_jm_invest_id and x_jm_invest_token:
        try:
            return reg.require(x_jm_invest_id, x_jm_invest_token)
        except KeyError:
            raise HTTPException(404, "Investment account not found") from None
        except PermissionError:
            raise HTTPException(403, "Invalid investment token") from None
    if not user.account_id:
        raise HTTPException(404, "No investment account linked")
    acc = reg.get(user.account_id)
    if acc is None:
        raise HTTPException(404, "Investment account not found")
    if x_jm_invest_token and acc.token != x_jm_invest_token:
        raise HTTPException(403, "Invalid investment token")
    return acc


def _session_response(user, acc: InvestmentAccount, reg) -> dict:
    auth_token = create_token({"sub": user.id, "role": user.role})
    dash = acc.dashboard(reg)
    return {
        "ok": True,
        "auth_token": auth_token,
        "user": user.public(),
        "account_id": acc.id,
        "account_token": acc.token,
        "account": dash,
    }


def _resolve_referrer(reg, code: str | None) -> str | None:
    if not code or not str(code).strip():
        return None
    referrer = reg.get_by_referral_code(str(code))
    if referrer is None:
        raise HTTPException(400, "Invalid referral code")
    return referrer.id


@router.post("/auth/register")
async def register_investor(body: RegisterBody) -> dict:
    reg = get_investment_registry()
    users = get_user_registry()
    try:
        referred_by = _resolve_referrer(reg, body.referral_code)
        acc = reg.create(
            label=body.full_name or body.email.split("@")[0],
            referred_by=referred_by,
        )
        user = users.register(
            email=str(body.email),
            password=body.password,
            full_name=body.full_name,
            account_id=acc.id,
        )
        acc.user_id = user.id
        reg.save()
        return _session_response(user, acc, reg)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/auth/login")
async def login_investor(body: LoginBody) -> dict:
    users = get_user_registry()
    reg = get_investment_registry()
    user = users.authenticate(str(body.email), body.password)
    if user is None:
        raise HTTPException(401, "Invalid email or password")
    if not user.account_id and user.role == "investor":
        raise HTTPException(404, "No investment account linked")
    acc = reg.get(user.account_id) if user.account_id else None
    if user.role == "investor" and acc is None:
        raise HTTPException(404, "Investment account not found")
    if acc:
        reg.save()
        return _session_response(user, acc, reg)
    auth_token = create_token({"sub": user.id, "role": user.role})
    return {
        "ok": True,
        "auth_token": auth_token,
        "user": user.public(),
        "account": None,
    }


@router.get("/auth/me")
async def auth_me(authorization: str | None = Header(default=None)) -> dict:
    ctx = _auth_user(authorization)
    user = ctx["user"]
    reg = get_investment_registry()
    account = None
    if user.account_id:
        acc = reg.get(user.account_id)
        if acc:
            account = acc.dashboard(reg)
            reg.save()
    return {"ok": True, "user": user.public(), "account": account}


@router.get("/accounts/me")
async def investment_me(
    authorization: str | None = Header(default=None),
    x_jm_invest_id: str | None = Header(default=None, alias="X-JM-Invest-Id"),
    x_jm_invest_token: str | None = Header(default=None, alias="X-JM-Invest-Token"),
) -> dict:
    ctx = _auth_user(authorization)
    acc = _resolve_investor_account(ctx, x_jm_invest_id, x_jm_invest_token)
    reg = get_investment_registry()
    dash = acc.dashboard(reg)
    reg.save()
    return {"ok": True, "account": dash, "user": ctx["user"].public()}


@router.get("/referrals/me")
async def referral_me(authorization: str | None = Header(default=None)) -> dict:
    ctx = _auth_user(authorization)
    reg = get_investment_registry()
    acc = reg.get(ctx["user"].account_id) if ctx["user"].account_id else None
    if acc is None:
        raise HTTPException(404, "Investment account not found")
    from app.investment.referrals import referral_dashboard

    acc.sync_accrual(reg)
    reg.save()
    return {"ok": True, **referral_dashboard(reg, acc)}


@router.post("/cash-in")
async def investment_cash_in(
    body: CashBody,
    authorization: str | None = Header(default=None),
    x_jm_invest_id: str | None = Header(default=None, alias="X-JM-Invest-Id"),
    x_jm_invest_token: str | None = Header(default=None, alias="X-JM-Invest-Token"),
) -> dict:
    ctx = _auth_user(authorization)
    acc = _resolve_investor_account(ctx, x_jm_invest_id, x_jm_invest_token)
    reg = get_investment_registry()
    try:
        dash = acc.cash_in(body.amount, body.note or "", registry=reg)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    reg.save()
    return {"ok": True, "account": dash}


@router.post("/cash-out")
async def investment_cash_out(
    body: CashBody,
    authorization: str | None = Header(default=None),
    x_jm_invest_id: str | None = Header(default=None, alias="X-JM-Invest-Id"),
    x_jm_invest_token: str | None = Header(default=None, alias="X-JM-Invest-Token"),
) -> dict:
    ctx = _auth_user(authorization)
    acc = _resolve_investor_account(ctx, x_jm_invest_id, x_jm_invest_token)
    reg = get_investment_registry()
    try:
        dash = acc.cash_out(body.amount, body.note or "", registry=reg)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    reg.save()
    return {"ok": True, "account": dash}


@router.get("/admin/stats")
async def admin_stats(authorization: str | None = Header(default=None)) -> dict:
    _require_admin(authorization)
    reg = get_investment_registry()
    users = get_user_registry()
    accounts = reg.list_all()
    total_deposited = sum(a.total_deposited for a in accounts)
    total_withdrawn = sum(a.total_withdrawn for a in accounts)
    total_earned = sum(a.total_earned + a.referral_earned for a in accounts)
    total_balance = sum(a.balance for a in accounts)
    return {
        "ok": True,
        "investors": len([u for u in users.list_all() if u.role == "investor"]),
        "accounts": len(accounts),
        "total_deposited": round(total_deposited, 2),
        "total_withdrawn": round(total_withdrawn, 2),
        "total_earned": round(total_earned, 2),
        "total_balance": round(total_balance, 2),
        "monthly_rate_pct": period_rate_pct(),
        "period_rate_pct": period_rate_pct(),
        "period_days": period_days(),
    }


@router.get("/admin/accounts")
async def admin_accounts(authorization: str | None = Header(default=None)) -> dict:
    _require_admin(authorization)
    reg = get_investment_registry()
    users = get_user_registry()
    by_account = {u.account_id: u for u in users.list_all() if u.account_id}
    rows = []
    for acc in reg.list_all():
        acc.sync_accrual(reg)
        user = by_account.get(acc.id)
        dash = acc.dashboard(reg)
        rows.append(
            {
                **dash,
                "user": user.public() if user else None,
                "referred_by_code": (
                    reg.get(acc.referred_by).code if acc.referred_by and reg.get(acc.referred_by) else None
                ),
            }
        )
    reg.save()
    rows.sort(key=lambda r: r.get("balance") or 0, reverse=True)
    return {"ok": True, "accounts": rows, "count": len(rows)}

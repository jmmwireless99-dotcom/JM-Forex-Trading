"""FastAPI helpers to resolve the caller's isolated paper account."""

from __future__ import annotations

from fastapi import Header, HTTPException, Request

from app.api.deps import get_engine
from app.paper_accounts import PaperAccount


async def require_paper_account(
    request: Request,
    x_jm_account_id: str | None = Header(default=None, alias="X-JM-Account-Id"),
    x_jm_account_token: str | None = Header(default=None, alias="X-JM-Account-Token"),
) -> PaperAccount:
    """Resolve paper account from headers (required for money / trade routes)."""
    engine = get_engine()
    account_id = x_jm_account_id or request.query_params.get("account_id")
    token = x_jm_account_token or request.query_params.get("account_token")
    if not account_id:
        raise HTTPException(
            status_code=400,
            detail="Missing X-JM-Account-Id — create an account via POST /api/accounts",
        )
    try:
        return engine.accounts.require(account_id, token)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Paper account not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Invalid account token") from exc

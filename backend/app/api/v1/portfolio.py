"""
Portfolio optimization endpoints — /api/v1/portfolio/*

Protected by: active subscription + accepted disclaimer (per PDF §
"disable all analytical buttons until login and payment are completed").
Every successful optimization is recorded in `portfolio_runs` for audit.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUserDep,
    DbDep,
    DisclaimedUserDep,
    SubscribedUserDep,
    client_ip,
)
from app.db.models import (
    AdminConfig,
    AuditLog,
    Portfolio,
    PortfolioHolding,
    PortfolioRun,
    Stock,
)
from app.schemas.portfolio import (
    BacktestRequest,
    BacktestResponse,
    CorrelationRequest,
    CorrelationResponse,
    CovQualityReport,
    FrontierPoint,
    FrontierResponse,
    FrtbResult,
    HoldingIn,
    MetricsRequest,
    MetricsResponse,
    OptimizeRequest,
    OptimizeResponse,
    AddHoldingRequest,
    ComputeWeightsRequest,
    ComputeWeightsResponse,
    PortfolioOut,
    PortfolioRunOut,
    SavePortfolio,
    UpdatePortfolioRequest,
    VarFullRequest,
    VarFullResponse,
    VarMethodResult,
)
from app.services.analytics import (
    UniverseAnalytics,
    compute_universe_analytics,
    min_individual_annual_sd,
)
from app.services.optimizer import (
    PortfolioInputs,
    efficient_frontier,
    portfolio_return,
    portfolio_volatility,
    risk_contribution,
    sharpe_ratio,
    solve_sharpe_qp,
    solve_sharpe_slsqp,
)
from app.services.pdf_report import build_run_report
from app.services.var import (
    compute_all as var_compute_all,
    compute_frtb_es,
    historical_var,
    parametric_var,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


# ---------------------------------------------------------------------------
# Config lookup helpers
# ---------------------------------------------------------------------------
def _config_float(db: Session, key: str, fallback: float) -> float:
    row = db.get(AdminConfig, key)
    if row is None:
        return fallback
    try:
        return float(json.loads(row.value))
    except (ValueError, TypeError):
        return fallback


def _config_int(db: Session, key: str, fallback: int) -> int:
    row = db.get(AdminConfig, key)
    if row is None:
        return fallback
    try:
        return int(json.loads(row.value))
    except (ValueError, TypeError):
        return fallback


# ---------------------------------------------------------------------------
def _build_inputs_from_payload(
    req: OptimizeRequest, db: Session
) -> tuple[PortfolioInputs, UniverseAnalytics | None, float]:
    """
    Return (PortfolioInputs, analytics_or_None, risk_free_rate).
    analytics is None when the client supplied pre-computed matrices.
    """
    rf = req.risk_free_rate
    if rf is None:
        rf = _config_float(db, "risk_free_rate", 0.0475)

    if req.use_db_data:
        tdy = _config_int(db, "trading_days_per_year", 252)
        lookback = req.lookback_days or _config_int(db, "lookback_days", 252 * 5)

        analytics = compute_universe_analytics(
            db=db,
            tickers=req.tickers,
            lookback_days=lookback,
            risk_free_rate=rf,
            trading_days_per_year=tdy,
            end=req.as_of,
        )

        min_sd = req.min_stock_sd or (
            min_individual_annual_sd(analytics.annual_volatility)
            if req.apply_min_sd_constraint
            else None
        )
        inputs = PortfolioInputs(
            tickers=analytics.tickers,
            expected_returns=analytics.capm_expected_return,
            cov_daily=analytics.cov_daily,
            risk_free_rate=rf,
            min_stock_sd=min_sd,
            allow_shorting=req.allow_shorting,
        )
        return inputs, analytics, rf

    # Manual mode — cov_daily or daily_returns must be supplied
    if req.expected_returns is None or len(req.expected_returns) != len(req.tickers):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "expected_returns length must match tickers in manual mode.",
        )
    if req.cov_daily is not None:
        cov = np.asarray(req.cov_daily, dtype=float)
    elif req.daily_returns is not None:
        rets = np.asarray(req.daily_returns, dtype=float)
        if rets.ndim != 2 or rets.shape[1] != len(req.tickers):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"daily_returns must be T × {len(req.tickers)}.",
            )
        cov = np.cov(rets, rowvar=False, ddof=0)
    else:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Provide cov_daily or daily_returns in manual mode.",
        )

    inputs = PortfolioInputs(
        tickers=req.tickers,
        expected_returns=np.asarray(req.expected_returns, dtype=float),
        cov_daily=cov,
        risk_free_rate=rf,
        min_stock_sd=req.min_stock_sd,
        allow_shorting=req.allow_shorting,
    )
    return inputs, None, rf


# ---------------------------------------------------------------------------
# Optimize
# ---------------------------------------------------------------------------
@router.post("/optimize", response_model=OptimizeResponse)
def optimize(
    req: OptimizeRequest,
    db: DbDep,
    user: DisclaimedUserDep,
    _: SubscribedUserDep,
    request: Request,
) -> OptimizeResponse:
    """
    Implements slides 123-126: maximize Sharpe ratio subject to
    sum(w)=1, w>=0 (unless shorting), σ_p ≤ min(σ_i), R_p ≥ R_f.
    """
    inputs, analytics, rf = _build_inputs_from_payload(req, db)

    try:
        if req.method == "qp":
            result = solve_sharpe_qp(inputs)
        else:
            result = solve_sharpe_slsqp(
                inputs,
                enforce_min_sd_constraint=req.apply_min_sd_constraint,
                enforce_return_floor=req.apply_return_floor,
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # Build response metadata
    if analytics is not None:
        capm_map = {t: float(v) for t, v in zip(analytics.tickers, analytics.capm_expected_return)}
        vol_map = {t: float(v) for t, v in zip(analytics.tickers, analytics.annual_volatility)}
        beta_map = {t: float(v) for t, v in zip(analytics.tickers, analytics.beta)}
        cov_out = analytics.cov_daily.tolist()
    else:
        capm_map = {t: float(v) for t, v in zip(inputs.tickers, inputs.expected_returns)}
        vol_map = {
            t: float(np.sqrt(v * 252))
            for t, v in zip(inputs.tickers, np.diag(inputs.cov_daily))
        }
        beta_map = dict.fromkeys(inputs.tickers, 0.0)
        cov_out = inputs.cov_daily.tolist()

    # Record run for audit (PDF §3)
    run = PortfolioRun(
        user_id=user.id,
        run_at=datetime.now(timezone.utc),
        method=req.method,
        risk_free_rate=Decimal(str(rf)),
        min_stock_sd=Decimal(str(inputs.min_stock_sd)) if inputs.min_stock_sd else None,
        allow_shorting=req.allow_shorting,
        expected_return=Decimal(str(result["expected_return"])),
        volatility=Decimal(str(result["volatility"])),
        sharpe=Decimal(str(result["sharpe"])),
        weights=result["weights"],
        inputs_snapshot={
            "tickers": list(inputs.tickers),
            "risk_free_rate": rf,
            "method": req.method,
            "use_db_data": req.use_db_data,
        },
        success=bool(result["success"]),
        solver_message=str(result["message"]),
    )
    db.add(run)
    db.add(
        AuditLog(
            user_id=user.id,
            action="portfolio.optimize",
            resource_type="portfolio_runs",
            resource_id=None,
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_method=request.method,
            request_path=str(request.url.path),
            details={"tickers": list(inputs.tickers), "method": req.method},
        )
    )
    db.commit()
    db.refresh(run)

    return OptimizeResponse(
        success=bool(result["success"]),
        method=result["method"],
        message=str(result["message"]),
        weights={k: float(v) for k, v in result["weights"].items()},
        sharpe=float(result["sharpe"]),
        expected_return=float(result["expected_return"]),
        volatility=float(result["volatility"]),
        sum_weights=float(result["sum_weights"]),
        risk_free_rate=float(rf),
        min_stock_sd=float(inputs.min_stock_sd) if inputs.min_stock_sd else None,
        tickers=list(inputs.tickers),
        capm_expected_return=capm_map,
        annual_volatility=vol_map,
        beta=beta_map,
        cov_daily=cov_out,
        run_id=run.id,
    )


# ---------------------------------------------------------------------------
# Frontier
# ---------------------------------------------------------------------------
@router.post("/frontier", response_model=FrontierResponse)
def frontier(
    req: OptimizeRequest,
    db: DbDep,
    user: DisclaimedUserDep,
    _: SubscribedUserDep,
    n_points: int = 50,
) -> FrontierResponse:
    inputs, _analytics, _rf = _build_inputs_from_payload(req, db)
    points = efficient_frontier(inputs, n_points=n_points)
    tangency = solve_sharpe_slsqp(
        inputs,
        enforce_min_sd_constraint=False,
        enforce_return_floor=False,
    )
    return FrontierResponse(
        tickers=list(inputs.tickers),
        points=[FrontierPoint(**p) for p in points],
        tangency_return=float(tangency["expected_return"]),
        tangency_volatility=float(tangency["volatility"]),
        tangency_weights={k: float(v) for k, v in tangency["weights"].items()},
    )


# ---------------------------------------------------------------------------
# Metrics (live slider)
# ---------------------------------------------------------------------------
@router.post("/metrics", response_model=MetricsResponse)
def metrics(
    req: MetricsRequest,
    db: DbDep,
    user: DisclaimedUserDep,
    _: SubscribedUserDep,
) -> MetricsResponse:
    if len(req.weights) != len(req.tickers):
        raise HTTPException(422, "weights length must match tickers.")

    rf = req.risk_free_rate if req.risk_free_rate is not None else _config_float(
        db, "risk_free_rate", 0.0475
    )
    w = np.asarray(req.weights, dtype=float)

    if req.use_db_data:
        tdy = _config_int(db, "trading_days_per_year", 252)
        lookback = _config_int(db, "lookback_days", 252 * 5)
        analytics = compute_universe_analytics(
            db=db, tickers=req.tickers, lookback_days=lookback,
            risk_free_rate=rf, trading_days_per_year=tdy,
        )
        mu = analytics.capm_expected_return
        cov_annual = analytics.cov_daily * tdy
        daily_rets = analytics.daily_returns
    else:
        if req.expected_returns is None or req.cov_daily is None:
            raise HTTPException(422, "Provide expected_returns + cov_daily in manual mode.")
        mu = np.asarray(req.expected_returns, dtype=float)
        cov_daily = np.asarray(req.cov_daily, dtype=float)
        cov_annual = cov_daily * 252
        daily_rets = (
            np.asarray(req.daily_returns, dtype=float)
            if req.daily_returns is not None
            else None
        )

    rc = risk_contribution(w, cov_annual)
    labels = list(req.tickers)

    # VaR — prefer historical if we have daily_returns, else parametric
    if daily_rets is not None:
        v1 = historical_var(w, daily_rets, confidence=0.95, horizon_days=1)
        v10 = historical_var(w, daily_rets, confidence=0.95, horizon_days=10)
    else:
        cov_daily = cov_annual / 252
        v1 = parametric_var(w, cov_daily=cov_daily, mu_daily=mu / 252, confidence=0.95, horizon_days=1)
        v10 = parametric_var(w, cov_daily=cov_daily, mu_daily=mu / 252, confidence=0.95, horizon_days=10)

    return MetricsResponse(
        sharpe=sharpe_ratio(w, mu, cov_annual, rf),
        expected_return=portfolio_return(w, mu),
        volatility=portfolio_volatility(w, cov_annual),
        sum_weights=float(w.sum()),
        risk_contribution={labels[i]: float(rc[i]) for i in range(len(w))},
        var_95_daily=v1.var_loss,
        var_95_10d=v10.var_loss,
        cvar_95_daily=float(v1.cvar_loss or 0.0),
    )


# ---------------------------------------------------------------------------
# Saved portfolios CRUD
# ---------------------------------------------------------------------------
@router.get("/", response_model=list[PortfolioOut])
def list_portfolios(db: DbDep, user: CurrentUserDep) -> list[PortfolioOut]:
    rows = db.execute(
        select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.created_at.desc())
    ).scalars().all()
    return [_portfolio_out(db, p) for p in rows]


@router.get("/{portfolio_id}", response_model=PortfolioOut)
def get_portfolio(
    portfolio_id: int, db: DbDep, user: CurrentUserDep
) -> PortfolioOut:
    p = db.get(Portfolio, portfolio_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found.")
    return _portfolio_out(db, p)


@router.post("/", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED)
def save_portfolio(
    payload: SavePortfolio,
    db: DbDep,
    user: CurrentUserDep,
    request: Request,
) -> PortfolioOut:
    # When holdings are supplied (optimize flow) the weights must sum to 1.0.
    # When holdings are empty (Loay's "Create new portfolio" modal) we accept
    # a bare name + initial_capital and the portfolio starts as "inactive".
    if payload.holdings:
        # Resolve tickers → stock_ids
        tickers = [h.ticker for h in payload.holdings]
        stocks = db.execute(
            select(Stock).where(Stock.ticker_suffix.in_(tickers))
        ).scalars().all()
        by_ticker = {s.ticker_suffix: s for s in stocks}
        missing = [t for t in tickers if t not in by_ticker]
        if missing:
            raise HTTPException(400, f"Unknown tickers: {missing}")

        total_weight = sum(h.weight for h in payload.holdings)
        if abs(total_weight - 1.0) > 1e-4:
            raise HTTPException(422, f"Holdings weights must sum to 1.0 (got {total_weight:.6f})")
    else:
        by_ticker = {}

    p = Portfolio(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        initial_capital=Decimal(str(payload.initial_capital)) if payload.initial_capital else None,
        target_loss_threshold=Decimal(str(payload.target_loss_threshold)) if payload.target_loss_threshold else None,
    )
    db.add(p)
    db.flush()
    for h in payload.holdings:
        db.add(PortfolioHolding(
            portfolio_id=p.id,
            stock_id=by_ticker[h.ticker].id,
            weight=Decimal(str(h.weight)),
        ))
    db.add(AuditLog(
        user_id=user.id,
        action="portfolio.save",
        resource_type="portfolios",
        resource_id=str(p.id),
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_method=request.method,
        request_path=str(request.url.path),
        details={"holdings_count": len(payload.holdings)},
    ))
    db.commit()
    db.refresh(p)
    return _portfolio_out(db, p)


# ---------------------------------------------------------------------------
# PATCH /portfolio/{id} — update name / amount / target loss
# ---------------------------------------------------------------------------
@router.patch("/{portfolio_id}", response_model=PortfolioOut)
def update_portfolio(
    portfolio_id: int,
    payload: UpdatePortfolioRequest,
    db: DbDep,
    user: CurrentUserDep,
    request: Request,
) -> PortfolioOut:
    """
    Update an existing portfolio's metadata. Returns `needs_recompute=true`
    iff `initial_capital` changed AND the portfolio currently has holdings —
    per Loay's rule (the saved weights no longer match the new amount).
    """
    p = db.get(Portfolio, portfolio_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found.")

    old_capital = float(p.initial_capital) if p.initial_capital is not None else None
    capital_changed = False
    changes: dict[str, object] = {}

    if payload.name is not None and payload.name != p.name:
        changes["name"] = {"from": p.name, "to": payload.name}
        p.name = payload.name
    if payload.description is not None and payload.description != p.description:
        changes["description_changed"] = True
        p.description = payload.description
    if payload.initial_capital is not None:
        new_capital = float(payload.initial_capital)
        if new_capital != (old_capital or 0.0):
            changes["initial_capital"] = {"from": old_capital, "to": new_capital}
            p.initial_capital = Decimal(str(new_capital))
            capital_changed = True
    if payload.target_loss_threshold is not None:
        new_tl = float(payload.target_loss_threshold)
        if new_tl != (float(p.target_loss_threshold) if p.target_loss_threshold else None):
            changes["target_loss_threshold"] = new_tl
            p.target_loss_threshold = Decimal(str(new_tl))

    holding_count = db.execute(
        select(PortfolioHolding).where(PortfolioHolding.portfolio_id == p.id)
    ).first()
    needs_recompute = bool(capital_changed and holding_count is not None)

    db.add(AuditLog(
        user_id=user.id,
        action="portfolio.update",
        resource_type="portfolios",
        resource_id=str(p.id),
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_method=request.method,
        request_path=str(request.url.path),
        details={"changes": changes, "needs_recompute": needs_recompute},
    ))
    db.commit()
    db.refresh(p)
    return _portfolio_out(db, p, needs_recompute=needs_recompute)


# ---------------------------------------------------------------------------
# DELETE /portfolio/{id} — hard delete, cascades to holdings
# ---------------------------------------------------------------------------
@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(
    portfolio_id: int,
    db: DbDep,
    user: CurrentUserDep,
    request: Request,
) -> Response:
    p = db.get(Portfolio, portfolio_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found.")

    name = p.name
    db.add(AuditLog(
        user_id=user.id,
        action="portfolio.delete",
        resource_type="portfolios",
        resource_id=str(p.id),
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_method=request.method,
        request_path=str(request.url.path),
        details={"name": name},
    ))
    db.delete(p)   # cascades to portfolio_holdings via the FK
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Portfolio holdings CRUD — add / remove a single stock
# ---------------------------------------------------------------------------
@router.post("/{portfolio_id}/holdings", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED)
def add_holding(
    portfolio_id: int,
    payload: AddHoldingRequest,
    db: DbDep,
    user: CurrentUserDep,
    request: Request,
) -> PortfolioOut:
    """
    Add one stock to a portfolio's holdings (weight starts at 0).

    Called from the Screener when a user clicks "Add" while the Screener is
    in portfolio-context mode (URL `?portfolio=<id>`). Weights get filled in
    later by `POST /portfolio/{id}/compute`.
    """
    p = db.get(Portfolio, portfolio_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found.")

    stock = db.execute(
        select(Stock).where(Stock.ticker_suffix == payload.ticker)
    ).scalar_one_or_none()
    if stock is None:
        # Also accept the bare "2222" form for Loay's Tadawul muscle-memory.
        stock = db.execute(select(Stock).where(Stock.symbol == payload.ticker)).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown stock: {payload.ticker}")

    existing = db.execute(
        select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == p.id,
            PortfolioHolding.stock_id == stock.id,
        )
    ).scalar_one_or_none()
    # Slide-#8 capture: default purchase_date to today and purchase_price to
    # the stock's last price snapshot when the caller omits them.
    purchase_date = payload.purchase_date or date.today()
    if payload.purchase_price is not None:
        purchase_price = Decimal(str(payload.purchase_price))
    elif stock.last_price is not None:
        purchase_price = stock.last_price
    else:
        purchase_price = None

    if existing is None:
        db.add(PortfolioHolding(
            portfolio_id=p.id,
            stock_id=stock.id,
            weight=Decimal("0"),
            purchase_date=purchase_date,
            purchase_price=purchase_price,
        ))
        # Adding a stock invalidates any previously-computed weights — we
        # drop them back to 0 so the portfolio flips to "inactive" until
        # the user re-runs compute.
        db.execute(
            # SQLAlchemy UPDATE on the related rows
            PortfolioHolding.__table__.update()
            .where(PortfolioHolding.portfolio_id == p.id)
            .values(weight=Decimal("0"))
        )
    else:
        # Holding already exists — refresh the purchase metadata if the
        # caller passed it explicitly (covers the "I bought more" case).
        if payload.purchase_date is not None:
            existing.purchase_date = purchase_date
        if payload.purchase_price is not None:
            existing.purchase_price = purchase_price

    db.add(AuditLog(
        user_id=user.id,
        action="portfolio.add_holding",
        resource_type="portfolios",
        resource_id=str(p.id),
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_method=request.method,
        request_path=str(request.url.path),
        details={"ticker": stock.ticker_suffix, "symbol": stock.symbol},
    ))
    db.commit()
    db.refresh(p)
    return _portfolio_out(db, p)


@router.delete("/{portfolio_id}/holdings/{ticker}", response_model=PortfolioOut)
def remove_holding(
    portfolio_id: int,
    ticker: str,
    db: DbDep,
    user: CurrentUserDep,
    request: Request,
) -> PortfolioOut:
    p = db.get(Portfolio, portfolio_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found.")

    stock = db.execute(
        select(Stock).where(Stock.ticker_suffix == ticker)
    ).scalar_one_or_none()
    if stock is None:
        stock = db.execute(select(Stock).where(Stock.symbol == ticker)).scalar_one_or_none()
    if stock is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown stock: {ticker}")

    holding = db.execute(
        select(PortfolioHolding).where(
            PortfolioHolding.portfolio_id == p.id,
            PortfolioHolding.stock_id == stock.id,
        )
    ).scalar_one_or_none()
    if holding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Holding not found in portfolio.")

    db.delete(holding)
    # Removing a holding also invalidates computed weights.
    db.execute(
        PortfolioHolding.__table__.update()
        .where(PortfolioHolding.portfolio_id == p.id)
        .values(weight=Decimal("0"))
    )
    db.add(AuditLog(
        user_id=user.id,
        action="portfolio.remove_holding",
        resource_type="portfolios",
        resource_id=str(p.id),
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_method=request.method,
        request_path=str(request.url.path),
        details={"ticker": stock.ticker_suffix, "symbol": stock.symbol},
    ))
    db.commit()
    db.refresh(p)
    return _portfolio_out(db, p)


# ---------------------------------------------------------------------------
# POST /portfolio/{id}/compute — run Markowitz, persist weights, flip Active
# ---------------------------------------------------------------------------
@router.post("/{portfolio_id}/compute", response_model=ComputeWeightsResponse)
def compute_portfolio_weights(
    portfolio_id: int,
    payload: ComputeWeightsRequest,
    db: DbDep,
    user: DisclaimedUserDep,
    _: SubscribedUserDep,
    request: Request,
) -> ComputeWeightsResponse:
    """
    Run the Markowitz optimizer on the portfolio's current holdings, then
    WRITE the computed weights back to `portfolio_holdings`. This closes
    Loay's "active" loop: after compute, sum(weights) ≈ 1.0 → status="active".
    """
    p = db.get(Portfolio, portfolio_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Portfolio not found.")

    # Gather tickers from holdings
    rows = db.execute(
        select(PortfolioHolding, Stock.ticker_suffix, Stock.id)
        .join(Stock, Stock.id == PortfolioHolding.stock_id)
        .where(PortfolioHolding.portfolio_id == p.id)
    ).all()
    if len(rows) < 2:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Portfolio needs at least 2 holdings before weights can be computed.",
        )
    tickers = [ticker for _, ticker, _ in rows]

    # Build an OptimizeRequest and reuse the existing solver code path.
    rf = payload.risk_free_rate
    if rf is None:
        rf = _config_float(db, "risk_free_rate", 0.0475)
    tdy = _config_int(db, "trading_days_per_year", 252)
    lookback = payload.lookback_days or _config_int(db, "lookback_days", 252 * 5)

    try:
        analytics = compute_universe_analytics(
            db=db,
            tickers=tickers,
            lookback_days=lookback,
            risk_free_rate=rf,
            trading_days_per_year=tdy,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    min_sd = (
        min_individual_annual_sd(analytics.annual_volatility)
        if payload.apply_min_sd_constraint
        else None
    )
    inputs = PortfolioInputs(
        tickers=analytics.tickers,
        expected_returns=analytics.capm_expected_return,
        cov_daily=analytics.cov_daily,
        risk_free_rate=rf,
        min_stock_sd=min_sd,
        allow_shorting=payload.allow_shorting,
    )

    try:
        if payload.method == "qp":
            result = solve_sharpe_qp(inputs)
        else:
            result = solve_sharpe_slsqp(
                inputs,
                enforce_min_sd_constraint=payload.apply_min_sd_constraint,
                enforce_return_floor=payload.apply_return_floor,
            )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # Persist computed weights back into the holdings (ticker → stock_id map)
    ticker_to_stock_id = {ticker: sid for _, ticker, sid in rows}
    new_weights: dict[str, float] = {}
    for ticker, w in result["weights"].items():
        new_weights[ticker] = float(w)
        sid = ticker_to_stock_id[ticker]
        db.execute(
            PortfolioHolding.__table__.update()
            .where(
                PortfolioHolding.portfolio_id == p.id,
                PortfolioHolding.stock_id == sid,
            )
            .values(weight=Decimal(str(round(float(w), 6))))
        )

    # Audit trail: persist a PortfolioRun row (reused in /portfolio/runs endpoint)
    run = PortfolioRun(
        portfolio_id=p.id,
        user_id=user.id,
        run_at=datetime.now(timezone.utc),
        method=payload.method,
        risk_free_rate=Decimal(str(rf)),
        min_stock_sd=Decimal(str(min_sd)) if min_sd else None,
        allow_shorting=payload.allow_shorting,
        expected_return=Decimal(str(result["expected_return"])),
        volatility=Decimal(str(result["volatility"])),
        sharpe=Decimal(str(result["sharpe"])),
        weights=new_weights,
        inputs_snapshot={
            "tickers": list(analytics.tickers),
            "risk_free_rate": rf,
            "method": payload.method,
            "source": "portfolio.compute",
        },
        success=bool(result["success"]),
        solver_message=str(result["message"]),
    )
    db.add(run)
    db.add(AuditLog(
        user_id=user.id,
        action="portfolio.compute",
        resource_type="portfolios",
        resource_id=str(p.id),
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_method=request.method,
        request_path=str(request.url.path),
        details={"method": payload.method, "tickers": tickers, "sharpe": float(result["sharpe"])},
    ))
    db.commit()
    db.refresh(run)

    return ComputeWeightsResponse(
        portfolio_id=p.id,
        run_id=run.id,
        success=bool(result["success"]),
        method=result["method"],
        message=str(result["message"]),
        sharpe=float(result["sharpe"]),
        expected_return=float(result["expected_return"]),
        volatility=float(result["volatility"]),
        risk_free_rate=float(rf),
        weights=new_weights,
        annual_volatility={
            t: float(v) for t, v in zip(analytics.tickers, analytics.annual_volatility)
        },
        beta={t: float(v) for t, v in zip(analytics.tickers, analytics.beta)},
        capm_expected_return={
            t: float(v) for t, v in zip(analytics.tickers, analytics.capm_expected_return)
        },
    )


def _portfolio_out(
    db: Session, p: Portfolio, *, needs_recompute: bool | None = None
) -> PortfolioOut:
    rows = db.execute(
        select(PortfolioHolding, Stock.ticker_suffix)
        .join(Stock, Stock.id == PortfolioHolding.stock_id)
        .where(PortfolioHolding.portfolio_id == p.id)
    ).all()
    holdings_out = [
        HoldingIn(
            ticker=ticker,
            weight=float(h.weight),
            purchase_date=h.purchase_date,
            purchase_price=float(h.purchase_price) if h.purchase_price is not None else None,
        )
        for h, ticker in rows
    ]

    # Loay's definition (slide 1): "Active" iff user has picked stocks AND
    # computed weights. Weights summing to ~1.0 implies Markowitz has run.
    total_weight = sum(h.weight for h in holdings_out)
    is_active = bool(holdings_out) and abs(total_weight - 1.0) < 0.01

    return PortfolioOut(
        id=p.id,
        name=p.name,
        description=p.description,
        initial_capital=float(p.initial_capital) if p.initial_capital else None,
        target_loss_threshold=float(p.target_loss_threshold) if p.target_loss_threshold else None,
        holdings=holdings_out,
        status="active" if is_active else "inactive",
        holding_count=len(holdings_out),
        total_weight=float(total_weight),
        needs_recompute=needs_recompute,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------
@router.get("/runs/{run_id}/report.pdf")
def download_run_report(
    run_id: int,
    db: DbDep,
    user: CurrentUserDep,
    locale: str = "en",
) -> Response:
    """
    Render the run as a bilingual PDF. `locale` can be `ar` or `en`; defaults
    to English because it works without an Arabic font installed.
    """
    if locale not in ("ar", "en"):
        raise HTTPException(422, "locale must be 'ar' or 'en'")

    run = db.get(PortfolioRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(404, "Run not found.")

    weights = {k: float(v) for k, v in (run.weights or {}).items()}

    # Hydrate bilingual stock names for the weights table
    tickers = list(weights)
    stock_rows = db.execute(
        select(Stock.ticker_suffix, Stock.name_ar, Stock.name_en)
        .where(Stock.ticker_suffix.in_(tickers))
    ).all()
    if locale == "ar":
        name_map = {t: (ar or en or t) for t, ar, en in stock_rows}
    else:
        name_map = {t: (en or ar or t) for t, ar, en in stock_rows}

    user_display = (
        user.full_name_ar or user.full_name_en
        if locale == "ar"
        else (user.full_name_en or user.full_name_ar)
    ) or user.email

    pdf_bytes = build_run_report(
        run_id=run.id,
        user_name=user_display,
        locale=locale,
        run_at=run.run_at,
        method=run.method,
        sharpe=float(run.sharpe) if run.sharpe else 0.0,
        expected_return=float(run.expected_return) if run.expected_return else 0.0,
        volatility=float(run.volatility) if run.volatility else 0.0,
        risk_free_rate=float(run.risk_free_rate),
        var_95=float(run.var_95) if run.var_95 else None,
        weights=weights,
        stock_name_map=name_map,
    )
    filename = f"portfolio-run-{run.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/runs", response_model=list[PortfolioRunOut])
def list_runs(
    db: DbDep, user: CurrentUserDep, limit: int = 20
) -> list[PortfolioRunOut]:
    rows = db.execute(
        select(PortfolioRun)
        .where(PortfolioRun.user_id == user.id)
        .order_by(PortfolioRun.run_at.desc())
        .limit(max(1, min(limit, 200)))
    ).scalars().all()
    return [
        PortfolioRunOut(
            id=r.id,
            run_at=r.run_at,
            method=r.method,
            risk_free_rate=float(r.risk_free_rate),
            expected_return=float(r.expected_return) if r.expected_return else None,
            volatility=float(r.volatility) if r.volatility else None,
            sharpe=float(r.sharpe) if r.sharpe else None,
            var_95=float(r.var_95) if r.var_95 else None,
            success=r.success,
            weights=r.weights,
        )
        for r in rows
    ]


# ===========================================================================
# Phase 2 Endpoints
# ===========================================================================

# ---------------------------------------------------------------------------
# VaR Full — all methods + FRTB ES
# ---------------------------------------------------------------------------
def _resolve_daily_returns(
    req_tickers: list[str],
    req_weights: list[float],
    req_use_db: bool,
    req_daily_returns: list[list[float]] | None,
    req_lookback: int | None,
    req_rf: float | None,
    db: Session,
) -> tuple[np.ndarray, np.ndarray, "UniverseAnalytics | None"]:
    """Shared resolver for the Phase 2 endpoints that need daily_returns."""
    w = np.asarray(req_weights, dtype=float)
    if len(w) != len(req_tickers):
        raise HTTPException(422, "weights length must match tickers.")

    if req_use_db:
        rf = req_rf if req_rf is not None else _config_float(db, "risk_free_rate", 0.0475)
        tdy = _config_int(db, "trading_days_per_year", 252)
        lookback = req_lookback or _config_int(db, "lookback_days", 252 * 5)
        analytics = compute_universe_analytics(
            db=db, tickers=req_tickers, lookback_days=lookback,
            risk_free_rate=rf, trading_days_per_year=tdy,
        )
        return w, analytics.daily_returns, analytics

    if req_daily_returns is None:
        raise HTTPException(422, "Provide daily_returns in manual mode.")

    dr = np.asarray(req_daily_returns, dtype=float)
    if dr.ndim != 2 or dr.shape[1] != len(req_tickers):
        raise HTTPException(422, f"daily_returns must be T × {len(req_tickers)}.")
    return w, dr, None


@router.post("/var-full", response_model=VarFullResponse)
def var_full(
    req: VarFullRequest,
    db: DbDep,
    user: DisclaimedUserDep,
    _: SubscribedUserDep,
) -> VarFullResponse:
    """
    Phase 2: Full VaR analysis — all 4 methods (historical, parametric,
    Monte Carlo normal, GARCH-t) plus Basel FRTB Expected Shortfall at 97.5%.
    """
    w, daily_rets, _analytics = _resolve_daily_returns(
        req.tickers, req.weights, req.use_db_data,
        req.daily_returns, req.lookback_days, req.risk_free_rate, db,
    )

    results = var_compute_all(
        w, daily_rets,
        confidence=req.confidence,
        horizon_days=req.horizon_days,
        n_paths=req.n_paths,
        include_garch=req.include_garch,
    )

    methods_out = {}
    for name, vr in results.items():
        methods_out[name] = VarMethodResult(
            method=vr.method,
            confidence=vr.confidence,
            horizon_days=vr.horizon_days,
            var_loss=float(vr.var_loss),
            cvar_loss=float(vr.cvar_loss) if vr.cvar_loss is not None else None,
            portfolio_mean_daily=float(vr.portfolio_mean_daily),
            portfolio_vol_daily=float(vr.portfolio_vol_daily),
            simulated_paths=vr.simulated_paths,
        )

    frtb_out = None
    if req.include_frtb:
        frtb = compute_frtb_es(w, daily_rets, horizon_days=10, n_paths=req.n_paths)
        frtb_out = FrtbResult(**frtb)

    return VarFullResponse(
        tickers=req.tickers,
        methods=methods_out,
        frtb=frtb_out,
    )


# ---------------------------------------------------------------------------
# VaR Backtest — Kupiec POF + Christoffersen
# ---------------------------------------------------------------------------
@router.post("/backtest", response_model=BacktestResponse)
def backtest(
    req: BacktestRequest,
    db: DbDep,
    user: DisclaimedUserDep,
    _: SubscribedUserDep,
) -> BacktestResponse:
    """
    Phase 2: Run a rolling-window VaR backtest and validate with Kupiec
    Proportion of Failures and Christoffersen Conditional Coverage tests.
    """
    from app.services.backtesting import run_backtest

    w, daily_rets, _analytics = _resolve_daily_returns(
        req.tickers, req.weights, req.use_db_data,
        req.daily_returns, req.lookback_days, req.risk_free_rate, db,
    )

    try:
        result = run_backtest(
            weights=w,
            daily_returns=daily_rets,
            confidence=req.confidence,
            var_method=req.var_method,
            window=req.window,
            significance=req.significance,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return BacktestResponse(
        var_method=result.var_method,
        confidence=result.confidence,
        n_observations=result.n_observations,
        n_violations=result.n_violations,
        expected_violations=result.expected_violations,
        violation_rate=result.violation_rate,
        expected_violation_rate=result.expected_violation_rate,
        kupiec_lr=result.kupiec_lr,
        kupiec_pval=result.kupiec_pval,
        pass_kupiec=result.pass_kupiec,
        christoffersen_lr=result.christoffersen_lr,
        christoffersen_pval=result.christoffersen_pval,
        pass_christoffersen=result.pass_christoffersen,
        independence_lr=result.independence_lr,
        independence_pval=result.independence_pval,
    )


# ---------------------------------------------------------------------------
# Correlation Matrix + Covariance Quality
# ---------------------------------------------------------------------------
@router.post("/correlation", response_model=CorrelationResponse)
def correlation(
    req: CorrelationRequest,
    db: DbDep,
    user: DisclaimedUserDep,
    _: SubscribedUserDep,
) -> CorrelationResponse:
    """
    Phase 2: Full correlation matrix (Pearson Formula 2, cross-checked),
    Ledoit-Wolf shrinkage covariance, covariance quality report, and
    Blume-adjusted betas.
    """
    from app.services.covariance import covariance_quality_report

    rf = req.risk_free_rate if req.risk_free_rate is not None else _config_float(
        db, "risk_free_rate", 0.0475
    )

    if req.use_db_data:
        tdy = _config_int(db, "trading_days_per_year", 252)
        lookback = req.lookback_days or _config_int(db, "lookback_days", 252 * 5)
        analytics = compute_universe_analytics(
            db=db, tickers=req.tickers, lookback_days=lookback,
            risk_free_rate=rf, trading_days_per_year=tdy,
        )
        quality = covariance_quality_report(analytics.cov_daily)

        return CorrelationResponse(
            tickers=analytics.tickers,
            correlation=analytics.correlation.tolist(),
            correlation_parity_pass=analytics.correlation_parity.get("parity_pass", False),
            correlation_max_diff=analytics.correlation_parity.get("formula2_vs_corrcoef_max_diff", 0.0),
            cov_daily=analytics.cov_daily.tolist(),
            cov_daily_shrunk=analytics.cov_daily_shrunk.tolist(),
            shrinkage_intensity=analytics.shrinkage_intensity,
            cov_quality=CovQualityReport(
                condition_number=quality.condition_number,
                is_psd=quality.is_psd,
                min_eigenvalue=quality.min_eigenvalue,
                max_eigenvalue=quality.max_eigenvalue,
                trace=quality.trace,
                determinant_log=quality.determinant_log,
                suggested_shrinkage=quality.suggested_shrinkage,
            ),
            beta_raw={t: float(b) for t, b in zip(analytics.tickers, analytics.beta)},
            beta_blume={t: float(b) for t, b in zip(analytics.tickers, analytics.beta_blume)},
        )

    # Manual mode
    if req.daily_returns is None:
        raise HTTPException(422, "Provide daily_returns in manual mode.")

    dr = np.asarray(req.daily_returns, dtype=float)
    from app.services.covariance import (
        correlation_from_covariance,
        ledoit_wolf_shrinkage_fast,
        validate_correlation_parity,
    )
    cov_daily = np.cov(dr, rowvar=False, ddof=0)
    cov_shrunk, shrinkage = ledoit_wolf_shrinkage_fast(dr)
    corr = correlation_from_covariance(cov_daily)
    parity = validate_correlation_parity(dr, cov_daily)
    quality = covariance_quality_report(cov_daily)

    return CorrelationResponse(
        tickers=req.tickers,
        correlation=corr.tolist(),
        correlation_parity_pass=parity.get("parity_pass", False),
        correlation_max_diff=parity.get("formula2_vs_corrcoef_max_diff", 0.0),
        cov_daily=cov_daily.tolist(),
        cov_daily_shrunk=cov_shrunk.tolist(),
        shrinkage_intensity=shrinkage,
        cov_quality=CovQualityReport(
            condition_number=quality.condition_number,
            is_psd=quality.is_psd,
            min_eigenvalue=quality.min_eigenvalue,
            max_eigenvalue=quality.max_eigenvalue,
            trace=quality.trace,
            determinant_log=quality.determinant_log,
            suggested_shrinkage=quality.suggested_shrinkage,
        ),
        beta_raw=dict.fromkeys(req.tickers, 0.0),
        beta_blume=dict.fromkeys(req.tickers, 0.33),
    )

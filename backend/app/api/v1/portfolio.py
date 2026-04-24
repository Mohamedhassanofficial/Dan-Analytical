"""
Portfolio optimization endpoints — /api/v1/portfolio/*

Protected by: active subscription + accepted disclaimer (per PDF §
"disable all analytical buttons until login and payment are completed").
Every successful optimization is recorded in `portfolio_runs` for audit.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
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
    FrontierPoint,
    FrontierResponse,
    HoldingIn,
    MetricsRequest,
    MetricsResponse,
    OptimizeRequest,
    OptimizeResponse,
    PortfolioOut,
    PortfolioRunOut,
    SavePortfolio,
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
from app.services.var import historical_var, parametric_var

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


@router.post("/", response_model=PortfolioOut, status_code=status.HTTP_201_CREATED)
def save_portfolio(
    payload: SavePortfolio,
    db: DbDep,
    user: CurrentUserDep,
    request: Request,
) -> PortfolioOut:
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
    ))
    db.commit()
    db.refresh(p)
    return _portfolio_out(db, p)


def _portfolio_out(db: Session, p: Portfolio) -> PortfolioOut:
    holdings = db.execute(
        select(PortfolioHolding, Stock.ticker_suffix)
        .join(Stock, Stock.id == PortfolioHolding.stock_id)
        .where(PortfolioHolding.portfolio_id == p.id)
    ).all()
    return PortfolioOut(
        id=p.id,
        name=p.name,
        description=p.description,
        initial_capital=float(p.initial_capital) if p.initial_capital else None,
        target_loss_threshold=float(p.target_loss_threshold) if p.target_loss_threshold else None,
        holdings=[
            HoldingIn(ticker=ticker, weight=float(h.weight))
            for h, ticker in holdings
        ],
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

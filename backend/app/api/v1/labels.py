"""
UI labels endpoints — admins edit user-facing strings without a code change.

The frontend fetches labels at boot (see frontend/src/contexts/LabelsContext.tsx)
and layers them on top of the static i18n bundles (`src/i18n/ar.json` and
`en.json`). A missing label key falls back to the static bundle, so pages
still render if the DB is empty.

The user explicitly asked for this: "don't waste time translating now; make
labels editable from the admin dashboard so I can rename / translate later."
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import AdminUserDep, CurrentUserDep, DbDep, client_ip
from app.db.models import AuditLog, UiLabel
from app.schemas.labels import UiLabelOut, UiLabelUpdate

router = APIRouter(tags=["labels"])


# ---------------------------------------------------------------------------
@router.get("/ui-labels", response_model=list[UiLabelOut])
def list_labels(
    db: DbDep,
    _: CurrentUserDep,
    context: str | None = None,
) -> list[UiLabelOut]:
    """Return every label, optionally filtered to a single context (screener / admin / auth / …)."""
    stmt = select(UiLabel).order_by(UiLabel.key)
    if context:
        stmt = stmt.where(UiLabel.context == context)
    rows = db.execute(stmt).scalars().all()
    return [UiLabelOut.model_validate(r) for r in rows]


@router.get("/ui-labels/{key}", response_model=UiLabelOut)
def get_label(key: str, db: DbDep, _: CurrentUserDep) -> UiLabelOut:
    row = db.get(UiLabel, key)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown label key: {key}")
    return UiLabelOut.model_validate(row)


# ---------------------------------------------------------------------------
# Admin writes
# ---------------------------------------------------------------------------
@router.put("/admin/ui-labels/{key}", response_model=UiLabelOut)
def update_label(
    key: str,
    payload: UiLabelUpdate,
    db: DbDep,
    admin: AdminUserDep,
    request: Request,
) -> UiLabelOut:
    row = db.get(UiLabel, key)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown label key: {key}")

    old = {
        "label_ar": row.label_ar, "label_en": row.label_en,
        "description_ar": row.description_ar, "description_en": row.description_en,
    }
    if payload.label_ar is not None:
        row.label_ar = payload.label_ar
    if payload.label_en is not None:
        row.label_en = payload.label_en
    if payload.description_ar is not None:
        row.description_ar = payload.description_ar
    if payload.description_en is not None:
        row.description_en = payload.description_en
    row.updated_by = admin.id

    db.add(
        AuditLog(
            user_id=admin.id,
            action="ui_label.update",
            resource_type="ui_labels",
            resource_id=key,
            request_method=request.method,
            request_path=str(request.url.path),
            ip_address=client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details={"old": old, "new": payload.model_dump(exclude_none=True)},
        )
    )
    db.commit()
    db.refresh(row)
    return UiLabelOut.model_validate(row)

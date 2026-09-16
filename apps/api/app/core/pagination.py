"""Reusable pagination, sorting and filtering helpers."""

from __future__ import annotations

from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


class PageParams(BaseModel):
    page: int = Field(1, ge=1, le=10_000)
    page_size: int = Field(25, ge=1, le=200)
    sort_by: str | None = None
    sort_dir: str = Field("desc", pattern="^(asc|desc)$")
    q: str | None = None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(25, ge=1, le=200),
    sort_by: str | None = Query(None, max_length=64),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    q: str | None = Query(None, max_length=200, description="Free-text search"),
) -> PageParams:
    return PageParams(page=page, page_size=page_size, sort_by=sort_by, sort_dir=sort_dir, q=q)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, params: PageParams) -> Page[T]:
        pages = max(1, -(-total // params.page_size))
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
            pages=pages,
        )


def apply_sort(stmt: Select, model: type, params: PageParams, default_column: str) -> Select:
    column_name = params.sort_by or default_column
    column = getattr(model, column_name, None)
    if column is None:
        column = getattr(model, default_column)
    return stmt.order_by(asc(column) if params.sort_dir == "asc" else desc(column))


def paginate(db: Session, stmt: Select, params: PageParams) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(stmt.offset(params.offset).limit(params.page_size)).scalars().all()
    return list(rows), int(total)

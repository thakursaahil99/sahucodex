from __future__ import annotations

import math
from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel

MAX_PAGE_SIZE = 100


class PageParams(BaseModel):
    page: int
    limit: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.limit


def page_params(
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> PageParams:
    return PageParams(page=page, limit=limit)


PageParamsDep = Annotated[PageParams, Depends(page_params)]


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    limit: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, params: PageParams) -> Page[T]:
        return cls(
            items=items, total=total, page=params.page, limit=params.limit, pages=math.ceil(total / params.limit)
        )

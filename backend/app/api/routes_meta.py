from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import SessionDep, TxSourceDep, UserDep
from app.api.schemas import CategoryInfo, MeOut
from app.domain import NON_SPENDING, SUBCATEGORIES, Category
from app.models import User

router = APIRouter()


@router.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/me", tags=["meta"], response_model=MeOut)
def get_me(session: SessionDep, user_id: UserDep, source: TxSourceDep) -> MeOut:
    user = session.scalar(select(User).where(User.id == user_id))
    assert user is not None  # noqa: S101  (get_user_id already 404s)
    return MeOut(
        id=user.id,
        name=user.name,
        balance_paisa=source.get_balance(user_id),
        balance_hidden=user.balance_hidden,
    )


@router.get("/categories", tags=["meta"], response_model=list[CategoryInfo])
def list_categories() -> list[CategoryInfo]:
    return [
        CategoryInfo(
            name=c,
            subcategories=list(SUBCATEGORIES.get(c, ())),
            counts_as_spending=c not in NON_SPENDING,
        )
        for c in Category
    ]

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DepositSourceDep, SessionDep, TodayDep, TxSourceDep, UserDep
from app.api.schemas import (
    BudgetIn,
    BudgetOut,
    BudgetPatch,
    GoalIn,
    GoalOut,
    GoalPatch,
    SmartDepositOut,
)
from app.models import Budget, Goal
from app.services.budgets import budget_statuses
from app.services.goals import goal_progress
from app.sources.base import TransactionSource

budgets = APIRouter(prefix="/budgets", tags=["budgets"])
goals = APIRouter(prefix="/goals", tags=["goals"])
smart_deposits = APIRouter(prefix="/smart-deposits", tags=["goals"])


# --- budgets -------------------------------------------------------------------------------


def _budget_out(
    session: Session, source: TransactionSource, user_id: str, today: dt.date, budget_id: int
) -> BudgetOut:
    for s in budget_statuses(session, source, user_id, today):
        if s.budget_id == budget_id:
            return BudgetOut.of(s)
    raise HTTPException(status_code=404, detail="budget not found")


def _own_budget(session: Session, user_id: str, budget_id: int) -> Budget:
    b = session.get(Budget, budget_id)
    if b is None or b.user_id != user_id:
        raise HTTPException(status_code=404, detail="budget not found")
    return b


@budgets.get("", response_model=list[BudgetOut])
def list_budgets(
    session: SessionDep, user_id: UserDep, source: TxSourceDep, today: TodayDep
) -> list[BudgetOut]:
    """This month's status for every budget: overall first, then categories."""
    return [BudgetOut.of(s) for s in budget_statuses(session, source, user_id, today)]


@budgets.post("", response_model=BudgetOut)
def upsert_budget(
    body: BudgetIn, session: SessionDep, user_id: UserDep, source: TxSourceDep, today: TodayDep
) -> BudgetOut:
    """Create the budget for this category (or overall), or replace its limit if it exists.
    The chat's confirm_action card calls this after the user taps Confirm."""
    category = body.category.value if body.category else None
    q = select(Budget).where(Budget.user_id == user_id)
    q = (
        q.where(Budget.category.is_(None))
        if category is None
        else q.where(Budget.category == category)
    )
    budget = session.scalar(q)
    if budget is None:
        budget = Budget(user_id=user_id, category=category)
        session.add(budget)
    budget.limit_paisa = body.limit_paisa
    budget.calendar = body.calendar.value
    session.commit()
    return _budget_out(session, source, user_id, today, budget.id)


@budgets.patch("/{budget_id}", response_model=BudgetOut)
def update_budget(
    budget_id: int,
    body: BudgetPatch,
    session: SessionDep,
    user_id: UserDep,
    source: TxSourceDep,
    today: TodayDep,
) -> BudgetOut:
    budget = _own_budget(session, user_id, budget_id)
    if body.limit_paisa is not None:
        budget.limit_paisa = body.limit_paisa
    if body.calendar is not None:
        budget.calendar = body.calendar.value
    session.commit()
    return _budget_out(session, source, user_id, today, budget.id)


@budgets.delete("/{budget_id}", status_code=204)
def delete_budget(budget_id: int, session: SessionDep, user_id: UserDep) -> Response:
    session.delete(_own_budget(session, user_id, budget_id))
    session.commit()
    return Response(status_code=204)


# --- goals ---------------------------------------------------------------------------------


def _goal_out(goal: Goal, today: dt.date) -> GoalOut:
    progress = goal_progress(
        target_paisa=goal.target_paisa,
        saved_paisa=goal.saved_paisa,
        deadline=goal.deadline,
        today=today,
    )
    return GoalOut.of(goal.id, goal.name, goal.deadline, progress)


def _own_goal(session: Session, user_id: str, goal_id: int) -> Goal:
    g = session.get(Goal, goal_id)
    if g is None or g.user_id != user_id:
        raise HTTPException(status_code=404, detail="goal not found")
    return g


@goals.get("", response_model=list[GoalOut])
def list_goals(session: SessionDep, user_id: UserDep, today: TodayDep) -> list[GoalOut]:
    rows = session.scalars(select(Goal).where(Goal.user_id == user_id).order_by(Goal.deadline))
    return [_goal_out(g, today) for g in rows]


@goals.post("", response_model=GoalOut, status_code=201)
def create_goal(body: GoalIn, session: SessionDep, user_id: UserDep, today: TodayDep) -> GoalOut:
    """The chat's confirm_action card calls this after the user taps Confirm."""
    goal = Goal(
        user_id=user_id,
        name=body.name.strip(),
        target_paisa=body.target_paisa,
        saved_paisa=body.saved_paisa,
        deadline=body.deadline,
    )
    session.add(goal)
    session.commit()
    return _goal_out(goal, today)


@goals.patch("/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: int, body: GoalPatch, session: SessionDep, user_id: UserDep, today: TodayDep
) -> GoalOut:
    goal = _own_goal(session, user_id, goal_id)
    if body.name is not None:
        goal.name = body.name.strip()
    if body.target_paisa is not None:
        goal.target_paisa = body.target_paisa
    if body.saved_paisa is not None:
        goal.saved_paisa = body.saved_paisa
    if body.deadline is not None:
        goal.deadline = body.deadline
    session.commit()
    return _goal_out(goal, today)


@goals.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: int, session: SessionDep, user_id: UserDep) -> Response:
    session.delete(_own_goal(session, user_id, goal_id))
    session.commit()
    return Response(status_code=204)


@smart_deposits.get("", response_model=list[SmartDepositOut])
def list_smart_deposits(
    user_id: UserDep, deposits: DepositSourceDep, today: TodayDep
) -> list[SmartDepositOut]:
    """Existing Smart Deposit plans (read-only; 'Automate' deep-links to Smart Deposit)."""
    return [SmartDepositOut.of(p) for p in deposits.smart_deposits(user_id, today)]

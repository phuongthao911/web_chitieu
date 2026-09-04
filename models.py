# pyrefly: ignore [missing-import]
from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime, timezone, timedelta

from database import Base


def get_vietnam_time() -> datetime:
    vn_tz = timezone(timedelta(hours=7))
    return datetime.now(vn_tz).replace(tzinfo=None)


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    transaction_type = Column(
        String(20),
        nullable=False
    )

    amount = Column(
        Float,
        nullable=False
    )

    category = Column(
        String,
        nullable=False
    )

    wallet = Column(
        String(50),
        nullable=False,
        default="Tiền mặt"
    )

    note = Column(
        String,
        nullable=False,
        default=""
    )

    destination_wallet = Column(
        String(50),
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=get_vietnam_time,
        nullable=False
    )


class Category(Base):
    __tablename__ = "categories"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String(100),
        nullable=False,
        unique=True
    )

    type = Column(
        String(20),
        nullable=False  # "income" or "expense"
    )


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    category_name = Column(
        String(100),
        nullable=False
    )

    amount_limit = Column(
        Float,
        nullable=False
    )

    month = Column(
        String(7),  # "YYYY-MM"
        nullable=False
    )


class RecurringTransaction(Base):
    __tablename__ = "recurring_transactions"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    transaction_type = Column(
        String(20),
        nullable=False  # "Income", "Expense", "Transfer"
    )

    amount = Column(
        Float,
        nullable=False
    )

    category = Column(
        String,
        nullable=False
    )

    wallet = Column(
        String(50),
        nullable=False
    )

    destination_wallet = Column(
        String(50),
        nullable=True
    )

    note = Column(
        String,
        nullable=False,
        default=""
    )

    day_of_month = Column(
        Integer,
        nullable=False
    )

    last_executed_month = Column(
        String(7),  # "YYYY-MM"
        nullable=True
    )


class Note(Base):
    __tablename__ = "notes"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    title = Column(
        String(255),
        nullable=False
    )

    content_html = Column(
        String,
        nullable=False,
        default=""
    )

    color = Column(
        String(20),
        nullable=False,
        default="pink"
    )

    pinned = Column(
        Integer,  # 0 or 1
        nullable=False,
        default=0
    )

    created_at = Column(
        DateTime,
        default=get_vietnam_time,
        nullable=False
    )

    updated_at = Column(
        String(50),
        nullable=False,
        default=""
    )


class DayCounter(Base):
    __tablename__ = "day_counters"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    title = Column(
        String(255),
        nullable=False
    )

    target_date = Column(
        String(20),  # YYYY-MM-DD
        nullable=False
    )

    mode = Column(
        String(20),  # "workday" or "calendar"
        nullable=False,
        default="workday"
    )

    created_at = Column(
        DateTime,
        default=get_vietnam_time,
        nullable=False
    )
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
# pyrefly: ignore [missing-import]
from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime, timezone, timedelta

from database import Base


def get_vietnam_time():
    return datetime.now(timezone(timedelta(hours=7))).replace(tzinfo=None)


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
from sqlalchemy import Column, Integer, String, Float, DateTime
from datetime import datetime

from database import Base


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

    note = Column(
        String,
        nullable=False,
        default=""
    )

    created_at = Column(
        DateTime,
        default=datetime.now,
        nullable=False
    )

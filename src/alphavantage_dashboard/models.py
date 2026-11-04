"""Users. (The first version also defined tables for commodity prices, top movers, price history, orders and a
wallet; nothing ever filled or read them, so they are gone. See docs/erd.png for the model they came from.)"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .extensions import db


def utcnow() -> datetime.datetime:
    """Naive UTC (datetime.utcnow() is deprecated); the columns store naive UTC."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


class User(db.Model):
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)  # stored in lower case
    email: Mapped[str] = mapped_column(String(120), unique=True)  # stored in lower case
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=utcnow)

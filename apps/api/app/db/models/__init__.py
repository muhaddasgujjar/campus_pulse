"""ORM models. Tables from Architectural.md Section 5 are added in M2 with Alembic migrations.

Import every model module here so `Base.metadata` is complete for Alembic autogenerate.
"""

from app.db.models.base import Base

__all__ = ["Base"]

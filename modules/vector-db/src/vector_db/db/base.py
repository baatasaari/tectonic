from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for Vector DB's own ORM models -- migration
    bookkeeping only; the vector data plane itself is Qdrant, not this."""

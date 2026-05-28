import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import seed
from app.db.models import Base


@pytest.fixture
def db_session() -> Session:
    """An isolated in-memory database seeded from the fixture."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    seed._load(session)
    session.commit()
    yield session
    session.close()


def tools_by_name(tool_list) -> dict:
    return {t.name: t for t in tool_list}

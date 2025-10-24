from sqlmodel import SQLModel, create_engine, Session

from .config import settings


def get_engine():
    connect_args = {}
    if settings.database_url.startswith("sqlite"):  # pragma: no branch - simple guard
        connect_args = {"check_same_thread": False}
    return create_engine(settings.database_url, connect_args=connect_args)


engine = get_engine()


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def reset_engine(database_url: str | None = None) -> None:
    global engine
    if database_url:
        settings.database_url = database_url
    engine = get_engine()

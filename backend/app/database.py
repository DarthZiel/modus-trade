from sqlmodel import create_engine

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 3},
)

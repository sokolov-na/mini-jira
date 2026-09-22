from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mini_jira.config import settings

engine = create_engine(settings.database_url)

SessionLocal = sessionmaker(engine)

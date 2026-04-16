from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base
from config import DATABASE_URL

# SQLAlchemy 1.4+ требует, чтобы префикс был postgresql://, а не postgres://
if DATABASE_URL.startswith("postgres://"):
    db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    db_url = DATABASE_URL

engine = create_engine(db_url, echo=False)
Session = sessionmaker(bind=engine)


def init_db():
    """Создать все таблицы"""
    Base.metadata.create_all(engine)
    print("✅ База данных инициализирована")


def get_session():
    """Получить сессию БД"""
    return Session()


if __name__ == "__main__":
    init_db()

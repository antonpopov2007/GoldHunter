from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)
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

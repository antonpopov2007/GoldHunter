from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base
from config import DATABASE_URL

import urllib.parse

# SQLAlchemy 1.4+ требует, чтобы префикс был postgresql://, а не postgres://
if DATABASE_URL.startswith("postgres://"):
    db_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    db_url = DATABASE_URL

# Автоматически чиним пароли со спецсимволами (например, с '@' или '#'), 
# если пользователь забыл их экранировать:
if db_url.startswith("postgresql://") and db_url.count("@") > 1:
    parts = db_url.rsplit("@", 1)
    host_part = parts[1]
    cred_part = parts[0]
    prefix = "postgresql://"
    creds = cred_part[len(prefix):]
    if ":" in creds:
        user, pwd = creds.split(":", 1)
        safe_pwd = urllib.parse.quote_plus(pwd)
        db_url = f"{prefix}{user}:{safe_pwd}@{host_part}"

# Также на всякий случай можно экранировать пароль, даже если `@` один, но есть `#` или `?`
elif db_url.startswith("postgresql://") and db_url.count("@") == 1:
    parts = db_url.split("@", 1)
    host_part = parts[1]
    cred_part = parts[0]
    prefix = "postgresql://"
    creds = cred_part[len(prefix):]
    if ":" in creds:
        user, pwd = creds.split(":", 1)
        # экранируем только если не было экранировано ранее (нет %)
        if "%" not in pwd and any(c in pwd for c in ["#", "?", "/", "="]):
            safe_pwd = urllib.parse.quote_plus(pwd)
            db_url = f"{prefix}{user}:{safe_pwd}@{host_part}"

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

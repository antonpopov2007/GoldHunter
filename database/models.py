from sqlalchemy import (
    Column, Integer, String, Float, DateTime,
    Boolean, ForeignKey, Text
)
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()


class Product(Base):
    """Товар — золотое украшение"""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    source = Column(String(50), nullable=False)        # "sokolov", "585gold"
    external_id = Column(String(100))                   # Артикул на сайте
    name = Column(String(500), nullable=False)
    url = Column(Text)
    image_url = Column(Text)
    probe = Column(Integer)                             # 375, 585, 750
    weight_grams = Column(Float)                        # Вес в граммах
    category = Column(String(100))                      # кольцо, цепь, серьги...
    subcategory = Column(String(100))                   # обручальное, дизайнерское
    has_stones = Column(Boolean, default=False)
    stone_type = Column(String(200))
    material = Column(String(200))                      # "Белое золото 585 пробы"
    liquidity_score = Column(Float)                     # Рассчитанная ликвидность 0-1
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)

    # Связь с историей цен
    price_history = relationship("PriceHistory", back_populates="product")

    def __repr__(self):
        return (
            f"<Product {self.name} | {self.source} | "
            f"{self.weight_grams}г {self.probe}>"
        )


class PriceHistory(Base):
    """Снапшот цены — новая строка каждый день"""
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    price = Column(Float, nullable=False)               # Текущая цена
    old_price_displayed = Column(Float)                 # "Старая цена" по версии сайта
    discount_percent = Column(Float)                    # Скидка в %
    discount_label = Column(String(200))                # "Распродажа -40%"
    promocodes = Column(String(500))                    # Действующие промокоды
    gold_rate_per_gram_999 = Column(Float)              # Цена золота 999 на бирже
    parsed_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="price_history")


class GoldRate(Base):
    """Цена золота на бирже / ЦБ — ежедневно"""
    __tablename__ = "gold_rates"

    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False)
    price_per_gram_999 = Column(Float, nullable=False)  # Чистое золото
    price_per_gram_585 = Column(Float)
    price_per_gram_750 = Column(Float)
    source = Column(String(50))                          # "cbr", "moex"

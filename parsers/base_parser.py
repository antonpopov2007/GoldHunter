from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime
from database.db import get_session
from database.models import Product, PriceHistory


class BaseParser(ABC):
    """Базовый класс для всех парсеров ювелирных магазинов"""

    SOURCE_NAME = "unknown"

    @abstractmethod
    def parse_catalog(self, max_pages: int = 5) -> list[dict]:
        """
        Спарсить каталог и вернуть список товаров.
        Каждый товар — словарь с ключами:
        {
            "external_id": str,
            "name": str,
            "url": str,
            "image_url": str,
            "probe": int (585, 750...),
            "weight_grams": float,
            "category": str,
            "subcategory": str or None,
            "has_stones": bool,
            "stone_type": str or None,
            "material": str or None,
            "price": float,
            "old_price": float or None,
            "discount_percent": float or None,
            "discount_label": str or None,
            "promocodes": str or None,
        }
        """
        pass

    def save_to_db(self, items: list[dict], gold_rate_999: float):
        """Сохранить товары и цены в базу"""
        session = get_session()
        new_products = 0
        updated_prices = 0

        for item in items:
            # Ищем товар в базе
            product = session.query(Product).filter_by(
                source=self.SOURCE_NAME,
                external_id=item["external_id"]
            ).first()

            if product is None:
                # Новый товар
                product = Product(
                    source=self.SOURCE_NAME,
                    external_id=item["external_id"],
                    name=item["name"],
                    url=item.get("url"),
                    image_url=item.get("image_url"),
                    probe=item.get("probe"),
                    weight_grams=item.get("weight_grams"),
                    category=item.get("category"),
                    subcategory=item.get("subcategory"),
                    has_stones=item.get("has_stones", False),
                    stone_type=item.get("stone_type"),
                    material=item.get("material"),
                )
                session.add(product)
                session.flush()  # Чтобы получить ID
                new_products += 1
            else:
                # Обновляем данные если вес/проба появились
                if item.get("weight_grams") and not product.weight_grams:
                    product.weight_grams = item["weight_grams"]
                if item.get("probe") and not product.probe:
                    product.probe = item["probe"]

            # Обновляем last_seen
            product.last_seen = datetime.utcnow()

            # Добавляем снапшот цены
            price_record = PriceHistory(
                product_id=product.id,
                price=item["price"],
                old_price_displayed=item.get("old_price"),
                discount_percent=item.get("discount_percent"),
                discount_label=item.get("discount_label"),
                promocodes=item.get("promocodes"),
                gold_rate_per_gram_999=gold_rate_999,
                parsed_at=datetime.utcnow(),
            )
            session.add(price_record)
            updated_prices += 1

        session.commit()
        session.close()

        print(
            f"  ✅ {self.SOURCE_NAME}: "
            f"{new_products} новых товаров, "
            f"{updated_prices} записей цен"
        )

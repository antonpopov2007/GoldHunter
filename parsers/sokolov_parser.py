from __future__ import annotations
"""
Парсер Sokolov — через REST API catalog.sokolov.ru

Двухшаговый подход:
1. Catalog API → список артикулов с ценами (быстро, постранично)
2. Product API → полные данные (вес, проба, камни)

Catalog: GET https://catalog.sokolov.ru/api/v2/catalog/{category}/gold/?page={N}
Product: GET https://catalog.sokolov.ru/api/v2/products/{article}/
"""

import requests
import re
import time
from parsers.base_parser import BaseParser


class SokolovParser(BaseParser):
    SOURCE_NAME = "sokolov"
    API_BASE = "https://catalog.sokolov.ru/api/v2"
    SITE_BASE = "https://sokolov.ru"

    # Категории на сайте Sokolov → наши категории
    CATEGORY_MAP = {
        "rings": "кольцо",
        "earrings": "серьги",
        "chains": "цепь",
        "bracelets": "браслет",
        "pendants": "подвеска",
        "necklaces": "колье",
        "brooches": "брошь",
        "piercings": "пирсинг",
    }

    # Категории для сканирования (только самые ликвидные)
    CATALOG_CATEGORIES = [
        "rings", "earrings", "chains", "bracelets",
        "pendants", "necklaces",
    ]

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }

    def parse_catalog(self, max_pages: int = 3) -> list[dict]:
        """
        Парсим каталог Sokolov через Catalog API + Product API.

        Шаг 1: Catalog API → получаем артикулы и базовые цены.
        Шаг 2: Product API → получаем вес, пробу, камни.

        max_pages — максимум страниц на категорию (20 товаров/стр).
        """
        all_items = []
        seen_articles = set()

        for category in self.CATALOG_CATEGORIES:
            print(f"  📂 Sokolov — категория: {category}/gold/")

            # Шаг 1: Catalog API — получаем артикулы
            articles_data = self._get_catalog_articles(category, max_pages)

            for article_info in articles_data:
                article = article_info["article"]
                if article in seen_articles:
                    continue
                seen_articles.add(article)

                # Шаг 2: Product API — полные данные
                item = self._fetch_product(article)
                if item:
                    all_items.append(item)

                time.sleep(0.3)  # Пауза между запросами

            print(f"    ✅ Найдено {len(articles_data)} артикулов")

        print(f"\n  📦 Sokolov итого: {len(all_items)} товаров")
        return all_items

    def parse_by_articles(self, articles: list[str]) -> list[dict]:
        """Парсинг конкретных товаров по списку артикулов"""
        items = []
        for article in articles:
            item = self._fetch_product(article)
            if item:
                items.append(item)
            time.sleep(0.3)
        return items

    def _get_catalog_articles(
        self, category: str, max_pages: int = 3
    ) -> list[dict]:
        """
        Получить список артикулов из каталога через API.

        Endpoint: /api/v2/catalog/{category}/gold/?page={N}
        Возвращает 20 товаров/стр с базовой информацией.
        """
        articles = []

        for page in range(1, max_pages + 1):
            url = f"{self.API_BASE}/catalog/{category}/gold/?page={page}"

            try:
                response = requests.get(
                    url, headers=self.HEADERS, timeout=15
                )
                if response.status_code != 200:
                    print(f"    ⚠️ Статус {response.status_code}, стоп")
                    break

                result = response.json()
                data = result.get("data", [])
                meta = result.get("meta", {})

                if not data:
                    break

                for item in data:
                    articles.append({
                        "article": item.get("article", ""),
                        "name": item.get("name", ""),
                        "price": item.get("price"),
                        "old_price": item.get("old_price"),
                        "discount": item.get("discount"),
                    })

                # Проверяем, есть ли следующая страница
                if page >= meta.get("page_count", 0):
                    break

                time.sleep(0.5)  # Пауза между страницами

            except Exception as e:
                print(f"    ⚠️ Ошибка загрузки каталога: {e}")
                break

        return articles

    def _fetch_product(self, article: str) -> dict | None:
        """Получить полные данные товара через Product API"""
        url = f"{self.API_BASE}/products/{article}/"

        try:
            response = requests.get(
                url, headers=self.HEADERS, timeout=10
            )
            if response.status_code != 200:
                return None

            data = response.json()
            return self._parse_api_response(data)

        except Exception as e:
            print(f"    ⚠️ Ошибка API для {article}: {e}")
            return None

    def _parse_api_response(self, data: dict) -> dict | None:
        """Преобразовать ответ Product API в наш формат"""
        try:
            # Извлекаем пробу из material_purity или material
            probe = self._extract_probe(data)

            # Извлекаем вес
            weight = self._extract_weight(data)

            # Категория
            category = self.CATEGORY_MAP.get(
                data.get("category", ""), "другое"
            )

            # Подкатегория
            subcategory = self._detect_subcategory(
                data.get("name", ""), category
            )

            # Камни
            has_stones, stone_type = self._extract_stones(data)

            # Промокоды
            promo = data.get("promocode", {})
            promocode_str = promo.get("promocode", "") if promo else ""

            # Пропускаем серебро и другие не-золотые
            material = data.get("material", "")
            if "золото" not in material.lower() and "золот" not in material.lower():
                return None

            price = data.get("price")
            if not price or price == 0:
                return None

            return {
                "external_id": data.get("article", ""),
                "name": data.get("name", "Без названия"),
                "url": f"{self.SITE_BASE}/jewelry-catalog/product/{data.get('article', '')}/",
                "image_url": self._extract_image(data),
                "probe": probe,
                "weight_grams": weight,
                "category": subcategory if subcategory else category,
                "subcategory": subcategory,
                "has_stones": has_stones,
                "stone_type": stone_type,
                "material": material,
                "price": float(price),
                "old_price": float(data["old_price"]) if data.get("old_price") else None,
                "discount_percent": float(data["discount"]) if data.get("discount") else None,
                "discount_label": f"-{data['discount']}%" if data.get("discount") else None,
                "promocodes": promocode_str if promocode_str else None,
            }

        except Exception as e:
            print(f"    ⚠️ Ошибка парсинга: {e}")
            return None

    def _extract_probe(self, data: dict) -> int | None:
        """Извлечь пробу из данных API"""
        # Из characteristic_short
        for char in data.get("characteristic_short", []):
            if char.get("title") == "Материал":
                match = re.search(r"(\d{3})\s*проб", char.get("value", ""))
                if match:
                    return int(match.group(1))

        # Из characteristic (полные)
        for section in data.get("characteristic", []):
            for val in section.get("values", []):
                if val.get("code") == "material_purity":
                    try:
                        return int(val["value"])
                    except (ValueError, TypeError):
                        pass

        # Из material текста
        material = data.get("material", "")
        match = re.search(r"(\d{3})\s*проб", material)
        if match:
            return int(match.group(1))

        return None

    def _extract_weight(self, data: dict) -> float | None:
        """Извлечь вес из данных API"""
        weight_str = data.get("weight", "")
        if weight_str:
            match = re.search(r"([\d.,]+)\s*г", weight_str)
            if match:
                return float(match.group(1).replace(",", "."))

        # Из weight_by_size (берём среднее)
        wbs = data.get("weight_by_size", {})
        if wbs:
            weights = list(wbs.values())
            return round(sum(weights) / len(weights), 2)

        return None

    def _extract_stones(self, data: dict) -> tuple[bool, str | None]:
        """Извлечь информацию о камнях"""
        inserts = data.get("inserts", [])
        if not inserts:
            return False, None

        stone_names = [ins.get("name", "") for ins in inserts]
        return True, ", ".join(stone_names) if stone_names else None

    def _extract_image(self, data: dict) -> str:
        """Извлечь URL главного изображения"""
        media = data.get("media", [])
        for item in media:
            if item.get("type") == "photo":
                img_data = item.get("data", {})
                return img_data.get("jpg", "")
        return ""

    def _detect_subcategory(self, name: str, category: str) -> str | None:
        """Определить подкатегорию по названию"""
        name_lower = name.lower()

        if category == "кольцо":
            if "обручальн" in name_lower:
                return "кольцо обручальное"
            if "помолвочн" in name_lower:
                return "кольцо обручальное"  # Тоже ликвидно
            if "печатк" in name_lower:
                return "кольцо"

        return None


if __name__ == "__main__":
    parser = SokolovParser()

    # Тест: каталог (1 стр на категорию)
    print("🧪 Тест Sokolov Catalog API...")
    items = parser.parse_catalog(max_pages=1)

    for item in items[:5]:
        print(f"\n  💍 {item['name']}")
        print(f"     Цена: {item['price']:.0f}₽")
        print(f"     Вес: {item['weight_grams']}г | Проба: {item['probe']}")
        print(f"     Категория: {item['category']}")
        print(f"     Камни: {item['stone_type'] or 'нет'}")

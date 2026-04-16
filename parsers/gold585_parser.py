from __future__ import annotations
"""
Парсер 585 Золотой (585zolotoy.ru) — через JSON API

Двухфазный парсинг:
- Фаза 1: Catalog API → цены (быстро, ежедневно)
- Фаза 2: Product pages → вес и проба (только для новых товаров)
"""

import requests
import re
import time
from bs4 import BeautifulSoup
from parsers.base_parser import BaseParser


class Gold585Parser(BaseParser):
    SOURCE_NAME = "585gold"
    API_URL = "https://www.585zolotoy.ru/api/modules/catalog/v1/list/"
    SITE_BASE = "https://www.585zolotoy.ru"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/html",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }

    def parse_catalog(self, max_pages: int = 3) -> list[dict]:
        """
        Фаза 1: Получить товары из каталога через API.
        Возвращает товары БЕЗ веса и пробы (их нет в API каталога).
        """
        all_items = []

        for page in range(1, max_pages + 1):
            print(f"  📄 585gold — страница {page}/{max_pages}")

            params = {"page": page, "append": "1"}

            try:
                response = requests.get(
                    self.API_URL,
                    params=params,
                    headers=self.HEADERS,
                    timeout=15,
                )
                if response.status_code != 200:
                    print(f"    ⚠️ Статус {response.status_code}, пропускаем")
                    break

                data = response.json()
                items = data.get("items", [])

                if not items:
                    print("    ℹ️ Нет товаров, конец каталога")
                    break

                for item_data in items:
                    item = self._parse_catalog_item(item_data)
                    if item:
                        all_items.append(item)

                print(f"    ✅ Найдено {len(items)} товаров")

                # Проверяем есть ли следующая страница
                pagination = data.get("pagination", {})
                if not pagination.get("next_page_params"):
                    break

                time.sleep(1.5)  # Пауза между страницами

            except Exception as e:
                print(f"    ❌ Ошибка: {e}")
                break

        print(f"\n  📦 585gold итого: {len(all_items)} товаров (Phase 1)")
        return all_items

    def enrich_with_details(self, items: list[dict]) -> list[dict]:
        """
        Фаза 2: Для товаров без веса/пробы — загружаем страницу товара.
        Вызывать при первом обнаружении товара.
        """
        enriched = 0

        for item in items:
            if item.get("weight_grams") and item.get("probe"):
                continue  # Уже есть данные

            article = item.get("external_id", "")
            if not article:
                continue

            details = self._fetch_product_details(article)
            if details:
                item["weight_grams"] = details.get("weight_grams") or item.get("weight_grams")
                item["probe"] = details.get("probe") or item.get("probe")
                item["material"] = details.get("material") or item.get("material")
                enriched += 1

            time.sleep(2)  # Пауза — мы загружаем HTML страницы

        print(f"  🔍 Обогащено {enriched} товаров из {len(items)}")
        return items

    def _parse_catalog_item(self, data: dict) -> dict | None:
        """Распарсить товар из API каталога"""
        try:
            name = data.get("name", "")

            # Фильтруем серебро
            if "серебр" in name.lower():
                return None

            # Цены из analytics (числовые)
            analytics = data.get("analytics", {})
            price = analytics.get("final_price")
            old_price = analytics.get("base_price")

            if not price or price == 0:
                return None

            # Скидка
            pricing = data.get("pricing", {})
            discount_text = pricing.get("discount", "")
            discount_pct = None
            if discount_text:
                match = re.search(r"(\d+)", discount_text)
                if match:
                    discount_pct = float(match.group(1))

            # Промокоды
            promocodes = analytics.get("promocodes")
            promo_str = ", ".join(promocodes) if promocodes else None

            # Артикул
            article = data.get("article", "")

            # Извлекаем пробу и вес из названия (fallback)
            probe = self._extract_probe_from_name(name)
            weight = self._extract_weight_from_name(name)

            # Категория
            category = self._detect_category(name)
            subcategory = self._detect_subcategory(name, category)

            # Камни
            has_stones, stone_type = self._detect_stones(name)

            # Изображение
            image_url = ""
            media = data.get("media", [])
            if media and media[0].get("image"):
                image_url = media[0]["image"].get("url", "")

            return {
                "external_id": article,
                "name": name,
                "url": f"{self.SITE_BASE}/catalog/products/{article}/",
                "image_url": image_url,
                "probe": probe,
                "weight_grams": weight,
                "category": subcategory if subcategory else category,
                "subcategory": subcategory,
                "has_stones": has_stones,
                "stone_type": stone_type,
                "material": None,
                "price": float(price),
                "old_price": float(old_price) if old_price and old_price != price else None,
                "discount_percent": discount_pct,
                "discount_label": discount_text if discount_text else None,
                "promocodes": promo_str,
            }

        except Exception as e:
            print(f"    ⚠️ Ошибка парсинга: {e}")
            return None

    def _fetch_product_details(self, article: str) -> dict | None:
        """Фаза 2: загрузить HTML страницы товара, извлечь вес и пробу"""
        url = f"{self.SITE_BASE}/catalog/products/{article}/"

        try:
            response = requests.get(
                url, headers=self.HEADERS, timeout=15
            )
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, "html.parser")

            result = {}

            # Ищем характеристики в тексте страницы
            text = soup.get_text()

            # Вес
            weight_match = re.search(
                r'(?:Вес|вес)[:\s]*(?:от\s+)?([\d.,]+)\s*г', text
            )
            if weight_match:
                result["weight_grams"] = float(
                    weight_match.group(1).replace(",", ".")
                )

            # Проба
            probe_match = re.search(r'(?:Проба|проба)[:\s]*(\d{3})', text)
            if probe_match:
                result["probe"] = int(probe_match.group(1))

            # Материал
            mat_match = re.search(
                r'(?:Материал|Металл)[:\s]*([\w\s]+(?:золото|золот)[\w\s]*\d{3})',
                text
            )
            if mat_match:
                result["material"] = mat_match.group(1).strip()

            return result if result else None

        except Exception as e:
            print(f"    ⚠️ Ошибка загрузки деталей {article}: {e}")
            return None

    def _extract_probe_from_name(self, name: str) -> int | None:
        """Извлечь пробу из названия"""
        if "золот" in name.lower():
            match = re.search(r"\b(375|585|750|999)\b", name)
            return int(match.group(1)) if match else 585
        return None

    def _extract_weight_from_name(self, name: str) -> float | None:
        """Извлечь вес из названия"""
        match = re.search(r"(\d+[.,]\d+)\s*г", name)
        if match:
            return float(match.group(1).replace(",", "."))
        return None

    def _detect_category(self, name: str) -> str:
        """Определить категорию по названию"""
        name_lower = name.lower()
        categories = {
            "кольцо": ["кольц", "перстен", "обручал"],
            "серьги": ["серьг", "серёг", "пусет"],
            "цепь": ["цепь", "цепоч"],
            "браслет": ["браслет"],
            "подвеска": ["подвеск", "кулон"],
            "колье": ["колье", "ожерел"],
            "брошь": ["брошь", "брош"],
            "пирсинг": ["пирсинг"],
        }
        for category, keywords in categories.items():
            for kw in keywords:
                if kw in name_lower:
                    return category
        return "другое"

    def _detect_subcategory(self, name: str, category: str) -> str | None:
        """Определить подкатегорию"""
        name_lower = name.lower()
        if category == "кольцо":
            if "обручальн" in name_lower or "обручал" in name_lower:
                return "кольцо обручальное"
            if "помолвочн" in name_lower:
                return "кольцо обручальное"
        return None

    def _detect_stones(self, name: str) -> tuple[bool, str | None]:
        """Определить наличие камней по названию"""
        name_lower = name.lower()
        stones = {
            "бриллиант": ["бриллиант", "diamond"],
            "фианит": ["фианит", "cz"],
            "сапфир": ["сапфир"],
            "рубин": ["рубин"],
            "изумруд": ["изумруд"],
            "топаз": ["топаз"],
            "аметист": ["аметист"],
            "гранат": ["гранат"],
            "оникс": ["оникс"],
            "цирконий": ["цирконий", "циркон"],
        }
        found = []
        for stone, keywords in stones.items():
            for kw in keywords:
                if kw in name_lower:
                    found.append(stone)
                    break

        if found:
            return True, ", ".join(found)
        return False, None


if __name__ == "__main__":
    parser = Gold585Parser()
    items = parser.parse_catalog(max_pages=1)

    for item in items[:5]:
        print(
            f"  {item['name']} | "
            f"{item['price']:.0f}₽ | "
            f"{item['weight_grams']}г | "
            f"{item['category']}"
        )

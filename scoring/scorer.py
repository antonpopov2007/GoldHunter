from __future__ import annotations
"""
GoldHunter — Система скоринга выгодности

Скоринг 0–100 учитывает:
1. Коэффициент выгодности (цена металла vs цена товара)
2. Типичную наценку для категории
3. Наличие камней (снижает ценность при перепродаже)
4. Историю цен
5. Ликвидность (насколько легко перепродать)
6. Вес (тяжёлые изделия ликвиднее)
"""

from database.db import get_session
from database.models import Product, PriceHistory
from config import GOLD_PROBES, LIQUIDITY_SCORES, CATEGORY_MULTIPLIERS
from sqlalchemy import desc


class GoldScorer:
    """Считает выгодность покупки золотого украшения для перепродажи"""

    def calculate_score(
        self,
        product: Product,
        current_price: float,
        gold_rate_999: float,
    ) -> dict:
        """
        Рассчитать скоринг выгодности.

        Возвращает:
        {
            "score": int (0-100),
            "metal_value": float (стоимость металла),
            "markup_percent": float (наценка над ломом в %),
            "coefficient": float (стоимость металла / цена),
            "liquidity": float (0-1),
            "verdict": str,
            "details": str,
        }
        """

        result = {
            "score": 0,
            "metal_value": 0,
            "markup_percent": 0,
            "coefficient": 0,
            "liquidity": 0,
            "verdict": "Нет данных",
            "details": "",
        }

        # Если нет веса или пробы — не можем считать
        if not product.weight_grams or not product.probe:
            result["verdict"] = "⚠️ Нет данных о весе или пробе"
            return result

        # 1. Стоимость чистого металла в изделии
        purity = GOLD_PROBES.get(product.probe, 0.585)
        metal_value = product.weight_grams * purity * gold_rate_999
        result["metal_value"] = round(metal_value, 2)

        # 2. Коэффициент выгодности
        coefficient = metal_value / current_price if current_price > 0 else 0
        result["coefficient"] = round(coefficient, 3)

        # 3. Наценка над ломом
        markup = (
            (current_price - metal_value) / metal_value * 100
            if metal_value > 0
            else 999
        )
        result["markup_percent"] = round(markup, 1)

        # 4. Ликвидность
        category = product.category or "другое"
        liquidity = LIQUIDITY_SCORES.get(category, 0.50)

        # Бонус ликвидности за вес
        if product.weight_grams >= 5:
            liquidity = min(1.0, liquidity + 0.10)  # Тяжёлые — ликвиднее
        elif product.weight_grams < 2:
            liquidity = max(0.0, liquidity - 0.15)  # Лёгкие — хуже

        result["liquidity"] = round(liquidity, 2)

        # ========================
        # Считаем скор (компоненты)
        # ========================

        # A. Базовый скор от коэффициента (0-60 баллов)
        if coefficient >= 1.0:
            base_score = 60  # Дешевле лома!
        elif coefficient >= 0.8:
            base_score = 50
        elif coefficient >= 0.6:
            base_score = 40
        elif coefficient >= 0.4:
            base_score = 25
        elif coefficient >= 0.3:
            base_score = 15
        else:
            base_score = 5

        # B. Бонус за категорию (0-15 баллов)
        expected_multiplier = CATEGORY_MULTIPLIERS.get(category, 1.5)
        expected_price = metal_value * expected_multiplier

        if current_price <= expected_price:
            category_bonus = 15
        elif current_price <= expected_price * 1.2:
            category_bonus = 10
        elif current_price <= expected_price * 1.5:
            category_bonus = 5
        else:
            category_bonus = 0

        # C. Штраф за камни (-10 баллов)
        stone_penalty = -10 if product.has_stones else 0

        # D. Бонус за историю цен (0-25 баллов)
        history_bonus = self._history_bonus(product, current_price)

        # ========================
        # Итоговый скор с ликвидностью
        # ========================

        raw_score = base_score + category_bonus + stone_penalty + history_bonus
        raw_score = max(0, min(100, raw_score))

        # Умножаем на ликвидность
        # (товар с ликвидностью 0.2 получит max 20% от скора)
        total_score = int(raw_score * liquidity)
        total_score = max(0, min(100, total_score))

        result["score"] = total_score

        # Вердикт
        if total_score >= 80:
            result["verdict"] = "🔥 Отличная сделка!"
        elif total_score >= 60:
            result["verdict"] = "✅ Выгодно"
        elif total_score >= 40:
            result["verdict"] = "🟡 Нормально"
        elif total_score >= 25:
            result["verdict"] = "🟠 Дороговато"
        else:
            result["verdict"] = "🔴 Невыгодно"

        # Детали
        result["details"] = (
            f"Металл: {metal_value:.0f}₽ | "
            f"Цена: {current_price:.0f}₽ | "
            f"Наценка: {markup:.0f}% | "
            f"Коэфф: {coefficient:.2f} | "
            f"Ликвидность: {liquidity:.0f}%"
        )

        return result

    def _history_bonus(self, product: Product, current_price: float) -> int:
        """
        Бонус за историю цен:
        - Цена ниже исторического минимума → +25
        - Цена падает последние 2 недели → +15
        - Есть история, но без тренда → +5
        - Мало данных → +0
        """
        session = get_session()

        history = (
            session.query(PriceHistory)
            .filter_by(product_id=product.id)
            .order_by(PriceHistory.parsed_at)
            .all()
        )

        session.close()

        if len(history) < 3:
            return 0  # Мало данных

        prices = [h.price for h in history]
        min_price = min(prices)

        # Ниже исторического минимума
        if current_price <= min_price:
            return 25

        # Цена падает (последние 5 записей)
        recent = prices[-5:]
        if len(recent) >= 3 and all(
            recent[i] >= recent[i + 1] for i in range(len(recent) - 1)
        ):
            return 15

        return 5  # Есть история, но без явного тренда

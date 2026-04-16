from __future__ import annotations
"""
GoldHunter — Ежедневный запуск

Парсинг → Сохранение → Скоринг → Вывод ТОП-10
"""

from database.db import init_db, get_session
from database.models import GoldRate, Product, PriceHistory
from parsers.gold_rate_parser import save_gold_rate
from parsers.sokolov_parser import SokolovParser
from parsers.gold585_parser import Gold585Parser
from scoring.scorer import GoldScorer
from sqlalchemy import desc
from datetime import datetime


def run_daily():
    """Ежедневный запуск: парсинг + сохранение + скоринг"""

    print("=" * 60)
    print(f"🚀 GoldHunter — запуск {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. Инициализация БД
    init_db()

    # 2. Получаем цену золота
    print("\n📊 Получаем цену золота...")
    gold_rate = save_gold_rate()

    if gold_rate is None:
        # Берём последнюю из базы
        session = get_session()
        last_rate = (
            session.query(GoldRate)
            .order_by(desc(GoldRate.date))
            .first()
        )
        session.close()

        if last_rate:
            gold_rate = last_rate.price_per_gram_999
            print(f"  ℹ️ Используем последнюю: {gold_rate:.2f} ₽/г")
        else:
            print("  ❌ Нет данных о цене золота! Прерываем.")
            return

    # 3. Парсим Sokolov (приоритет №1 — идеальный API)
    print("\n🏪 Парсим Sokolov...")
    parser_sokolov = SokolovParser()
    items_sokolov = parser_sokolov.parse_catalog(max_pages=2)
    if items_sokolov:
        parser_sokolov.save_to_db(items_sokolov, gold_rate)

    # 4. Парсим 585 Gold
    print("\n🏪 Парсим 585 Gold...")
    parser_585 = Gold585Parser()
    items_585 = parser_585.parse_catalog(max_pages=2)
    if items_585:
        # Фаза 2: обогащаем новые товары весом/пробой
        items_585 = parser_585.enrich_with_details(items_585)
        parser_585.save_to_db(items_585, gold_rate)

    # 5. Топ выгодных
    print("\n" + "=" * 60)
    print("🏆 Топ-10 самых выгодных для перепродажи:")
    print("=" * 60)
    print_top_deals(gold_rate)

    print("\n✅ Готово!")


def print_top_deals(gold_rate: float, limit: int = 10):
    """Вывести самые выгодные предложения"""
    session = get_session()
    scorer = GoldScorer()

    # Берём товары с весом и пробой
    products = (
        session.query(Product)
        .filter(
            Product.weight_grams.isnot(None),
            Product.probe.isnot(None),
        )
        .all()
    )

    scored = []
    for product in products:
        # Берём последнюю цену
        last_price = (
            session.query(PriceHistory)
            .filter_by(product_id=product.id)
            .order_by(desc(PriceHistory.parsed_at))
            .first()
        )

        if last_price:
            score_result = scorer.calculate_score(
                product, last_price.price, gold_rate
            )
            scored.append((product, last_price, score_result))

    session.close()

    # Сортируем по скору
    scored.sort(key=lambda x: x[2]["score"], reverse=True)

    if not scored:
        print("\n  ℹ️ Пока нет товаров с полными данными.")
        print("  Запустите ещё раз для обогащения данных.")
        return

    for i, (product, price, score) in enumerate(scored[:limit], 1):
        print(f"\n  {'─' * 50}")
        print(f"  #{i} {score['verdict']}  Скор: {score['score']}/100")
        print(f"  💍 {product.name}")
        print(f"  📍 {product.source} | {product.category or '—'}")
        print(
            f"  💰 {price.price:,.0f} ₽"
            + (f" (было {price.old_price_displayed:,.0f} ₽)" if price.old_price_displayed else "")
        )
        print(f"  ⚖️ {product.weight_grams}г | Проба: {product.probe}")
        print(f"  📊 {score['details']}")
        print(f"  🔗 {product.url}")


if __name__ == "__main__":
    run_daily()

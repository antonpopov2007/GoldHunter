from __future__ import annotations
import requests
from datetime import datetime, date, timedelta
from database.db import get_session
from database.models import GoldRate
from config import GOLD_PROBES


def fetch_gold_rate_cbr() -> float | None:
    """
    Получить цену золота за грамм 999 пробы с сайта ЦБ РФ.
    Пробуем сегодня, вчера и позавчера (выходные/праздники).
    """
    url = "https://www.cbr.ru/scripts/xml_metall.asp"

    # Пробуем несколько дней (ЦБ не публикует в выходные)
    for days_back in range(0, 5):
        target_date = date.today() - timedelta(days=days_back)
        params = {
            "date_req1": target_date.strftime("%d/%m/%Y"),
            "date_req2": target_date.strftime("%d/%m/%Y"),
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.encoding = "windows-1251"

            from xml.etree import ElementTree
            root = ElementTree.fromstring(response.text)

            for record in root.findall(".//Record"):
                code_el = record.find("Code")
                buy_el = record.find("Buy")
                if code_el is None or buy_el is None:
                    continue

                if code_el.text.strip() == "1":
                    price_str = buy_el.text.strip().replace(",", ".")
                    price_999 = float(price_str)

                    print(
                        f"  💰 Цена золота ЦБ РФ ({target_date}): "
                        f"{price_999:.2f} ₽/г (999 проба)"
                    )
                    return price_999

        except Exception as e:
            if days_back == 0:
                continue  # Попробуем вчерашний день
            print(f"  ❌ Ошибка получения цены золота: {e}")

    return None


def save_gold_rate() -> float | None:
    """Сохранить текущую цену в базу и вернуть цену 999 пробы"""
    price_999 = fetch_gold_rate_cbr()

    if price_999 is None:
        print("  ⚠️ Не удалось получить цену золота, пропускаем")
        return None

    session = get_session()

    rate = GoldRate(
        date=datetime.utcnow(),
        price_per_gram_999=price_999,
        price_per_gram_585=price_999 * GOLD_PROBES[585],
        price_per_gram_750=price_999 * GOLD_PROBES[750],
        source="cbr",
    )

    session.add(rate)
    session.commit()
    session.close()

    print(f"  ✅ Цена золота сохранена: {price_999:.2f} ₽/г")
    return price_999


if __name__ == "__main__":
    save_gold_rate()

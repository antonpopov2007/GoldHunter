# GoldHunter — Система поиска выгодных золотых украшений

## Описание
CamelCamelCamel для ювелирки — мониторинг цен на золотые украшения, 
скоринг выгодности через стоимость металла, детектор фейковых скидок.

## Быстрый старт
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m scheduler.daily_run
```

## Структура
```
goldhunter/
├── parsers/           # Парсеры магазинов
├── database/          # Модели и подключение к БД
├── scoring/           # Скоринг выгодности
├── scheduler/         # Ежедневный запуск
└── config.py          # Настройки
```

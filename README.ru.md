# FarmTrack

[English](README.md) | [Русский](README.ru.md)

![FarmTrack brand header](marketing/brand/farmtrack-brand-header.svg)

Локальное desktop-приложение для отслеживания crypto airdrop farming: протоколы, кошельки, балансы, P&L и perp-позиции. Собрано на Python + Flask + pywebview. Без облака, без аккаунтов, всё остаётся на вашем компьютере.

![Version](https://img.shields.io/badge/version-alpha%20v0.91-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)
![Tests](https://img.shields.io/badge/tests-255%20passing-brightgreen)

---

## Скриншоты

Скриншоты ниже используют обезличенные демо-данные.

![Overview dashboard](marketing/Screenshots%20for%20readme/sanitized/main_example.png)

<p>
  <img src="marketing/Screenshots%20for%20readme/sanitized/protocols_example.png" alt="Protocols table" width="49%">
  <img src="marketing/Screenshots%20for%20readme/sanitized/wallets_example.png" alt="Wallets table" width="49%">
</p>

<p>
  <img src="marketing/Screenshots%20for%20readme/sanitized/nado_protocol_example.png" alt="Protocol detail" width="49%">
  <img src="marketing/Screenshots%20for%20readme/sanitized/perp_nado_example.png" alt="Perp positions" width="49%">
</p>

---

## Возможности

- **Профили** — отдельные базы данных для разных наборов кошельков, быстрое переключение между ними
- **Протоколы** — учёт каждого проекта: депозит, баланс, потрачено, выведено, поинты, $/point, статус
- **Недельные снапшоты** — разбивайте данные протокола по неделям и отслеживайте прогресс во времени
- **Кошельки** — управляйте адресами между протоколами, добавляйте метки, массово импортируйте из таблиц
- **Импорт** — вставляйте данные кошельков из Google Sheets в любой протокол или недельный снапшот
- **Экспорт** — экспорт всех данных в Excel в один клик
- **Perp** — live-позиции из HyperLiquid, Nado, Extended, Pacifica; группировка по аккаунтам с бейджами P&L, Margin Ratio и Account Leverage для каждого аккаунта
- **Telegram-бот** — алерты по ликвидации и периодические отчёты по позициям в Telegram; поддерживает команды `/report` и `/danger` из чата
- **Overview** — общий баланс, потрачено, чистая прибыль и $/point по всем протоколам на одном экране
- **Светлая/тёмная тема** — переключатель в сайдбаре, выбор сохраняется между запусками

---

## Скачать

Готовые сборки доступны в [Actions → latest build → Artifacts](../../actions):

- **FarmTrack-Windows** — распакуйте архив и запустите `FarmTrack.exe`
- **FarmTrack-Mac** — распакуйте архив и запустите `FarmTrack.app` (при первом запуске: правый клик → Open)

Python не требуется.

---

## Запуск из исходников

### 1. Клонировать

```bash
git clone https://github.com/DontFoldBB/farmtrack.git
cd farmtrack
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Запустить

```bash
python main.py
```

Приложение откроется как нативное desktop-окно. При первом запуске создайте профиль, чтобы начать работу.

---

## Стек

| Слой | Технологии |
|---|---|
| Backend | Python 3.10+, Flask |
| Frontend | Vanilla JS + HTML/CSS (OpenCode design system, light + dark) |
| Desktop | pywebview (нативное окно, браузер не нужен) |
| Database | SQLite (один `.db` файл на профиль) |
| Export | openpyxl |
| Tests | pytest (255 tests) |

---

## Структура проекта

```
farmtrack/
├── main.py           # Точка входа — запускает Flask + открывает webview-окно
├── app.py            # Flask routes / REST API
├── database.py       # SQLite-логика, все операции с БД
├── telegram_bot.py   # Telegram-бот — алерты, отчёты, polling команд
├── requirements.txt  # Python-зависимости
├── tests/
│   ├── test_database.py    # Операции БД (191 тест)
│   ├── test_app.py         # Flask routes
│   └── test_migrations.py # Безопасность миграций схемы
└── templates/
    ├── index.html    # Основной UI приложения (single-page)
    └── profiles.html # Экран выбора профиля
```

Данные хранятся в `data/<profile-name>.db` — файл создаётся автоматически и не отслеживается git.

---

## Запуск тестов

```bash
pytest tests/
```

Каждый тест получает собственную изолированную in-memory базу данных: нет общего состояния и ручной очистки. Миграционные тесты проверяют, что существующие строки переживают обновления схемы.

---

## Руководство по использованию

### 1. Создайте профиль
При первом запуске вы увидите экран профилей. Создайте профиль — каждый профиль получает собственную изолированную базу данных. Переключаться между профилями можно в любой момент через **Switch Profile** в сайдбаре.

### 2. Добавьте протоколы
Перейдите в **Protocols** и добавьте каждый проект, который фармите. Заполняйте депозит, баланс, потрачено, выведено и поинты по мере работы. Укажите статус (active / done / pending) и оценку $/point.

### 3. Отслеживайте кошельки
В **Wallets** добавляйте свои адреса и привязывайте их к протоколам. Можно массово импортировать пары кошелёк-протокол, вставив таблицу из Google Sheets.

### 4. Недельные снапшоты
Внутри любого протокола переключитесь на вкладку **Weekly**, чтобы логировать данные по неделям — это удобно для отслеживания прогресса во времени или сравнения эпох.

### 5. Live perp-позиции
В **Perp** добавьте аккаунты HyperLiquid, Nado, Extended или Pacifica. Позиции обновляются при каждом открытии вкладки. Аккаунты Pacifica показывают бейджи Margin Ratio и Account Leverage для каждого аккаунта.

### 6. Telegram-уведомления
Перейдите в **Telegram** в сайдбаре. Создайте бота через [@BotFather](https://t.me/BotFather), вставьте токен и ваш chat ID, настройте порог алерта ликвидации и интервал отчётов, затем включите бота и нажмите Save.

**Команды, которые можно отправлять боту:**
- `/report` — полный отчёт по позициям со всех аккаунтов и бирж
- `/danger` — только позиции ниже порога расстояния до ликвидации

> **Примечание:** бот работает внутри процесса FarmTrack — он активен только пока приложение открыто. Если закрыть окно, уведомления остановятся до следующего запуска.

### 7. Overview
**Overview** агрегирует общий баланс, потрачено, чистую прибыль и $/point по всем протоколам активного профиля.

### 8. Экспорт
Нажмите **Export Excel** в любой момент, чтобы скачать все данные в Excel-файл.

---

## Заметки

- Все данные локальные — ничего никуда не отправляется, кроме получения live-цен из публичных API бирж (без авторизации)
- Адреса кошельков никогда не отправляются и не логируются
- Папка `data/` находится в `.gitignore` — ваши базы данных не попадут в коммит случайно, если вы форкнете проект
- **API-ключи (Extended exchange) хранятся открытым текстом внутри локальной SQLite-базы.** База не зашифрована. Не используйте FarmTrack на общем компьютере или в среде, где другие люди имеют доступ к файловой системе.

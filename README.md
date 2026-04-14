# hh-career-ops

Инструмент для поиска работы на hh.ru с ИИ-оценкой вакансий через Claude Code.

Ищет вакансии → оценивает каждую по 10 критериям (A–F грейд) → помогает откликнуться с персонализированным письмом.

## Возможности

- Поиск вакансий через официальный hh.ru API или Playwright-парсер (без ключей)
- Автоматическая оценка Claude по 10 критериям с учётом вашего профиля
- Анализ рыночных зарплат: медиана, перцентили, разбивка по опыту и формату
- Интерактивный дашборд с историей оценённых вакансий
- Отклик с автогенерацией сопроводительного письма

## Быстрый старт

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Установить браузер (для scraper-режима)
playwright install chromium

# 3. Заполнить профиль соискателя
nano data/profile.yaml

# 4. Скопировать и настроить конфиг
cp config.yaml.example config.yaml   # если нет своего config.yaml
nano config.yaml                      # выбрать backend, указать регион и зарплату
```

Дальнейшая работа ведётся через Claude Code (команды `/search`, `/dashboard` и т.д.).

## Конфигурация

Скопируйте `config.yaml.example` → `config.yaml` и заполните:

```yaml
backend: scraper   # "scraper" (без ключей) или "api" (OAuth2)

search:
  area: [1]         # 1=Москва, 2=СПб, 113=Россия
  salary_from: 150000
  schedule: [remote, flexible, fullDay]

evaluation:
  min_score_to_apply: 3.5   # порог для предложения откликнуться
```

> `config.yaml` добавлен в `.gitignore` — токены не попадут в репозиторий.

### Бэкенды

| Значение | Описание |
|----------|----------|
| `scraper` | Playwright-парсинг hh.ru. **Не требует API ключей.** Рекомендуется. |
| `api` | Официальный REST API. Требует регистрации на [dev.hh.ru](https://dev.hh.ru) (только для организаций). |

#### Авторизация для API-режима

```bash
python -m src.api.auth   # откроет браузер, сохранит токены в config.yaml
```

## Профиль соискателя

`data/profile.yaml` — главный файл настройки. Claude использует его для оценки соответствия каждой вакансии.

```yaml
personal:
  target_role: "Backend Developer"
  experience_years: 5

skills:
  primary: [Python, FastAPI, PostgreSQL]
  secondary: [Docker, Redis, Kubernetes]

salary:
  min: 150000
  target: 200000

priorities:
  remote_work: high      # high / medium / low — влияет на веса критериев
  salary: high
  company_stability: medium

dealbreakers:
  - "без опыта"
  - "стажёр"
```

## Команды Claude Code

| Команда | Описание |
|---------|----------|
| `/search <запрос>` | Поиск и оценка вакансий |
| `/evaluate <id или url>` | Детальная оценка одной вакансии |
| `/apply <id или url>` | Откликнуться (с подтверждением) |
| `/dashboard` | Статистика и список оценённых вакансий |
| `/salary <запрос>` | Анализ рыночных зарплат |
| `/salary <запрос> --trend` | Динамика зарплат по снапшотам |

Примеры:

```
/search директор по ИТ
/salary CIO Москва
/dashboard
/evaluate 123456789
```

## Система оценки

Каждая вакансия оценивается по 10 критериям (1.0–5.0), веса автоматически регулируются через `priorities` в профиле:

| Критерий | Базовый вес |
|----------|-------------|
| Соответствие навыков | 25% |
| Зарплата | 20% |
| Формат работы (удалёнка) | 15% |
| Стабильность компании | 10% |
| Стек технологий | 10% |
| Карьерный рост | 7% |
| ДМС и льготы | 5% |
| Локация | 4% |
| Соответствие опыта | 3% |
| Тестовое задание | 1% |

Итоговый грейд: **A** (≥4.5) / **B** (≥3.5) / **C** (≥2.5) / **D** (≥1.5) / **F** (<1.5)

## Структура проекта

```
hh-career-ops/
├── config.yaml          # локальный конфиг (в .gitignore)
├── data/
│   ├── profile.yaml     # профиль соискателя
│   └── vacancies.db     # SQLite с историей оценок
├── src/
│   ├── api/
│   │   ├── base.py      # абстрактный интерфейс бэкендов
│   │   ├── auth.py      # OAuth2 авторизация hh.ru
│   │   ├── client.py    # HTTP-клиент
│   │   ├── scraper.py   # Playwright-парсер
│   │   ├── vacancies.py # API-бэкенд
│   │   └── negotiations.py  # отклики
│   ├── core/
│   │   ├── evaluator.py     # цикл поиск → оценка → сохранение
│   │   ├── scorer.py        # 10 критериев и промпт для Claude
│   │   ├── salary_analysis.py
│   │   └── db.py
│   └── ui/
│       ├── dashboard.py
│       └── salary_report.py
└── .claude/commands/    # команды Claude Code (/search, /apply и др.)
```

## Зависимости

- Python 3.11+
- [Claude Code](https://claude.ai/code) — для оценки вакансий
- `httpx`, `pyyaml`, `rich` — базовые
- `playwright`, `beautifulsoup4` — для scraper-режима

# hh-career-ops — инструкции для Claude

Ты — умный ассистент по поиску работы для российского рынка через hh.ru.

## Контекст проекта

Этот инструмент помогает соискателю:
1. Искать вакансии на hh.ru (через API или парсинг — настраивается)
2. Оценивать их по 10 критериям (A-F грейд) через Claude Code CLI
3. Управлять откликами с персонализированными письмами

## Бэкенды (переключаются в config.yaml → `backend`)

| Значение | Описание |
|----------|----------|
| `scraper` | Playwright парсинг hh.ru. **Не требует API ключей.** Используется по умолчанию. |
| `api`     | Официальный hh.ru REST API. Требует регистрации на dev.hh.ru (только для организаций). |

## Ключевые файлы

- `data/profile.yaml` — профиль соискателя (навыки, зарплата, приоритеты)
- `config.yaml` — выбор бэкенда, OAuth2 токены, параметры поиска
- `data/vacancies.db` — SQLite база с вакансиями и оценками
- `src/api/base.py` — фабрика бэкендов (`get_backend()`)
- `src/api/scraper.py` — Playwright парсер
- `src/api/vacancies.py` — API клиент
- `src/core/evaluator.py` — оценка через claude CLI
- `src/core/scorer.py` — 10 критериев и промпт для оценки

## Правила

1. **НИКОГДА** не отправляй отклик на вакансию без явного "да" от пользователя
2. Всегда показывай dry_run перед реальной отправкой
3. Если вакансия получила грейд D или F — предупреди и спроси дважды
4. Не сохраняй токены в логах и выводе
5. При captcha в scraper режиме — браузер откроется в видимом режиме для ручного прохождения

## Первый запуск (scraper режим — рекомендуется)

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Установить браузер (один раз)
playwright install chromium

# 3. Заполнить профиль соискателя
nano data/profile.yaml

# 4. Найти и оценить вакансии
# В Claude Code: /search Python разработчик

# 5. Посмотреть результаты
# В Claude Code: /dashboard
# Или напрямую:   python -m src.ui.dashboard
```

## Первый запуск (api режим)

```bash
# Дополнительно к шагам выше:
# - Установить backend: "api" в config.yaml
# - Зарегистрировать приложение на dev.hh.ru
# - Вписать client_id и client_secret в config.yaml
# - Авторизоваться: python -m src.api.auth
```

## Команды (skills)

| Команда | Описание |
|---------|----------|
| `/search <запрос>` | Поиск и оценка вакансий |
| `/evaluate <id или url>` | Детальная оценка одной вакансии |
| `/apply <id или url>` | Откликнуться (с подтверждением) |
| `/dashboard` | Статистика и список вакансий |
| `/salary <запрос>` | Анализ рыночных зарплат (медиана, перцентили, разбивка) |
| `/salary <запрос> --trend` | Динамика зарплат по снапшотам |

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (90-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk vitest run          # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%)
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->
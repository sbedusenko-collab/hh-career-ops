# Отклик на вакансию

Отправь отклик на вакансию с персонализированным сопроводительным письмом.

## Инструкция

1. Получи ID вакансии из аргумента.

2. Загрузи данные вакансии и профиль:

```python
from src.api.vacancies import VacancySearch
from src.core.evaluator import load_profile
searcher = VacancySearch()
vacancy = searcher.get_detail("VACANCY_ID")
profile = load_profile()
```

3. **ОБЯЗАТЕЛЬНО** проверь оценку вакансии в БД. Если оценка < 3.5 — предупреди пользователя и спроси подтверждение.

4. Сгенерируй сопроводительное письмо на основе шаблона из `profile.yaml`:
   - Используй реальное название вакансии и компании
   - В `ai_generated_body` напиши 2-3 предложения о релевантном опыте
   - Упомяни 2-3 конкретных навыка из требований вакансии
   - Тон: профессиональный, конкретный, без воды

5. Покажи письмо пользователю и **спроси подтверждение**:
   ```
   📋 СОПРОВОДИТЕЛЬНОЕ ПИСЬМО:
   ─────────────────────────────
   [текст письма]
   ─────────────────────────────
   Отправить отклик? (да/нет)
   ```

6. Только после "да" — отправь:

```python
from src.api.negotiations import NegotiationAPI
from src.core.db import VacancyDB
api = NegotiationAPI()
resume_id = profile["resume_id"]
result = api.apply(vacancy.id, resume_id, message=cover_letter)
db = VacancyDB()
db.save_application(vacancy.id, resume_id, cover_letter)
```

7. Подтверди успешную отправку.

## Важно
- НИКОГДА не отправляй отклик без явного подтверждения "да"
- Используй dry_run=True для проверки перед отправкой

## Пример использования

```
/apply 12345678
/apply https://hh.ru/vacancy/12345678
```

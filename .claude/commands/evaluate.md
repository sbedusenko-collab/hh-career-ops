# Оценка конкретной вакансии

Детально оцени вакансию по URL или ID.

## Инструкция

1. Определи ID вакансии из аргумента (URL или числовой ID).
   - Из URL `https://hh.ru/vacancy/12345678` → ID `12345678`
   - Числовой аргумент используй напрямую

2. Загрузи детали вакансии:

```python
from src.api.vacancies import VacancySearch
from src.core.evaluator import evaluate_vacancy, load_profile
from src.api.client import HHClient
import anthropic

client = HHClient()
searcher = VacancySearch(client)
vacancy = searcher.get_detail("VACANCY_ID")
profile = load_profile()
claude = anthropic.Anthropic()
result = evaluate_vacancy(vacancy, profile, claude)
```

3. Покажи детальный отчёт по всем 10 критериям в формате:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ВАКАНСИЯ: [Название] @ [Компания]
ИТОГ: [Оценка]/5.0  [Грейд]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Критерий            Вес    Оценка  Грейд
──────────────────────────────────────────
Соответствие навык  25%    4.2     B
Зарплата            20%    3.0     C
...

ВЫВОД: [summary]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

4. В конце спроси: "Хочешь откликнуться на эту вакансию? (да/нет)"

## Пример использования

```
/evaluate https://hh.ru/vacancy/12345678
/evaluate 12345678
```

"""
10 критериев оценки вакансии под российский рынок.
Веса настраиваются через profile.yaml (priorities).
"""

from dataclasses import dataclass

from src.api.vacancies import Vacancy

# Буква → числовая оценка
GRADE_MAP = {"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "F": 1.0}

# Базовые веса (сумма = 1.0)
DEFAULT_WEIGHTS = {
    "skills_match":       0.25,
    "salary":             0.20,
    "remote":             0.15,
    "company_stability":  0.10,
    "tech_stack":         0.10,
    "career_growth":      0.07,
    "dms_benefits":       0.05,
    "location":           0.04,
    "experience_fit":     0.03,
    "test_task":          0.01,
}

# Как приоритеты из profile.yaml меняют веса
PRIORITY_MULTIPLIERS = {"high": 1.4, "medium": 1.0, "low": 0.6}


@dataclass
class CriterionScore:
    name: str
    weight: float
    score: float      # 1.0–5.0
    grade: str        # A/B/C/D/F
    reasoning: str


@dataclass
class EvaluationResult:
    vacancy_id: str
    title: str
    company: str
    total_score: float    # взвешенная сумма, 1.0–5.0
    grade: str            # итоговая буква
    criteria: list[CriterionScore]
    summary: str          # короткий вывод
    dealbreaker_hit: bool
    dealbreaker_reason: str = ""

    def should_apply(self, min_score: float = 3.5) -> bool:
        return not self.dealbreaker_hit and self.total_score >= min_score


def score_to_grade(score: float) -> str:
    if score >= 4.5:
        return "A"
    if score >= 3.5:
        return "B"
    if score >= 2.5:
        return "C"
    if score >= 1.5:
        return "D"
    return "F"


def adjust_weights(base: dict, priorities: dict) -> dict:
    """Масштабирует веса согласно приоритетам из профиля."""
    mapping = {
        "remote_work":        "remote",
        "salary":             "salary",
        "tech_stack":         "tech_stack",
        "company_stability":  "company_stability",
        "career_growth":      "career_growth",
        "dms":                "dms_benefits",
    }
    weights = dict(base)
    for prio_key, criterion_key in mapping.items():
        level = priorities.get(prio_key, "medium")
        weights[criterion_key] *= PRIORITY_MULTIPLIERS.get(level, 1.0)

    # Нормализуем, чтобы сумма = 1.0
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def build_scoring_prompt(vacancy: Vacancy, profile: dict) -> str:
    """Формирует промпт для Claude для оценки вакансии."""
    salary_text = vacancy.salary.display() if vacancy.salary else "не указана"
    skills_text = ", ".join(vacancy.key_skills) if vacancy.key_skills else "не указаны"

    primary_skills = ", ".join(profile.get("skills", {}).get("primary", []))
    secondary_skills = ", ".join(profile.get("skills", {}).get("secondary", []))
    salary_min = profile.get("salary", {}).get("min", 0)
    salary_target = profile.get("salary", {}).get("target", 0)

    return f"""Оцени вакансию для соискателя. Отвечай ТОЛЬКО валидным JSON без markdown.

## ВАКАНСИЯ
Название: {vacancy.title}
Компания: {vacancy.company}
Город: {vacancy.area}
Зарплата: {salary_text}
Занятость: {vacancy.employment}
График: {vacancy.schedule}
Опыт: {vacancy.experience}
Навыки: {skills_text}
Сопроводительное письмо обязательно: {vacancy.response_letter_required}
Тестовое задание: {vacancy.has_test}

Описание вакансии:
{vacancy.description[:3000]}

## ПРОФИЛЬ СОИСКАТЕЛЯ
Должность: {profile.get('personal', {}).get('target_role', '')}
Опыт: {profile.get('personal', {}).get('experience_years', '')} лет
Ключевые навыки: {primary_skills}
Дополнительные навыки: {secondary_skills}
Зарплата мин: {salary_min} руб., целевая: {salary_target} руб.
Удалёнка предпочтительна: {profile.get('personal', {}).get('remote_preferred', False)}
Готов к переезду: {profile.get('personal', {}).get('relocation', False)}
Стоп-слова: {", ".join(profile.get("dealbreakers", []))}

## ЗАДАЧА
Оцени по 10 критериям, каждый от 1.0 до 5.0:
1. skills_match — соответствие навыков требованиям
2. salary — соответствие зарплаты ожиданиям (учти gross/net разницу ~13%)
3. remote — формат работы (удалёнка/гибрид vs офис)
4. company_stability — стабильность компании (если известна)
5. tech_stack — привлекательность стека технологий
6. career_growth — возможности роста и развития
7. dms_benefits — соц. пакет, ДМС, бонусы
8. location — локация, удобство офиса (если релевантно)
9. experience_fit — соответствие требований к опыту реальному уровню
10. test_task — наличие/отсутствие тестового задания (нет теста = лучше)

Верни JSON строго в этом формате:
{{
  "criteria": {{
    "skills_match":      {{"score": 4.2, "grade": "B", "reasoning": "..."}},
    "salary":            {{"score": 3.0, "grade": "C", "reasoning": "..."}},
    "remote":            {{"score": 5.0, "grade": "A", "reasoning": "..."}},
    "company_stability": {{"score": 3.5, "grade": "B", "reasoning": "..."}},
    "tech_stack":        {{"score": 4.0, "grade": "B", "reasoning": "..."}},
    "career_growth":     {{"score": 3.0, "grade": "C", "reasoning": "..."}},
    "dms_benefits":      {{"score": 3.0, "grade": "C", "reasoning": "..."}},
    "location":          {{"score": 4.0, "grade": "B", "reasoning": "..."}},
    "experience_fit":    {{"score": 4.5, "grade": "A", "reasoning": "..."}},
    "test_task":         {{"score": 4.0, "grade": "B", "reasoning": "..."}}
  }},
  "dealbreaker": false,
  "dealbreaker_reason": "",
  "summary": "Краткий вывод на 2-3 предложения почему стоит/не стоит откликаться"
}}"""

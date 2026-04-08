"""
Оценка вакансий через Claude Code CLI (без отдельного API ключа).

Использует `claude -p <prompt>` — тот же Claude Code, что запущен у пользователя.
"""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml

from src.api.vacancies import Vacancy, VacancySearch
from src.core.db import VacancyDB
from src.core.scorer import (
    CriterionScore,
    DEFAULT_WEIGHTS,
    EvaluationResult,
    adjust_weights,
    build_scoring_prompt,
    score_to_grade,
)


def load_profile(path: str = "data/profile.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _call_claude(prompt: str) -> str:
    """
    Вызывает Claude Code CLI: `claude -p "<prompt>"`.
    Не требует ANTHROPIC_API_KEY — использует авторизацию Claude Code.
    """
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr.strip()}")
    return result.stdout.strip()


def evaluate_vacancy(vacancy: Vacancy, profile: dict) -> EvaluationResult:
    """Оценивает одну вакансию через Claude Code CLI."""
    prompt = build_scoring_prompt(vacancy, profile)
    raw = _call_claude(prompt)

    # Убираем markdown-обёртку если есть
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            if part.startswith("json"):
                raw = part[4:].strip()
                break
            if part.strip().startswith("{"):
                raw = part.strip()
                break

    data = json.loads(raw)

    priorities = profile.get("priorities", {})
    weights = adjust_weights(DEFAULT_WEIGHTS, priorities)

    criteria_scores = []
    total = 0.0
    for key, weight in weights.items():
        c = data["criteria"].get(key, {})
        score = float(c.get("score", 3.0))
        total += score * weight
        criteria_scores.append(CriterionScore(
            name=key,
            weight=weight,
            score=score,
            grade=c.get("grade", score_to_grade(score)),
            reasoning=c.get("reasoning", ""),
        ))

    total = round(total, 2)

    return EvaluationResult(
        vacancy_id=vacancy.id,
        title=vacancy.title,
        company=vacancy.company,
        total_score=total,
        grade=score_to_grade(total),
        criteria=criteria_scores,
        summary=data.get("summary", ""),
        dealbreaker_hit=data.get("dealbreaker", False),
        dealbreaker_reason=data.get("dealbreaker_reason", ""),
    )


class BatchEvaluator:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.profile = load_profile(self.config["paths"]["profile"])
        self.db = VacancyDB(self.config["paths"]["db"])
        self.searcher = VacancySearch()
        self.batch_size = self.config["evaluation"].get("batch_size", 5)
        self.min_score = self.config["evaluation"].get("min_score_to_save", 2.0)

    def run(self, query: str) -> list[EvaluationResult]:
        """
        Полный цикл: поиск → детали → оценка через claude CLI → сохранение.

        Args:
            query: Поисковый запрос, например "Python разработчик"

        Returns:
            Список результатов оценки, отсортированный по убыванию оценки
        """
        print(f"Ищу вакансии: «{query}»...")
        vacancies = list(self.searcher.search(query))
        print(f"Найдено: {len(vacancies)} вакансий")

        # Фильтруем уже оценённые
        new_vacancies = [v for v in vacancies if not self.db.exists(v.id)]
        print(f"Новых для оценки: {len(new_vacancies)}")

        # Подгружаем детальное описание
        print("Загружаю описания...")
        detailed = []
        for v in new_vacancies:
            try:
                detailed.append(self.searcher.get_detail(v.id))
            except Exception as e:
                print(f"  Пропускаю {v.id}: {e}")

        # Параллельная оценка (осторожно с rate limits claude CLI)
        results = []
        with ThreadPoolExecutor(max_workers=min(self.batch_size, 3)) as pool:
            futures = {
                pool.submit(evaluate_vacancy, v, self.profile): v
                for v in detailed
            }
            for future in as_completed(futures):
                v = futures[future]
                try:
                    result = future.result()
                    print(f"  [{result.grade}] {result.total_score:.1f} — {result.title} @ {result.company}")

                    if result.total_score >= self.min_score:
                        self.db.save(result, v)
                        results.append(result)
                except Exception as e:
                    print(f"  Ошибка оценки {v.id}: {e}")

        results.sort(key=lambda r: r.total_score, reverse=True)
        print(f"\nСохранено {len(results)} вакансий с оценкой >= {self.min_score}")
        return results

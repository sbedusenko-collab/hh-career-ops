"""
Анализ рыночных зарплат по вакансиям hh.ru.

Собирает выборку вакансий, извлекает зарплатные данные,
считает статистику и сохраняет снапшот для отслеживания динамики.
"""

import statistics
from dataclasses import dataclass, field

import yaml

from src.api.base import get_backend
from src.api.vacancies import Salary, Vacancy
from src.core.db import VacancyDB

# Коэффициент gross → net (НДФЛ 13%)
NET_FACTOR = 0.87

EXPERIENCE_LABELS = {
    "noExperience":  "Без опыта",
    "between1And3":  "1–3 года",
    "between3And6":  "3–6 лет",
    "moreThan6":     "6+ лет",
    "":              "Не указан",
}

SCHEDULE_LABELS = {
    "remote":   "Удалённо",
    "flexible": "Гибкий",
    "fullDay":  "Офис",
    "shift":    "Сменный",
    "":         "Не указан",
}


@dataclass
class SalaryPoint:
    vacancy_id: str
    title: str
    company: str
    salary_net: int       # всегда net для сравнимости
    salary_raw: Salary
    experience: str
    schedule: str
    area: str


@dataclass
class GroupStats:
    label: str
    count: int
    median: int
    p25: int
    p75: int
    mean: int
    min_: int
    max_: int


@dataclass
class SalaryReport:
    query: str
    total_found: int
    sample_size: int       # вакансий с зарплатой
    coverage_pct: float    # % вакансий с зарплатой

    # Общая статистика (net руб.)
    salary_min: int
    salary_p25: int
    salary_median: int
    salary_p75: int
    salary_max: int
    salary_mean: int
    iqr: int               # межквартильный размах

    # Разбивка по опыту и графику
    by_experience: list[GroupStats] = field(default_factory=list)
    by_schedule:   list[GroupStats] = field(default_factory=list)

    # Топ компаний по зарплате
    top_companies: list[dict] = field(default_factory=list)

    # Гистограмма (для визуализации в терминале)
    histogram: list[tuple[str, int]] = field(default_factory=list)

    points: list[SalaryPoint] = field(default_factory=list, repr=False)


def _to_net(salary: Salary) -> int | None:
    """Возвращает среднее значение зарплаты в net рублях."""
    vals = []
    if salary.from_:
        vals.append(salary.from_)
    if salary.to:
        vals.append(salary.to)
    if not vals:
        return None

    mid = sum(vals) / len(vals)

    # Конвертация валют (приблизительно)
    rate = {"RUR": 1, "USD": 90, "EUR": 98, "KZT": 0.2}.get(salary.currency, 1)
    mid_rur = mid * rate

    return int(mid_rur * NET_FACTOR if salary.gross else mid_rur)


def _percentile(data: list[int], p: float) -> int:
    if not data:
        return 0
    sorted_data = sorted(data)
    idx = (len(sorted_data) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_data) - 1)
    return int(sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (idx - lo))


def _group_stats(label: str, points: list[SalaryPoint]) -> GroupStats | None:
    if len(points) < 3:
        return None
    vals = [p.salary_net for p in points]
    return GroupStats(
        label=label,
        count=len(vals),
        median=_percentile(vals, 50),
        p25=_percentile(vals, 25),
        p75=_percentile(vals, 75),
        mean=int(statistics.mean(vals)),
        min_=min(vals),
        max_=max(vals),
    )


def _build_histogram(vals: list[int], buckets: int = 8) -> list[tuple[str, int]]:
    """Строит гистограмму: список (метка диапазона, количество)."""
    if not vals:
        return []
    lo, hi = min(vals), max(vals)
    if lo == hi:
        return [(f"{lo // 1000}k", len(vals))]
    step = (hi - lo) / buckets
    result = []
    for i in range(buckets):
        low  = lo + step * i
        high = lo + step * (i + 1)
        cnt  = sum(1 for v in vals if low <= v < high)
        if i == buckets - 1:
            cnt += sum(1 for v in vals if v == hi)
        label = f"{int(low // 1000)}–{int(high // 1000)}k"
        result.append((label, cnt))
    return result


class SalaryAnalyzer:
    def __init__(self, config_path: str = "config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.db = VacancyDB(self.config["paths"]["db"])
        self.backend = get_backend(config_path)
        self.config_path = config_path

    def analyze(
        self,
        query: str,
        max_pages: int = 5,
        save_snapshot: bool = True,
    ) -> SalaryReport:
        """
        Собирает вакансии по запросу и строит зарплатный отчёт.

        Args:
            query:         Поисковый запрос, напр. «Python разработчик»
            max_pages:     Максимум страниц для сбора (≈50 вакансий/страница)
            save_snapshot: Сохранить снапшот в БД для динамики

        Returns:
            SalaryReport со статистикой
        """
        print(f"Сбор вакансий для анализа зарплат: «{query}»...")

        all_vacancies: list[Vacancy] = []
        count = 0
        for v in self.backend.search(query, self.config_path):
            all_vacancies.append(v)
            count += 1
            if count >= max_pages * 50:
                break

        print(f"Собрано вакансий: {len(all_vacancies)}")

        # Извлекаем зарплатные точки
        points: list[SalaryPoint] = []
        for v in all_vacancies:
            if not v.salary:
                continue
            net = _to_net(v.salary)
            if not net or net < 10_000 or net > 5_000_000:  # фильтр аномалий
                continue
            points.append(SalaryPoint(
                vacancy_id=v.id,
                title=v.title,
                company=v.company,
                salary_net=net,
                salary_raw=v.salary,
                experience=v.experience or "",
                schedule=v.schedule or "",
                area=v.area,
            ))

        total = len(all_vacancies)
        sample = len(points)
        coverage = round(sample / total * 100, 1) if total else 0
        print(f"С данными по зарплате: {sample} ({coverage}%)")

        if sample < 5:
            print("Недостаточно данных для анализа (нужно минимум 5 вакансий с зарплатой).")
            return SalaryReport(
                query=query, total_found=total, sample_size=0, coverage_pct=0,
                salary_min=0, salary_p25=0, salary_median=0, salary_p75=0,
                salary_max=0, salary_mean=0, iqr=0, points=[],
            )

        vals = [p.salary_net for p in points]
        p25    = _percentile(vals, 25)
        median = _percentile(vals, 50)
        p75    = _percentile(vals, 75)

        # Разбивка по опыту
        by_exp = []
        for code, label in EXPERIENCE_LABELS.items():
            group = [p for p in points if p.experience == code]
            gs = _group_stats(label, group)
            if gs:
                by_exp.append(gs)
        by_exp.sort(key=lambda g: g.median)

        # Разбивка по графику
        by_sched = []
        for code, label in SCHEDULE_LABELS.items():
            group = [p for p in points if p.schedule == code]
            gs = _group_stats(label, group)
            if gs:
                by_sched.append(gs)
        by_sched.sort(key=lambda g: g.median, reverse=True)

        # Топ-10 компаний по медианной зарплате (мин. 2 вакансии)
        companies: dict[str, list[int]] = {}
        for p in points:
            companies.setdefault(p.company, []).append(p.salary_net)
        top_companies = sorted(
            [
                {"company": name, "median": _percentile(salaries, 50),
                 "count": len(salaries), "max": max(salaries)}
                for name, salaries in companies.items()
                if len(salaries) >= 2
            ],
            key=lambda x: x["median"],
            reverse=True,
        )[:10]

        report = SalaryReport(
            query=query,
            total_found=total,
            sample_size=sample,
            coverage_pct=coverage,
            salary_min=min(vals),
            salary_p25=p25,
            salary_median=median,
            salary_p75=p75,
            salary_max=max(vals),
            salary_mean=int(statistics.mean(vals)),
            iqr=p75 - p25,
            by_experience=by_exp,
            by_schedule=by_sched,
            top_companies=top_companies,
            histogram=_build_histogram(vals),
            points=points,
        )

        if save_snapshot:
            area = self.config.get("search", {}).get("area", [0])[0]
            self.db.save_salary_snapshot({
                "query":         query,
                "area":          area,
                "experience":    "all",
                "schedule":      "all",
                "sample_size":   sample,
                "total_found":   total,
                "salary_min":    report.salary_min,
                "salary_p25":    p25,
                "salary_median": median,
                "salary_p75":    p75,
                "salary_max":    report.salary_max,
                "salary_mean":   report.salary_mean,
                "gross":         False,  # всегда храним net
                "breakdown": {
                    "by_experience": [
                        {"label": g.label, "median": g.median, "count": g.count}
                        for g in by_exp
                    ],
                    "by_schedule": [
                        {"label": g.label, "median": g.median, "count": g.count}
                        for g in by_sched
                    ],
                },
            })
            print("Снапшот сохранён в БД.")

        return report

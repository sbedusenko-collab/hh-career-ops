"""
Поиск и получение деталей вакансий с hh.ru.
"""

from dataclasses import dataclass, field
from typing import Iterator

import yaml

from src.api.client import HHClient


@dataclass
class Salary:
    from_: int | None
    to: int | None
    currency: str
    gross: bool  # True = до вычета налогов

    def net_from(self) -> int | None:
        """Конвертирует gross → net (примерно, НДФЛ 13%)."""
        if self.from_ and self.gross:
            return int(self.from_ * 0.87)
        return self.from_

    def display(self) -> str:
        parts = []
        if self.from_:
            parts.append(f"от {self.from_:,}")
        if self.to:
            parts.append(f"до {self.to:,}")
        label = " ".join(parts) if parts else "не указана"
        gross_label = " (gross)" if self.gross else " (net)"
        return f"{label} {self.currency}{gross_label}"


@dataclass
class Vacancy:
    id: str
    title: str
    url: str
    company: str
    company_id: str
    area: str
    salary: Salary | None
    employment: str
    schedule: str
    published_at: str
    description: str = ""          # заполняется при детальном запросе
    key_skills: list[str] = field(default_factory=list)
    experience: str = ""
    response_letter_required: bool = False
    has_test: bool = False
    raw: dict = field(default_factory=dict, repr=False)


def _parse_salary(data: dict | None) -> Salary | None:
    if not data:
        return None
    return Salary(
        from_=data.get("from"),
        to=data.get("to"),
        currency=data.get("currency", "RUR"),
        gross=data.get("gross", True),
    )


def _parse_vacancy(data: dict) -> Vacancy:
    return Vacancy(
        id=str(data["id"]),
        title=data["name"],
        url=data.get("alternate_url", ""),
        company=data.get("employer", {}).get("name", ""),
        company_id=str(data.get("employer", {}).get("id", "")),
        area=data.get("area", {}).get("name", ""),
        salary=_parse_salary(data.get("salary")),
        employment=data.get("employment", {}).get("id", ""),
        schedule=data.get("schedule", {}).get("id", ""),
        published_at=data.get("published_at", ""),
        experience=data.get("experience", {}).get("id", ""),
        response_letter_required=data.get("response_letter_required", False),
        has_test=bool(data.get("test")),
        raw=data,
    )


class VacancySearch:  # реализует VacancyBackend (импорт избегаем для предотвращения циклов)
    def __init__(self, client: HHClient | None = None):
        self.client = client or HHClient()

    def search(self, query: str, config_path: str = "config.yaml") -> Iterator[Vacancy]:
        """Поиск вакансий по запросу с параметрами из config.yaml."""
        with open(config_path) as f:
            config = yaml.safe_load(f)
        search_cfg = config["search"]

        params: dict = {
            "text": query,
            "per_page": search_cfg.get("per_page", 50),
            "search_period": search_cfg.get("search_period", 7),
            "only_with_salary": search_cfg.get("only_with_salary", False),
        }

        if search_cfg.get("salary_from"):
            params["salary"] = search_cfg["salary_from"]

        # Множественные значения: area, employment, schedule
        areas = search_cfg.get("area", [])
        if areas:
            params["area"] = areas[0]  # API принимает один area за раз

        employment = search_cfg.get("employment", [])
        if employment:
            params["employment"] = employment[0]

        page = 0
        while True:
            params["page"] = page
            data = self.client.get("/vacancies", params=params, auth=False)

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                yield _parse_vacancy(item)

            pages = data.get("pages", 1)
            page += 1
            if page >= pages:
                break

    def get_detail(self, vacancy_id: str) -> Vacancy:
        """Получает полные данные вакансии включая описание и навыки."""
        data = self.client.get(f"/vacancies/{vacancy_id}", auth=False)
        v = _parse_vacancy(data)
        v.description = data.get("description", "")
        v.key_skills = [s["name"] for s in data.get("key_skills", [])]
        return v

    def get_suitable_resumes(self, vacancy_id: str) -> list[dict]:
        """Возвращает резюме соискателя, подходящие для вакансии."""
        data = self.client.get(f"/vacancies/{vacancy_id}/suitable_resumes")
        return data.get("items", [])

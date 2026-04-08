"""
Абстрактный интерфейс для получения вакансий.
Оба бэкенда (API и scraper) реализуют этот протокол.
"""

from abc import ABC, abstractmethod
from typing import Iterator

from src.api.vacancies import Vacancy


class VacancyBackend(ABC):

    @abstractmethod
    def search(self, query: str, config_path: str = "config.yaml") -> Iterator[Vacancy]:
        """Поиск вакансий по запросу."""
        ...

    @abstractmethod
    def get_detail(self, vacancy_id: str) -> Vacancy:
        """Получить полные данные вакансии включая описание и навыки."""
        ...


def get_backend(config_path: str = "config.yaml") -> VacancyBackend:
    """
    Фабрика: возвращает нужный бэкенд согласно config.yaml.

    backend: api     → HH API (требует OAuth2)
    backend: scraper → Playwright парсер (без API ключей)
    """
    import yaml
    with open(config_path) as f:
        config = yaml.safe_load(f)

    backend = config.get("backend", "scraper")

    if backend == "api":
        from src.api.vacancies import VacancySearch
        return VacancySearch()
    elif backend == "scraper":
        from src.api.scraper import PlaywrightScraper
        return PlaywrightScraper()
    else:
        raise ValueError(f"Неизвестный бэкенд: '{backend}'. Допустимые значения: api, scraper")

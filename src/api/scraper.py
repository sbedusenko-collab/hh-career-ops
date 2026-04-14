"""
Playwright-парсер hh.ru — альтернатива официальному API.
Не требует регистрации, OAuth2 или API-ключей.

Установка браузера (один раз):
    playwright install chromium
"""

import re
import time
from typing import Iterator

import yaml
from playwright.sync_api import Page, sync_playwright

from src.api.base import VacancyBackend
from src.api.vacancies import Salary, Vacancy

BASE_URL = "https://hh.ru"

# Параметры чтобы не выглядеть как бот
VIEWPORT  = {"width": 1280, "height": 800}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ── Парсинг данных ─────────────────────────────────────────────────────────────

def _parse_salary_text(text: str | None) -> Salary | None:
    if not text:
        return None
    text = text.strip()
    gross = "до вычета" in text or "gross" in text.lower()
    cur = "RUR"
    if "€" in text or "EUR" in text:
        cur = "EUR"
    elif "$" in text or "USD" in text:
        cur = "USD"

    nums = re.findall(r"[\d\s]+", text)
    nums = [int(n.replace(" ", "").replace("\u00a0", "")) for n in nums if n.strip()]

    from_ = nums[0] if len(nums) >= 1 else None
    to    = nums[1] if len(nums) >= 2 else None

    if "от" in text and "до" not in text:
        to = None
    elif "до" in text and "от" not in text:
        from_, to = None, from_

    return Salary(from_=from_, to=to, currency=cur, gross=gross)


def _parse_card(card) -> Vacancy | None:
    """Парсит карточку вакансии из списка результатов поиска."""
    try:
        title_el = card.query_selector("[data-qa='serp-item__title']")
        if not title_el:
            return None
        title = title_el.inner_text().strip()

        link_el = card.query_selector("a[data-qa='serp-item__title']")
        url = link_el.get_attribute("href") if link_el else ""
        # Убираем UTM-метки
        url = url.split("?")[0] if url else ""
        vacancy_id = re.search(r"/vacancy/(\d+)", url)
        if not vacancy_id:
            return None
        vacancy_id = vacancy_id.group(1)

        company_el = card.query_selector("[data-qa='vacancy-serp__vacancy-employer']")
        company = company_el.inner_text().strip() if company_el else ""

        area_el = card.query_selector("[data-qa='vacancy-serp__vacancy-address']")
        area = area_el.inner_text().strip() if area_el else ""

        salary_el = card.query_selector("[data-qa='vacancy-serp__vacancy-compensation']")
        salary = _parse_salary_text(salary_el.inner_text() if salary_el else None)

        return Vacancy(
            id=vacancy_id,
            title=title,
            url=f"{BASE_URL}/vacancy/{vacancy_id}",
            company=company,
            company_id="",
            area=area,
            salary=salary,
            employment="",
            schedule="",
            published_at="",
        )
    except Exception:
        return None


def _parse_detail(page: Page, vacancy: Vacancy) -> Vacancy:
    """Загружает страницу вакансии и обогащает данными."""
    try:
        # Описание
        desc_el = page.query_selector("[data-qa='vacancy-description']")
        vacancy.description = desc_el.inner_text() if desc_el else ""

        # Навыки
        skills = page.query_selector_all("[data-qa='bloko-tag__text']")
        vacancy.key_skills = [s.inner_text().strip() for s in skills]

        # График и занятость
        conditions = page.query_selector_all(
            "[data-qa='vacancy-view-employment-mode'] p, "
            "[data-qa='vacancy-view-schedule'] p"
        )
        cond_texts = [c.inner_text().strip().lower() for c in conditions]

        schedule_map = {
            "удалённая работа": "remote",
            "гибкий график": "flexible",
            "полный день": "fullDay",
            "сменный график": "shift",
        }
        for text, code in schedule_map.items():
            if any(text in c for c in cond_texts):
                vacancy.schedule = code
                break

        employ_map = {"полная занятость": "full", "частичная занятость": "part"}
        for text, code in employ_map.items():
            if any(text in c for c in cond_texts):
                vacancy.employment = code
                break

        # Опыт
        exp_el = page.query_selector("[data-qa='vacancy-experience']")
        if exp_el:
            exp_text = exp_el.inner_text().lower()
            if "без опыта" in exp_text:
                vacancy.experience = "noExperience"
            elif "1" in exp_text:
                vacancy.experience = "between1And3"
            elif "3" in exp_text:
                vacancy.experience = "between3And6"
            elif "6" in exp_text:
                vacancy.experience = "moreThan6"

        # Зарплата (более точная со страницы деталей)
        salary_el = page.query_selector("[data-qa='vacancy-salary']")
        if salary_el and not vacancy.salary:
            vacancy.salary = _parse_salary_text(salary_el.inner_text())

        # Дата публикации
        date_el = page.query_selector("[data-qa='vacancy-creation-time']")
        if date_el:
            vacancy.published_at = date_el.get_attribute("datetime") or ""

        # Тестовое задание
        vacancy.has_test = bool(page.query_selector("[data-qa='test-task-link']"))

        # Сопроводительное письмо обязательно
        vacancy.response_letter_required = bool(
            page.query_selector("[data-qa='vacancy-response-letter-required']")
        )

    except Exception as e:
        print(f"  Предупреждение при парсинге деталей {vacancy.id}: {e}")

    return vacancy


# ── Бэкенд ────────────────────────────────────────────────────────────────────

class PlaywrightScraper(VacancyBackend):
    """
    Парсит hh.ru через headless Chromium.
    Вся сессия — один браузер, чтобы сохранять куки и не вызывать captcha.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw        = None
        self._browser   = None
        self._page: Page | None = None

    def _start(self):
        if self._browser:
            return
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        context       = self._browser.new_context(
            viewport=VIEWPORT,
            user_agent=USER_AGENT,
            locale="ru-RU",
        )
        self._page = context.new_page()
        # Принимаем куки при первом заходе
        self._page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)

    def _stop(self):
        if self._browser:
            self._browser.close()
            self._pw.stop()
            self._browser = None
            self._page    = None

    def search(self, query: str, config_path: str = "config.yaml") -> Iterator[Vacancy]:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        search_cfg = config["search"]

        areas = search_cfg.get("area", [1])
        area  = areas[0] if areas else 1

        salary_from   = search_cfg.get("salary_from", 0)
        search_period = search_cfg.get("search_period", 7)
        schedules     = search_cfg.get("schedule", [])

        self._start()
        page = 0

        while True:
            params = {
                "text":          query,
                "area":          area,
                "search_period": search_period,
                "page":          page,
            }
            if salary_from:
                params["salary"] = salary_from
            if schedules:
                params["schedule"] = schedules[0]

            qs  = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{BASE_URL}/search/vacancy?{qs}"

            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"  Таймаут на странице {page}, завершаю поиск: {e.__class__.__name__}")
                break
            time.sleep(1.5)  # пауза чтобы не триггерить captcha

            # Проверяем captcha
            if "captcha" in self._page.url or self._page.query_selector("[data-qa='captcha']"):
                print("  Обнаружена captcha. Переключаем в режим с браузером...")
                self._stop()
                self._browser = None
                self._start_visible()
                continue

            cards = self._page.query_selector_all("[data-qa='vacancy-serp__vacancy']")
            if not cards:
                break

            for card in cards:
                v = _parse_card(card)
                if v:
                    yield v

            # Проверяем наличие следующей страницы
            next_btn = self._page.query_selector("[data-qa='pager-next']")
            if not next_btn:
                break
            page += 1
            time.sleep(1)

        self._stop()

    def get_detail(self, vacancy_id: str) -> Vacancy:
        self._start()
        url = f"{BASE_URL}/vacancy/{vacancy_id}"
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)

        # Базовая вакансия (заголовок и компания со страницы деталей)
        title_el   = self._page.query_selector("[data-qa='vacancy-title']")
        company_el = self._page.query_selector("[data-qa='vacancy-company-name']")
        area_el    = self._page.query_selector("[data-qa='vacancy-view-location']")

        vacancy = Vacancy(
            id=vacancy_id,
            title=title_el.inner_text().strip() if title_el else "",
            url=url,
            company=company_el.inner_text().strip() if company_el else "",
            company_id="",
            area=area_el.inner_text().strip() if area_el else "",
            salary=None,
            employment="",
            schedule="",
            published_at="",
        )
        return _parse_detail(self._page, vacancy)

    def _start_visible(self):
        """Запускает видимый браузер — для ручного прохождения captcha."""
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=False)
        context       = self._browser.new_context(viewport=VIEWPORT, user_agent=USER_AGENT, locale="ru-RU")
        self._page    = context.new_page()
        self._page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        print("  Пройди captcha в браузере и нажми Enter в терминале...")
        input()

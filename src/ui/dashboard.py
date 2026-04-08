"""
Терминальный дашборд для hh-career-ops.

Запуск: python -m src.ui.dashboard
Выход:  q или Ctrl+C
"""

import json
import sqlite3
import subprocess
import sys
import webbrowser
from pathlib import Path

import yaml
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

console = Console()

GRADE_COLORS = {"A": "bold green", "B": "green", "C": "yellow", "D": "red", "F": "bold red"}
GRADE_EMOJI  = {"A": "★", "B": "◆", "C": "●", "D": "▲", "F": "✕"}


# ── Загрузка данных ────────────────────────────────────────────────────────────

def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def get_vacancies(db_path: str, min_grade: str = "F", limit: int = 100) -> list[dict]:
    grade_scores = {"A": 4.5, "B": 3.5, "C": 2.5, "D": 1.5, "F": 1.0}
    min_score = grade_scores.get(min_grade, 1.0)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT v.id, v.title, v.company, v.area, v.url,
               v.salary_from, v.salary_to, v.salary_cur, v.salary_gross,
               v.schedule, v.published_at, v.key_skills,
               e.total_score, e.grade, e.summary, e.dealbreaker, e.criteria,
               a.applied_at
        FROM vacancies v
        JOIN evaluations e ON v.id = e.vacancy_id
        LEFT JOIN applications a ON a.vacancy_id = v.id
        WHERE e.total_score >= ?
        ORDER BY e.total_score DESC
        LIMIT ?
    """, (min_score, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)
    total    = conn.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
    by_grade = dict(conn.execute("SELECT grade, COUNT(*) FROM evaluations GROUP BY grade").fetchall())
    applied  = conn.execute("SELECT COUNT(DISTINCT vacancy_id) FROM applications").fetchone()[0]
    conn.close()
    return {"total": total, "by_grade": by_grade, "applied": applied}


# ── Форматирование ─────────────────────────────────────────────────────────────

def fmt_salary(row: dict) -> str:
    if not row["salary_from"] and not row["salary_to"]:
        return "[dim]—[/dim]"
    parts = []
    if row["salary_from"]:
        parts.append(f"от {row['salary_from']:,}")
    if row["salary_to"]:
        parts.append(f"до {row['salary_to']:,}")
    cur  = row.get("salary_cur") or "RUR"
    gross = " gross" if row.get("salary_gross") else ""
    return " ".join(parts) + f" {cur}{gross}"


def fmt_schedule(s: str) -> str:
    return {"remote": "удалёнка", "flexible": "гибкий", "fullDay": "офис", "shift": "сменный"}.get(s, s)


def bar(count: int, total: int, width: int = 12) -> str:
    if not total:
        return " " * width
    filled = round(count / total * width)
    return "█" * filled + "░" * (width - filled)


# ── Виджеты ───────────────────────────────────────────────────────────────────

def make_stats_panel(stats: dict) -> Panel:
    by_grade = stats["by_grade"]
    total    = stats["total"] or 1

    lines = Text()
    lines.append(f"  Всего оценено:  {stats['total']}\n", style="bold")
    lines.append(f"  Откликов:       {stats['applied']}\n\n", style="bold")

    for grade in ["A", "B", "C", "D", "F"]:
        n     = by_grade.get(grade, 0)
        color = GRADE_COLORS[grade]
        emoji = GRADE_EMOJI[grade]
        b     = bar(n, total)
        lines.append(f"  {emoji} ", style=color)
        lines.append(f"{grade} ", style=f"bold {color}")
        lines.append(f"{b} ", style=color)
        lines.append(f"{n}\n", style="dim")

    return Panel(lines, title="[bold]Статистика[/bold]", border_style="blue", padding=(0, 1))


def make_vacancy_table(rows: list[dict], selected: int = 0) -> Table:
    t = Table(
        box=box.SIMPLE_HEAD,
        header_style="bold cyan",
        show_lines=False,
        expand=True,
    )
    t.add_column("#",        width=3,  justify="right")
    t.add_column("Грейд",   width=6,  justify="center")
    t.add_column("Оценка",  width=7,  justify="right")
    t.add_column("Компания", width=22, no_wrap=True)
    t.add_column("Должность", width=35, no_wrap=True)
    t.add_column("Зарплата", width=20)
    t.add_column("График",  width=10)
    t.add_column("Отклик",  width=8,  justify="center")

    for i, row in enumerate(rows):
        grade = row["grade"]
        color = GRADE_COLORS.get(grade, "white")
        emoji = GRADE_EMOJI.get(grade, "")
        style = "on grey23" if i == selected else ""
        applied_mark = "[green]✓[/green]" if row.get("applied_at") else ""

        t.add_row(
            str(i + 1),
            Text(f"{emoji} {grade}", style=f"bold {color}"),
            Text(f"{row['total_score']:.1f}", style=color),
            row["company"] or "—",
            row["title"],
            fmt_salary(row),
            fmt_schedule(row.get("schedule", "")),
            applied_mark,
            style=style,
        )

    return t


def make_detail_panel(row: dict) -> Panel:
    skills = []
    try:
        skills = json.loads(row.get("key_skills") or "[]")
    except Exception:
        pass

    criteria = []
    try:
        criteria = json.loads(row.get("criteria") or "[]")
    except Exception:
        pass

    lines = Text()
    lines.append(f"{row['title']}\n", style="bold white")
    lines.append(f"{row['company']}  ·  {row['area'] or '—'}\n", style="dim")
    lines.append(f"Зарплата: {fmt_salary(row)}\n")
    lines.append(f"График:   {fmt_schedule(row.get('schedule', ''))}\n\n")

    if row.get("summary"):
        lines.append("Вывод:\n", style="bold")
        lines.append(f"{row['summary']}\n\n", style="italic")

    if criteria:
        lines.append("Критерии:\n", style="bold")
        crit_names = {
            "skills_match": "Навыки", "salary": "Зарплата", "remote": "Формат",
            "company_stability": "Компания", "tech_stack": "Стек",
            "career_growth": "Рост", "dms_benefits": "Соц.пакет",
            "location": "Локация", "experience_fit": "Опыт", "test_task": "Тест",
        }
        for c in sorted(criteria, key=lambda x: x.get("score", 0), reverse=True):
            g     = c.get("grade", "C")
            color = GRADE_COLORS.get(g, "white")
            name  = crit_names.get(c["name"], c["name"])
            score = c.get("score", 0)
            pct   = int(c.get("weight", 0) * 100)
            lines.append(f"  {name:<12}", style="dim")
            lines.append(f" {score:.1f} {g}", style=f"bold {color}")
            lines.append(f"  ({pct}%)\n", style="dim")

    if skills:
        lines.append(f"\nНавыки: ", style="bold")
        lines.append(", ".join(skills[:12]) + "\n", style="dim")

    if row.get("url"):
        lines.append(f"\n{row['url']}", style="link")

    return Panel(
        lines,
        title=f"[bold cyan]{GRADE_EMOJI.get(row['grade'],'') } {row['grade']} — {row['total_score']:.1f}/5.0[/bold cyan]",
        border_style="cyan",
    )


# ── Главный цикл ──────────────────────────────────────────────────────────────

def run_dashboard():
    config   = load_config()
    db_path  = config["paths"]["db"]

    if not Path(db_path).exists():
        console.print(Panel(
            "[yellow]База данных не найдена.[/yellow]\n\n"
            "Сначала запусти поиск вакансий:\n"
            "  [bold]claude[/bold]  →  /search Python разработчик",
            title="hh-career-ops", border_style="yellow"
        ))
        return

    # Фильтр по грейду
    filter_grade = "C"
    page         = 0
    page_size    = 15
    selected     = 0

    def reload():
        return get_vacancies(db_path, min_grade=filter_grade, limit=200)

    rows = reload()

    console.clear()
    console.print(Panel(
        "[bold]hh-career-ops[/bold]  ·  Управление: [cyan]↑↓[/cyan] навигация  "
        "[cyan]Enter[/cyan] детали  [cyan]o[/cyan] открыть  [cyan]a[/cyan] откликнуться  "
        "[cyan]f[/cyan] фильтр  [cyan]r[/cyan] обновить  [cyan]q[/cyan] выход",
        border_style="blue",
    ))

    while True:
        stats        = get_stats(db_path)
        page_rows    = rows[page * page_size: (page + 1) * page_size]
        total_pages  = max(1, (len(rows) + page_size - 1) // page_size)
        sel_abs      = page * page_size + selected  # абсолютный индекс

        # Рендер
        layout = Layout()
        layout.split_row(
            Layout(make_stats_panel(stats), name="stats", ratio=1),
            Layout(name="main", ratio=3),
        )
        layout["main"].split_column(
            Layout(
                Panel(
                    make_vacancy_table(page_rows, selected),
                    title=f"Вакансии [{filter_grade}+] — {len(rows)} шт.  "
                          f"стр. {page + 1}/{total_pages}",
                    border_style="blue",
                ),
                name="table",
                ratio=2,
            ),
            Layout(
                make_detail_panel(rows[sel_abs]) if rows else Panel("Нет данных"),
                name="detail",
                ratio=3,
            ),
        )

        with Live(layout, console=console, screen=True, refresh_per_second=4) as live:
            live.stop()  # рисуем один раз, ждём ввод

            console.print(layout)
            console.print()
            key = Prompt.ask(
                f"[dim]Выбор (1-{len(page_rows)}) или команда[/dim]",
                default="",
            ).strip().lower()

        if key in ("q", "exit", "quit", ""):
            if key == "":
                continue
            break

        # Числовой выбор строки
        if key.isdigit():
            idx = int(key) - 1
            if 0 <= idx < len(page_rows):
                selected = idx
            continue

        if key in ("r", "refresh"):
            rows = reload()
            selected = 0
            page = 0

        elif key == "f":
            grades = ["A", "B", "C", "D", "F"]
            cur_idx = grades.index(filter_grade) if filter_grade in grades else 2
            filter_grade = grades[(cur_idx + 1) % len(grades)]
            rows = reload()
            selected = 0
            page = 0
            console.print(f"Фильтр: {filter_grade}+")

        elif key in ("j", "down", "n"):
            if selected < len(page_rows) - 1:
                selected += 1
            elif page < total_pages - 1:
                page += 1
                selected = 0

        elif key in ("k", "up", "p"):
            if selected > 0:
                selected -= 1
            elif page > 0:
                page -= 1
                selected = page_size - 1

        elif key in ("o", "open") and rows:
            url = rows[sel_abs].get("url")
            if url:
                webbrowser.open(url)
                console.print(f"Открываю: {url}")

        elif key in ("a", "apply") and rows:
            row = rows[sel_abs]
            console.print(f"\n[bold]Отклик:[/bold] {row['title']} @ {row['company']}")
            console.print(f"Оценка: {row['total_score']:.1f} [{row['grade']}]")

            if row["grade"] in ("D", "F"):
                if not Confirm.ask("[yellow]Оценка низкая. Всё равно откликнуться?[/yellow]"):
                    continue

            console.print("\n[dim]Запускаю /apply через claude CLI...[/dim]")
            subprocess.run(["claude", "-p", f"/apply {row['id']}"])
            rows = reload()

        elif key in ("enter", "d", "detail") and rows:
            # Детальная панель уже отображается при выборе — просто показываем ещё раз
            console.print(make_detail_panel(rows[sel_abs]))
            Prompt.ask("[dim]Enter для возврата[/dim]", default="")

    console.print("[dim]Пока![/dim]")


if __name__ == "__main__":
    run_dashboard()

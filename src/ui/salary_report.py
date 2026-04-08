"""
Терминальный отчёт по анализу зарплат.

Запуск: python -m src.ui.salary_report "Python разработчик"
"""

import json
import sys

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from src.core.db import VacancyDB
from src.core.salary_analysis import GroupStats, SalaryReport

console = Console()


def _fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _bar_chart(items: list[tuple[str, int]], width: int = 30, color: str = "cyan") -> str:
    """Горизонтальная гистограмма в виде строки."""
    if not items:
        return ""
    max_val = max(v for _, v in items) or 1
    lines = []
    for label, val in items:
        filled = round(val / max_val * width)
        bar = "█" * filled + "░" * (width - filled)
        lines.append(f"  {label:<12} [{color}]{bar}[/{color}] {val}")
    return "\n".join(lines)


def render_report(report: SalaryReport) -> None:
    console.print()
    console.print(Rule(
        f"[bold cyan]Анализ зарплат: «{report.query}»[/bold cyan]",
        style="cyan",
    ))

    # ── Сводка ────────────────────────────────────────────────────────────────
    summary = Table.grid(padding=(0, 3))
    summary.add_column(style="dim")
    summary.add_column(style="bold white")
    summary.add_column(style="dim")
    summary.add_column(style="bold white")

    summary.add_row(
        "Всего вакансий:", str(report.total_found),
        "С зарплатой:", f"{report.sample_size} ({report.coverage_pct}%)",
    )
    summary.add_row(
        "Минимум:",  f"{_fmt(report.salary_min)} ₽",
        "Максимум:", f"{_fmt(report.salary_max)} ₽",
    )
    summary.add_row(
        "25-й перц.:", f"{_fmt(report.salary_p25)} ₽",
        "75-й перц.:", f"{_fmt(report.salary_p75)} ₽",
    )
    summary.add_row(
        "Среднее:",  f"{_fmt(report.salary_mean)} ₽",
        "Медиана:",  f"[bold green]{_fmt(report.salary_median)} ₽[/bold green]",
    )
    summary.add_row(
        "МКР (разброс):", f"{_fmt(report.iqr)} ₽", "", "",
    )

    console.print(Panel(summary, title="[bold]Общая статистика (net, руб.)[/bold]",
                        border_style="green", padding=(1, 2)))

    # ── Гистограмма ───────────────────────────────────────────────────────────
    if report.histogram:
        hist_text = _bar_chart(report.histogram, width=35, color="green")
        console.print(Panel(
            hist_text,
            title="[bold]Распределение зарплат[/bold]",
            border_style="blue",
        ))

    # ── По опыту и графику рядом ───────────────────────────────────────────────
    def make_group_table(title: str, groups: list[GroupStats]) -> Panel:
        t = Table(box=box.SIMPLE, header_style="bold cyan", show_edge=False)
        t.add_column("Группа",   style="white",      min_width=14)
        t.add_column("N",        justify="right",     style="dim")
        t.add_column("P25",      justify="right")
        t.add_column("Медиана",  justify="right",     style="bold green")
        t.add_column("P75",      justify="right")
        t.add_column("Среднее",  justify="right",     style="dim")
        for g in groups:
            t.add_row(
                g.label, str(g.count),
                f"{_fmt(g.p25)} ₽",
                f"{_fmt(g.median)} ₽",
                f"{_fmt(g.p75)} ₽",
                f"{_fmt(g.mean)} ₽",
            )
        return Panel(t, title=f"[bold]{title}[/bold]", border_style="blue")

    panels = []
    if report.by_experience:
        panels.append(make_group_table("По опыту", report.by_experience))
    if report.by_schedule:
        panels.append(make_group_table("По формату работы", report.by_schedule))

    if panels:
        console.print(Columns(panels, equal=True))

    # ── Топ компаний ──────────────────────────────────────────────────────────
    if report.top_companies:
        t = Table(box=box.SIMPLE, header_style="bold cyan", show_edge=False)
        t.add_column("#",         width=3,  justify="right", style="dim")
        t.add_column("Компания",  width=35)
        t.add_column("Вакансий", width=9,  justify="right", style="dim")
        t.add_column("Медиана",  width=16, justify="right", style="bold green")
        t.add_column("Макс.",    width=16, justify="right", style="dim")

        for i, c in enumerate(report.top_companies, 1):
            t.add_row(
                str(i),
                c["company"],
                str(c["count"]),
                f"{_fmt(c['median'])} ₽",
                f"{_fmt(c['max'])} ₽",
            )

        console.print(Panel(
            t,
            title="[bold]Топ компаний по медианной зарплате[/bold]",
            border_style="blue",
        ))

    console.print(
        "[dim]  Все суммы приведены к net (после НДФЛ 13%). "
        "Снапшот сохранён — запусти /salary-trend для динамики.[/dim]\n"
    )


def render_trend(history: list[dict], query: str) -> None:
    """Показывает динамику медианной зарплаты по снапшотам."""
    if not history:
        console.print(f"[yellow]Нет истории для «{query}».[/yellow]")
        return

    console.print(Rule(f"[bold cyan]Динамика зарплат: «{query}»[/bold cyan]", style="cyan"))

    t = Table(box=box.SIMPLE, header_style="bold cyan", show_edge=False)
    t.add_column("Дата",     width=12)
    t.add_column("Выборка",  width=9,  justify="right", style="dim")
    t.add_column("P25",      width=14, justify="right")
    t.add_column("Медиана",  width=14, justify="right", style="bold green")
    t.add_column("P75",      width=14, justify="right")
    t.add_column("Среднее",  width=14, justify="right", style="dim")

    prev_median = None
    for row in history:
        med = row["salary_median"]
        arrow = ""
        if prev_median:
            diff = med - prev_median
            if diff > 1000:
                arrow = f" [green]▲{_fmt(diff)}[/green]"
            elif diff < -1000:
                arrow = f" [red]▼{_fmt(abs(diff))}[/red]"
        t.add_row(
            row["snapshot_date"],
            str(row["sample_size"]),
            f"{_fmt(row['salary_p25'])} ₽",
            f"{_fmt(med)} ₽{arrow}",
            f"{_fmt(row['salary_p75'])} ₽",
            f"{_fmt(row['salary_mean'])} ₽",
        )
        prev_median = med

    console.print(Panel(t, border_style="blue"))


def run(query: str, trend: bool = False) -> None:
    from src.core.salary_analysis import SalaryAnalyzer

    if trend:
        db = VacancyDB()
        history = db.get_salary_history(query)
        render_trend(history, query)
        return

    analyzer = SalaryAnalyzer()
    report = analyzer.analyze(query)
    if report.sample_size > 0:
        render_report(report)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        console.print("[red]Укажи поисковый запрос:[/red] python -m src.ui.salary_report 'Python разработчик'")
        sys.exit(1)
    trend_mode = "--trend" in args
    query_args = [a for a in args if not a.startswith("--")]
    run(" ".join(query_args), trend=trend_mode)

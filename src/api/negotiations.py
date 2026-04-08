"""
Отклики на вакансии (negotiations) через hh.ru API.
Всегда требует подтверждения пользователя перед отправкой.
"""

from src.api.client import HHClient


class NegotiationAPI:
    def __init__(self, client: HHClient | None = None):
        self.client = client or HHClient()

    def list_active(self) -> list[dict]:
        """Список активных откликов."""
        data = self.client.get("/negotiations", params={"status": "active"})
        return data.get("items", [])

    def list_all(self) -> list[dict]:
        """Все отклики (все статусы)."""
        data = self.client.get("/negotiations")
        return data.get("items", [])

    def get_messages(self, negotiation_id: str) -> list[dict]:
        """История сообщений по отклику."""
        data = self.client.get(f"/negotiations/{negotiation_id}/messages")
        return data.get("items", [])

    def apply(
        self,
        vacancy_id: str,
        resume_id: str,
        message: str = "",
        *,
        dry_run: bool = False,
    ) -> dict | None:
        """
        Отправить отклик на вакансию.

        Args:
            vacancy_id: ID вакансии на hh.ru
            resume_id:  ID резюме соискателя
            message:    Сопроводительное письмо
            dry_run:    Если True — только показывает что будет отправлено, не отправляет

        Returns:
            Данные созданного отклика или None при dry_run
        """
        payload = {
            "vacancy_id": vacancy_id,
            "resume_id": resume_id,
        }
        if message:
            payload["message"] = message

        if dry_run:
            print("[DRY RUN] Отклик НЕ отправлен. Payload:")
            for k, v in payload.items():
                val = v[:100] + "..." if isinstance(v, str) and len(v) > 100 else v
                print(f"  {k}: {val}")
            return None

        result = self.client.post("/negotiations", json=payload)
        print(f"Отклик отправлен: vacancy_id={vacancy_id}")
        return result

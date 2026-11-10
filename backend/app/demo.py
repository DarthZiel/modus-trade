"""Explicit local demonstration dataset; never runs on application startup."""

import argparse
import os
import secrets
from datetime import timedelta
from getpass import getpass
from uuid import uuid4

from sqlalchemy import delete
from sqlmodel import Session, select

from app.database import engine
from app.models import (
    Appeal,
    AppealAttachment,
    AppealEvent,
    AppealFeedback,
    AppealMessage,
    AppealRelation,
    AppealSupporter,
    AppealPriority,
    PriorityEvent,
    Company,
    Department,
    Experiment,
    Invitation,
    LoginSession,
    Notification,
    TelegramLink,
    TelegramLinkToken,
    User,
    utcnow,
)
from app.security import password_hasher

NAME = "ДЕМО — Modus Feedback"
EMAILS = {
    "demo.coordinator@example.com",
    "demo.employee@example.com",
    "demo.responsible@example.com",
}


def clear(db, company):
    users = db.exec(select(User).where(User.company_id == company.id)).all()
    if {u.email for u in users} != EMAILS:
        raise SystemExit(
            "Набор пользователей отличается от демонстрационного. Удаление остановлено."
        )
    appeal_ids = select(Appeal.id).where(Appeal.company_id == company.id)
    if db.exec(
        select(AppealAttachment).where(AppealAttachment.appeal_id.in_(appeal_ids))
    ).first():
        raise SystemExit(
            "В демо добавлены вложения. Удаление остановлено, чтобы сохранить файлы."
        )
    for model in [
        AppealSupporter,
        PriorityEvent,
        AppealPriority,
        Notification,
        Experiment,
        AppealFeedback,
        AppealMessage,
        AppealEvent,
    ]:
        db.execute(delete(model).where(model.appeal_id.in_(appeal_ids)))
    db.execute(
        delete(AppealRelation).where(
            AppealRelation.left_id.in_(appeal_ids)
            | AppealRelation.right_id.in_(appeal_ids)
        )
    )
    db.execute(delete(Appeal).where(Appeal.company_id == company.id))
    for model in [LoginSession, TelegramLinkToken, TelegramLink]:
        db.execute(delete(model).where(model.user_id.in_([u.id for u in users])))
    db.execute(delete(Invitation).where(Invitation.company_id == company.id))
    db.execute(delete(User).where(User.company_id == company.id))
    db.execute(delete(Department).where(Department.company_id == company.id))
    db.delete(company)
    db.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Удалить только отдельную демонстрационную компанию",
    )
    args = parser.parse_args()
    with Session(engine) as db:
        company = db.exec(select(Company).where(Company.name == NAME)).first()
        if args.clear:
            if company:
                clear(db, company)
            print("Демонстрационный набор удалён. Другие компании не изменены.")
            return
        if company:
            print(
                "Демонстрационный набор уже существует. Повторный запуск не создаёт дубликатов."
            )
            return
        password = os.environ.get("DEMO_PASSWORD") or getpass(
            "Пароль для трёх демонстрационных аккаунтов: "
        )
        if len(password) < 12:
            raise SystemExit("Нужен пароль минимум 12 символов.")
        company = Company(name=NAME)
        db.add(company)
        db.flush()
        department = Department(company_id=company.id, name="Демонстрационный склад")
        db.add(department)
        db.flush()
        people = []
        for name, email, roles in [
            (
                "Координатор демо",
                "demo.coordinator@example.com",
                ["employee", "coordinator"],
            ),
            ("Сотрудник демо", "demo.employee@example.com", ["employee"]),
            (
                "Ответственный демо",
                "demo.responsible@example.com",
                ["employee", "responsible"],
            ),
        ]:
            user = User(
                name=name,
                email=email,
                company_id=company.id,
                department_id=department.id,
                roles=roles,
                password_hash=password_hasher.hash(password),
            )
            db.add(user)
            people.append(user)
        db.flush()
        coordinator, author, responsible = people
        now = utcnow()
        for index, title, status in [
            (1, "Похожие коробки сложно различать", "received"),
            (2, "Проверка маркировки одной полки", "in_progress"),
            (3, "Изменение порядка проверки отгрузок", "awaiting_confirmation"),
            (4, "Не хватает подсветки в зоне упаковки", "reviewing"),
            (5, "Обновлён шаблон передачи смены", "closed"),
        ]:
            item = Appeal(
                submission_id=uuid4(),
                payload_hash=secrets.token_hex(32),
                kind="idea" if index in {2, 3, 5} else "problem",
                title=title,
                description="Демонстрационный пример, не фактические сведения о компании. "
                + title
                + ". Предлагаем проверить небольшое изменение и спросить сотрудника о результате.",
                original_description="Демонстрационный пример: " + title,
                category="warehouse",
                author_id=author.id,
                company_id=company.id,
                department_id=department.id,
                status=status,
                responsible_id=responsible.id if index > 1 else None,
                next_response_at=(
                    now - timedelta(hours=2) if index == 4 else now + timedelta(days=2)
                )
                if status in {"reviewing", "in_progress"}
                else None,
                assignment_version=1 if index > 1 else 0,
                created_at=now - timedelta(days=index),
            )
            if status in {"awaiting_confirmation", "closed"}:
                item.decision = "Выполнено"
                item.result = "Демонстрационный результат: изменение выполнено, ожидается проверка сотрудником."
                item.decided_at = now - timedelta(days=1)
            db.add(item)
            db.flush()
            db.add(
                AppealEvent(
                    appeal_id=item.id,
                    actor_id=author.id,
                    text="Загружен явно обозначенный демонстрационный пример.",
                )
            )
            if index in {2, 3}:
                experiment = Experiment(
                    appeal_id=item.id,
                    created_by=coordinator.id,
                    client_id=uuid4(),
                    responsible_id=responsible.id,
                    hypothesis="Маркировка помогает различать похожие коробки"
                    if index == 2
                    else "Проверка по списку уменьшает пропуски",
                    change="Проверить одну полку / одну рабочую смену",
                    success_criterion="Сравнить ошибки за одинаковое число операций и спросить автора",
                    starts_at=now - timedelta(days=2),
                    ends_at=now + timedelta(days=3),
                    baseline="Синтетические данные для демонстрации, не реальные показатели компании.",
                    metric="Пропуски на 20 операций" if index == 3 else "",
                    unit="случаев" if index == 3 else "",
                    before_value=12 if index == 3 else None,
                    status="completed" if index == 3 else "active",
                    actions="Проверили список на одинаковом числе операций"
                    if index == 3
                    else "",
                    observations="Синтетический пример измерений: до 12, после 3"
                    if index == 3
                    else "",
                    after_value=3 if index == 3 else None,
                    outcome="expand" if index == 3 else None,
                    finished_at=now - timedelta(days=1) if index == 3 else None,
                )
                db.add(experiment)
            if index == 5:
                db.add(
                    AppealFeedback(
                        appeal_id=item.id,
                        author_id=author.id,
                        client_id=uuid4(),
                        outcome="helped",
                        comment="Демонстрационное подтверждение: шаблон помогает",
                        result_snapshot=item.result,
                    )
                )
            db.add(
                Notification(
                    user_id=author.id,
                    appeal_id=item.id,
                    kind="demo",
                    title="Демонстрационный пример доступен",
                    dedupe_key=f"demo:{item.id}",
                )
            )
            print(f"MT-{item.id:06} · {status} · {title}")
        db.commit()
        print("Созданы 3 аккаунта и 5 демонстрационных обращений. Пароль не выводится.")
        for email in sorted(EMAILS):
            print(email)


if __name__ == "__main__":
    main()

"""Extend the isolated organizer dataset with a director and three priority examples."""

import argparse
import os
from datetime import timedelta
from getpass import getpass
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import text
from sqlmodel import Session, select

from app.database import engine
from app.hackathon_demo import EMAIL, NAME, seed_dataset
from app.models import (
    Appeal,
    AppealEvent,
    AppealPriority,
    Company,
    PriorityEvent,
    User,
    utcnow,
)
from app.priorities import contexts, fingerprint
from app.security import password_hasher

DIRECTOR_EMAIL = "dataset.director@example.com"


def seed_director(db, password):
    seed_dataset(db, password)
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('director-dataset-seed'))"))
    company = db.exec(select(Company).where(Company.name == NAME)).one()
    coordinator = db.exec(select(User).where(User.email == EMAIL)).one()
    author = db.exec(
        select(User).where(User.email == "dataset.employee1@example.com")
    ).one()
    director = db.exec(select(User).where(User.email == DIRECTOR_EMAIL)).first()
    if director and (
        director.company_id != company.id or "director" not in director.roles
    ):
        raise ValueError("Email демонстрационного директора уже занят другим профилем")
    if not director:
        director = User(
            name="Директор датасета",
            email=DIRECTOR_EMAIL,
            password_hash=password_hasher.hash(password),
            roles=["employee", "director"],
            company_id=company.id,
            department_id=coordinator.department_id,
        )
        db.add(director)
        db.flush()
    examples = [
        (
            "DIR-025",
            "Не нравится печенье в офисе",
            "idea",
            "Мне не нравится вкус печенья в офисной кухне. Предлагаю выбрать другой сорт.",
            "routine",
            "low",
            "Обычное пожелание об ассортименте кухни, сведения о риске для здоровья отсутствуют.",
            "Передать обычное пожелание административному ответственному.",
        ),
        (
            "DIR-026",
            "Подозрение на пропажу оборудования",
            "problem",
            "Кажется, у нас воруют оборудование со склада. Доказательств у меня пока нет, прошу проверить расхождения в учёте.",
            "attention",
            "high",
            "Сообщение содержит непроверенное подозрение на хищение. Это повод для проверки, а не установленный факт.",
            "Передать уполномоченному сотруднику для проверки расхождений и уточнения фактов.",
        ),
        (
            "DIR-027",
            "Обещание повысить эффективность на 300 процентов",
            "idea",
            "Я знаю, как повысить эффективность на 300 процентов, но конкретный способ и расчёты пока не описал.",
            "routine",
            "low",
            "Большая цифра не подкреплена описанием изменения или измерениями. Потенциальный эффект не подтверждён.",
            "Запросить конкретное изменение, исходные данные и способ проверки результата.",
        ),
    ]
    seeded = []
    for code, title, kind, description, lane, level, reason, next_step in examples:
        submission_id = uuid5(NAMESPACE_URL, f"modus-director:{code}")
        appeal = db.exec(
            select(Appeal).where(
                Appeal.author_id == author.id, Appeal.submission_id == submission_id
            )
        ).first()
        if not appeal:
            appeal = Appeal(
                submission_id=submission_id,
                payload_hash=f"director-dataset:{code}",
                kind=kind,
                title=title,
                description=f"Синтетический пример {code}, не факт о компании.\n\n{description}",
                original_description=description,
                category="workplace" if code == "DIR-025" else "process",
                author_id=author.id,
                company_id=company.id,
                department_id=author.department_id,
                created_at=utcnow() - timedelta(days=1),
            )
            db.add(appeal)
            db.flush()
            db.add(
                AppealEvent(
                    appeal_id=appeal.id,
                    actor_id=author.id,
                    text=f"Синтетический пример {code} для демонстрации приоритетов. Не сведения о компании.",
                )
            )
        seeded.append((appeal, lane, level, reason, next_step))
    concrete_idea = db.exec(
        select(Appeal).where(
            Appeal.company_id == company.id,
            Appeal.submission_id == uuid5(NAMESPACE_URL, "modus-hackathon:A-006"),
        )
    ).one()
    seeded.append(
        (
            concrete_idea,
            "promising",
            "medium",
            "Предлагается конкретная памятка для межотдельных операций. Пользу и затраты нужно проверить.",
            "Согласовать владельца памятки и провести небольшую проверку в одном процессе.",
        )
    )
    db.flush()
    context = contexts(
        db, list(db.exec(select(Appeal).where(Appeal.company_id == company.id)).all())
    )
    for appeal, lane, level, reason, next_step in seeded:
        if db.get(AppealPriority, appeal.id):
            continue
        reason = "Подготовленный демонстрационный пример: " + reason
        db.add(
            AppealPriority(
                appeal_id=appeal.id,
                version=1,
                ai_lane=lane,
                ai_level=level,
                ai_reason=reason,
                ai_next_step=next_step,
                ai_source="dataset",
                ai_updated_at=utcnow(),
                ai_context_hash=fingerprint(appeal, context[appeal.id]),
            )
        )
        db.add(
            PriorityEvent(
                appeal_id=appeal.id,
                actor_id=coordinator.id,
                action="seed",
                lane=lane,
                level=level,
                reason=reason,
                next_step=next_step,
                source="dataset",
                version=1,
            )
        )
    db.commit()
    return {
        "director_id": str(director.id),
        "company_id": str(company.id),
        "appeals": len(context),
    }


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    password = os.environ.get("DEMO_PASSWORD") or getpass(
        "Пароль нового демонстрационного директора (12–128 символов): "
    )
    if not 12 <= len(password) <= 128:
        raise SystemExit("Нужен пароль от 12 до 128 символов")
    with Session(engine) as db:
        result = seed_director(db, password)
    print(
        f"Демонстрационный директор: {DIRECTOR_EMAIL}. Обращений в компании: {result['appeals']}."
    )
    print(
        "Существующие пользователи, пароли и оценки не изменены. Подготовленные оценки не являются ответом ИИ."
    )


if __name__ == "__main__":
    main()

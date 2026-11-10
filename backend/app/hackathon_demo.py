"""Explicit, isolated seed adapted from the organizer's synthetic DOCX dataset."""

import argparse
import json
import os
from datetime import timedelta
from getpass import getpass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import text
from sqlmodel import Session, select

from app.database import engine
from app.models import (
    Appeal,
    AppealEvent,
    AppealFeedback,
    AppealMessage,
    AppealRelation,
    Company,
    Department,
    User,
    utcnow,
)
from app.security import password_hasher

NAME = "ДЕМО — Датасет хакатона"
EMAIL = "dataset.coordinator@example.com"
DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "hackathon_appeals.json"
TITLES = [
    "Добавить обязательные параметры в заявки закупок",
    "Показывать закупкам общую стадию проекта",
    "Единые обозначения изделий в номенклатуре",
    "Короткие занятия по новым товарным линейкам",
    "Показывать этап и ответственного за пакет документов",
    "Пошаговая памятка для межотдельных операций",
    "Убрать повторный ввод данных между системами",
    "Памятка по передаче сложной задачи новичку",
    "Определить ответственных за версии приложения к договору",
    "Закрывать задачи после подтверждения результата",
    "Показывать срок ответа смежного подразделения",
    "Единое место для итоговых решений по задаче",
    "История изменений строк спецификации",
    "Обзор загрузки проектной группы",
    "Указывать результат и дату завершения поручений",
    "Практические занятия с образцами оборудования",
    "Организовать зону для коротких перерывов",
    "Сохранить полезный формат внутренних учебных встреч",
    "Правила хранения актуальных редакций инструкций",
    "Обзор завершённых внутренних улучшений",
]
AUTHOR_DEPARTMENTS = {
    "Сотрудник закупок": "Закупки",
    "Сотрудник проектирования": "Проектирование",
    "Сотрудник бухгалтерии": "Бухгалтерия",
    "Менеджер по продажам": "Продажи",
    "Координатор проекта": "Проекты",
    "Руководитель проекта": "Проекты",
    "Сотрудник офиса": "Офис",
}


def seed_dataset(db: Session, password: str) -> dict:
    if not 12 <= len(password) <= 128:
        raise ValueError("Пароль должен содержать от 12 до 128 символов")
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('hackathon-dataset-seed'))"))
    company = db.exec(select(Company).where(Company.name == NAME)).first()
    if company:
        return {
            "created": False,
            "company_id": str(company.id),
            "appeals": len(
                db.exec(select(Appeal).where(Appeal.company_id == company.id)).all()
            ),
        }
    records = json.loads(DATA_PATH.read_text())["records"]
    company = Company(name=NAME)
    db.add(company)
    db.flush()
    departments = {}
    for name in sorted(set(AUTHOR_DEPARTMENTS.values()) | {"Координация"}):
        department = Department(name=name, company_id=company.id)
        db.add(department)
        db.flush()
        departments[name] = department
    users = {}
    hashed = password_hasher.hash(password)
    people = [
        ("Координатор датасета", EMAIL, ["employee", "coordinator"], "Координация"),
        (
            "Ответственный датасета",
            "dataset.responsible@example.com",
            ["employee", "responsible"],
            "Координация",
        ),
    ]
    for n, (role, department) in enumerate(AUTHOR_DEPARTMENTS.items(), 1):
        people.append(
            (
                role + " (пример)",
                f"dataset.employee{n}@example.com",
                ["employee"],
                department,
            )
        )
    for name, email, roles, department in people:
        user = User(
            name=name,
            email=email,
            roles=roles,
            company_id=company.id,
            department_id=departments[department].id,
            password_hash=hashed,
        )
        db.add(user)
        db.flush()
        users[email] = user
    authors = {
        role: users[f"dataset.employee{n}@example.com"]
        for n, role in enumerate(AUTHOR_DEPARTMENTS, 1)
    }
    responsible, coordinator = users["dataset.responsible@example.com"], users[EMAIL]
    extra = [
        {
            "source_id": "EXT-021",
            "source_author": "Менеджер по продажам",
            "source_kind": "Проблема",
            "source_category": "Каталог и данные",
            "source_status": "На рассмотрении",
            "description": "Одна и та же модель оборудования записана в спецификации под разными названиями. Нужен единый справочник обозначений изделий, чтобы не проверять каждую позицию вручную.",
            "title": "Одна модель оборудования под разными названиями",
        },
        {
            "source_id": "EXT-022",
            "source_author": "Сотрудник закупок",
            "source_kind": "Проблема",
            "source_category": "Каталог и данные",
            "source_status": "Новое",
            "description": "Не могу сопоставить артикул из заявки с карточкой товара: одно изделие называют по-разному. Нужны единые наименования и ссылка на актуальную карточку позиции.",
            "title": "Разные наименования мешают найти карточку изделия",
        },
        {
            "source_id": "EXT-023",
            "source_author": "Сотрудник бухгалтерии",
            "source_kind": "Предложение",
            "source_category": "Регламенты",
            "source_status": "Закрыто",
            "description": "Для передачи документов между отделами предлагаю короткий чек-лист с ответственными на каждом этапе.",
            "title": "Чек-лист передачи документов подтверждён автором",
        },
        {
            "source_id": "EXT-024",
            "source_author": "Координатор проекта",
            "source_kind": "Проблема",
            "source_category": "Постановка задач",
            "source_status": "В работе",
            "description": "В поручении снова не указан срок и ожидаемый результат. Предыдущий шаблон не помог: поля по-прежнему можно пропустить.",
            "title": "Возврат: поручения всё ещё без срока и результата",
        },
    ]
    now, seeded = utcnow(), {}
    for n, record in enumerate(records + extra):
        author = authors[record["source_author"]]
        code = record["source_id"]
        status = {
            "Новое": "received",
            "На рассмотрении": "reviewing",
            "В работе": "in_progress",
            "Ожидает уточнения": "needs_info",
            "Реализовано": "awaiting_confirmation",
            "Отклонено": "rejected",
            "Закрыто": "reviewing",
        }[record["source_status"]]
        if code == "EXT-023":
            status = "closed"
        created = now - timedelta(days=3 + (n * 3) % 25, hours=n % 5)
        response_at = (
            created + timedelta(hours=2 + n % 18) if status != "received" else None
        )
        text_value = record["description"]
        if record["source_kind"] == "Положительный отзыв":
            text_value = (
                "Положительный отзыв и предложение сохранить формат. " + text_value
            )
        category = (
            "workplace"
            if record["source_category"] == "Корпоративная среда"
            else "process"
        )
        item = Appeal(
            submission_id=uuid5(NAMESPACE_URL, f"modus-hackathon:{code}"),
            payload_hash=f"hackathon-dataset:{code}",
            kind="problem" if record["source_kind"] == "Проблема" else "idea",
            title=record.get("title") or TITLES[n],
            description=f"Синтетический пример {code}, не факт о компании.\n\n"
            + text_value,
            original_description=record["description"],
            category=category,
            author_id=author.id,
            company_id=company.id,
            department_id=author.department_id,
            status=status,
            created_at=created,
            first_response_at=response_at,
            responsible_id=responsible.id if status != "received" else None,
            assignment_version=1 if status != "received" else 0,
            resume_status="reviewing" if status == "needs_info" else None,
            next_response_at=(
                now - timedelta(days=1) if n % 4 == 0 else now + timedelta(days=3)
            )
            if status in {"reviewing", "in_progress", "needs_info"}
            else None,
        )
        if status in {"awaiting_confirmation", "closed", "rejected"}:
            item.decision = "Отклонено" if status == "rejected" else "Выполнено"
            item.result = (
                "Синтетический мотивированный отказ: сейчас нет подходящего помещения; вернуться к вопросу при перепланировке."
                if status == "rejected"
                else "Синтетический результат: подготовлен и проверен учебный материал / памятка. Требуется оценка автора."
            )
            item.decided_at = response_at + timedelta(days=1)
        db.add(item)
        db.flush()
        db.add(
            AppealEvent(
                appeal_id=item.id,
                actor_id=author.id,
                created_at=created,
                text=f"Демонстрационный набор: {code}. Все обращения, даты и результаты синтетические.",
            )
        )
        if response_at:
            db.add(
                AppealMessage(
                    appeal_id=item.id,
                    sender_id=responsible.id,
                    client_id=uuid4(),
                    body="Синтетический ответ: уточните пример и ожидаемый результат."
                    if status == "needs_info"
                    else "Синтетический первый ответ: изучили описание, согласуем дальнейшие действия.",
                    kind="question" if status == "needs_info" else "message",
                    created_at=response_at,
                )
            )
        if code == "EXT-023":
            db.add(
                AppealFeedback(
                    appeal_id=item.id,
                    author_id=author.id,
                    client_id=uuid4(),
                    outcome="helped",
                    comment="Синтетическое подтверждение: чек-лист помогает.",
                    result_snapshot=item.result,
                    created_at=item.decided_at + timedelta(hours=4),
                )
            )
        if code == "EXT-024":
            db.add(
                AppealFeedback(
                    appeal_id=item.id,
                    author_id=author.id,
                    client_id=uuid4(),
                    outcome="reopen",
                    comment="Синтетический возврат: обязательные поля всё ещё можно пропустить.",
                    result_snapshot="Синтетический предыдущий результат: шаблон поручения обновлён.",
                    created_at=response_at + timedelta(days=1),
                )
            )
        seeded[code] = item
    # Explicitly prepared coordinator decisions, never presented as model output.
    for left_code, right_code, kind, status, topic in [
        (
            "A-003",
            "EXT-021",
            "same_problem",
            "confirmed",
            "Единые наименования и карточки оборудования",
        ),
        (
            "A-004",
            "A-016",
            "related_topic",
            "pending",
            "Внутреннее обучение оборудованию",
        ),
    ]:
        left, right = sorted([seeded[left_code].id, seeded[right_code].id])
        db.add(
            AppealRelation(
                left_id=left,
                right_id=right,
                kind=kind,
                status=status,
                topic=topic,
                reason="Подготовленная связь для демонстрации по синтетическим данным. Проверьте тексты обращений.",
                source="dataset",
                reviewed_by=coordinator.id if status == "confirmed" else None,
                reviewed_at=now if status == "confirmed" else None,
                version=1 if status == "confirmed" else 0,
            )
        )
    db.commit()
    return {"created": True, "company_id": str(company.id), "appeals": len(seeded)}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    password = os.environ.get("DEMO_PASSWORD") or getpass(
        "Пароль демонстрационных аккаунтов (12–128 символов): "
    )
    with Session(engine) as db:
        result = seed_dataset(db, password)
    print(
        "Создан" if result["created"] else "Уже существует",
        NAME,
        f"— {result['appeals']} обращений. Пароль не выводится.",
    )
    print("Координатор:", EMAIL)
    print("Ответственный: dataset.responsible@example.com")
    print("Сотрудники: dataset.employee1@example.com … dataset.employee7@example.com")


if __name__ == "__main__":
    main()

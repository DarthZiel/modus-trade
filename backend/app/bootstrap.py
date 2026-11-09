"""Create the first coordinator interactively; no default passwords."""

import argparse
from getpass import getpass

from pydantic import EmailStr, TypeAdapter
from sqlmodel import Session, select

from app.database import engine
from app.models import Company, Department, User
from app.security import password_hasher


def main():
    parser = argparse.ArgumentParser(description="Создать первого координатора")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--company", default="Модус Трейд")
    parser.add_argument("--department", default="Администрация")
    args = parser.parse_args()
    email = str(TypeAdapter(EmailStr).validate_python(args.email.strip().lower()))
    names = [args.name.strip(), args.company.strip(), args.department.strip()]
    if any(not name or len(name) > 160 for name in names):
        raise SystemExit("Имена и названия должны содержать от 1 до 160 символов")
    password = getpass("Пароль (12–128 символов): ")
    if not 12 <= len(password) <= 128:
        raise SystemExit("Пароль должен содержать от 12 до 128 символов")
    if password != getpass("Повторите пароль: "):
        raise SystemExit("Пароли не совпадают")
    with Session(engine) as db:
        if db.exec(select(User).where(User.email == email)).first():
            raise SystemExit("Аккаунт с таким email уже существует")
        company = db.exec(select(Company).where(Company.name == names[1])).first()
        if not company:
            company = Company(name=names[1])
            db.add(company)
            db.flush()
        department = db.exec(
            select(Department).where(
                Department.company_id == company.id, Department.name == names[2]
            )
        ).first()
        if not department:
            department = Department(company_id=company.id, name=names[2])
            db.add(department)
            db.flush()
        db.add(
            User(
                name=names[0],
                email=email,
                company_id=company.id,
                department_id=department.id,
                roles=["employee", "coordinator"],
                password_hash=password_hasher.hash(password),
            )
        )
        db.commit()
    print("Координатор создан. Войдите на сайт с указанными email и паролем.")


if __name__ == "__main__":
    main()

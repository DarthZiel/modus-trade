import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models import Company, Department, Invitation, LoginSession, User, utcnow
from app.schemas import (
    AcceptInput,
    CompanyPublic,
    DepartmentInput,
    DepartmentPublic,
    InviteCreated,
    InviteInput,
    InvitePreview,
    InvitePublic,
    LoginInput,
    NameInput,
    TokenInput,
    UserPublic,
    UserUpdate,
)
from app.security import (
    COOKIE_NAME,
    DUMMY_HASH,
    Coordinator,
    CurrentUser,
    Db,
    create_session,
    digest,
    limit_auth,
    limiter,
    password_hasher,
)

router = APIRouter(tags=["Accounts"])


def roles_with_employee(roles) -> list[str]:
    return sorted({"employee", *roles})


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Такая запись уже существует") from None


@router.post("/auth/login", dependencies=[Depends(limit_auth)])
def login(data: LoginInput, response: Response, request: Request, db: Db) -> UserPublic:
    limiter.check("login:" + str(data.email))
    user = db.exec(select(User).where(User.email == str(data.email))).first()
    valid = password_hasher.verify(
        data.password, user.password_hash if user else DUMMY_HASH
    )
    if not valid or not user or not user.is_active:
        raise HTTPException(401, "Неверный email или пароль")
    create_session(db, user, response, request)
    db.commit()
    return UserPublic.model_validate(user)


@router.get("/auth/me")
def me(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: Db) -> None:
    authorization = request.headers.get("Authorization", "")
    token = (
        authorization.removeprefix("Bearer ")
        if authorization.startswith("Bearer ")
        else request.cookies.get(COOKIE_NAME)
    )
    if token:
        db.exec(delete(LoginSession).where(LoginSession.token_hash == digest(token)))
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


def valid_invite(db, token: str, lock: bool = False) -> Invitation:
    statement = select(Invitation).where(Invitation.token_hash == digest(token))
    if lock:
        statement = statement.with_for_update()
    invite = db.exec(statement).first()
    if (
        not invite
        or invite.used_at
        or invite.revoked_at
        or invite.expires_at <= utcnow()
    ):
        raise HTTPException(
            410, "Приглашение недействительно или срок его действия истёк"
        )
    return invite


@router.post("/auth/invitation", dependencies=[Depends(limit_auth)])
def preview_invite(data: TokenInput, db: Db) -> InvitePreview:
    invite = valid_invite(db, data.token)
    return InvitePreview(
        name=invite.name,
        email=invite.email,
        company=db.get(Company, invite.company_id).name,
        department=db.get(Department, invite.department_id).name,
        roles=invite.roles,
        expires_at=invite.expires_at,
    )


@router.post("/auth/accept", dependencies=[Depends(limit_auth)], status_code=201)
def accept_invite(
    data: AcceptInput, response: Response, request: Request, db: Db
) -> UserPublic:
    invite = valid_invite(db, data.token, lock=True)
    user = User(
        name=invite.name,
        email=invite.email,
        company_id=invite.company_id,
        department_id=invite.department_id,
        roles=invite.roles,
        password_hash=password_hasher.hash(data.password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Аккаунт с таким email уже существует. Войдите в него."
        ) from None
    invite.used_at = utcnow()
    db.add(invite)
    create_session(db, user, response, request)
    commit(db)
    return UserPublic.model_validate(user)


@router.get("/directory/companies")
def companies(user: CurrentUser, db: Db) -> list[CompanyPublic]:
    query = select(Company).order_by(Company.name)
    if "coordinator" not in user.roles:
        query = query.where(Company.id == user.company_id)
    return [CompanyPublic.model_validate(item) for item in db.exec(query).all()]


@router.get("/directory/departments")
def departments(user: CurrentUser, db: Db) -> list[DepartmentPublic]:
    query = select(Department).order_by(Department.name)
    if "coordinator" not in user.roles:
        query = query.where(Department.company_id == user.company_id)
    return [DepartmentPublic.model_validate(item) for item in db.exec(query).all()]


@router.post("/admin/companies", status_code=201)
def create_company(data: NameInput, user: Coordinator, db: Db) -> CompanyPublic:
    company = Company(name=data.name)
    db.add(company)
    commit(db)
    return CompanyPublic.model_validate(company)


@router.post("/admin/departments", status_code=201)
def create_department(
    data: DepartmentInput, user: Coordinator, db: Db
) -> DepartmentPublic:
    if not db.get(Company, data.company_id):
        raise HTTPException(422, "Выберите существующую компанию")
    department = Department(**data.model_dump())
    db.add(department)
    commit(db)
    return DepartmentPublic.model_validate(department)


@router.get("/admin/users")
def users(user: Coordinator, db: Db) -> list[UserPublic]:
    return [
        UserPublic.model_validate(item)
        for item in db.exec(select(User).order_by(User.created_at)).all()
    ]


@router.patch("/admin/users/{user_id}")
def update_user(
    user_id: UUID, data: UserUpdate, actor: Coordinator, db: Db
) -> UserPublic:
    # Serialise role changes to prevent concurrent removal of the last coordinator.
    db.execute(text("SELECT pg_advisory_xact_lock(9374101)"))
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Сотрудник не найден")
    roles = roles_with_employee(data.roles)
    if (
        "coordinator" in target.roles
        and target.is_active
        and ("coordinator" not in roles or not data.is_active)
    ):
        active = db.exec(select(User).where(User.is_active == True)).all()
        if sum("coordinator" in item.roles for item in active) <= 1:
            raise HTTPException(
                409, "Нельзя отключить последнего активного координатора"
            )
    target.roles = roles
    target.is_active = data.is_active
    db.add(target)
    if not target.is_active:
        db.exec(delete(LoginSession).where(LoginSession.user_id == target.id))
    db.commit()
    return UserPublic.model_validate(target)


@router.get("/admin/invitations")
def invitations(user: Coordinator, db: Db) -> list[InvitePublic]:
    return [
        InvitePublic.model_validate(item)
        for item in db.exec(
            select(Invitation).order_by(Invitation.created_at.desc())
        ).all()
    ]


@router.post("/admin/invitations", status_code=201)
def create_invite(data: InviteInput, user: Coordinator, db: Db) -> InviteCreated:
    department = db.get(Department, data.department_id)
    if not department or department.company_id != data.company_id:
        raise HTTPException(422, "Подразделение должно принадлежать выбранной компании")
    if db.exec(select(User).where(User.email == str(data.email))).first():
        raise HTTPException(409, "Сотрудник с таким email уже зарегистрирован")
    # Serialise invitation creation for the same email across requests.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:email))"),
        {"email": str(data.email)},
    )
    pending = db.exec(
        select(Invitation).where(
            Invitation.email == str(data.email),
            Invitation.used_at == None,
            Invitation.revoked_at == None,
            Invitation.expires_at > utcnow(),
        )
    ).first()
    if pending:
        raise HTTPException(
            409, "Для этого email уже есть активное приглашение. Сначала отзовите его."
        )
    token = secrets.token_urlsafe(32)
    invite = Invitation(
        token_hash=digest(token),
        name=data.name,
        email=str(data.email),
        company_id=data.company_id,
        department_id=data.department_id,
        roles=roles_with_employee(data.roles),
        created_by=user.id,
        expires_at=utcnow() + timedelta(days=data.expires_in_days),
    )
    db.add(invite)
    db.commit()
    # Fragment keeps the token out of HTTP access logs and Referer headers.
    return InviteCreated(
        **InvitePublic.model_validate(invite).model_dump(),
        activation_path=f"/invite#token={token}",
    )


@router.post("/admin/invitations/{invite_id}/revoke")
def revoke_invite(invite_id: UUID, user: Coordinator, db: Db) -> InvitePublic:
    invite = db.exec(
        select(Invitation).where(Invitation.id == invite_id).with_for_update()
    ).first()
    if not invite:
        raise HTTPException(404, "Приглашение не найдено")
    if invite.used_at:
        raise HTTPException(409, "Приглашение уже использовано")
    if not invite.revoked_at:
        invite.revoked_at = utcnow()
        db.add(invite)
        db.commit()
    return InvitePublic.model_validate(invite)

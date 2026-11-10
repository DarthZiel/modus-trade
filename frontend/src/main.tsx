import { Tabs, TabsList, TabsTrigger, TabsContent } from "./components/ui/tabs";
import { Badge } from "./components/ui/badge";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "./components/ui/empty";
import { ChevronDown, Copy, UserPlus } from "lucide-react";
import { TelegramSettings, loginFromTelegram } from "./telegram";
import { Notifications } from "./notifications";
import { WorkQueue } from "./work-queue";
import { Appeals } from "./appeals";
import { Impact } from "./impact";
import { navigate, usePath } from "./navigation";
import { StrictMode, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { api, ApiError, roleNames } from "./api";
import type { User, Role, Company, Department, Invitation } from "./api";
import "@fontsource-variable/golos-text";
import {
  MessageSquare,
  ArrowRight,
  CheckCheck,
  Eye,
  EyeOff,
  LoaderCircle,
} from "lucide-react";
import {
  Field as UIField,
  FieldLabel,
  FieldGroup,
} from "./components/ui/field";
import { Skeleton } from "./components/ui/skeleton";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import {
  InputGroup,
  InputGroupInput,
  InputGroupAddon,
  InputGroupButton,
} from "./components/ui/input-group";
import "./styles.css";

function ErrorBox({ message }: { message: string }) {
  return message ? (
    <div className="error" role="alert">
      {message}
    </div>
  ) : null;
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <UIField>
      <FieldLabel className="field">
        <span>{label}</span>
        {children}
      </FieldLabel>
    </UIField>
  );
}
function RoleFields({
  value,
  onChange,
}: {
  value: Role[];
  onChange: (roles: Role[]) => void;
}) {
  return (
    <fieldset>
      <legend>Роли</legend>
      <p className="hint">Каждый участник может подавать свои обращения.</p>
      {(["responsible", "coordinator"] as Role[]).map((role) => (
        <label className="check" key={role}>
          <input
            type="checkbox"
            checked={value.includes(role)}
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? [...value, role]
                  : value.filter((item) => item !== role),
              )
            }
          />
          {roleNames[role]}
        </label>
      ))}
    </fieldset>
  );
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      onLogin(
        await api<User>("/auth/login", "POST", {
          email: data.get("email"),
          password: data.get("password"),
        }),
      );
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-layout">
      <section className="login-story" aria-labelledby="login-story-title">
        <div className="service-wordmark">
          фидбек<span aria-hidden="true">.</span>
        </div>
        <h1 id="login-story-title">
          Есть что изменить.
          <br />
          Есть кому услышать.
        </h1>
        <p className="intro">
          Проблемы и идеи о вашей работе — в одном месте. С понятным
          ответственным и ответом по существу.
        </p>
        <div className="login-principle">
          <CheckCheck aria-hidden="true" />
          <div>
            <h2>Последнее слово — за вами</h2>
            <p>
              Ответственный сообщает о результате. Вы подтверждаете, что
              помогло, или возвращаете обращение в работу.
            </p>
          </div>
        </div>
        <p className="login-identity">
          Обращения именные. Доступ — только по приглашению.
        </p>
      </section>
      <section className="card login-card" aria-labelledby="login-title">
        <h2 id="login-title">Войти в кабинет</h2>
        <p className="hint">Используйте email из приглашения.</p>
        <form onSubmit={submit} aria-busy={busy}>
          <FieldGroup>
            <Field label="Email">
              <Input
                name="email"
                placeholder="name@company.ru"
                autoCapitalize="none"
                spellCheck={false}
                type="email"
                autoComplete="username"
                required
                maxLength={254}
              />
            </Field>
            <UIField>
              <FieldLabel htmlFor="login-password">Пароль</FieldLabel>
              <InputGroup className="login-password">
                <InputGroupInput
                  id="login-password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  maxLength={128}
                />
                <InputGroupAddon align="inline-end">
                  <InputGroupButton
                    size="icon-sm"
                    aria-label={
                      showPassword ? "Скрыть пароль" : "Показать пароль"
                    }
                    aria-pressed={showPassword}
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? <EyeOff /> : <Eye />}
                  </InputGroupButton>
                </InputGroupAddon>
              </InputGroup>
            </UIField>
          </FieldGroup>
          <ErrorBox message={error} />
          <Button className="login-submit" disabled={busy}>
            {busy ? (
              <>
                <LoaderCircle
                  className="login-spinner"
                  data-icon="inline-start"
                  aria-hidden="true"
                />
                Входим…
              </>
            ) : (
              <>
                Войти
                <ArrowRight data-icon="inline-end" aria-hidden="true" />
              </>
            )}
          </Button>
        </form>
        <p className="hint note">
          Нет доступа или забыли пароль?
          <span className="login-help">
            Обратитесь к координатору вашей компании.
          </span>
        </p>
      </section>
    </div>
  );
}

type Preview = {
  name: string;
  email: string;
  company: string;
  department: string;
  roles: Role[];
  expires_at: string;
};
function Activate({ onLogin }: { onLogin: (user: User) => void }) {
  const [token] = useState(
    () => new URLSearchParams(location.hash.slice(1)).get("token") || "",
  );
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    // Keep the token only in this component after reading the link.
    history.replaceState(null, "", "/invite");
    if (!token) {
      setLoadError(
        "В ссылке нет приглашения. Попросите координатора выдать новую ссылку.",
      );
      return;
    }
    api<Preview>("/auth/invitation", "POST", { token })
      .then(setPreview)
      .catch((error) => setLoadError(error.message));
  }, [token]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setError("");
    if (data.get("password") !== data.get("confirmation")) {
      setError("Пароли не совпадают");
      return;
    }
    setBusy(true);
    try {
      const user = await api<User>("/auth/accept", "POST", {
        token,
        password: data.get("password"),
      });
      history.replaceState(null, "", "/");
      onLogin(user);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card activation">
      <h1>Добро пожаловать</h1>
      {loadError ? (
        <>
          <ErrorBox message={loadError} />
          <a href="/">Перейти ко входу</a>
        </>
      ) : !preview ? (
        <p role="status">Проверяем приглашение…</p>
      ) : (
        <>
          <h2>{preview.name}</h2>
          <p>
            {preview.company} · {preview.department}
          </p>
          <p className="hint">
            {preview.email} ·{" "}
            {preview.roles.map((role) => roleNames[role]).join(", ")}
          </p>
          <p className="hint">
            Приглашение действует до{" "}
            {new Date(preview.expires_at).toLocaleString("ru-RU")}.
          </p>
          <form onSubmit={submit}>
            <Field label="Придумайте пароль">
              <input
                name="password"
                type="password"
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                required
                aria-describedby="password-help"
              />
            </Field>
            <p id="password-help" className="hint">
              От 12 до 128 символов. Можно использовать парольную фразу.
            </p>
            <Field label="Повторите пароль">
              <input
                name="confirmation"
                type="password"
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
                required
              />
            </Field>
            <ErrorBox message={error} />
            <Button variant="outline" className="primary" disabled={busy}>
              {busy ? "Создаём аккаунт…" : "Активировать и войти"}
            </Button>
          </form>
        </>
      )}
    </section>
  );
}

function UserRow({
  user,
  self,
  company,
  department,
  onUpdate,
}: {
  user: User;
  self: boolean;
  company?: string;
  department?: string;
  onUpdate: (user: User) => void;
}) {
  const [roles, setRoles] = useState(user.roles);
  const [active, setActive] = useState(user.is_active);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const changed =
    [...roles].sort().join() !== [...user.roles].sort().join() ||
    active !== user.is_active;
  async function save() {
    setBusy(true);
    setError("");
    try {
      const updated = await api<User>("/admin/users/" + user.id, "PATCH", {
        roles,
        is_active: active,
      });
      setRoles(updated.roles);
      setActive(updated.is_active);
      onUpdate(updated);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="team-user">
      <div className="team-user-summary">
        <div>
          <h3>
            {user.name} {self && <Badge variant="secondary">Вы</Badge>}
          </h3>
          <p>{user.email}</p>
          <p className="hint">
            {company} · {department}
          </p>
        </div>
        <div className="team-user-status">
          <Badge variant="secondary">
            {user.is_active ? "Активен" : "Доступ закрыт"}
          </Badge>
          <p className="hint">
            {user.roles.map((role) => roleNames[role]).join(", ")}
          </p>
        </div>
      </div>
      <details className="team-access">
        <summary>
          <span>Настроить доступ{changed ? " · есть изменения" : ""}</span>
          <ChevronDown aria-hidden="true" />
        </summary>
        <fieldset disabled={busy} className="team-access-fields">
          <RoleFields value={roles} onChange={setRoles} />
          <label className="check">
            <input
              type="checkbox"
              checked={active}
              onChange={(event) => setActive(event.target.checked)}
            />
            Доступ разрешён
          </label>
          <p className="hint">
            Закрытие доступа завершает все сессии сотрудника.
          </p>
          <ErrorBox message={error} />
          <div className="team-save-actions">
            <Button disabled={busy || !changed} onClick={save}>
              {busy ? "Сохраняем…" : "Сохранить доступ"}
            </Button>
            <Button
              variant="ghost"
              disabled={busy || !changed}
              onClick={() => {
                setRoles(user.roles);
                setActive(user.is_active);
                setError("");
              }}
            >
              Отменить изменения
            </Button>
          </div>
        </fieldset>
      </details>
    </article>
  );
}

function Admin({
  current,
  onSelfUpdate,
}: {
  current: User;
  onSelfUpdate: (user: User) => void;
}) {
  const [tab, setTab] = useState("invitations");
  const [userSearch, setUserSearch] = useState("");
  const [companies, setCompanies] = useState<Company[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [roles, setRoles] = useState<Role[]>(["employee"]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [link, setLink] = useState("");
  const [notice, setNotice] = useState("");
  async function load() {
    try {
      const [c, d, u, i] = await Promise.all([
        api<Company[]>("/directory/companies"),
        api<Department[]>("/directory/departments"),
        api<User[]>("/admin/users"),
        api<Invitation[]>("/admin/invitations"),
      ]);
      setCompanies(c);
      setDepartments(d);
      setUsers(u);
      setInvites(i);
      setCompanyId((value) => value || c[0]?.id || "");
      setReady(true);
    } catch (error) {
      setError((error as Error).message);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    setLink("");
    setNotice("");
    try {
      const result = await api<Invitation & { activation_path: string }>(
        "/admin/invitations",
        "POST",
        {
          name: data.get("name"),
          email: data.get("email"),
          company_id: companyId,
          department_id: data.get("department"),
          roles,
          expires_in_days: Number(data.get("days")),
        },
      );
      setLink(location.origin + result.activation_path);
      form.reset();
      setRoles(["employee"]);
      await load();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: string) {
    setBusy(true);
    setError("");
    try {
      await api("/admin/invitations/" + id + "/revoke", "POST");
      setLink("");
      setNotice("Приглашение отозвано.");
      await load();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function directory(
    event: FormEvent<HTMLFormElement>,
    type: "companies" | "departments",
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api("/admin/" + type, "POST", {
        name: data.get("name"),
        ...(type === "departments" ? { company_id: data.get("company") } : {}),
      });
      form.reset();
      setNotice(
        type === "companies"
          ? "Компания добавлена."
          : "Подразделение добавлено.",
      );
      await load();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const companyName = (id: string) =>
    companies.find((company) => company.id === id)?.name;
  const departmentName = (id: string) =>
    departments.find((department) => department.id === id)?.name;
  return (
    <section className="team-admin">
      <Tabs
        value={tab}
        onValueChange={(value) => {
          setTab(value);
          setError("");
          setNotice("");
        }}
        className="team-tabs"
      >
        <TabsList aria-label="Управление командой">
          <TabsTrigger value="invitations">Приглашения</TabsTrigger>
          <TabsTrigger value="users">Сотрудники</TabsTrigger>
          <TabsTrigger value="directory">Структура компании</TabsTrigger>
        </TabsList>
        <TabsContent value={tab}>
          <ErrorBox message={error} />
          {notice && (
            <p role="status" className="success">
              {notice}
            </p>
          )}
          {!ready && error ? (
            <Button variant="outline" onClick={() => void load()}>
              Повторить загрузку команды
            </Button>
          ) : !ready ? (
            <div
              className="employee-loading"
              role="status"
              aria-label="Загружаем команду"
            >
              <Skeleton />
              <Skeleton />
            </div>
          ) : (
            <>
              {tab === "invitations" && (
                <>
                  <div className="admin-grid">
                    <section className="card">
                      <h2>Пригласить сотрудника</h2>
                      <p className="hint">
                        Ссылка одноразовая. Отправьте её сотруднику лично.
                      </p>
                      <form onSubmit={invite} aria-busy={busy}>
                        <fieldset disabled={busy} className="invitation-fields">
                          <FieldGroup>
                            <Field label="Имя и фамилия">
                              <Input name="name" required maxLength={160} />
                            </Field>
                            <Field label="Email">
                              <Input
                                name="email"
                                type="email"
                                required
                                maxLength={254}
                              />
                            </Field>
                            <Field label="Компания">
                              <select
                                value={companyId}
                                onChange={(event) =>
                                  setCompanyId(event.target.value)
                                }
                                required
                              >
                                {companies.map((company) => (
                                  <option key={company.id} value={company.id}>
                                    {company.name}
                                  </option>
                                ))}
                              </select>
                            </Field>
                            <Field label="Подразделение">
                              <select
                                name="department"
                                key={companyId}
                                required
                                defaultValue=""
                              >
                                <option value="" disabled>
                                  Выберите подразделение
                                </option>
                                {departments
                                  .filter(
                                    (department) =>
                                      department.company_id === companyId,
                                  )
                                  .map((department) => (
                                    <option
                                      key={department.id}
                                      value={department.id}
                                    >
                                      {department.name}
                                    </option>
                                  ))}
                              </select>
                            </Field>
                            <RoleFields value={roles} onChange={setRoles} />
                            <Field label="Срок действия">
                              <select name="days" defaultValue="7">
                                <option value="1">1 день</option>
                                <option value="7">7 дней</option>
                                <option value="30">30 дней</option>
                              </select>
                            </Field>
                          </FieldGroup>
                          <Button disabled={busy}>
                            <UserPlus
                              data-icon="inline-start"
                              aria-hidden="true"
                            />
                            {busy ? "Создаём…" : "Создать приглашение"}
                          </Button>
                        </fieldset>
                      </form>
                    </section>
                    <aside className="invitation-guide">
                      <h2>Приглашение — личная ссылка</h2>
                      <p>
                        Сотрудник проверит данные и задаст пароль. Передайте
                        ссылку ему лично.
                      </p>
                      <p className="hint note">
                        Ссылка показывается только при создании. Если потеряли
                        её — отзовите приглашение и создайте новое.
                      </p>
                      {link && (
                        <div className="link-result">
                          <Field label="Ссылка приглашения">
                            <Input
                              value={link}
                              readOnly
                              onFocus={(event) => event.currentTarget.select()}
                            />
                          </Field>
                          <Button
                            variant="outline"
                            onClick={async () => {
                              try {
                                await navigator.clipboard.writeText(link);
                                setNotice("Ссылка скопирована.");
                              } catch {
                                setNotice(
                                  "Выделите ссылку и скопируйте вручную.",
                                );
                              }
                            }}
                          >
                            <Copy data-icon="inline-start" aria-hidden="true" />
                            Скопировать ссылку
                          </Button>
                        </div>
                      )}
                    </aside>
                  </div>
                  <section className="card section-gap">
                    <h2>
                      Выданные приглашения{" "}
                      <span className="count">{invites.length}</span>
                    </h2>
                    {!invites.length ? (
                      <Empty>
                        <EmptyHeader>
                          <EmptyTitle>Пока никто не приглашён</EmptyTitle>
                          <EmptyDescription>
                            Создайте личное приглашение в форме выше. Здесь
                            появится его статус.
                          </EmptyDescription>
                        </EmptyHeader>
                      </Empty>
                    ) : (
                      <div className="invites">
                        {invites.map((invite) => {
                          const pending =
                            !invite.used_at &&
                            !invite.revoked_at &&
                            new Date(invite.expires_at) > new Date();
                          const status = invite.used_at
                            ? "Использовано"
                            : invite.revoked_at
                              ? "Отозвано"
                              : pending
                                ? "Ожидает активации"
                                : "Истекло";
                          return (
                            <article className="invite-row" key={invite.id}>
                              <div>
                                <h3>{invite.name}</h3>
                                <p>{invite.email}</p>
                                <p className="hint">
                                  {companyName(invite.company_id)} ·{" "}
                                  {departmentName(invite.department_id)}
                                </p>
                                <p className="hint">
                                  До{" "}
                                  {new Date(invite.expires_at).toLocaleString(
                                    "ru-RU",
                                  )}
                                </p>
                              </div>
                              <div>
                                <Badge variant="secondary">{status}</Badge>
                                {pending && (
                                  <Button
                                    variant="outline"
                                    disabled={busy}
                                    onClick={() => revoke(invite.id)}
                                  >
                                    Отозвать
                                  </Button>
                                )}
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    )}
                  </section>
                </>
              )}
              {tab === "users" && (
                <section className="card">
                  <h2>
                    Сотрудники <span className="count">{users.length}</span>
                  </h2>
                  <p className="hint">
                    Блокировка завершает все сессии сотрудника. Роли можно
                    совмещать.
                  </p>
                  <UIField className="team-search">
                    <FieldLabel htmlFor="team-search">
                      Поиск сотрудника
                    </FieldLabel>
                    <Input
                      id="team-search"
                      value={userSearch}
                      onChange={(event) => setUserSearch(event.target.value)}
                      placeholder="Имя или email"
                      maxLength={200}
                    />
                  </UIField>
                  {!users.some((item) =>
                    `${item.name} ${item.email}`
                      .toLocaleLowerCase("ru")
                      .includes(userSearch.trim().toLocaleLowerCase("ru")),
                  ) && (
                    <Empty>
                      <EmptyHeader>
                        <EmptyTitle>Сотрудник не найден</EmptyTitle>
                        <EmptyDescription>
                          Попробуйте другое имя или email.
                        </EmptyDescription>
                      </EmptyHeader>
                    </Empty>
                  )}
                  {users
                    .filter((item) =>
                      `${item.name} ${item.email}`
                        .toLocaleLowerCase("ru")
                        .includes(userSearch.trim().toLocaleLowerCase("ru")),
                    )
                    .map((user) => (
                      <UserRow
                        key={user.id}
                        user={user}
                        self={current.id === user.id}
                        company={companyName(user.company_id)}
                        department={departmentName(user.department_id)}
                        onUpdate={(updated) => {
                          setUsers((value) =>
                            value.map((item) =>
                              item.id === updated.id ? updated : item,
                            ),
                          );
                          if (updated.id === current.id) onSelfUpdate(updated);
                        }}
                      />
                    ))}
                </section>
              )}
              {tab === "directory" && (
                <div className="admin-grid">
                  <section className="card">
                    <h2>Компании</h2>
                    <ul className="directory-list">
                      {companies.map((company) => (
                        <li key={company.id}>{company.name}</li>
                      ))}
                    </ul>
                    <form onSubmit={(event) => directory(event, "companies")}>
                      <FieldGroup>
                        <Field label="Название новой компании">
                          <Input name="name" required maxLength={160} />
                        </Field>
                      </FieldGroup>
                      <Button variant="outline" disabled={busy}>
                        Добавить компанию
                      </Button>
                    </form>
                  </section>
                  <section className="card">
                    <h2>Подразделения</h2>
                    <ul className="directory-list">
                      {departments.map((department) => (
                        <li key={department.id}>
                          {department.name}
                          <small>{companyName(department.company_id)}</small>
                        </li>
                      ))}
                    </ul>
                    <form onSubmit={(event) => directory(event, "departments")}>
                      <FieldGroup>
                        <Field label="Компания">
                          <select name="company" required>
                            {companies.map((company) => (
                              <option key={company.id} value={company.id}>
                                {company.name}
                              </option>
                            ))}
                          </select>
                        </Field>
                        <Field label="Название нового подразделения">
                          <Input name="name" required maxLength={160} />
                        </Field>
                      </FieldGroup>
                      <Button variant="outline" disabled={busy}>
                        Добавить подразделение
                      </Button>
                    </form>
                  </section>
                </div>
              )}
            </>
          )}
        </TabsContent>
      </Tabs>
    </section>
  );
}

function App() {
  const path = usePath();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [logoutBusy, setLogoutBusy] = useState(false);
  const [activation] = useState(location.pathname === "/invite");
  useEffect(() => {
    if (activation) {
      setLoading(false);
      return;
    }
    loginFromTelegram()
      .then((telegramUser) => telegramUser || api<User>("/auth/me"))
      .then(setUser)
      .catch((error) => {
        if (
          location.pathname.startsWith("/mini") ||
          !(error instanceof ApiError) ||
          error.status !== 401
        )
          setError(
            error instanceof Error
              ? error.message
              : "Сервис временно недоступен. Обновите страницу.",
          );
      })
      .finally(() => setLoading(false));
  }, [activation]);
  async function logout() {
    setLogoutBusy(true);
    try {
      await api("/auth/logout", "POST");
      setUser(null);
      history.replaceState(null, "", "/");
      location.assign("/");
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setLogoutBusy(false);
    }
  }
  return (
    <div className={user ? "shell authenticated" : "shell guest"}>
      <header>
        <a className="brand" href="/" aria-label="Модус Трейд — главная">
          <span className="mark">
            <MessageSquare aria-hidden="true" />
          </span>
          <span>
            МОДУС ТРЕЙД<small>фидбек / обратная связь</small>
          </span>
        </a>
        {user ? (
          <div className="header-user">
            <span>{user.name}</span>
            <Notifications key={user.id} />
            <Button variant="outline" onClick={() => navigate("/settings")}>
              Telegram
            </Button>
            <Button variant="outline" disabled={logoutBusy} onClick={logout}>
              {logoutBusy ? "Выходим…" : "Выйти"}
            </Button>
          </div>
        ) : (
          <span className="service-label">Сервис для сотрудников</span>
        )}
      </header>
      <main>
        <ErrorBox message={error} />
        {loading ? (
          <div
            role="status"
            aria-label="Загружаем кабинет"
            className="loading-workspace"
          >
            <Skeleton className="loading-title" />
            <Skeleton className="loading-row" />
            <Skeleton className="loading-row" />
          </div>
        ) : user ? (
          <>
            {(user.roles.includes("coordinator") ||
              user.roles.includes("responsible")) && (
              <nav className="tabs workspace-nav" aria-label="Разделы кабинета">
                <Button
                  variant="outline"
                  aria-current={
                    !path.startsWith("/team") &&
                    !path.startsWith("/queue") &&
                    !path.startsWith("/impact") &&
                    !path.startsWith("/settings")
                      ? "page"
                      : undefined
                  }
                  onClick={() => navigate("/appeals")}
                >
                  Мои обращения
                </Button>
                <Button
                  variant="outline"
                  aria-current={path.startsWith("/queue") ? "page" : undefined}
                  onClick={() => navigate("/queue")}
                >
                  {user.roles.includes("coordinator")
                    ? "Очередь обращений"
                    : "Назначенные мне"}
                </Button>
                <Button
                  variant="outline"
                  aria-current={path.startsWith("/impact") ? "page" : undefined}
                  onClick={() => navigate("/impact")}
                >
                  Эффект
                </Button>
                {user.roles.includes("coordinator") && (
                  <Button
                    variant="outline"
                    aria-current={path.startsWith("/team") ? "page" : undefined}
                    onClick={() => navigate("/team")}
                  >
                    Управление командой
                  </Button>
                )}
              </nav>
            )}
            {path === "/settings" ? (
              <TelegramSettings />
            ) : path.startsWith("/team") &&
              user.roles.includes("coordinator") ? (
              <>
                <div className="page-heading">
                  <h1>Команда</h1>
                  <p className="hint">
                    Приглашения, роли и структура компании.
                  </p>
                </div>
                <Admin
                  current={user}
                  onSelfUpdate={(updated) => {
                    if (!updated.is_active) void logout();
                    else setUser(updated);
                  }}
                />
              </>
            ) : path.startsWith("/queue") &&
              (user.roles.includes("coordinator") ||
                user.roles.includes("responsible")) ? (
              <WorkQueue user={user} />
            ) : path === "/impact" &&
              (user.roles.includes("coordinator") ||
                user.roles.includes("responsible")) ? (
              <Impact user={user} />
            ) : (
              <Appeals user={user} />
            )}
          </>
        ) : activation ? (
          <Activate onLogin={setUser} />
        ) : (
          <Login onLogin={setUser} />
        )}
      </main>
      <footer>
        <span>Модус Трейд</span>
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

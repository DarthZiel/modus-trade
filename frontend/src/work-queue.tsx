import { Tabs, TabsList, TabsTrigger, TabsContent } from "./components/ui/tabs";
import { Field, FieldGroup, FieldLabel } from "./components/ui/field";
import { Input } from "./components/ui/input";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
} from "./components/ui/empty";
import { Skeleton } from "./components/ui/skeleton";
import { RefreshCw, ArrowRight, ChevronDown } from "lucide-react";
import { Button } from "./components/ui/button";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "./api";
import type { Company, Department, User } from "./api";
import { AppealCard, date, openLink, Status, statusNames } from "./appeals";
import type { Summary } from "./appeals";
import type { Responsible } from "./assignment";
import { usePath } from "./navigation";

type Page = {
  items: Summary[];
  total: number;
  page: number;
  page_size: number;
};
type Filters = {
  filter: string;
  status: string;
  kind: string;
  company_id: string;
  department_id: string;
  responsible_id: string;
  q: string;
};
const emptyFilters: Filters = {
  filter: "all",
  status: "",
  kind: "",
  company_id: "",
  department_id: "",
  responsible_id: "",
  q: "",
};
function QueueList({ user }: { user: User }) {
  const coordinator = user.roles.includes("coordinator");
  const [overviewError, setOverviewError] = useState(false);
  const [overview, setOverview] = useState<Record<string, number>>();
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<Page | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setOverviewError(false);
    api<Record<string, number>>("/work/overview")
      .then((value) => {
        if (active) setOverview(value);
      })
      .catch(() => {
        if (active) setOverviewError(true);
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [responsibles, setResponsibles] = useState<Responsible[]>([]);
  const [directoryError, setDirectoryError] = useState("");
  useEffect(() => {
    if (!coordinator) return;
    let cancelled = false;
    setDirectoryError("");
    Promise.all([
      api<Company[]>("/directory/companies"),
      api<Department[]>("/directory/departments"),
      api<Responsible[]>("/work/responsibles"),
    ])
      .then(([c, d, r]) => {
        if (!cancelled) {
          setCompanies(c);
          setDepartments(d);
          setResponsibles(r);
        }
      })
      .catch((error) => {
        if (!cancelled) setDirectoryError(error.message);
      });
    return () => {
      cancelled = true;
    };
  }, [coordinator, attempt]);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    const query = new URLSearchParams({ page: String(page) });
    Object.entries(filters).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    api<Page>("/work/appeals?" + query)
      .then((data) => {
        if (!cancelled) setResult(data);
      })
      .catch((error) => {
        if (!cancelled) setError(error.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [filters, page, attempt]);
  function change(key: keyof Filters, value: string) {
    setFilters((previous) => ({
      ...previous,
      [key]: value,
      ...(key === "company_id" ? { department_id: "" } : {}),
    }));
    setPage(1);
  }
  function submitSearch(event: FormEvent) {
    event.preventDefault();
    change("q", search.trim());
  }
  const scopes = coordinator
    ? [
        ["all", "Все"],
        ["mine", "Назначенные мне"],
        ["unassigned", "Без ответственного"],
        ["overdue", "Просроченные"],
        ["awaiting_confirmation", "Ожидают подтверждения"],
      ]
    : [
        ["all", "Назначенные мне"],
        ["overdue", "Просроченные"],
        ["awaiting_confirmation", "Ожидают подтверждения"],
      ];
  return (
    <section className="coordinator-queue">
      <div className="appeal-heading">
        <div>
          <h1>{coordinator ? "Очередь обращений" : "Назначенные мне"}</h1>
          <p className="hint">
            {coordinator
              ? "Распределяйте обращения и следите за сроками ответа."
              : "Здесь обращения, за рассмотрение которых вы отвечаете."}
          </p>
        </div>
        <Button
          variant="outline"
          disabled={loading}
          onClick={() => setAttempt((value) => value + 1)}
        >
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
          Обновить
        </Button>
      </div>
      {overview && (
        <section className="queue-priorities" aria-label="Обзор работы">
          <div className="queue-priority-links">
            {coordinator && (
              <Button
                variant="outline"
                aria-pressed={filters.filter === "unassigned"}
                onClick={() => change("filter", "unassigned")}
              >
                <span>Без ответственного</span>
                <strong>{overview.unassigned}</strong>
                <ArrowRight data-icon="inline-end" aria-hidden="true" />
              </Button>
            )}
            <Button
              variant="outline"
              aria-pressed={filters.filter === "overdue"}
              onClick={() => change("filter", "overdue")}
            >
              <span>Просроченные</span>
              <strong>{overview.overdue}</strong>
              <ArrowRight data-icon="inline-end" aria-hidden="true" />
            </Button>
          </div>
          <p className="queue-summary">
            <span>Идёт экспериментов: <strong>{overview.active_experiments}</strong></span>
            <span>
              Ждут подтверждения:{" "}
              <strong>{overview.awaiting_confirmation}</strong>
            </span>
            <span>
              Подтверждено авторами: <strong>{overview.confirmed}</strong>
            </span>
          </p>
          <p className="queue-overview-note">
            Обзор всей доступной очереди. Фильтры ниже меняют только список.
          </p>
        </section>
      )}
      {overviewError && (
        <p className="hint" role="status">
          Обзор временно недоступен. Список обращений можно использовать; кнопка
          «Обновить» повторит загрузку.
        </p>
      )}
      <Tabs
        value={filters.filter}
        onValueChange={(value) => change("filter", value)}
        className="queue-scope-tabs"
      >
        <TabsList aria-label="Разделы очереди">
          {scopes.map(([key, label]) => (
            <TabsTrigger key={key} value={key}>
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value={filters.filter} aria-busy={loading}>
          <section className="card queue-filters" aria-label="Поиск и фильтры">
            <form className="queue-search" onSubmit={submitSearch}>
              <Field>
                <FieldLabel htmlFor="queue-search">
                  Поиск по номеру, тексту или автору
                </FieldLabel>
                <div className="queue-search-controls">
                  <Input
                    id="queue-search"
                    value={search}
                    maxLength={200}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Номер, тема или имя сотрудника"
                  />
                  <Button variant="outline">Найти</Button>
                </div>
              </Field>
            </form>
            <details className="queue-advanced">
              <summary>
                <span>
                  Дополнительные фильтры
                  {Object.entries(filters).filter(
                    ([key, value]) => !["filter", "q"].includes(key) && value,
                  ).length > 0 &&
                    ` · выбрано: ${Object.entries(filters).filter(([key, value]) => !["filter", "q"].includes(key) && value).length}`}
                </span>
                <ChevronDown aria-hidden="true" />
              </summary>
              <FieldGroup className="queue-filter-grid">
                <Field>
                  <FieldLabel htmlFor="queue-status">Статус</FieldLabel>
                  <select
                    id="queue-status"
                    value={filters.status}
                    onChange={(event) => change("status", event.target.value)}
                  >
                    <option value="">Любой</option>
                    {Object.entries(statusNames).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field>
                  <FieldLabel htmlFor="queue-kind">Тип</FieldLabel>
                  <select
                    id="queue-kind"
                    value={filters.kind}
                    onChange={(event) => change("kind", event.target.value)}
                  >
                    <option value="">Любой</option>
                    <option value="problem">Проблема</option>
                    <option value="idea">Идея</option>
                  </select>
                </Field>
                {coordinator && (
                  <>
                    <Field>
                      <FieldLabel htmlFor="queue-company">Компания</FieldLabel>
                      <select
                        id="queue-company"
                        value={filters.company_id}
                        onChange={(event) =>
                          change("company_id", event.target.value)
                        }
                      >
                        <option value="">Все компании</option>
                        {companies.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="queue-department">
                        Подразделение
                      </FieldLabel>
                      <select
                        id="queue-department"
                        value={filters.department_id}
                        onChange={(event) =>
                          change("department_id", event.target.value)
                        }
                      >
                        <option value="">Все подразделения</option>
                        {departments
                          .filter(
                            (item) =>
                              !filters.company_id ||
                              item.company_id === filters.company_id,
                          )
                          .map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.name}
                            </option>
                          ))}
                      </select>
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="queue-responsible">
                        Ответственный
                      </FieldLabel>
                      <select
                        id="queue-responsible"
                        value={filters.responsible_id}
                        onChange={(event) =>
                          change("responsible_id", event.target.value)
                        }
                      >
                        <option value="">Любой</option>
                        {responsibles.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}
                          </option>
                        ))}
                      </select>
                    </Field>
                  </>
                )}
              </FieldGroup>
            </details>
            <Button
              variant="ghost"
              disabled={
                !Object.entries(filters).some(([key, value]) =>
                  key === "filter" ? value !== "all" : !!value,
                ) && !search
              }
              onClick={() => {
                setFilters(emptyFilters);
                setSearch("");
                setPage(1);
              }}
            >
              Сбросить фильтры
            </Button>
            {directoryError && (
              <p role="alert" className="error">
                Не удалось загрузить справочники: {directoryError}
              </p>
            )}
          </section>
          {error ? (
            <>
              <p role="alert" className="error">
                {error}
              </p>
              <Button
                variant="outline"
                onClick={() => setAttempt((value) => value + 1)}
              >
                Повторить загрузку
              </Button>
            </>
          ) : loading ? (
            <div
              className="employee-loading queue-loading"
              role="status"
              aria-label="Загружаем очередь"
            >
              <Skeleton />
              <Skeleton />
              <Skeleton />
            </div>
          ) : (
            result && (
              <>
                <p className="hint list-total section-gap" role="status">
                  Найдено обращений: {result.total}
                </p>
                {result.items.length ? (
                  <>
                    <div className="queue-table-wrap">
                      <table className="queue-table">
                        <caption className="sr-only">
                          Очередь обращений с автором, статусом, ответственным и
                          следующим шагом
                        </caption>
                        <thead>
                          <tr>
                            <th>Обращение</th>
                            <th>Автор / подразделение</th>
                            <th>Статус</th>
                            <th>Ответственный</th>
                            <th>Следующий шаг</th>
                          </tr>
                        </thead>
                        <tbody>
                          {result.items.map((item) => (
                            <tr key={item.id}>
                              <td data-label="Обращение">
                                <a
                                  href={`/queue/${item.id}`}
                                  onClick={(event) =>
                                    openLink(event, `/queue/${item.id}`)
                                  }
                                >
                                  <small>
                                    {item.number} ·{" "}
                                    {item.kind === "problem"
                                      ? "Проблема"
                                      : "Идея"}
                                  </small>
                                  <strong>{item.title}</strong>
                                </a>
                                <small>{date(item.created_at)}</small>
                              </td>
                              <td data-label="Автор / подразделение">
                                {item.author}
                                <small>
                                  {item.company} · {item.department}
                                </small>
                              </td>
                              <td data-label="Статус">
                                <Status status={item.status} />
                              </td>
                              <td data-label="Ответственный">
                                {item.responsible || "Не назначен"}
                                {item.responsible_available === false &&
                                  ![
                                    "closed",
                                    "rejected",
                                    "awaiting_confirmation",
                                  ].includes(item.status) && (
                                    <small className="field-error">
                                      Недоступен — требуется переназначение
                                    </small>
                                  )}
                              </td>
                              <td data-label="Следующий шаг">
                                {["closed", "rejected"].includes(item.status)
                                  ? "Рассмотрение завершено"
                                  : item.status === "awaiting_confirmation"
                                    ? "Подтверждение автора"
                                    : item.status === "needs_info"
                                      ? "Уточнение от автора"
                                      : !item.responsible
                                        ? "Назначить ответственного"
                                        : item.next_response_at
                                          ? date(item.next_response_at)
                                          : "Назначить срок ответа"}
                                {item.is_overdue && (
                                  <span className="overdue-tag">
                                    Просрочено
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {result.total > result.page_size && (
                      <div className="pagination">
                        <Button
                          variant="outline"
                          disabled={page === 1}
                          onClick={() => setPage((value) => value - 1)}
                        >
                          Назад
                        </Button>
                        <span>
                          Страница {page} из{" "}
                          {Math.max(
                            1,
                            Math.ceil(result.total / result.page_size),
                          )}
                        </span>
                        <Button
                          variant="outline"
                          disabled={page * result.page_size >= result.total}
                          onClick={() => setPage((value) => value + 1)}
                        >
                          Далее
                        </Button>
                      </div>
                    )}
                  </>
                ) : (
                  <Empty className="queue-empty">
                    <EmptyHeader>
                      <EmptyTitle>В этом разделе обращений нет</EmptyTitle>
                      <EmptyDescription>
                        Измените условия поиска или покажите всю доступную
                        очередь.
                      </EmptyDescription>
                    </EmptyHeader>
                    <EmptyContent>
                      <Button
                        variant="outline"
                        onClick={() => {
                          setFilters(emptyFilters);
                          setSearch("");
                          setPage(1);
                        }}
                      >
                        Показать все обращения
                      </Button>
                    </EmptyContent>
                  </Empty>
                )}
              </>
            )
          )}
        </TabsContent>
      </Tabs>
    </section>
  );
}
export function WorkQueue({ user }: { user: User }) {
  const path = usePath();
  const match = /^\/queue\/([1-9]\d*)$/.exec(path);
  return match ? (
    <AppealCard
      key={Number(match[1])}
      id={Number(match[1])}
      notice=""
      user={user}
      backPath="/queue"
    />
  ) : (
    <QueueList user={user} />
  );
}

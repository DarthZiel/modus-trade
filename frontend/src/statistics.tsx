import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "./api";
import type { Company, Department } from "./api";
import { categories, date, openLink, Status } from "./appeals";
import { TopicList } from "./similarities";
import type { RelatedAppeal, Topic } from "./similarities";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Field, FieldGroup, FieldLabel } from "./components/ui/field";
import { Alert, AlertDescription } from "./components/ui/alert";
import { Skeleton } from "./components/ui/skeleton";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "./components/ui/empty";
import { ArrowDown, RefreshCw } from "lucide-react";

type CountItem = { key: string; count: number };
type StatisticAppeal = RelatedAppeal & {
  kind: string;
  category: string;
  company_id: string;
  department_id: string;
  first_response_at: string | null;
  overdue: boolean;
  confirmed: boolean;
  reopened: boolean;
};
type StatisticsResult = {
  date_from: string;
  date_to: string;
  generated_at: string;
  total: number;
  answered: number;
  unanswered: number;
  overdue: number;
  confirmed: number;
  awaiting_confirmation: number;
  rejected: number;
  reopened: number;
  confirmed_percent: number | null;
  average_first_response_hours: number | null;
  kinds: CountItem[];
  categories: CountItem[];
  trend: { date: string; received: number; confirmed: number }[];
  topics: Topic[];
  appeals: StatisticAppeal[];
};
type Metric =
  | "all"
  | "answered"
  | "unanswered"
  | "overdue"
  | "confirmed"
  | "reopened"
  | "rejected"
  | "awaiting_confirmation";
const labels: Record<Metric, string> = {
  all: "Все обращения",
  answered: "Получили ответ",
  unanswered: "Без первого ответа",
  overdue: "Просрочены",
  confirmed: "Решено с подтверждением",
  reopened: "Возвращались в работу",
  rejected: "Отклонены",
  awaiting_confirmation: "Ожидают подтверждения",
};
function localDay(value: Date) {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}
const today = () => localDay(new Date());
function initialFrom() {
  const value = new Date();
  value.setDate(value.getDate() - 29);
  return localDay(value);
}
function dayLabel(value: string) {
  return new Date(value + "T12:00:00").toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
  });
}
function duration(hours: number | null) {
  if (hours === null) return "Нет данных";
  if (hours < 1) return `${Math.round(hours * 60)} мин`;
  if (hours >= 24)
    return `${(hours / 24).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} дн`;
  return `${hours.toLocaleString("ru-RU", { maximumFractionDigits: 1 })} ч`;
}

export function Statistics({
  appealBasePath = "/queue",
  embedded = false,
}: { appealBasePath?: string; embedded?: boolean } = {}) {
  const Heading = embedded ? "h2" : "h1";
  const [draft, setDraft] = useState({
    date_from: initialFrom(),
    date_to: today(),
    company_id: "",
    department_id: "",
  });
  const [filters, setFilters] = useState(draft);
  const [result, setResult] = useState<StatisticsResult>();
  const [companies, setCompanies] = useState<Company[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [error, setError] = useState("");
  const [directoryError, setDirectoryError] = useState("");
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [metric, setMetric] = useState<Metric>("all");
  const [category, setCategory] = useState("");
  const [kind, setKind] = useState("");
  const [limit, setLimit] = useState(20);
  useEffect(() => {
    let active = true;
    setDirectoryError("");
    Promise.all([
      api<Company[]>("/directory/companies"),
      api<Department[]>("/directory/departments"),
    ])
      .then(([c, d]) => {
        if (active) {
          setCompanies(c);
          setDepartments(d);
        }
      })
      .catch(() => {
        if (active)
          setDirectoryError(
            "Не удалось загрузить компании и подразделения. Повторите загрузку.",
          );
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setResult(undefined);
    const query = new URLSearchParams({
      date_from: filters.date_from,
      date_to: filters.date_to,
      utc_offset_minutes: String(-new Date().getTimezoneOffset()),
    });
    if (filters.company_id) query.set("company_id", filters.company_id);
    if (filters.department_id)
      query.set("department_id", filters.department_id);
    api<StatisticsResult>("/work/statistics?" + query)
      .then((value) => {
        if (active) setResult(value);
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [filters, attempt]);
  function submit(event: FormEvent) {
    event.preventDefault();
    setFilters({ ...draft });
    setMetric("all");
    setCategory("");
    setKind("");
    setLimit(20);
  }
  function drilldown(next: Metric, nextCategory = "", nextKind = "") {
    setMetric(next);
    setCategory(nextCategory);
    setKind(nextKind);
    setLimit(20);
    requestAnimationFrame(() => {
      const element = document.getElementById("statistic-appeals");
      element?.scrollIntoView({ block: "start" });
      element?.focus({ preventScroll: true });
    });
  }
  const filtered =
    result?.appeals.filter(
      (item) =>
        (metric === "all" ||
          (metric === "answered"
            ? !!item.first_response_at
            : metric === "unanswered"
              ? !item.first_response_at
              : metric === "rejected"
                ? item.status === "rejected"
                : metric === "awaiting_confirmation"
                  ? item.status === "awaiting_confirmation"
                  : item[metric])) &&
        (!category || item.category === category) &&
        (!kind || item.kind === kind),
    ) || [];
  return (
    <section className="insights-page">
      <div className="appeal-heading">
        <div>
          <Heading>Статистика</Heading>
          <p className="hint">
            Как быстро отвечаем сотрудникам и какие обращения доводим до
            результата.
          </p>
        </div>
        <Button
          variant="outline"
          disabled={loading}
          onClick={() => setAttempt((n) => n + 1)}
        >
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
          Обновить
        </Button>
      </div>
      <form className="statistics-filters" onSubmit={submit}>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="stats-from">С даты подачи</FieldLabel>
            <Input
              id="stats-from"
              type="date"
              required
              max={draft.date_to || today()}
              value={draft.date_from}
              onChange={(event) =>
                setDraft({ ...draft, date_from: event.target.value })
              }
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="stats-to">По дату включительно</FieldLabel>
            <Input
              id="stats-to"
              type="date"
              required
              min={draft.date_from}
              max={today()}
              value={draft.date_to}
              onChange={(event) =>
                setDraft({ ...draft, date_to: event.target.value })
              }
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="stats-company">Компания</FieldLabel>
            <select
              id="stats-company"
              value={draft.company_id}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  company_id: event.target.value,
                  department_id: "",
                })
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
            <FieldLabel htmlFor="stats-department">Подразделение</FieldLabel>
            <select
              id="stats-department"
              value={draft.department_id}
              onChange={(event) =>
                setDraft({ ...draft, department_id: event.target.value })
              }
            >
              <option value="">Все подразделения</option>
              {departments
                .filter(
                  (item) =>
                    !draft.company_id || item.company_id === draft.company_id,
                )
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                    {!draft.company_id
                      ? ` · ${companies.find((c) => c.id === item.company_id)?.name || ""}`
                      : ""}
                  </option>
                ))}
            </select>
          </Field>
        </FieldGroup>
        <Button disabled={loading}>Показать</Button>
      </form>
      {directoryError && (
        <Alert variant="destructive">
          <AlertDescription>
            {directoryError}{" "}
            <Button variant="link" onClick={() => setAttempt((n) => n + 1)}>
              Повторить
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>
            {error}{" "}
            <Button variant="link" onClick={() => setAttempt((n) => n + 1)}>
              Повторить
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {loading ? (
        <div
          role="status"
          aria-label="Рассчитываем статистику"
          className="statistics-loading"
        >
          <Skeleton />
          <Skeleton />
          <Skeleton />
        </div>
      ) : (
        result && (
          <>
            <p className="statistics-scope">
              Обращения, поданные {dayLabel(result.date_from)} —{" "}
              {dayLabel(result.date_to)}. Состояние на{" "}
              {date(result.generated_at)}. Границы дат — в вашем часовом поясе.
            </p>
            <dl className="statistics-metrics">
              {(
                [
                  ["all", result.total, "Проблемы и идеи за выбранный период"],
                  [
                    "answered",
                    duration(result.average_first_response_hours),
                    `Первый ответ человека · обращений: ${result.answered}`,
                  ],
                  [
                    "unanswered",
                    result.unanswered,
                    "Автоматическое уведомление не считается ответом",
                  ],
                  [
                    "overdue",
                    result.overdue,
                    "Истёк назначенный срок следующего ответа",
                  ],
                  [
                    "confirmed",
                    result.confirmed,
                    result.confirmed_percent === null
                      ? "Доля не рассчитана: нет обращений"
                      : `${result.confirmed_percent.toLocaleString("ru-RU")}% всех поступивших · подтвердили авторы`,
                  ],
                  [
                    "reopened",
                    result.reopened,
                    "Хотя бы раз вернулись после оценки автора",
                  ],
                ] as [Metric, number | string, string][]
              ).map(([key, value, description]) => (
                <div key={key}>
                  <dt>
                    {key === "answered"
                      ? "Среднее время первого ответа"
                      : labels[key]}
                  </dt>
                  <dd>
                    <Button
                      variant="ghost"
                      onClick={() => drilldown(key)}
                      aria-label={`${key === "answered" ? "Среднее время первого ответа" : labels[key]}: ${value}. Показать обращения`}
                    >
                      {value}
                      <ArrowDown data-icon="inline-end" aria-hidden="true" />
                    </Button>
                    <span className="hint">{description}</span>
                  </dd>
                </div>
              ))}
            </dl>
            <p className="statistics-secondary">
              <Button
                variant="link"
                onClick={() => drilldown("awaiting_confirmation")}
              >
                Ожидают подтверждения: {result.awaiting_confirmation}
              </Button>
              <Button variant="link" onClick={() => drilldown("rejected")}>
                Отклонены с объяснением: {result.rejected}
              </Button>
            </p>
            {!result.total ? (
              <section className="card">
                <Empty>
                  <EmptyHeader>
                    <EmptyTitle>За этот период обращений нет</EmptyTitle>
                    <EmptyDescription>
                      Измените даты или выберите другую компанию и
                      подразделение.
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
              </section>
            ) : (
              <>
                <div className="statistics-comparisons">
                  <section className="card">
                    <h2>Поступление и подтверждение</h2>
                    <p className="hint">
                      По неделям выбранного периода. Подтверждения относятся
                      только к обращениям этой выборки, которые сейчас закрыты.
                    </p>
                    <div
                      className="statistics-trend"
                      role="table"
                      aria-label="Поступление и подтверждение по неделям"
                    >
                      <div className="trend-heading" role="row">
                        <span role="columnheader">Неделя с</span>
                        <span role="columnheader">Поступило</span>
                        <span role="columnheader">Подтверждено</span>
                      </div>
                      {result.trend.map((item) => (
                        <div className="trend-row" role="row" key={item.date}>
                          <span role="cell">{dayLabel(item.date)}</span>
                          <span role="cell">
                            <meter
                              min={0}
                              max={Math.max(
                                1,
                                ...result.trend.map((v) =>
                                  Math.max(v.received, v.confirmed),
                                ),
                              )}
                              value={item.received}
                              aria-label={`Поступило за неделю с ${dayLabel(item.date)}: ${item.received}`}
                            />
                            <strong>{item.received}</strong>
                          </span>
                          <span role="cell">
                            <meter
                              min={0}
                              max={Math.max(
                                1,
                                ...result.trend.map((v) =>
                                  Math.max(v.received, v.confirmed),
                                ),
                              )}
                              value={item.confirmed}
                              aria-label={`Подтверждено за неделю с ${dayLabel(item.date)}: ${item.confirmed}`}
                            />
                            <strong>{item.confirmed}</strong>
                          </span>
                        </div>
                      ))}
                    </div>
                  </section>
                  <section className="card">
                    <h2>Типы и категории</h2>
                    <div className="statistics-kind">
                      {result.kinds.map((item) => (
                        <Button
                          key={item.key}
                          variant="outline"
                          onClick={() => drilldown("all", "", item.key)}
                        >
                          {item.key === "problem" ? "Проблемы" : "Идеи"}
                          <strong>{item.count}</strong>
                        </Button>
                      ))}
                    </div>
                    <ul className="category-distribution">
                      {result.categories.map((item) => (
                        <li key={item.key}>
                          <Button
                            variant="link"
                            onClick={() => drilldown("all", item.key)}
                          >
                            <span>
                              {categories[
                                item.key as keyof typeof categories
                              ] || item.key}
                            </span>
                            <strong>{item.count}</strong>
                          </Button>
                          <meter
                            min={0}
                            max={result.total}
                            value={item.count}
                            aria-label={`${categories[item.key as keyof typeof categories] || item.key}: ${item.count} из ${result.total}`}
                          />
                        </li>
                      ))}
                    </ul>
                  </section>
                </div>
                <section className="card section-gap">
                  <h2>Повторяющиеся проблемы · {result.topics.length}</h2>
                  <p className="hint">
                    Только связи «Одна проблема», подтверждённые координатором.
                    Состав групп ограничен выбранным периодом и подразделением.
                  </p>
                  <TopicList
                    topics={result.topics}
                    appealBasePath={appealBasePath}
                  />
                </section>
                <section
                  className="card section-gap statistic-appeals"
                  aria-labelledby="statistic-appeals"
                >
                  <div className="insight-section-heading">
                    <h2 id="statistic-appeals" tabIndex={-1}>
                      {labels[metric]} · {filtered.length}
                    </h2>
                    {(metric !== "all" || category || kind) && (
                      <Button
                        variant="outline"
                        onClick={() => {
                          setMetric("all");
                          setCategory("");
                          setKind("");
                          setLimit(20);
                        }}
                      >
                        Все обращения выборки
                      </Button>
                    )}
                  </div>
                  {category && (
                    <p className="hint">
                      Категория:{" "}
                      {categories[category as keyof typeof categories] ||
                        category}
                    </p>
                  )}
                  {kind && (
                    <p className="hint">
                      Тип: {kind === "problem" ? "Проблемы" : "Идеи"}
                    </p>
                  )}
                  {filtered.length ? (
                    <>
                      <ul className="statistic-appeal-list">
                        {filtered.slice(0, limit).map((item) => (
                          <li key={item.id}>
                            <a
                              href={`${appealBasePath}/${item.id}`}
                              onClick={(event) =>
                                openLink(event, event.currentTarget.pathname)
                              }
                            >
                              <small>
                                {item.number} · {date(item.created_at)}
                              </small>
                              <strong>{item.title}</strong>
                            </a>
                            <Status status={item.status} />
                            <span className="hint">
                              Первый ответ:{" "}
                              {item.first_response_at
                                ? duration(
                                    (new Date(
                                      item.first_response_at,
                                    ).getTime() -
                                      new Date(item.created_at).getTime()) /
                                      3600000,
                                  )
                                : "пока нет"}
                            </span>
                          </li>
                        ))}
                      </ul>
                      {filtered.length > limit && (
                        <Button
                          variant="outline"
                          onClick={() => setLimit((n) => n + 20)}
                        >
                          Показать ещё
                        </Button>
                      )}
                    </>
                  ) : (
                    <p className="hint">Обращений по этому показателю нет.</p>
                  )}
                </section>
              </>
            )}
            <details className="statistics-method">
              <summary>Как считаются показатели</summary>
              <p>
                Выборка включает обращения по дате подачи. Статусы и сроки
                показаны на момент расчёта. Среднее время ответа — календарное,
                среди обращений с известным первым ответом человека: сообщением,
                уточнением или решением. Назначение исполнителя и автоматические
                уведомления не учитываются. Для старых записей время
                восстанавливается только при наличии истории.
              </p>
              <p>
                Решено с подтверждением — сейчас закрыто и есть положительная
                оценка автора. Доля считается от всех поступивших обращений
                выборки. Возвраты считаются по уникальным обращениям, а не по
                числу нажатий. Подтверждения после выбранного периода входят в
                итоговый счётчик, но не в график за этот период. Группы отражают
                повторяемость обращений, а не доказанную причину инцидентов.
              </p>
            </details>
          </>
        )
      )}
    </section>
  );
}

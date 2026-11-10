import { useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCheck,
  FlaskConical,
  RefreshCw,
  Users,
} from "lucide-react";
import { Button } from "./components/ui/button";
import { Skeleton } from "./components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "./components/ui/toggle-group";
import { api } from "./api";
import type { User } from "./api";
import { openLink, Status } from "./appeals";
import { colleagues } from "./similar";

type Breakdown = {
  key: string;
  label: string;
  total: number;
  active: number;
  confirmed: number;
  helped_rate: number | null;
  supporters: number;
};
type Metrics = {
  period_days: number | null;
  scope: "all" | "mine" | "company";
  generated_at: string;
  funnel: {
    received: number;
    assigned: number;
    result_reported: number;
    confirmed: number;
  };
  loop: {
    ratings: number;
    helped: number;
    reopened: number;
    helped_rate: number | null;
    helped_first_time: number;
    helped_after_rework: number;
    awaiting: number;
    rejected: number;
  };
  timing: {
    median_hours_to_assign: number | null;
    median_days_to_result: number | null;
    median_days_to_confirmed: number | null;
    active: number;
    overdue: number;
    on_time_rate: number | null;
  };
  duplicates_prevented: number;
  most_supported: {
    appeal_id: number;
    number: string;
    title: string;
    status: string;
    supporters: number;
  }[];
  categories: Breakdown[];
  departments: Breakdown[];
  experiments: {
    total: number;
    active: number;
    finished: number;
    outcomes: Record<string, number>;
    measured: number;
    unmeasured_finished: number;
    examples: {
      appeal_id: number;
      number: string;
      title: string;
      metric: string;
      unit: string;
      before: number;
      after: number;
      outcome: string | null;
    }[];
  };
  weeks: { start: string; created: number; confirmed: number }[];
};

const percent = (value: number | null) =>
  value === null ? "—" : `${Math.round(value * 100)}%`;
const number = (value: number) => value.toLocaleString("ru-RU");
const days = (value: number | null) =>
  value === null ? "—" : `${value.toLocaleString("ru-RU")} дн.`;
const outcomeNames: Record<string, string> = {
  expand: "Внедрить шире",
  iterate: "Доработать",
  stop: "Прекратить",
};

function Bar({
  value,
  max,
  label,
}: {
  value: number;
  max: number;
  label: string;
}) {
  const width = max ? Math.max((value / max) * 100, value ? 2 : 0) : 0;
  return (
    <span className="impact-bar" title={label}>
      <span style={{ width: `${width}%` }} />
    </span>
  );
}

export function Impact({
  user,
  appealBasePath = "/queue",
  embedded = false,
}: {
  user: User;
  appealBasePath?: string;
  embedded?: boolean;
}) {
  const Heading = embedded ? "h2" : "h1";
  const [period, setPeriod] = useState("0");
  const [data, setData] = useState<Metrics | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError("");
    api<Metrics>(`/work/metrics?days=${period}`)
      .then((value) => active && setData(value))
      .catch((error) => active && setError(error.message));
    return () => {
      active = false;
    };
  }, [period, attempt]);
  const coordinator = user.roles.includes("coordinator");
  return (
    <section className="impact-page">
      <div className="appeal-heading">
        <div>
          <Heading>Эффект обратной связи</Heading>
          <p className="hint">
            Решено не тогда, когда ответственный отчитался, а когда автор
            подтвердил: «Помогло». Здесь только записанные факты — оценки
            авторов, статусы и измерения экспериментов.
            {!coordinator &&
              (user.roles.includes("director")
                ? " Показаны обращения вашей компании."
                : " Показаны обращения, назначенные вам.")}
          </p>
        </div>
        <div className="impact-controls">
          <ToggleGroup
            type="single"
            value={period}
            onValueChange={(value) => value && setPeriod(value)}
            aria-label="Период"
            className="impact-period"
          >
            <ToggleGroupItem value="30">30 дней</ToggleGroupItem>
            <ToggleGroupItem value="90">90 дней</ToggleGroupItem>
            <ToggleGroupItem value="0">Всё время</ToggleGroupItem>
          </ToggleGroup>
          <Button
            variant="outline"
            onClick={() => setAttempt((value) => value + 1)}
            aria-label="Обновить показатели"
          >
            <RefreshCw aria-hidden="true" />
          </Button>
        </div>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!data ? (
        !error && (
          <div className="impact-hero" role="status" aria-label="Считаем">
            <Skeleton />
            <Skeleton />
            <Skeleton />
            <Skeleton />
          </div>
        )
      ) : (
        <ImpactBody data={data} appealBasePath={appealBasePath} />
      )}
    </section>
  );
}

function ImpactBody({
  data,
  appealBasePath,
}: {
  data: Metrics;
  appealBasePath: string;
}) {
  const { funnel, loop, timing, experiments } = data;
  const steps: [string, number, string][] = [
    [
      "Поступило обращений",
      funnel.received,
      "Всё, что сотрудники отправили за период",
    ],
    [
      "Назначен ответственный",
      funnel.assigned,
      "Есть конкретный человек и срок",
    ],
    [
      "Сообщён результат",
      funnel.result_reported,
      "Ответственный зафиксировал, что сделано",
    ],
    ["Подтверждено автором", funnel.confirmed, "Автор сам нажал «Помогло»"],
  ];
  const categoryMax = Math.max(...data.categories.map((item) => item.total), 0);
  const departmentMax = Math.max(
    ...data.departments.map((item) => item.total),
    0,
  );
  const weekMax = Math.max(...data.weeks.map((item) => item.created), 0);
  return (
    <>
      <div className="impact-hero">
        <article className="impact-tile lead">
          <span className="impact-label">Авторы подтвердили «Помогло»</span>
          <strong className="impact-value">{percent(loop.helped_rate)}</strong>
          <p>
            {loop.ratings
              ? `${number(loop.helped)} из ${number(loop.ratings)} оценок результата. Вернули на доработку: ${number(loop.reopened)}.`
              : "Оценок пока нет: автор оценивает результат после выполнения."}
          </p>
        </article>
        <article className="impact-tile">
          <span className="impact-label">Закрыто с подтверждением</span>
          <strong className="impact-value">{number(funnel.confirmed)}</strong>
          <p>
            С первого раза: {number(loop.helped_first_time)}. После доработки:{" "}
            {number(loop.helped_after_rework)}. Ждут оценки автора:{" "}
            {number(loop.awaiting)}.
          </p>
        </article>
        <article className="impact-tile">
          <span className="impact-label">Медиана до результата</span>
          <strong className="impact-value">
            {days(timing.median_days_to_result)}
          </strong>
          <p>
            До ответственного —{" "}
            {timing.median_hours_to_assign === null
              ? "нет данных"
              : `${timing.median_hours_to_assign.toLocaleString("ru-RU")} ч`}
            . До подтверждения автором — {days(timing.median_days_to_confirmed)}
          </p>
        </article>
        <article className="impact-tile">
          <span className="impact-label">Дублей не создано</span>
          <strong className="impact-value">
            {number(data.duplicates_prevented)}
          </strong>
          <p>
            Сотрудники присоединились к уже открытым обращениям вместо новых.
          </p>
        </article>
      </div>

      <div className="impact-grid">
        <section
          className="card impact-funnel"
          aria-labelledby="funnel-heading"
        >
          <h2 id="funnel-heading">Замкнутый цикл</h2>
          <p className="hint">
            Каждый шаг — доля от поступивших. Последний шаг делает автор, не
            ответственный.
          </p>
          <ol>
            {steps.map(([label, value, note], index) => (
              <li key={label}>
                <div className="impact-row-head">
                  <span>
                    <span className="impact-step">{index + 1}</span>
                    {label}
                  </span>
                  <strong>
                    {number(value)}
                    <span className="hint">
                      {" "}
                      {funnel.received ? percent(value / funnel.received) : ""}
                    </span>
                  </strong>
                </div>
                <Bar
                  value={value}
                  max={funnel.received}
                  label={`${label}: ${value}`}
                />
                <span className="hint impact-note">{note}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="card" aria-labelledby="timing-heading">
          <h2 id="timing-heading">Сроки сейчас</h2>
          <dl className="impact-facts">
            <div>
              <dt>В работе</dt>
              <dd>{number(timing.active)}</dd>
            </div>
            <div>
              <dt>Просрочен срок ответа</dt>
              <dd className={timing.overdue ? "impact-alert" : ""}>
                {number(timing.overdue)}
              </dd>
            </div>
            <div>
              <dt>Отвечаем в срок</dt>
              <dd>{percent(timing.on_time_rate)}</dd>
            </div>
            <div>
              <dt>Отклонено с объяснением</dt>
              <dd>{number(loop.rejected)}</dd>
            </div>
          </dl>
          <h3 className="impact-subhead">Новые обращения по неделям</h3>
          <div
            className="impact-weeks"
            role="img"
            aria-label={data.weeks
              .map(
                (w) =>
                  `${new Date(w.start).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}: ${w.created}`,
              )
              .join(", ")}
          >
            {data.weeks.map((week) => (
              <div
                key={week.start}
                className="impact-week"
                title={`Неделя с ${new Date(week.start).toLocaleDateString("ru-RU")}: новых ${week.created}, подтверждено «Помогло» ${week.confirmed}`}
              >
                <span className="impact-week-value">{week.created || ""}</span>
                <span
                  className="impact-week-bar"
                  style={{
                    height: `${weekMax ? Math.max((week.created / weekMax) * 100, week.created ? 6 : 0) : 0}%`,
                  }}
                />
                <span className="impact-week-label">
                  {new Date(week.start).toLocaleDateString("ru-RU", {
                    day: "numeric",
                    month: "numeric",
                  })}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="impact-grid">
        <BreakdownCard
          id="categories"
          title="По категориям"
          items={data.categories}
          max={categoryMax}
        />
        <BreakdownCard
          id="departments"
          title="По подразделениям"
          items={data.departments}
          max={departmentMax}
        />
      </div>

      <div className="impact-grid">
        <section className="card" aria-labelledby="experiments-heading">
          <h2 id="experiments-heading">
            <FlaskConical aria-hidden="true" className="impact-heading-icon" />
            Идеи, проверенные экспериментом
          </h2>
          <p className="hint">
            Эффект считается подтверждённым только при измерении «до» и «после».
          </p>
          <dl className="impact-facts">
            <div>
              <dt>Идёт сейчас</dt>
              <dd>{number(experiments.active)}</dd>
            </div>
            <div>
              <dt>Завершено</dt>
              <dd>{number(experiments.finished)}</dd>
            </div>
            <div>
              <dt>С измерениями</dt>
              <dd>{number(experiments.measured)}</dd>
            </div>
            <div>
              <dt>Без измерений</dt>
              <dd>{number(experiments.unmeasured_finished)}</dd>
            </div>
          </dl>
          {Object.keys(experiments.outcomes).length > 0 && (
            <p className="impact-outcomes">
              {Object.entries(experiments.outcomes).map(([key, value]) => (
                <span key={key}>
                  {outcomeNames[key] || "Без итога"}: <strong>{value}</strong>
                </span>
              ))}
            </p>
          )}
          {experiments.examples.map((item) => {
            const change = item.before
              ? Math.round(
                  ((item.after - item.before) / Math.abs(item.before)) * 100,
                )
              : null;
            return (
              <a
                key={item.number}
                className="impact-example"
                href={`${appealBasePath}/${item.appeal_id}`}
                onClick={(event) =>
                  openLink(event, `${appealBasePath}/${item.appeal_id}`)
                }
              >
                <span className="record-number">{item.number}</span>
                <strong>{item.title}</strong>
                <span className="impact-measure">
                  {item.metric}:{" "}
                  <b>
                    {item.before.toLocaleString("ru-RU")} →{" "}
                    {item.after.toLocaleString("ru-RU")}
                  </b>{" "}
                  {item.unit}
                  {change !== null && (
                    <span className="impact-delta">
                      {change > 0 ? "+" : ""}
                      {change}%
                    </span>
                  )}
                </span>
                {item.outcome && (
                  <span className="hint">
                    Итог: {outcomeNames[item.outcome] || item.outcome}
                  </span>
                )}
              </a>
            );
          })}
        </section>

        <section className="card" aria-labelledby="supported-heading">
          <h2 id="supported-heading">
            <Users aria-hidden="true" className="impact-heading-icon" />
            Касается многих
          </h2>
          <p className="hint">
            К этим обращениям присоединились коллеги с той же ситуацией — сигнал
            для приоритета.
          </p>
          {data.most_supported.length ? (
            <ol className="impact-supported">
              {data.most_supported.map((item) => (
                <li key={item.appeal_id}>
                  <a
                    href={`${appealBasePath}/${item.appeal_id}`}
                    onClick={(event) =>
                      openLink(event, `${appealBasePath}/${item.appeal_id}`)
                    }
                  >
                    <span className="supporters-chip">+{item.supporters}</span>
                    <span>
                      <span className="record-number">{item.number}</span>
                      <strong>{item.title}</strong>
                      <span className="hint">
                        {colleagues(item.supporters)} с той же ситуацией
                      </span>
                    </span>
                    <Status status={item.status} />
                    <ArrowRight aria-hidden="true" className="impact-arrow" />
                  </a>
                </li>
              ))}
            </ol>
          ) : (
            <p className="impact-empty">
              <CheckCheck aria-hidden="true" />
              Пока никто не присоединялся. Подсказка появляется у сотрудника,
              когда он пишет о похожей ситуации.
            </p>
          )}
        </section>
      </div>
      <p className="hint impact-footnote">
        Обновлено{" "}
        {new Date(data.generated_at).toLocaleString("ru-RU", {
          day: "numeric",
          month: "long",
          hour: "2-digit",
          minute: "2-digit",
        })}
        .{" "}
        {data.scope === "all"
          ? "Все компании и подразделения."
          : data.scope === "company"
            ? "Ваша компания."
            : "Ваши назначенные обращения."}
      </p>
    </>
  );
}

function BreakdownCard({
  id,
  title,
  items,
  max,
}: {
  id: string;
  title: string;
  items: Breakdown[];
  max: number;
}) {
  return (
    <section className="card" aria-labelledby={`${id}-heading`}>
      <h2 id={`${id}-heading`}>{title}</h2>
      {items.length ? (
        <div
          className="impact-table-scroll"
          role="region"
          aria-labelledby={`${id}-heading`}
          tabIndex={0}
        >
          <table className="impact-table">
            <thead>
              <tr>
                <th scope="col">Раздел</th>
                <th scope="col">Обращений</th>
                <th scope="col">Закрыто</th>
                <th scope="col">«Помогло»</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.key}>
                  <th scope="row">
                    {item.label}
                    <Bar
                      value={item.total}
                      max={max}
                      label={`${item.label}: ${item.total} обращений`}
                    />
                  </th>
                  <td>
                    {item.total}
                    {item.supporters > 0 && (
                      <span className="supporters-chip">+{item.supporters}</span>
                    )}
                  </td>
                  <td>{item.confirmed}</td>
                  <td>{percent(item.helped_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="hint">Пока нет обращений за выбранный период.</p>
      )}
    </section>
  );
}

import { useEffect, useState } from "react";
import type { User, Company, Department } from "./api";
import { api } from "./api";
import { navigate, usePath } from "./navigation";
import { AppealCard, Status, date, openLink } from "./appeals";
import { Statistics } from "./statistics";
import { Impact } from "./impact";
import {
  PriorityReason,
  PriorityConsent,
  usePriorityAI,
  laneNames,
} from "./priorities";
import type { Priority, Lane } from "./priorities";
import { Button } from "./components/ui/button";
import { Badge } from "./components/ui/badge";
import { Field, FieldGroup, FieldLabel } from "./components/ui/field";
import { Alert, AlertDescription } from "./components/ui/alert";
import { Skeleton } from "./components/ui/skeleton";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "./components/ui/empty";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "./components/ui/toggle-group";
import { RefreshCw, ArrowRight, Sparkles, LoaderCircle } from "lucide-react";

type Item = {
  id: number;
  number: string;
  title: string;
  kind: string;
  status: string;
  created_at: string;
  department: string;
  responsible: string | null;
  priority: Priority;
};
type Overview = {
  total: number;
  counts: Record<Lane, number>;
  unassessed: number;
  stale: number;
  items: Item[];
  page: number;
  page_size: number;
};
function DirectorQueue({
  user,
  initialLane,
}: {
  user: User;
  initialLane: Lane;
}) {
  const [lane, setLane] = useState<Lane>(initialLane);
  const [company, setCompany] = useState("");
  const [department, setDepartment] = useState("");
  const [completed, setCompleted] = useState(false);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [result, setResult] = useState<Overview>();
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [directoryError, setDirectoryError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState("");
  const [consent, setConsent] = useState(false);
  const status = usePriorityAI();
  const coordinator = user.roles.includes("coordinator");
  useEffect(() => {
    setLane(initialLane);
    setPage(1);
  }, [initialLane]);
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
            "Не удалось загрузить фильтры компаний и подразделений.",
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
    const query = new URLSearchParams({
      lane,
      page: String(page),
      include_completed: String(completed),
    });
    if (company) query.set("company_id", company);
    if (department) query.set("department_id", department);
    api<Overview>("/director/overview?" + query)
      .then((value) => {
        if (active) {
          setResult(value);
          if (page > 1 && !value.items.length && value.total > 0) {
            setPage(Math.ceil(value.total / value.page_size));
          }
        }
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
  }, [lane, company, department, completed, page, attempt]);
  async function suggestBatch() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const query = new URLSearchParams();
      if (company) query.set("company_id", company);
      if (department) query.set("department_id", department);
      const targets = await api<
        { appeal_id: number; expected_version: number }[]
      >("/director/unassessed?" + query);
      if (!targets.length) {
        setNotice(
          "Все активные обращения выборки уже получили предложение. Отдельную оценку можно обновить в карточке.",
        );
        return;
      }
      await api("/work/priorities/suggest", "POST", {
        appeals: targets,
        consent,
      });
      setNotice(
        `Подготовлены предложения: ${targets.length}. Ручные оценки координатора сохранены. Проверьте объяснения в карточках.`,
      );
      setAttempt((n) => n + 1);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="director-queue" aria-busy={busy}>
      <div className="insight-section-heading">
        <div>
          <h2>{laneNames[lane]}</h2>
          <p className="hint">
            {lane === "attention"
              ? "Риски, повторяющиеся проблемы и задержки, которые стоит проверить в первую очередь."
              : lane === "promising"
                ? "Идеи с конкретным изменением процесса. Потенциальная польза требует оценки и проверки."
                : "Все остальные обращения сохраняются здесь и продолжают обрабатываться."}
          </p>
        </div>
        <Button
          variant="outline"
          disabled={loading || busy}
          onClick={() => setAttempt((n) => n + 1)}
        >
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
          Обновить
        </Button>
      </div>
      <FieldGroup className="director-filters">
        <Field>
          <FieldLabel htmlFor="director-company">Компания</FieldLabel>
          <select
            id="director-company"
            value={company}
            onChange={(e) => {
              setCompany(e.target.value);
              setDepartment("");
              setPage(1);
            }}
          >
            <option value="">
              {coordinator ? "Все доступные компании" : "Моя компания"}
            </option>
            {companies.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </Field>
        <Field>
          <FieldLabel htmlFor="director-department">Подразделение</FieldLabel>
          <select
            id="director-department"
            value={department}
            onChange={(e) => {
              setDepartment(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Все подразделения</option>
            {departments
              .filter((item) => !company || item.company_id === company)
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
          </select>
        </Field>
        <Field>
          <FieldLabel className="check">
            <input
              type="checkbox"
              checked={completed}
              onChange={(e) => {
                setCompleted(e.target.checked);
                setPage(1);
              }}
            />
            Включить закрытые и отклонённые
          </FieldLabel>
        </Field>
      </FieldGroup>
      {directoryError && (
        <Alert variant="destructive">
          <AlertDescription>
            {directoryError}{" "}
            <Button variant="link" onClick={() => setAttempt((n) => n + 1)}>
              Повторить загрузку фильтров
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {result && (
        <p className="director-counts">
          Требуют внимания: <strong>{result.counts.attention}</strong> ·
          Перспективные идеи: <strong>{result.counts.promising}</strong> ·
          Обычная очередь: <strong>{result.counts.routine}</strong>
          <br />
          Ещё не оценены: {result.unassessed} · Данные изменились после оценки
          ИИ: {result.stale}
        </p>
      )}
      {initialLane === "attention" && (
        <ToggleGroup
          type="single"
          value={lane}
          onValueChange={(v) => {
            if (v) {
              setLane(v as Lane);
              setPage(1);
            }
          }}
          aria-label="Очередь директора"
        >
          <ToggleGroupItem value="attention">Требуют внимания</ToggleGroupItem>
          <ToggleGroupItem value="routine">Обычная очередь</ToggleGroupItem>
        </ToggleGroup>
      )}
      {coordinator && (
        <details className="director-assess">
          <summary>
            <Sparkles aria-hidden="true" />
            Подготовить приоритеты с ИИ
          </summary>
          <p className="hint">
            За один запрос оцениваем до пяти активных обращений без предложения.
            Ручные исправления сохраняются. Предложения не меняют статус
            обращения.
          </p>
          <PriorityConsent
            status={status}
            consent={consent}
            setConsent={setConsent}
            disabled={busy}
          />
          <Button
            variant="outline"
            disabled={
              busy || !status?.available || (status.mode !== "demo" && !consent)
            }
            onClick={() => void suggestBatch()}
          >
            {busy && (
              <LoaderCircle
                data-icon="inline-start"
                className="insight-spinner"
                aria-hidden="true"
              />
            )}
            {busy ? "Подготавливаем оценки…" : "Оценить следующие 5 обращений"}
          </Button>
        </details>
      )}
      {notice && (
        <p className="insight-notice" role="status">
          {notice}
        </p>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertDescription>
            {error}{" "}
            <Button
              variant="link"
              disabled={loading || busy}
              onClick={() => setAttempt((n) => n + 1)}
            >
              Повторить загрузку
            </Button>
          </AlertDescription>
        </Alert>
      )}
      {loading ? (
        <div role="status" aria-label="Загружаем приоритеты">
          <Skeleton className="insight-skeleton" />
        </div>
      ) : (
        !error &&
        result &&
        (result.items.length ? (
          <section className="card director-journal">
            <ul>
              {result.items.map((item) => (
                <li key={item.id}>
                  <div className="director-item-heading">
                    <div>
                      <p className="hint">
                        {item.number} ·{" "}
                        {item.kind === "idea" ? "Идея" : "Проблема"} ·{" "}
                        {item.department} · {date(item.created_at)}
                      </p>
                      <h3>
                        <a
                          href={`/director/appeals/${item.id}`}
                          onClick={(event) =>
                            openLink(event, event.currentTarget.pathname)
                          }
                        >
                          {item.title}
                          <ArrowRight aria-hidden="true" />
                        </a>
                      </h3>
                    </div>
                    <Status status={item.status} />
                  </div>
                  <PriorityReason priority={item.priority} />
                  <p className="hint">
                    Ответственный: {item.responsible || "не назначен"}
                    {item.priority.overdue ? " · Срок ответа просрочен" : ""}
                  </p>
                  <div className="director-item-foot">
                    <Badge variant="outline">
                      {laneNames[item.priority.effective.lane]}
                    </Badge>
                    <a
                      href={`/director/appeals/${item.id}`}
                      onClick={(event) =>
                        openLink(event, event.currentTarget.pathname)
                      }
                    >
                      {coordinator
                        ? "Проверить и исправить оценку"
                        : "Открыть обращение"}
                    </a>
                  </div>
                </li>
              ))}
            </ul>
            {result.total > result.page_size && (
              <div className="pagination">
                <Button
                  variant="outline"
                  disabled={page === 1}
                  onClick={() => setPage((n) => n - 1)}
                >
                  Назад
                </Button>
                <span>
                  Страница {page} из{" "}
                  {Math.ceil(result.total / result.page_size)}
                </span>
                <Button
                  variant="outline"
                  disabled={page * result.page_size >= result.total}
                  onClick={() => setPage((n) => n + 1)}
                >
                  Далее
                </Button>
              </div>
            )}
          </section>
        ) : (
          <section className="card">
            <Empty>
              <EmptyHeader>
                <EmptyTitle>В этой подборке пока нет обращений</EmptyTitle>
                <EmptyDescription>
                  {coordinator
                    ? "Проверьте фильтры или подготовьте оценки для неоценённых обращений."
                    : "Координатор может уточнить приоритеты. Неоценённые обращения остаются в обычной очереди."}
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          </section>
        ))
      )}
    </section>
  );
}

function DirectorStatistics({ user }: { user: User }) {
  const [tab, setTab] = useState("processing");
  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList
        className="director-statistics-switch"
        aria-label="Виды статистики"
      >
        <TabsTrigger value="processing">Обработка обращений</TabsTrigger>
        <TabsTrigger value="impact">Результаты и эксперименты</TabsTrigger>
      </TabsList>
      <TabsContent value={tab}>
        {tab === "processing" ? (
          <Statistics embedded appealBasePath="/director/appeals" />
        ) : (
          <Impact user={user} embedded appealBasePath="/director/appeals" />
        )}
      </TabsContent>
    </Tabs>
  );
}

export function DirectorCabinet({ user }: { user: User }) {
  const path = usePath();
  const match = path.match(/^\/director\/appeals\/(\d+)$/);
  if (match)
    return (
      <AppealCard
        key={match[1]}
        id={Number(match[1])}
        notice=""
        user={user}
        backPath="/director"
      />
    );
  const tab =
    path === "/director/statistics"
      ? "statistics"
      : path === "/director/ideas"
        ? "promising"
        : "attention";
  return (
    <section className="director-cabinet">
      <div className="page-heading">
        <h1>Кабинет директора</h1>
        <p className="hint">
          {user.roles.includes("coordinator")
            ? "Обзор для руководителя. Вы можете проверять и исправлять приоритеты обращений."
            : "Обращения и результаты вашей компании. Оценки помогают выбрать порядок рассмотрения; факты и эффект требуют проверки."}
        </p>
      </div>
      <Tabs
        value={tab}
        onValueChange={(value) =>
          navigate(
            value === "statistics"
              ? "/director/statistics"
              : value === "promising"
                ? "/director/ideas"
                : "/director",
          )
        }
      >
        <TabsList aria-label="Разделы кабинета директора">
          <TabsTrigger value="attention">Требуют внимания</TabsTrigger>
          <TabsTrigger value="promising">Перспективные идеи</TabsTrigger>
          <TabsTrigger value="statistics">Статистика</TabsTrigger>
        </TabsList>
        <TabsContent value={tab}>
          {tab === "statistics" ? (
            <DirectorStatistics user={user} />
          ) : (
            <DirectorQueue
              user={user}
              initialLane={tab === "promising" ? "promising" : "attention"}
            />
          )}
        </TabsContent>
      </Tabs>
    </section>
  );
}

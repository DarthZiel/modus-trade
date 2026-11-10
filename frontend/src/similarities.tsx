import { useEffect, useState } from "react";
import {
  LoaderCircle,
  Search,
  Check,
  X,
  ArrowRight,
  ChevronDown,
} from "lucide-react";
import { api } from "./api";
import { openLink, Status, date } from "./appeals";
import { Button } from "./components/ui/button";
import { Badge } from "./components/ui/badge";
import { Alert, AlertDescription } from "./components/ui/alert";
import { Field, FieldGroup, FieldLabel } from "./components/ui/field";
import { Skeleton } from "./components/ui/skeleton";
import { Separator } from "./components/ui/separator";
import { ToggleGroup, ToggleGroupItem } from "./components/ui/toggle-group";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "./components/ui/empty";

export type RelatedAppeal = {
  id: number;
  number: string;
  title: string;
  status: string;
  created_at: string;
};
type Relation = {
  id: string;
  appeal: RelatedAppeal;
  kind: "same_problem" | "related_topic";
  topic: string;
  reason: string;
  source: string;
  status: "pending" | "confirmed" | "dismissed";
  version: number;
  reviewer: string | null;
  reviewed_at: string | null;
};
export type Topic = {
  id: number;
  title: string;
  company_id: string;
  authors: number;
  confirmed: number;
  reopened: number;
  latest_at: string;
  appeals: RelatedAppeal[];
};
type AIStatus = { mode: string; available: boolean };

function Failure({ message }: { message: string }) {
  return message ? (
    <Alert variant="destructive">
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  ) : null;
}

function RelationRow({
  item,
  busy,
  onReview,
}: {
  item: Relation;
  busy: boolean;
  onReview: (
    item: Relation,
    status: "confirmed" | "dismissed",
    kind: Relation["kind"],
  ) => void;
}) {
  const [kind, setKind] = useState(item.kind);
  return (
    <li className="similarity-row">
      <div className="similarity-row-heading">
        <a
          href={`/queue/${item.appeal.id}`}
          onClick={(event) => openLink(event, event.currentTarget.pathname)}
        >
          <small>{item.appeal.number}</small>
          <strong>{item.appeal.title}</strong>
        </a>
        <Badge variant={item.status === "confirmed" ? "secondary" : "outline"}>
          {item.status === "pending"
            ? "Предложение"
            : item.status === "confirmed"
              ? "Подтверждено"
              : "Отклонено"}
        </Badge>
      </div>
      <p>{item.reason}</p>
      <p className="hint">
        {item.source === "demo"
          ? "Подсказка по словам, без ИИ"
          : item.source === "dataset"
            ? "Подготовлено для демонстрации"
            : "Предложено ИИ"}{" "}
        · {item.topic}
      </p>
      <ToggleGroup
        type="single"
        value={kind}
        onValueChange={(value) => {
          if (value) setKind(value as Relation["kind"]);
        }}
        disabled={busy}
        aria-label={`Тип связи с ${item.appeal.number}`}
      >
        <ToggleGroupItem value="same_problem">Одна проблема</ToggleGroupItem>
        <ToggleGroupItem value="related_topic">Связанная тема</ToggleGroupItem>
      </ToggleGroup>
      <div className="similarity-actions">
        {(item.status !== "confirmed" || kind !== item.kind) && (
          <Button
            size="sm"
            disabled={busy}
            onClick={() => onReview(item, "confirmed", kind)}
          >
            <Check data-icon="inline-start" aria-hidden="true" />
            {item.status === "confirmed"
              ? "Сохранить тип связи"
              : "Подтвердить связь"}
          </Button>
        )}
        {item.status !== "dismissed" && (
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => onReview(item, "dismissed", item.kind)}
          >
            <X data-icon="inline-start" aria-hidden="true" />
            {item.status === "confirmed" ? "Отменить связь" : "Отклонить"}
          </Button>
        )}
      </div>
      {item.reviewer && item.reviewed_at && (
        <p className="hint">
          {item.reviewer} · {date(item.reviewed_at)}
        </p>
      )}
    </li>
  );
}

export function Similarities({ appealId }: { appealId: number }) {
  const [items, setItems] = useState<Relation[]>([]);
  const [status, setStatus] = useState<AIStatus>();
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [consent, setConsent] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setReady(false);
    setError("");
    Promise.all([
      api<Relation[]>(`/work/appeals/${appealId}/similarities`),
      api<AIStatus>("/ai/status"),
    ])
      .then(([relations, mode]) => {
        if (active) {
          setItems(relations);
          setStatus(mode);
          setReady(true);
        }
      })
      .catch((err) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [appealId, attempt]);
  async function search() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<{
        items: Relation[];
        considered: number;
        available: number;
      }>(`/work/appeals/${appealId}/similarities/search`, "POST", { consent });
      setItems(result.items);
      setNotice(
        result.considered
          ? `Проверено кандидатов: ${result.considered} из ${result.available}. ${result.items.some((item) => item.status === "pending") ? "Проверьте предложенные связи." : "Новых совпадений не найдено."}`
          : "Новых кандидатов нет. Все доступные пары уже проверены.",
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function review(
    item: Relation,
    decision: "confirmed" | "dismissed",
    kind: Relation["kind"],
  ) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(`/work/similarities/${item.id}`, "PATCH", {
        status: decision,
        kind,
        expected_version: item.version,
      });
      setItems(await api<Relation[]>(`/work/appeals/${appealId}/similarities`));
      setNotice(
        decision === "confirmed"
          ? "Связь подтверждена. Статусы и переписка обращений сохранены."
          : "Связь отклонена. Поиск не будет предлагать эту пару повторно.",
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const live = items.filter((item) => item.status !== "dismissed");
  const dismissed = items.filter((item) => item.status === "dismissed");
  return (
    <section
      className="card section-gap similarity-panel"
      aria-labelledby={`similarity-${appealId}`}
      aria-busy={busy}
    >
      <div className="insight-section-heading">
        <h2 id={`similarity-${appealId}`}>Похожие обращения</h2>
        <a
          href="/topics"
          onClick={(event) => openLink(event, event.currentTarget.pathname)}
        >
          Все повторяющиеся проблемы <ArrowRight aria-hidden="true" />
        </a>
      </div>
      <p className="hint">
        Доступно только координатору. Поиск предлагает связи, вы проверяете их.
        В повторяющиеся проблемы попадут только подтверждённые связи «Одна
        проблема».
      </p>
      <Failure message={error} />
      {!ready ? (
        error ? (
          <Button variant="outline" onClick={() => setAttempt((n) => n + 1)}>
            Повторить загрузку
          </Button>
        ) : (
          <div role="status" aria-label="Загружаем связи">
            <Skeleton className="insight-skeleton" />
          </div>
        )
      ) : (
        <>
          {status?.mode === "demo" && (
            <p className="hint">
              Демонстрационный режим: локальный поиск по словам, без обращения к
              модели.
            </p>
          )}
          {status && !status.available && (
            <p className="hint">
              ИИ-поиск не подключён. Сохранённые связи доступны для проверки.
            </p>
          )}
          {status && ["openai", "openrouter"].includes(status.mode) && (
            <FieldGroup>
              <Field>
                <FieldLabel className="check">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(event) => setConsent(event.target.checked)}
                    disabled={busy}
                  />
                  Разрешаю передать заголовки и тексты обращений этой компании в{" "}
                  {status.mode === "openrouter"
                    ? "OpenRouter и выбранную модель"
                    : "OpenAI"}
                  . Профили, переписка и вложения не передаются.
                </FieldLabel>
              </Field>
            </FieldGroup>
          )}
          <Button
            variant="outline"
            disabled={
              busy || !status?.available || (status.mode !== "demo" && !consent)
            }
            onClick={() => void search()}
          >
            {busy ? (
              <LoaderCircle
                data-icon="inline-start"
                className="insight-spinner"
                aria-hidden="true"
              />
            ) : (
              <Search data-icon="inline-start" aria-hidden="true" />
            )}
            {busy
              ? "Обрабатываем…"
              : status?.mode === "demo"
                ? "Найти похожие по словам"
                : "Найти похожие с ИИ"}
          </Button>
          <p className="hint">
            За один поиск сравниваем до 40 ещё не проверенных обращений той же
            компании, сначала наиболее близкие по тексту.
          </p>
          {notice && (
            <p role="status" className="insight-notice">
              {notice}
            </p>
          )}
          <Separator />
          {live.length ? (
            <ul className="similarity-list">
              {live.map((item) => (
                <RelationRow
                  key={`${item.id}-${item.version}`}
                  item={item}
                  busy={busy}
                  onReview={review}
                />
              ))}
            </ul>
          ) : (
            <p className="hint">
              Связей пока нет. Запустите поиск, чтобы проверить похожие
              обращения.
            </p>
          )}
          {!!dismissed.length && (
            <details>
              <summary>Отклонённые связи · {dismissed.length}</summary>
              <ul className="similarity-list">
                {dismissed.map((item) => (
                  <RelationRow
                    key={`${item.id}-${item.version}`}
                    item={item}
                    busy={busy}
                    onReview={review}
                  />
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}

export function TopicList({
  topics,
  appealBasePath = "/queue",
}: {
  topics: Topic[];
  appealBasePath?: string;
}) {
  return topics.length ? (
    <ul className="topic-list">
      {topics.map((topic) => (
        <li key={topic.id}>
          <details>
            <summary>
              <span>
                <strong>{topic.title}</strong>
                <span className="hint">
                  Обращений: {topic.appeals.length} · Сотрудников:{" "}
                  {topic.authors} · Решено с подтверждением: {topic.confirmed}
                </span>
              </span>
              <Badge variant="secondary">{topic.appeals.length}</Badge>
              <ChevronDown aria-hidden="true" />
            </summary>
            <p className="hint">
              Последнее обращение: {date(topic.latest_at)} · Возвращались в
              работу: {topic.reopened}
            </p>
            <ul className="topic-appeals">
              {topic.appeals.map((item) => (
                <li key={item.id}>
                  <a
                    href={`${appealBasePath}/${item.id}`}
                    onClick={(event) =>
                      openLink(event, event.currentTarget.pathname)
                    }
                  >
                    <small>{item.number}</small>
                    <strong>{item.title}</strong>
                  </a>
                  <Status status={item.status} />
                </li>
              ))}
            </ul>
          </details>
        </li>
      ))}
    </ul>
  ) : (
    <Empty>
      <EmptyHeader>
        <EmptyTitle>Повторяющихся проблем пока нет</EmptyTitle>
        <EmptyDescription>
          Группы появятся, когда координатор подтвердит связь «Одна проблема»
          между обращениями. Связанные темы учитываются отдельно.
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

export function Topics() {
  const [items, setItems] = useState<Topic[]>();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError("");
    setItems(undefined);
    api<Topic[]>("/work/topics")
      .then((value) => {
        if (active) setItems(value);
      })
      .catch((err) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  return (
    <section className="insights-page">
      <div className="appeal-heading">
        <div>
          <h1>Повторяющиеся проблемы</h1>
          <p className="hint">
            Общие проблемы из связей, подтверждённых координатором. Каждое
            обращение сохраняет собственный результат.
          </p>
        </div>
        <Button variant="outline" onClick={() => setAttempt((n) => n + 1)}>
          Обновить
        </Button>
      </div>
      <Failure message={error} />
      {error ? (
        <Button variant="outline" onClick={() => setAttempt((n) => n + 1)}>
          Повторить загрузку
        </Button>
      ) : items ? (
        <section className="card">
          <h2>Подтверждённые группы · {items.length}</h2>
          <TopicList topics={items} />
        </section>
      ) : (
        <Skeleton className="insight-skeleton" />
      )}
    </section>
  );
}

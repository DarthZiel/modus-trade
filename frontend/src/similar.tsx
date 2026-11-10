import { useEffect, useRef, useState } from "react";
import { ArrowRight, Check, LoaderCircle, Users } from "lucide-react";
import { Button } from "./components/ui/button";
import { Textarea } from "./components/ui/textarea";
import { Skeleton } from "./components/ui/skeleton";
import { api, ApiError } from "./api";
import { categories, date, openLink, Status } from "./appeals";
import { navigate } from "./navigation";

type Kind = "problem" | "idea";
type Category = keyof typeof categories;
export type SimilarItem = {
  id: number;
  number: string;
  title: string;
  kind: Kind;
  category: Category;
  status: string;
  responsible: string | null;
  supporters: number;
  created_at: string;
  relation: "own" | "supported" | "other";
  can_join: boolean;
  score: number;
};
export type SupportView = {
  id: number;
  number: string;
  title: string;
  kind: Kind;
  category: Category;
  status: string;
  responsible: string | null;
  next_response_at: string | null;
  is_overdue: boolean;
  decision: string | null;
  result: string | null;
  decided_at: string | null;
  supporters: number;
  joined_at: string;
  comment: string;
  experiment: {
    hypothesis: string;
    change: string;
    starts_at: string;
    ends_at: string;
    status: string;
    outcome: string | null;
  } | null;
};

export const colleagues = (count: number) => {
  const tail = count % 100;
  const word =
    tail >= 11 && tail <= 14
      ? "коллег"
      : count % 10 === 1
        ? "коллега"
        : [2, 3, 4].includes(count % 10)
          ? "коллеги"
          : "коллег";
  return `${count} ${word}`;
};

/** Live check for an existing appeal while the employee is still typing. */
export function SimilarAppeals({
  title,
  description,
  kind,
  onJoined,
  compact = false,
}: {
  title: string;
  description: string;
  kind: Kind;
  onJoined: (view: SupportView) => void;
  compact?: boolean;
}) {
  const [items, setItems] = useState<SimilarItem[]>([]);
  const [loading, setLoading] = useState(false);
  const request = useRef(0);
  const query = `${title} ${description}`.trim();
  useEffect(() => {
    const revision = ++request.current;
    if (query.length < 12) {
      setItems([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const timer = window.setTimeout(() => {
      api<SimilarItem[]>("/similar", "POST", {
        title: title.trim().slice(0, 160),
        description: description.trim().slice(0, 2000),
        kind,
      })
        .then((value) => {
          if (revision === request.current) setItems(value);
        })
        .catch(() => {
          // Similar search is a hint: it never blocks filing the appeal.
          if (revision === request.current) setItems([]);
        })
        .finally(() => {
          if (revision === request.current) setLoading(false);
        });
    }, 650);
    return () => window.clearTimeout(timer);
  }, [query, title, description, kind]);
  if (!items.length)
    return loading && !compact ? (
      <p className="similar-searching hint" role="status">
        <LoaderCircle className="spin" aria-hidden="true" />
        Ищем похожие обращения…
      </p>
    ) : null;
  return (
    <section
      className={`similar-panel${compact ? " compact" : ""}`}
      aria-labelledby="similar-heading"
      aria-live="polite"
    >
      <div className="similar-head">
        <span className="similar-icon">
          <Users aria-hidden="true" />
        </span>
        <div>
          <h2 id="similar-heading">Похоже, об этом уже сообщали</h2>
          <p className="hint">
            Присоединитесь вместо нового обращения: ответственный увидит, что
            ситуация касается не только вас, а вы получите результат. Если у
            вас другое — просто продолжайте.
          </p>
        </div>
      </div>
      <ol className="similar-list">
        {items.map((item) => (
          <SimilarRow key={item.id} item={item} onJoined={onJoined} />
        ))}
      </ol>
    </section>
  );
}

function SimilarRow({
  item,
  onJoined,
}: {
  item: SimilarItem;
  onJoined: (view: SupportView) => void;
}) {
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const strong = item.score >= 0.35;
  async function join() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      onJoined(
        await api<SupportView>(`/appeals/${item.id}/support`, "POST", {
          comment: comment.trim(),
        }),
      );
    } catch (error) {
      setError((error as Error).message);
      setBusy(false);
    }
  }
  const finished = ["closed", "rejected"].includes(item.status);
  return (
    <li className="similar-item">
      <div className="similar-meta">
        <span className="record-number">{item.number}</span>
        <Status status={item.status} />
        <span className={`similar-match${strong ? " strong" : ""}`}>
          {strong ? "Очень похоже" : "Возможно, то же"}
        </span>
      </div>
      <h3>{item.title}</h3>
      <p className="hint">
        {categories[item.category]} ·{" "}
        {item.responsible
          ? `Ответственный: ${item.responsible}`
          : "Ответственного скоро назначат"}
        {item.supporters > 0 &&
          ` · Присоединились: ${colleagues(item.supporters)}`}
      </p>
      {item.relation === "own" ? (
        <a
          className="similar-link"
          href={`/appeals/${item.id}`}
          onClick={(event) => openLink(event, `/appeals/${item.id}`)}
        >
          Это ваше обращение — дополните его в переписке
          <ArrowRight aria-hidden="true" />
        </a>
      ) : item.relation === "supported" ? (
        <a
          className="similar-link"
          href={`/appeals/${item.id}`}
          onClick={(event) => openLink(event, `/appeals/${item.id}`)}
        >
          <Check aria-hidden="true" />
          Вы уже присоединились — открыть
        </a>
      ) : finished ? (
        <p className="similar-done hint">
          {item.status === "closed"
            ? "Недавно решено и подтверждено автором. Если у вас повторилось — отправьте новое обращение."
            : "Рассмотрение завершено."}
        </p>
      ) : open ? (
        <div className="similar-join">
          <label htmlFor={`support-${item.id}`}>
            Что добавить ответственному?{" "}
            <span className="optional">необязательно</span>
          </label>
          <Textarea
            id={`support-${item.id}`}
            value={comment}
            maxLength={1000}
            rows={2}
            onChange={(event) => setComment(event.target.value)}
            placeholder="Например: у нас на втором складе то же самое, особенно по утрам"
          />
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <div className="form-actions">
            <Button
              variant="ghost"
              type="button"
              disabled={busy}
              onClick={() => setOpen(false)}
            >
              Отмена
            </Button>
            <Button type="button" disabled={busy} onClick={join}>
              {busy ? "Присоединяем…" : "Присоединиться"}
            </Button>
          </div>
        </div>
      ) : (
        <Button
          type="button"
          variant="outline"
          className="similar-cta"
          onClick={() => setOpen(true)}
        >
          <Users data-icon="inline-start" aria-hidden="true" />У меня то же
          самое
        </Button>
      )}
    </li>
  );
}

const outcomes: Record<string, string> = {
  expand: "Внедрить шире",
  iterate: "Доработать",
  stop: "Прекратить",
};

/** Limited card for a colleague who joined: official progress, never the private thread. */
export function SupportCard({ id, notice }: { id: number; notice?: string }) {
  const [view, setView] = useState<SupportView | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<SupportView>(`/appeals/${id}/support`)
      .then((value) => active && setView(value))
      .catch(
        (error) =>
          active &&
          setError(
            error instanceof ApiError && error.status === 404
              ? "Обращение не найдено или недоступно."
              : error.message,
          ),
      );
    return () => {
      active = false;
    };
  }, [id]);
  if (error)
    return (
      <p className="error" role="alert">
        {error}
      </p>
    );
  if (!view)
    return (
      <div className="employee-loading" role="status" aria-label="Загружаем">
        <Skeleton />
        <Skeleton />
      </div>
    );
  return (
    <>
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      <div className="appeal-heading">
        <div>
          <h1>{view.title}</h1>
          <p className="hint">
            {view.number} · {categories[view.category]} · вы присоединились{" "}
            {date(view.joined_at)}
          </p>
        </div>
        <Status status={view.status} />
      </div>
      <div className="appeal-columns">
        <div>
          <section className="card support-intro">
            <h2>Вы следите за этим обращением</h2>
            <p>
              Его отправил коллега. Описание и переписка видны только автору и
              ответственному. Вы получите уведомление, когда обращение примут в
              работу и когда появится результат.
            </p>
            {view.comment && (
              <blockquote className="support-comment">
                <span className="hint">Ваш комментарий ответственному</span>
                {view.comment}
              </blockquote>
            )}
          </section>
          {view.result && (
            <section className="card section-gap decision-result">
              <h2>
                {view.decision === "Отклонено"
                  ? "Причина отклонения"
                  : "Результат выполнения"}
              </h2>
              <p className="preserve-text">{view.result}</p>
              {view.decided_at && (
                <p className="hint note">
                  Зафиксировано: {date(view.decided_at)}
                </p>
              )}
              {view.status === "awaiting_confirmation" && (
                <p className="result-next-step">
                  Автор проверяет результат. Если у вас проблема осталась —
                  отправьте новое обращение со ссылкой на {view.number}.
                </p>
              )}
            </section>
          )}
          {view.experiment && (
            <section className="card section-gap">
              <h2>Проверка экспериментом</h2>
              <p>
                <strong>Что проверяем:</strong> {view.experiment.hypothesis}
              </p>
              <p className="section-gap-small">
                <strong>Что меняем:</strong> {view.experiment.change}
              </p>
              <p className="hint note">
                {date(view.experiment.starts_at)} —{" "}
                {date(view.experiment.ends_at)}
                {view.experiment.outcome
                  ? ` · Итог: ${outcomes[view.experiment.outcome] || view.experiment.outcome}`
                  : view.experiment.status === "active"
                    ? " · Идёт сейчас"
                    : ""}
              </p>
            </section>
          )}
        </div>
        <aside className="card appeal-aside">
          <h2>По обращению</h2>
          <dl>
            <dt>Ответственный</dt>
            <dd>{view.responsible || "Пока не назначен"}</dd>
            <dt>Дата следующего ответа</dt>
            <dd>
              {view.next_response_at
                ? date(view.next_response_at)
                : view.result
                  ? "Ответ уже предоставлен"
                  : "Пока не назначена"}
            </dd>
            <dt>Присоединились</dt>
            <dd>{colleagues(view.supporters)}</dd>
          </dl>
        </aside>
      </div>
    </>
  );
}

/** "Вы присоединились" block in the employee journal. */
export function SupportedList() {
  const [items, setItems] = useState<SupportView[]>([]);
  useEffect(() => {
    let active = true;
    api<SupportView[]>("/supports")
      .then((value) => active && setItems(value))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);
  if (!items.length) return null;
  return (
    <section className="journal-section" aria-labelledby="supported-heading">
      <div className="section-heading">
        <h2 id="supported-heading">Вы присоединились</h2>
        <span className="hint">Обращения коллег с той же ситуацией</span>
      </div>
      <div className="reply-list">
        {items.map((item) => (
          <a
            key={item.id}
            className="reply-row"
            href={`/appeals/${item.id}`}
            onClick={(event) => openLink(event, `/appeals/${item.id}`)}
          >
            <span className="reply-icon">
              <Users aria-hidden="true" />
            </span>
            <div>
              <span className="record-number">{item.number}</span>
              <h3>{item.title}</h3>
              <p>
                {item.result
                  ? "Есть результат — откройте, чтобы посмотреть."
                  : item.responsible
                    ? `Рассматривает ${item.responsible}.`
                    : "Ожидает назначения ответственного."}{" "}
                Присоединились: {colleagues(item.supporters)}.
              </p>
            </div>
            <Status status={item.status} />
          </a>
        ))}
      </div>
    </section>
  );
}

export function joinedNotice(view: SupportView) {
  return `Вы присоединились к ${view.number}. Мы сообщим, когда появится результат.`;
}

export function goToSupport(view: SupportView) {
  navigate(`/appeals/${view.id}`);
}

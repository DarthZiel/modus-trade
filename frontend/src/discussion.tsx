import {
  Message as UIMessage,
  MessageContent,
  MessageHeader,
  MessageFooter,
} from "./components/ui/message";
import { Bubble, BubbleContent } from "./components/ui/bubble";
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "./components/ui/field";
import { Textarea } from "./components/ui/textarea";
import { Badge } from "./components/ui/badge";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "./components/ui/empty";
import { Skeleton } from "./components/ui/skeleton";
import { Send, RefreshCw } from "lucide-react";
import { Button } from "./components/ui/button";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "./api";
import type { User } from "./api";
import type { Detail } from "./appeals";
import { ReplyAssistant } from "./reply-assistant";

type Message = {
  id: number;
  sender_id: string;
  sender: string;
  is_author: boolean;
  body: string;
  kind: string;
  created_at: string;
};
type Page = { items: Message[]; has_more: boolean };
const date = (value: string) =>
  new Date(value).toLocaleString("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  });
export function Conversation({
  appeal,
  user,
  onUpdated,
}: {
  appeal: Detail;
  user: User;
  onUpdated: (appeal: Detail) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [older, setOlder] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [clientId, setClientId] = useState(() => crypto.randomUUID());
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError("");
    api<Page>(`/appeals/${appeal.id}/messages`)
      .then((page) => {
        if (!cancelled) {
          setMessages(page.items);
          setMore(page.has_more);
        }
      })
      .catch((error) => {
        if (!cancelled) setLoadError(error.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [appeal.id, appeal.assignment_version, attempt]);
  async function loadOlder() {
    if (!messages.length) return;
    setOlder(true);
    setLoadError("");
    try {
      const page = await api<Page>(
        `/appeals/${appeal.id}/messages?before_id=${messages[0].id}`,
      );
      setMessages((previous) => {
        const known = new Set(previous.map((item) => item.id));
        return [
          ...page.items.filter((item) => !known.has(item.id)),
          ...previous,
        ];
      });
      setMore(page.has_more);
    } catch (error) {
      setLoadError((error as Error).message);
    } finally {
      setOlder(false);
    }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!body.trim()) {
      setError("Напишите сообщение.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await api<{ message: Message; appeal: Detail }>(
        `/appeals/${appeal.id}/messages`,
        "POST",
        { client_id: clientId, body: body.trim() },
      );
      setMessages((previous) =>
        previous.some((item) => item.id === result.message.id)
          ? previous
          : [...previous, result.message],
      );
      setBody("");
      setClientId(crypto.randomUUID());
      onUpdated(result.appeal);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card section-gap conversation">
      <div className="discussion-heading">
        <h2>Переписка</h2>
        <Button
          variant="outline"
          disabled={loading || busy}
          onClick={() => setAttempt((value) => value + 1)}
        >
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
          Обновить
        </Button>
      </div>
      <p className="hint">
        Сообщения видят автор и сотрудники, рассматривающие обращение.
      </p>
      {loadError && (
        <p className="error" role="alert">
          {loadError}
        </p>
      )}
      {more && (
        <Button variant="outline" disabled={older} onClick={loadOlder}>
          {older ? "Загружаем…" : "Показать предыдущие сообщения"}
        </Button>
      )}
      {loading && messages.length === 0 ? (
        <div
          role="status"
          aria-label="Загружаем переписку"
          className="thread-loading"
        >
          <Skeleton />
          <Skeleton />
        </div>
      ) : (
        <div
          className="appeal-thread"
          aria-label="Сообщения по обращению"
          role="log"
          aria-live="polite"
          aria-relevant="additions"
        >
          {messages.length
            ? messages.map((message) => (
                <UIMessage
                  key={message.id}
                  align={message.sender_id === user.id ? "end" : "start"}
                >
                  <MessageContent>
                    <MessageHeader>
                      {message.sender_id === user.id ? "Вы" : message.sender}
                      {message.is_author ? " · автор" : ""}
                    </MessageHeader>
                    <Bubble
                      variant={
                        message.sender_id === user.id ? "secondary" : "outline"
                      }
                    >
                      <BubbleContent>
                        {["question", "feedback_return"].includes(
                          message.kind,
                        ) && (
                          <Badge variant="secondary">
                            {message.kind === "question"
                              ? "Запрос уточнения"
                              : "Возврат в работу"}
                          </Badge>
                        )}
                        <p className="preserve-text">{message.body}</p>
                      </BubbleContent>
                    </Bubble>
                    <MessageFooter>
                      <time dateTime={message.created_at}>
                        {date(message.created_at)}
                      </time>
                    </MessageFooter>
                  </MessageContent>
                </UIMessage>
              ))
            : !loadError && (
                <Empty className="thread-empty">
                  <EmptyHeader>
                    <EmptyTitle>Начните разговор</EmptyTitle>
                    <EmptyDescription>
                      Дополните обращение или задайте вопрос. Ответы сохранятся
                      здесь.
                    </EmptyDescription>
                  </EmptyHeader>
                </Empty>
              )}
        </div>
      )}
      {(user.roles.includes("coordinator") ||
        (user.roles.includes("responsible") &&
          appeal.responsible_id === user.id)) &&
        appeal.author_id !== user.id &&
        !["closed", "rejected"].includes(appeal.status) && (
          <ReplyAssistant
            appealId={appeal.id}
            onInsert={(text) => {
              setBody(text);
              setError("");
              requestAnimationFrame(() =>
                document.getElementById("message-body")?.focus(),
              );
            }}
          />
        )}
      <form onSubmit={send} className="message-composer" aria-busy={busy}>
        <Field data-invalid={!!error}>
          <FieldLabel htmlFor="message-body">
            {appeal.status === "needs_info" && appeal.author_id === user.id
              ? "Ответить на уточнение"
              : "Новое сообщение"}
          </FieldLabel>
          {appeal.status === "needs_info" && appeal.author_id === user.id && (
            <p className="hint">
              После вашего ответа рассмотрение обращения продолжится.
            </p>
          )}
          <Textarea
            id="message-body"
            aria-invalid={!!error}
            aria-describedby="message-help"
            value={body}
            maxLength={10000}
            rows={3}
            required
            disabled={busy}
            onChange={(event) => {
              setBody(event.target.value);
              setError("");
            }}
          />
          <FieldDescription id="message-help">
            {body.length.toLocaleString("ru-RU")} / 10 000 символов
          </FieldDescription>
        </Field>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <Button disabled={busy || !body.trim()}>
          <Send data-icon="inline-start" aria-hidden="true" />
          {busy ? "Отправляем…" : "Отправить сообщение"}
        </Button>
      </form>
    </section>
  );
}

type Action = "request_info" | "resolve" | "reject";
export function ReviewPanel({
  appeal,
  onUpdated,
  onReload,
}: {
  appeal: Detail;
  onUpdated: (appeal: Detail) => void;
  onReload: () => void;
}) {
  const [action, setAction] = useState<Action>("request_info");
  const [explanation, setExplanation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  async function save(action: Action | "start") {
    if (action !== "start" && !explanation.trim()) {
      setError("Добавьте вопрос, описание результата или причину отклонения.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await api<Detail>(
        `/appeals/${appeal.id}/review`,
        "POST",
        {
          action,
          explanation: action === "start" ? "" : explanation.trim(),
          expected_version: appeal.assignment_version,
        },
      );
      if (action !== "start") setExplanation("");
      onUpdated(updated);
    } catch (error) {
      setError((error as Error).message);
      if (error instanceof ApiError && error.status === 409) setStale(true);
    } finally {
      setBusy(false);
    }
  }
  const labels = {
    request_info: "Вопрос автору",
    resolve: "Что выполнено и какой результат получен",
    reject: "Причина отклонения",
  };
  return (
    <section className="card section-gap review-panel">
      <h2>Рассмотрение обращения</h2>
      {appeal.status === "reviewing" && (
        <Button
          variant="outline"
          disabled={busy || stale}
          onClick={() => save("start")}
        >
          Принять в работу
        </Button>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save(action);
        }}
      >
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="review-action">Действие</FieldLabel>
            <select
              id="review-action"
              value={action}
              disabled={busy || stale}
              onChange={(event) => {
                setAction(event.target.value as Action);
                setError("");
              }}
            >
              <option value="request_info">Запросить уточнение</option>
              <option value="resolve">Зафиксировать выполнение</option>
              <option value="reject">Отклонить обращение</option>
            </select>
          </Field>
          <Field>
            <FieldLabel htmlFor="review-explanation">
              {labels[action]}
            </FieldLabel>
            <Textarea
              id="review-explanation"
              value={explanation}
              onChange={(event) => setExplanation(event.target.value)}
              rows={4}
              maxLength={10000}
              required
              disabled={busy || stale}
            />
            {action === "resolve" && (
              <p className="hint">
                Результат будет виден автору. Обращение перейдёт в ожидание
                подтверждения.
              </p>
            )}
          </Field>
        </FieldGroup>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {stale ? (
          <Button variant="outline" type="button" onClick={onReload}>
            Загрузить актуальную карточку
          </Button>
        ) : (
          <Button
            variant="outline"
            className="primary compact"
            disabled={busy || !explanation.trim()}
          >
            {busy
              ? "Сохраняем…"
              : action === "request_info"
                ? "Отправить запрос"
                : action === "resolve"
                  ? "Сохранить результат"
                  : "Отклонить с объяснением"}
          </Button>
        )}
      </form>
    </section>
  );
}

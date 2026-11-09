import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
  FieldSet,
  FieldLegend,
} from "./components/ui/field";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "./components/ui/toggle-group";
import { Plus, ArrowRight, MessageSquare, CheckCheck } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./components/ui/tabs";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
} from "./components/ui/empty";
import { Skeleton } from "./components/ui/skeleton";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Experiments } from "./experiments";
import { AIAssistant } from "./ai-assistant";
import { downloadAttachment } from "./api";
import { FeedbackPanel, FeedbackHistory } from "./feedback";
import type { Feedback } from "./feedback";
import { Conversation, ReviewPanel } from "./discussion";
import { AssignmentPanel } from "./assignment";
import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent, MouseEvent } from "react";
import { api } from "./api";
import type { User } from "./api";
import { navigate, usePath } from "./navigation";

export const categories = {
  warehouse: "Склад и логистика",
  sales: "Продажи и ассортимент",
  process: "Рабочие инструменты и процессы",
  workplace: "Условия труда",
  other: "Другое",
};
export const statusNames: Record<string, string> = {
  received: "Получено",
  reviewing: "На рассмотрении",
  needs_info: "Нужно уточнение",
  in_progress: "В работе",
  awaiting_confirmation: "Ожидает подтверждения",
  closed: "Закрыто",
  rejected: "Отклонено",
};
type Kind = "problem" | "idea";
type Category = keyof typeof categories;
type Draft = {
  original_description?: string;
  kind: Kind;
  title: string;
  description: string;
  category: Category;
};
export type Summary = {
  id: number;
  number: string;
  kind: Kind;
  title: string;
  category: Category;
  status: string;
  responsible: string | null;
  responsible_id: string | null;
  responsible_available: boolean | null;
  assignment_version: number;
  author: string;
  author_id: string;
  company: string;
  department: string;
  company_id: string;
  department_id: string;
  is_overdue: boolean;
  next_response_at: string | null;
  created_at: string;
  attachment_count: number;
};
type Attachment = {
  id: string;
  filename: string;
  size: number;
  download_url: string;
};
export type Detail = Summary & {
  original_description: string;
  feedback: Feedback[];
  decision: string | null;
  result: string | null;
  decided_at: string | null;
  description: string;
  author: string;
  company: string;
  department: string;
  attachments: Attachment[];
  history: { id: string; actor: string; text: string; created_at: string }[];
};
type Page = {
  items: Summary[];
  total: number;
  page: number;
  page_size: number;
};
const emptyDraft = (): Draft => ({
  kind: "problem",
  title: "",
  description: "",
  category: "other",
});
export const date = (value: string) =>
  new Date(value).toLocaleString("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  });
const size = (bytes: number) =>
  bytes < 1024 * 1024
    ? `${Math.max(1, Math.ceil(bytes / 1024))} КБ`
    : `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
export function openLink(event: MouseEvent<HTMLAnchorElement>, path: string) {
  if (
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey
  ) {
    event.preventDefault();
    navigate(path);
  }
}
function ErrorMessage({ message }: { message: string }) {
  return message ? (
    <p className="error" role="alert">
      {message}
    </p>
  ) : null;
}
export function Status({ status }: { status: string }) {
  return (
    <Badge
      variant="secondary"
      className={`pill appeal-status status-${status}`}
    >
      {statusNames[status] || status}
    </Badge>
  );
}
function Files({ files }: { files: Attachment[] }) {
  const [error, setError] = useState("");
  return files.length ? (
    <>
      {" "}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <ul className="attachment-list">
        {files.map((file) => (
          <li key={file.id}>
            <a
              href={file.download_url}
              onClick={(event) => {
                event.preventDefault();
                void downloadAttachment(file.download_url, file.filename).catch(
                  (e) => setError((e as Error).message),
                );
              }}
            >
              {file.filename}
              <span>{size(file.size)} · Скачать</span>
            </a>
          </li>
        ))}
      </ul>
    </>
  ) : (
    <p className="hint">Нет вложений.</p>
  );
}

function AppealList({ notice }: { notice: string }) {
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page | null>(null);
  const [attention, setAttention] = useState<Page | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    Promise.all([
      api<Page>(`/appeals?filter=${filter}&page=${page}`),
      api<Page>("/appeals?filter=needs_reply&page_size=3"),
    ])
      .then(([journal, replies]) => {
        if (!cancelled) {
          setData(journal);
          setAttention(replies);
        }
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
  }, [filter, page, attempt]);
  const changeFilter = (value: string) => {
    setFilter(value);
    setPage(1);
  };
  return (
    <section className="employee-workspace">
      <div className="appeal-heading">
        <div>
          <h1>Мои обращения</h1>
          <p className="hint">
            Следите за ответами и проверяйте, что изменилось.
          </p>
        </div>
        <Button onClick={() => navigate("/appeals/new")}>
          <Plus data-icon="inline-start" aria-hidden="true" />
          Новое обращение
        </Button>
      </div>
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      {error ? (
        <div className="workspace-error">
          <ErrorMessage message={error} />
          <Button
            variant="outline"
            onClick={() => setAttempt((value) => value + 1)}
          >
            Повторить загрузку
          </Button>
        </div>
      ) : (
        <>
          {loading && !attention ? (
            <div
              role="status"
              aria-label="Загружаем обращения"
              className="employee-loading"
            >
              <Skeleton />
              <Skeleton />
              <Skeleton />
            </div>
          ) : (
            attention && (
              <section
                className="reply-section"
                aria-labelledby="reply-heading"
              >
                <div className="section-heading">
                  <h2 id="reply-heading">
                    Нужен ваш ответ{" "}
                    <span className="reply-count">{attention.total}</span>
                  </h2>
                  {attention.total > 3 && (
                    <Button
                      variant="ghost"
                      onClick={() => changeFilter("needs_reply")}
                    >
                      Все ожидающие ответа
                      <ArrowRight data-icon="inline-end" aria-hidden="true" />
                    </Button>
                  )}
                </div>
                {attention.items.length ? (
                  <div className="reply-list">
                    {attention.items.map((item) => (
                      <a
                        key={item.id}
                        className="reply-row"
                        href={`/appeals/${item.id}`}
                        onClick={(event) =>
                          openLink(event, `/appeals/${item.id}`)
                        }
                      >
                        <span className="reply-icon">
                          {item.status === "needs_info" ? (
                            <MessageSquare aria-hidden="true" />
                          ) : (
                            <CheckCheck aria-hidden="true" />
                          )}
                        </span>
                        <div>
                          <span className="record-number">{item.number}</span>
                          <h3>{item.title}</h3>
                          <p>
                            {item.status === "needs_info"
                              ? "Ответственному нужны подробности, чтобы продолжить работу."
                              : "Результат готов. Подтвердите, что помогло, или верните в работу."}
                          </p>
                        </div>
                        <span className="reply-action">
                          {item.status === "needs_info"
                            ? "Ответить на уточнение"
                            : "Проверить результат"}
                          <ArrowRight aria-hidden="true" />
                        </span>
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="reply-clear">
                    <CheckCheck aria-hidden="true" />
                    Сейчас от вас ничего не требуется. Новые ответы появятся
                    здесь.
                  </p>
                )}
              </section>
            )
          )}
          <section
            className="journal-section"
            aria-labelledby="journal-heading"
          >
            <div className="section-heading">
              <h2 id="journal-heading">Журнал обращений</h2>
              {!loading && data && (
                <span className="hint">Всего в разделе: {data.total}</span>
              )}
            </div>
            <Tabs
              value={filter}
              onValueChange={changeFilter}
              className="journal-tabs"
            >
              <TabsList aria-label="Фильтры обращений">
                <TabsTrigger value="all">Все</TabsTrigger>
                <TabsTrigger value="active">Активные</TabsTrigger>
                <TabsTrigger value="needs_reply">Нужен мой ответ</TabsTrigger>
                <TabsTrigger value="completed">Завершённые</TabsTrigger>
              </TabsList>
              <TabsContent value={filter} aria-busy={loading}>
                {loading && (
                  <div
                    role="status"
                    aria-label="Загружаем журнал"
                    className="employee-loading"
                  >
                    <Skeleton />
                    <Skeleton />
                  </div>
                )}
                {!loading &&
                  data &&
                  (data.items.length ? (
                    <>
                      <div className="employee-journal">
                        <div className="journal-labels" aria-hidden="true">
                          <span>Обращение</span>
                          <span>Статус</span>
                          <span>Ответственный / срок</span>
                          <span />
                        </div>
                        {data.items.map((item) => (
                          <a
                            className="journal-row"
                            href={`/appeals/${item.id}`}
                            key={item.id}
                            onClick={(event) =>
                              openLink(event, `/appeals/${item.id}`)
                            }
                          >
                            <div className="journal-subject">
                              <span className="record-number">
                                {item.number} ·{" "}
                                {item.kind === "problem" ? "Проблема" : "Идея"}
                              </span>
                              <h3>{item.title}</h3>
                              <p>
                                {categories[item.category]} ·{" "}
                                {new Date(item.created_at).toLocaleDateString(
                                  "ru-RU",
                                )}
                                {item.attachment_count > 0 &&
                                  ` · Файлов: ${item.attachment_count}`}
                              </p>
                            </div>
                            <div className="journal-status">
                              <Status status={item.status} />
                            </div>
                            <div className="journal-owner">
                              <span>
                                {item.responsible ||
                                  "Ответственный не назначен"}
                              </span>
                              <p
                                className={
                                  item.is_overdue ? "journal-overdue" : ""
                                }
                              >
                                {["closed", "rejected"].includes(item.status)
                                  ? "Рассмотрение завершено"
                                  : [
                                        "needs_info",
                                        "awaiting_confirmation",
                                      ].includes(item.status)
                                    ? "Следующий шаг — ваш ответ"
                                    : item.next_response_at
                                      ? `${item.is_overdue ? "Срок ответа истёк" : "Ответ до"} ${date(item.next_response_at)}`
                                      : "Срок ответа не назначен"}
                              </p>
                            </div>
                            <ArrowRight
                              className="journal-arrow"
                              aria-hidden="true"
                            />
                          </a>
                        ))}
                      </div>
                      {data.total > data.page_size && (
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
                            {Math.ceil(data.total / data.page_size)}
                          </span>
                          <Button
                            variant="outline"
                            disabled={page * data.page_size >= data.total}
                            onClick={() => setPage((value) => value + 1)}
                          >
                            Далее
                          </Button>
                        </div>
                      )}
                    </>
                  ) : (
                    <Empty className="journal-empty">
                      <EmptyHeader>
                        <EmptyTitle>
                          {filter === "all"
                            ? "Что можно сделать лучше?"
                            : filter === "needs_reply"
                              ? "Вы на всё ответили"
                              : "В этом разделе пока нет обращений"}
                        </EmptyTitle>
                        <EmptyDescription>
                          {filter === "all"
                            ? "Сообщите о проблеме или предложите идею. Здесь будут ответы, сроки и история ваших обращений."
                            : "Все ваши обращения доступны на вкладке «Все»."}
                        </EmptyDescription>
                      </EmptyHeader>
                      <EmptyContent>
                        <Button
                          variant="outline"
                          onClick={() =>
                            filter === "all"
                              ? navigate("/appeals/new")
                              : changeFilter("all")
                          }
                        >
                          {filter === "all"
                            ? "Создать обращение"
                            : "Показать все"}
                        </Button>
                      </EmptyContent>
                    </Empty>
                  ))}
              </TabsContent>
            </Tabs>
          </section>
        </>
      )}
    </section>
  );
}

export function AppealCard({
  id,
  notice,
  user,
  backPath = "/appeals",
}: {
  id: number;
  notice: string;
  user: User;
  backPath?: string;
}) {
  const [assignmentNotice, setAssignmentNotice] = useState("");
  const [appeal, setAppeal] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    api<Detail>(`/appeals/${id}`)
      .then((result) => {
        if (!cancelled) setAppeal(result);
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
  }, [id, attempt]);
  return (
    <section className="appeal-detail">
      <Button
        variant="outline"
        className="back-link"
        onClick={() => navigate(backPath)}
      >
        {backPath === "/queue" ? "← Очередь обращений" : "← Мои обращения"}
      </Button>
      <Button
        variant="outline"
        className="card-refresh"
        onClick={() => {
          setAssignmentNotice("");
          setAttempt((value) => value + 1);
        }}
        disabled={loading}
      >
        Обновить карточку
      </Button>
      {notice && (
        <p className="success" role="status">
          {notice}
        </p>
      )}
      {assignmentNotice && (
        <p className="success" role="status">
          {assignmentNotice}
        </p>
      )}
      <ErrorMessage message={error} />
      {error ? (
        <Button
          variant="outline"
          onClick={() => setAttempt((value) => value + 1)}
        >
          Повторить загрузку
        </Button>
      ) : loading ? (
        <div
          className="employee-loading"
          role="status"
          aria-label="Загружаем обращение"
        >
          <Skeleton />
          <Skeleton />
          <Skeleton />
        </div>
      ) : (
        appeal && (
          <>
            <div className="appeal-heading">
              <div>
                <h1>{appeal.title}</h1>
                <p className="hint">
                  {appeal.number} · {categories[appeal.category]} ·{" "}
                  {date(appeal.created_at)}
                </p>
              </div>
              <Status status={appeal.status} />
            </div>
            {appeal.status === "in_progress" &&
              !appeal.next_response_at &&
              appeal.feedback.some((item) => item.outcome === "reopen") && (
                <p className="warning">
                  Обращение возвращено в работу. Срок следующего ответа пока не
                  назначен; координатору нужно установить новый срок.
                </p>
              )}
            {appeal.status === "received" &&
              appeal.feedback.some((item) => item.outcome === "reopen") && (
                <p className="warning">
                  Прежний ответственный недоступен. Обращение возвращено
                  координатору для нового назначения.
                </p>
              )}
            {appeal.is_overdue && (
              <p className="warning" role="status">
                Срок ответа просрочен:{" "}
                {appeal.next_response_at && date(appeal.next_response_at)}.
              </p>
            )}
            {appeal.responsible_available === false &&
              !["closed", "rejected", "awaiting_confirmation"].includes(
                appeal.status,
              ) && (
                <p className="warning">
                  Назначенный ответственный недоступен. Координатору нужно
                  выбрать другого сотрудника.
                </p>
              )}
            {backPath === "/queue" &&
              user.roles.includes("coordinator") &&
              !["closed", "rejected"].includes(appeal.status) && (
                <AssignmentPanel
                  key={`${appeal.id}-${appeal.assignment_version}`}
                  appeal={appeal}
                  onUpdated={(updated) => {
                    setAppeal(updated);
                    setAssignmentNotice(
                      "Назначение сохранено. Ответственный и срок доступны автору.",
                    );
                  }}
                  onReload={() => {
                    setAssignmentNotice("");
                    setAttempt((value) => value + 1);
                  }}
                />
              )}
            <div className="appeal-columns">
              <div>
                {appeal.result && (
                  <section className="card section-gap decision-result">
                    <h2>
                      {appeal.decision === "Отклонено"
                        ? "Причина отклонения"
                        : "Результат выполнения"}
                    </h2>
                    <p className="preserve-text">{appeal.result}</p>
                    {appeal.decided_at && (
                      <p className="hint note">
                        Зафиксировано: {date(appeal.decided_at)}
                      </p>
                    )}
                    {appeal.status === "awaiting_confirmation" && (
                      <p className="result-next-step">
                        {appeal.author_id === user.id
                          ? "Проверьте результат в работе. Только ваше подтверждение закроет обращение."
                          : "Ожидается подтверждение результата автором."}
                      </p>
                    )}
                  </section>
                )}
                {appeal.status === "awaiting_confirmation" &&
                  appeal.author_id === user.id && (
                    <FeedbackPanel
                      appeal={appeal}
                      onUpdated={(updated) => {
                        setAppeal(updated);
                        setAssignmentNotice(
                          updated.status === "closed"
                            ? "Вы подтвердили результат. Обращение закрыто."
                            : "Обращение возвращено на рассмотрение. Ваш комментарий сохранён.",
                        );
                      }}
                      onReload={() => setAttempt((value) => value + 1)}
                    />
                  )}
                {appeal.status === "closed" &&
                  appeal.feedback.some((item) => item.outcome === "helped") && (
                    <p className="success" role="status">
                      Результат подтверждён автором. Обращение закрыто.
                    </p>
                  )}
                {(user.roles.includes("coordinator") ||
                  (user.roles.includes("responsible") &&
                    appeal.responsible_id === user.id)) &&
                  ["reviewing", "in_progress"].includes(appeal.status) && (
                    <ReviewPanel
                      appeal={appeal}
                      onUpdated={(updated) => {
                        setAppeal(updated);
                        setAssignmentNotice("Действие сохранено.");
                      }}
                      onReload={() => setAttempt((value) => value + 1)}
                    />
                  )}
                {appeal.status === "needs_info" && (
                  <p className="warning">
                    Ожидается ответ автора на запрос уточнения в переписке.
                  </p>
                )}
                <Conversation
                  appeal={appeal}
                  user={user}
                  onUpdated={setAppeal}
                />
                <section className="card">
                  <h2>Описание</h2>
                  <p className="preserve-text">{appeal.description}</p>
                  {appeal.original_description &&
                    appeal.original_description !== appeal.description && (
                      <details>
                        <summary>Исходный текст автора</summary>
                        <p className="preserve-text">
                          {appeal.original_description}
                        </p>
                      </details>
                    )}
                  <h3 className="section-gap">
                    Вложения{" "}
                    <span className="count">{appeal.attachments.length}</span>
                  </h3>
                  <Files files={appeal.attachments} />
                </section>
                <Experiments
                  appeal={appeal}
                  user={user}
                  onReload={() => setAttempt((value) => value + 1)}
                />
                <FeedbackHistory items={appeal.feedback} />
                <section className="card section-gap">
                  <h2>История обращения</h2>
                  <ol className="timeline">
                    {appeal.history.map((event) => (
                      <li key={event.id}>
                        <strong>{event.text}</strong>
                        <p className="hint">
                          {event.actor} · {date(event.created_at)}
                        </p>
                      </li>
                    ))}
                  </ol>
                </section>
              </div>
              <aside className="card appeal-aside">
                <h2>По обращению</h2>
                {appeal.status === "received" && (
                  <p className="hint">
                    Обращение получено. Координатор назначит ответственного для
                    рассмотрения.
                  </p>
                )}
                <dl>
                  <dt>Ответственный</dt>
                  <dd>{appeal.responsible || "Пока не назначен"}</dd>
                  <dt>Дата следующего ответа</dt>
                  <dd>
                    {appeal.next_response_at
                      ? date(appeal.next_response_at)
                      : [
                            "awaiting_confirmation",
                            "closed",
                            "rejected",
                          ].includes(appeal.status)
                        ? "Ответ уже предоставлен"
                        : "Пока не назначена"}
                  </dd>
                  <dt>Автор</dt>
                  <dd>{appeal.author}</dd>
                  <dt>Компания</dt>
                  <dd>{appeal.company}</dd>
                  <dt>Подразделение</dt>
                  <dd>{appeal.department}</dd>
                </dl>
              </aside>
            </div>
          </>
        )
      )}
    </section>
  );
}

function AppealForm({
  draft,
  setDraft,
  files,
  setFiles,
  onSend,
  sending,
  sendError,
  onCancel,
  user,
}: {
  draft: Draft;
  setDraft: (draft: Draft) => void;
  files: File[];
  setFiles: (files: File[]) => void;
  onSend: () => void;
  sending: boolean;
  sendError: string;
  onCancel: () => void;
  user: User;
}) {
  const [preview, setPreview] = useState(false);
  const [assistantNotice, setAssistantNotice] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [fileError, setFileError] = useState("");
  const formRef = useRef<HTMLFormElement>(null);
  function change<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft({ ...draft, [key]: value });
    setErrors((previous) => ({ ...previous, [key]: "" }));
  }
  function review(event: FormEvent) {
    event.preventDefault();
    const errors: Record<string, string> = {};
    if (draft.title.trim().length < 5)
      errors.title = "Добавьте заголовок от 5 до 160 символов.";
    if (draft.description.trim().length < 10)
      errors.description = "Опишите ситуацию подробнее: минимум 10 символов.";
    setErrors(errors);
    if (Object.keys(errors).length) {
      requestAnimationFrame(() =>
        formRef.current
          ?.querySelector<HTMLElement>('[aria-invalid="true"]')
          ?.focus(),
      );
      return;
    }
    setPreview(true);
    window.scrollTo({ top: 0 });
  }
  function selectFiles(event: ChangeEvent<HTMLInputElement>) {
    const added = Array.from(event.target.files || []);
    event.target.value = "";
    setFileError("");
    if (files.length + added.length > 5) {
      setFileError("Можно прикрепить не более 5 файлов.");
      return;
    }
    for (const file of added) {
      if (!file.size) {
        setFileError(`Файл «${file.name}» пуст.`);
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        setFileError(`Файл «${file.name}» превышает 10 МБ.`);
        return;
      }
      if (!/\.(jpe?g|png|webp|pdf)$/i.test(file.name)) {
        setFileError("Поддерживаются JPEG, PNG, WebP и PDF.");
        return;
      }
    }
    setFiles([...files, ...added]);
  }
  return (
    <section className="new-appeal">
      <Button
        variant="ghost"
        className="back-link"
        disabled={sending}
        onClick={() => (preview ? setPreview(false) : onCancel())}
      >
        {preview ? "← Изменить обращение" : "← Мои обращения"}
      </Button>
      <div className="appeal-heading">
        <div>
          <h1>{preview ? "Проверьте обращение" : "Новое обращение"}</h1>
          <p className="hint">
            {preview
              ? "Убедитесь, что описание и вложения верны. Пока ничего не отправлено."
              : "Одна ситуация или идея — одно обращение. Начните со своих слов."}
          </p>
        </div>
      </div>
      <div className="appeal-columns">
        <section className="card appeal-form-card">
          {preview ? (
            <div className="appeal-preview">
              <div className="preview-meta">
                <Badge variant="secondary">
                  {draft.kind === "problem" ? "Проблема" : "Идея"}
                </Badge>
                <span className="hint">{categories[draft.category]}</span>
              </div>
              <h2>{draft.title.trim()}</h2>
              <p className="preserve-text">{draft.description.trim()}</p>
              <h3>
                Вложения <span className="hint">{files.length}</span>
              </h3>
              {files.length ? (
                <ul className="preview-files">
                  {files.map((file, index) => (
                    <li key={index}>
                      {file.name}
                      <span className="hint">{size(file.size)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="hint">Без вложений.</p>
              )}
              <p className="preview-author">
                Автор: {user.name}. Компания и подразделение — из вашего
                профиля.
              </p>
              <ErrorMessage message={sendError} />
              <div className="form-actions">
                <Button
                  variant="outline"
                  disabled={sending}
                  onClick={() => setPreview(false)}
                >
                  Изменить
                </Button>
                <Button disabled={sending} onClick={onSend}>
                  {sending ? "Отправляем…" : "Отправить обращение"}
                  <ArrowRight data-icon="inline-end" aria-hidden="true" />
                </Button>
              </div>
            </div>
          ) : (
            <form ref={formRef} noValidate onSubmit={review}>
              <FieldGroup>
                <FieldSet>
                  <FieldLegend>Что хотите отправить?</FieldLegend>
                  <ToggleGroup
                    type="single"
                    value={draft.kind}
                    onValueChange={(value) => {
                      if (value) change("kind", value as Kind);
                    }}
                    className="appeal-kind"
                    aria-label="Тип обращения"
                  >
                    <ToggleGroupItem value="problem">
                      <strong>Проблема</strong>
                      <span>Что-то мешает работе</span>
                    </ToggleGroupItem>
                    <ToggleGroupItem value="idea">
                      <strong>Идея</strong>
                      <span>Предлагаю улучшение</span>
                    </ToggleGroupItem>
                  </ToggleGroup>
                </FieldSet>
                <Field data-invalid={!!errors.description}>
                  <FieldLabel htmlFor="appeal-description">
                    {draft.kind === "problem"
                      ? "Что происходит?"
                      : "Что предлагаете изменить?"}
                  </FieldLabel>
                  <Textarea
                    id="appeal-description"
                    value={draft.description}
                    onChange={(event) => {
                      change("description", event.target.value);
                      setAssistantNotice("");
                    }}
                    minLength={10}
                    maxLength={10000}
                    rows={6}
                    required
                    aria-invalid={!!errors.description}
                    aria-describedby="description-help"
                    placeholder={
                      draft.kind === "problem"
                        ? "Где возникает проблема? Как часто? Как она влияет на вашу работу?"
                        : "Расскажите об идее: что изменится и кому это поможет."
                    }
                  />
                  <div className="field-help">
                    <FieldDescription id="description-help">
                      {errors.description ||
                        "Достаточно понятного описания. Официальный стиль не нужен."}
                    </FieldDescription>
                    <span className="hint">
                      {draft.description.length.toLocaleString("ru-RU")} / 10
                      000
                    </span>
                  </div>
                </Field>
                <AIAssistant
                  kind={draft.kind}
                  description={draft.description}
                  onApply={(value) => {
                    setDraft({
                      ...draft,
                      title: value.title,
                      description: value.description,
                      category: value.category as Category,
                      original_description:
                        draft.original_description || draft.description,
                    });
                    setErrors({});
                    setAssistantNotice(
                      "Предложение применено. Проверьте обновлённые поля перед отправкой.",
                    );
                  }}
                />
                {assistantNotice && (
                  <p className="assistant-applied" role="status">
                    <CheckCheck aria-hidden="true" />
                    {assistantNotice}
                  </p>
                )}
                <Field data-invalid={!!errors.title}>
                  <FieldLabel htmlFor="appeal-title">
                    Короткий заголовок
                  </FieldLabel>
                  <Input
                    id="appeal-title"
                    value={draft.title}
                    onChange={(event) => change("title", event.target.value)}
                    minLength={5}
                    maxLength={160}
                    required
                    aria-invalid={!!errors.title}
                    aria-describedby="title-help"
                    placeholder="Например, похожие коробки путают при отгрузке"
                  />
                  <FieldDescription id="title-help">
                    {errors.title ||
                      "Суть обращения в одной строке. От 5 до 160 символов."}
                  </FieldDescription>
                </Field>
                <Field>
                  <FieldLabel htmlFor="appeal-category">Категория</FieldLabel>
                  <select
                    id="appeal-category"
                    value={draft.category}
                    onChange={(event) =>
                      change("category", event.target.value as Category)
                    }
                  >
                    {Object.entries(categories).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                  <FieldDescription>
                    Не уверены — оставьте «Другое». Координатор разберётся.
                  </FieldDescription>
                </Field>
                <Field data-invalid={!!fileError}>
                  <FieldLabel htmlFor="appeal-files">
                    Вложения <span className="optional">необязательно</span>
                  </FieldLabel>
                  <Input
                    id="appeal-files"
                    type="file"
                    multiple
                    accept=".jpg,.jpeg,.png,.webp,.pdf"
                    onChange={selectFiles}
                    aria-invalid={!!fileError}
                    aria-describedby="files-help"
                  />
                  <FieldDescription id="files-help">
                    До 5 файлов по 10 МБ. Фото в JPEG, PNG, WebP или документ
                    PDF.
                  </FieldDescription>
                  <ErrorMessage message={fileError} />
                  {files.length > 0 && (
                    <ul className="selected-files">
                      {files.map((file, index) => (
                        <li key={index}>
                          <div>
                            <strong>{file.name}</strong>
                            <span className="hint">{size(file.size)}</span>
                          </div>
                          <Button
                            variant="ghost"
                            type="button"
                            aria-label={`Убрать файл ${file.name}`}
                            onClick={() => {
                              setFiles(files.filter((_, i) => i !== index));
                              setFileError("");
                            }}
                          >
                            Убрать
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </Field>
              </FieldGroup>
              <div className="form-actions">
                <Button variant="ghost" type="button" onClick={onCancel}>
                  Отменить
                </Button>
                <Button type="submit">
                  Проверить обращение
                  <ArrowRight data-icon="inline-end" aria-hidden="true" />
                </Button>
              </div>
              <p className="form-reassurance">
                На следующем экране можно всё проверить и изменить.
              </p>
            </form>
          )}
        </section>
        <aside className="appeal-form-guide">
          <h2>
            {preview
              ? "Что будет после отправки"
              : "Не нужно искать ответственного"}
          </h2>
          <p>
            Координатор направит обращение нужному человеку. Ответы и срок
            появятся в вашем кабинете.
          </p>
          <div>
            <h3>Обращение именное</h3>
            <p>Ваше имя видно сотрудникам, которые рассматривают обращение.</p>
          </div>
          <div>
            <h3>Результат проверяете вы</h3>
            <p>Подтвердите, что помогло, или верните обращение в работу.</p>
          </div>
        </aside>
      </div>
    </section>
  );
}

export function Appeals({ user }: { user: User }) {
  const path = usePath();
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [files, setFiles] = useState<File[]>([]);
  const [submissionId, setSubmissionId] = useState(() => crypto.randomUUID());
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [noticeId, setNoticeId] = useState<number | null>(null);
  function reset() {
    setDraft(emptyDraft());
    setFiles([]);
    setSubmissionId(crypto.randomUUID());
    setError("");
  }
  async function send() {
    if (sending) return;
    setSending(true);
    setError("");
    const data = new FormData();
    data.set("kind", draft.kind);
    data.set("title", draft.title.trim());
    data.set("description", draft.description.trim());
    data.set("category", draft.category);
    if (draft.original_description)
      data.set("original_description", draft.original_description);
    data.set("submission_id", submissionId);
    files.forEach((file) => data.append("files", file));
    try {
      const appeal = await api<Detail>("/appeals", "POST", data);
      reset();
      setNoticeId(appeal.id);
      setNotice(
        `Обращение ${appeal.number} принято. Оно сохранено в вашем кабинете.`,
      );
      navigate(`/appeals/${appeal.id}`);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setSending(false);
    }
  }
  if (path === "/appeals/new")
    return (
      <AppealForm
        draft={draft}
        setDraft={(value) => {
          setDraft(value);
          setError("");
        }}
        files={files}
        setFiles={setFiles}
        sending={sending}
        sendError={error}
        onSend={send}
        onCancel={() => {
          reset();
          setNotice("");
          navigate("/appeals");
        }}
        user={user}
      />
    );
  const match = /^\/appeals\/([1-9]\d*)$/.exec(path);
  if (match)
    return (
      <AppealCard
        key={Number(match[1])}
        user={user}
        id={Number(match[1])}
        notice={noticeId === Number(match[1]) ? notice : ""}
      />
    );
  return <AppealList notice={notice} />;
}

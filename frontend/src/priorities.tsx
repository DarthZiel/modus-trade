import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api } from "./api";
import { date } from "./appeals";
import { Alert, AlertDescription } from "./components/ui/alert";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Field, FieldGroup, FieldLabel } from "./components/ui/field";
import { Textarea } from "./components/ui/textarea";
import { Skeleton } from "./components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "./components/ui/toggle-group";
import { Sparkles, LoaderCircle, Pencil, RefreshCw } from "lucide-react";

export type Lane = "attention" | "promising" | "routine";
export type Level = "high" | "medium" | "low";
export type Evaluation = {
  lane: Lane;
  level: Level;
  reason: string;
  next_step: string;
  source: string;
  updated_at: string | null;
  reviewer: string | null;
};
export type Priority = {
  appeal_id: number;
  version: number;
  effective: Evaluation;
  ai: Evaluation | null;
  manual: Evaluation | null;
  assessed: boolean;
  stale: boolean;
  repeat_count: number;
  repeat_authors: number;
  overdue: boolean;
  measured: boolean;
  reopened: boolean;
  history: {
    action: string;
    lane: Lane;
    level: Level;
    reason: string;
    next_step: string;
    source: string;
    actor: string;
    created_at: string;
    version: number;
  }[];
};
export const laneNames: Record<Lane, string> = {
  attention: "Требуют внимания",
  promising: "Перспективные идеи",
  routine: "Обычная очередь",
};
export const levelNames: Record<Level, string> = {
  high: "Высокий приоритет",
  medium: "Средний приоритет",
  low: "Низкий приоритет",
};
export const sourceName = (source: string) =>
  ({
    coordinator: "Оценка координатора",
    openai: "Предложение ИИ",
    openrouter: "Предложение ИИ",
    demo: "Локальные правила, без ИИ",
    dataset: "Подготовлено для демонстрации",
    rules: "Правила системы",
    unassessed: "Ещё не оценено",
  })[source] || source;
export type AIStatus = { mode: string; available: boolean };
export function usePriorityAI() {
  const [status, setStatus] = useState<AIStatus>();
  useEffect(() => {
    let active = true;
    api<AIStatus>("/ai/status")
      .then((value) => {
        if (active) setStatus(value);
      })
      .catch(() => {
        if (active) setStatus({ mode: "disabled", available: false });
      });
    return () => {
      active = false;
    };
  }, []);
  return status;
}
export function PriorityConsent({
  status,
  consent,
  setConsent,
  disabled = false,
}: {
  status?: AIStatus;
  consent: boolean;
  setConsent: (value: boolean) => void;
  disabled?: boolean;
}) {
  if (!status) return null;
  if (status.mode === "demo")
    return (
      <p className="hint">
        Демонстрационный режим: оценка по локальным правилам, без обращения к
        модели.
      </p>
    );
  if (!status.available)
    return (
      <p className="hint">
        ИИ-оценка не подключена. Координатор может установить приоритет вручную.
      </p>
    );
  return (
    <FieldGroup>
      <Field>
        <FieldLabel className="check">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
            disabled={disabled}
          />
          Разрешаю передать заголовки, описания и показатели обращений в{" "}
          {status.mode === "openrouter"
            ? "OpenRouter и выбранную модель"
            : "OpenAI"}
          . Профили, переписка и вложения не передаются.
        </FieldLabel>
      </Field>
    </FieldGroup>
  );
}
export function PriorityReason({ priority }: { priority: Priority }) {
  const value = priority.effective;
  return (
    <div className="priority-reason">
      <div className="priority-labels">
        <Badge variant={value.level === "high" ? "destructive" : "secondary"}>
          {levelNames[value.level]}
        </Badge>
        <span className="hint">{sourceName(value.source)}</span>
        {priority.manual?.reviewer && (
          <span className="hint">{priority.manual.reviewer}</span>
        )}
      </div>
      <p className="preserve-text">{value.reason}</p>
      {value.next_step && (
        <p className="priority-next-step">
          <strong>Следующий шаг:</strong> {value.next_step}
        </p>
      )}
      <p className="hint">
        {priority.measured
          ? "Есть измерения эксперимента; причинный эффект требует проверки."
          : "Количественный эффект не подтверждён."}
        {priority.repeat_count > 1 || priority.repeat_authors > 1
          ? ` Обращений по теме: ${priority.repeat_count}, сотрудников: ${priority.repeat_authors}.`
          : ""}
        {priority.reopened ? " Автор возвращал обращение в работу." : ""}
      </p>
      {priority.stale && (
        <p className="priority-stale">
          Данные изменились после оценки ИИ. Координатору нужно проверить
          актуальность приоритета.
        </p>
      )}
    </div>
  );
}
export function PriorityPanel({
  appealId,
  editable,
  kind,
}: {
  appealId: number;
  editable: boolean;
  kind: string;
}) {
  const [value, setValue] = useState<Priority>();
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [consent, setConsent] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({
    lane: "routine" as Lane,
    level: "low" as Level,
    reason: "",
    next_step: "",
  });
  const status = usePriorityAI();
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<Priority>(`/work/appeals/${appealId}/priority`)
      .then((result) => {
        if (active) setValue(result);
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
  }, [appealId, attempt]);
  async function suggest() {
    if (!value) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<Priority[]>("/work/priorities/suggest", "POST", {
        appeals: [{ appeal_id: appealId, expected_version: value.version }],
        consent,
      });
      setValue(result[0]);
      setNotice(
        result[0].manual
          ? "Предложение обновлено. Ручная оценка координатора сохранена."
          : "Предложение готово. Проверьте причину и следующий шаг.",
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!value) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setValue(
        await api<Priority>(`/work/appeals/${appealId}/priority`, "PATCH", {
          ...draft,
          expected_version: value.version,
        }),
      );
      setEditing(false);
      setNotice(
        "Оценка координатора сохранена. Она определяет порядок в кабинете директора.",
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function useAI() {
    if (!value) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setValue(
        await api<Priority>(
          `/work/appeals/${appealId}/priority/use-ai`,
          "POST",
          { expected_version: value.version },
        ),
      );
      setEditing(false);
      setNotice(
        "Для сортировки снова используется сохранённое предложение ИИ.",
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="card section-gap priority-panel"
      aria-busy={busy}
      aria-labelledby={`priority-title-${appealId}`}
    >
      <div className="insight-section-heading">
        <h2 id={`priority-title-${appealId}`}>Приоритет для директора</h2>
        <Button
          variant="outline"
          size="sm"
          disabled={loading || busy}
          onClick={() => setAttempt((n) => n + 1)}
        >
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
          Обновить оценку
        </Button>
      </div>
      <p className="hint">
        Приоритет определяет порядок рассмотрения. Подозрения и обещания автора
        требуют проверки; статус обращения от этой оценки не меняется.
      </p>
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {loading ? (
        <Skeleton className="insight-skeleton" />
      ) : (
        value && (
          <>
            <p className="priority-lane">{laneNames[value.effective.lane]}</p>
            <PriorityReason priority={value} />
            {value.manual && value.ai && (
              <details>
                <summary>
                  Сохранённое предложение · {sourceName(value.ai.source)}
                </summary>
                <p>
                  {laneNames[value.ai.lane]} · {levelNames[value.ai.level]}
                </p>
                <p>{value.ai.reason}</p>
                <p>{value.ai.next_step}</p>
              </details>
            )}
            {editable && (
              <>
                <PriorityConsent
                  status={status}
                  consent={consent}
                  setConsent={setConsent}
                  disabled={busy}
                />
                <div className="priority-actions">
                  <Button
                    variant="outline"
                    disabled={
                      busy ||
                      !status?.available ||
                      (status.mode !== "demo" && !consent)
                    }
                    onClick={() => void suggest()}
                  >
                    {busy ? (
                      <LoaderCircle
                        data-icon="inline-start"
                        className="insight-spinner"
                        aria-hidden="true"
                      />
                    ) : (
                      <Sparkles data-icon="inline-start" aria-hidden="true" />
                    )}
                    {status?.mode === "demo"
                      ? "Оценить по локальным правилам"
                      : "Предложить приоритет с ИИ"}
                  </Button>
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => {
                      setDraft({
                        lane: value.effective.lane,
                        level: value.effective.level,
                        reason: value.manual?.reason || "",
                        next_step: value.effective.next_step,
                      });
                      setEditing(!editing);
                    }}
                  >
                    <Pencil data-icon="inline-start" aria-hidden="true" />
                    {editing ? "Скрыть исправление" : "Исправить приоритет"}
                  </Button>
                </div>
                {editing && (
                  <form onSubmit={save} className="priority-form">
                    <FieldGroup>
                      <Field>
                        <FieldLabel>Раздел кабинета</FieldLabel>
                        <ToggleGroup
                          type="single"
                          value={draft.lane}
                          onValueChange={(v) => {
                            if (v) setDraft({ ...draft, lane: v as Lane });
                          }}
                          disabled={busy}
                          aria-label="Раздел кабинета директора"
                        >
                          {(Object.keys(laneNames) as Lane[]).map((lane) => (
                            <ToggleGroupItem
                              key={lane}
                              value={lane}
                              disabled={lane === "promising" && kind !== "idea"}
                            >
                              {laneNames[lane]}
                            </ToggleGroupItem>
                          ))}
                        </ToggleGroup>
                      </Field>
                      <Field>
                        <FieldLabel>Приоритет рассмотрения</FieldLabel>
                        <ToggleGroup
                          type="single"
                          value={draft.level}
                          onValueChange={(v) => {
                            if (v) setDraft({ ...draft, level: v as Level });
                          }}
                          disabled={busy}
                          aria-label="Приоритет рассмотрения"
                        >
                          {(Object.keys(levelNames) as Level[]).map((level) => (
                            <ToggleGroupItem key={level} value={level}>
                              {levelNames[level]}
                            </ToggleGroupItem>
                          ))}
                        </ToggleGroup>
                      </Field>
                      <Field>
                        <FieldLabel htmlFor={`priority-reason-${appealId}`}>
                          Причина решения координатора
                        </FieldLabel>
                        <Textarea
                          id={`priority-reason-${appealId}`}
                          minLength={10}
                          maxLength={1200}
                          required
                          value={draft.reason}
                          onChange={(e) =>
                            setDraft({ ...draft, reason: e.target.value })
                          }
                          disabled={busy}
                        />
                      </Field>
                      <Field>
                        <FieldLabel htmlFor={`priority-next-${appealId}`}>
                          Следующий шаг
                        </FieldLabel>
                        <Textarea
                          id={`priority-next-${appealId}`}
                          maxLength={600}
                          value={draft.next_step}
                          onChange={(e) =>
                            setDraft({ ...draft, next_step: e.target.value })
                          }
                          disabled={busy}
                        />
                      </Field>
                    </FieldGroup>
                    <div className="priority-actions">
                      <Button disabled={busy}>Сохранить оценку</Button>
                      <Button
                        type="button"
                        variant="outline"
                        disabled={busy}
                        onClick={() => setEditing(false)}
                      >
                        Отмена
                      </Button>
                    </div>
                  </form>
                )}
                {value.manual && value.ai && (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => void useAI()}
                  >
                    Использовать предложение ИИ вместо ручной оценки
                  </Button>
                )}
              </>
            )}
            {notice && (
              <p className="insight-notice" role="status">
                {notice}
              </p>
            )}
            {!!value.history.length && (
              <details className="priority-history">
                <summary>
                  История приоритета · последние {value.history.length}
                </summary>
                <ol>
                  {value.history.map((event) => (
                    <li key={event.version}>
                      <p>
                        <strong>
                          {event.action === "override"
                            ? "Исправлено координатором"
                            : event.action === "use_ai"
                              ? "Возвращено предложение ИИ"
                              : event.action === "seed"
                                ? "Подготовлено для показа"
                                : "Обновлено предложение"}
                        </strong>{" "}
                        · {laneNames[event.lane]} · {levelNames[event.level]}
                      </p>
                      <p>{event.reason}</p>
                      <p className="hint">
                        {event.actor} · {sourceName(event.source)} ·{" "}
                        {date(event.created_at)}
                      </p>
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </>
        )
      )}
      {!loading && !value && (
        <Button variant="outline" onClick={() => setAttempt((n) => n + 1)}>
          Повторить загрузку
        </Button>
      )}
    </section>
  );
}

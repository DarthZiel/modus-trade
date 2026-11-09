import { Alert, AlertDescription } from "./components/ui/alert";
import { Field, FieldLabel, FieldDescription } from "./components/ui/field";
import { Textarea } from "./components/ui/textarea";
import { CheckCheck, Undo2, LoaderCircle } from "lucide-react";
import { Button } from "./components/ui/button";
import { useState } from "react";
import { api, ApiError } from "./api";
import type { Detail } from "./appeals";

export type Feedback = {
  id: string;
  outcome: "helped" | "reopen";
  comment: string;
  result_snapshot: string;
  author: string;
  created_at: string;
};
export function FeedbackPanel({
  appeal,
  onUpdated,
  onReload,
}: {
  appeal: Detail;
  onUpdated: (appeal: Detail) => void;
  onReload: () => void;
}) {
  const [returning, setReturning] = useState(false);
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [clientId] = useState(() => crypto.randomUUID());
  async function submit(outcome: "helped" | "reopen") {
    if (outcome === "reopen" && !comment.trim()) {
      setError("Опишите, почему проблема осталась.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      onUpdated(
        await api<Detail>(`/appeals/${appeal.id}/feedback`, "POST", {
          client_id: clientId,
          outcome,
          comment: comment.trim(),
          expected_version: appeal.assignment_version,
        }),
      );
    } catch (error) {
      setError((error as Error).message);
      if (error instanceof ApiError && error.status === 409) setStale(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="feedback-panel" aria-labelledby="feedback-title" aria-busy={busy}>
      <h2 id="feedback-title">{returning ? "Вернуть обращение в работу" : "Помогло ли решение?"}</h2>
      <p className="hint">
        {returning ? "Расскажите, что осталось нерешённым. Комментарий получит ответственный." : "Если всё в порядке — закройте обращение. Если проблема осталась — сообщите об этом."}
      </p>
      <Field data-invalid={!!error}><FieldLabel htmlFor="feedback-comment">
        {returning
          ? "Почему проблема осталась?"
          : "Комментарий к результату (необязательно)"}
      </FieldLabel>
      <Textarea
        id="feedback-comment"
        value={comment}
        maxLength={10000}
        rows={3}
        aria-invalid={!!error}
        aria-describedby="feedback-help"
        disabled={busy || stale}
        onChange={(event) => {
          setComment(event.target.value);
          setError("");
        }}
      />
      <FieldDescription id="feedback-help">{returning ? "Комментарий обязателен. Он сохранится в истории вместе с результатом." : "Комментарий сохранится вместе с вашей оценкой."}</FieldDescription></Field>
      {error && (
        <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>
      )}
      {stale ? (
        <Button variant="outline" onClick={onReload}>Загрузить актуальную карточку</Button>
      ) : (
        <div className="feedback-actions">
          {returning ? (
            <>
              <Button variant="outline"
                disabled={busy}
                onClick={() => {
                  setReturning(false);
                  setError("");
                }}
              >
                Отмена
              </Button>
              <Button
                disabled={busy}
                onClick={() => submit("reopen")}
              >
                {busy ? <LoaderCircle className="action-spinner" data-icon="inline-start" aria-hidden="true" /> : <Undo2 data-icon="inline-start" aria-hidden="true" />}{busy ? "Сохраняем…" : "Вернуть в работу"}
              </Button>
            </>
          ) : (
            <>
              <Button
                disabled={busy}
                onClick={() => submit("helped")}
              >
                {busy ? <LoaderCircle className="action-spinner" data-icon="inline-start" aria-hidden="true" /> : <CheckCheck data-icon="inline-start" aria-hidden="true" />}{busy ? "Сохраняем…" : "Помогло — закрыть"}
              </Button>
              <Button variant="outline" disabled={busy} onClick={() => setReturning(true)}>
                Проблема осталась
              </Button>
            </>
          )}
        </div>
      )}
    </section>
  );
}
export function FeedbackHistory({ items }: { items: Feedback[] }) {
  if (!items.some((item) => item.outcome === "reopen")) return null;
  return (
    <section className="card section-gap">
      <h2>История проверки результата</h2>
      {[...items].reverse().map((item) => (
        <article className="feedback-history-item" key={item.id}>
          <span className="pill">
            {item.outcome === "helped" ? "Помогло" : "Проблема осталась"}
          </span>
          <p className="hint">
            {item.author} · {new Date(item.created_at).toLocaleString("ru-RU")}
          </p>
          <h3>Рассмотренный результат</h3>
          <p className="preserve-text">{item.result_snapshot}</p>
          {item.comment && (
            <>
              <h3>Комментарий автора</h3>
              <p className="preserve-text">{item.comment}</p>
            </>
          )}
        </article>
      ))}
    </section>
  );
}

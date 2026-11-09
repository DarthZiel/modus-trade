import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "./components/ui/field";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import { Skeleton } from "./components/ui/skeleton";
import { Button } from "./components/ui/button";
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { api, ApiError } from "./api";
import type { Detail } from "./appeals";

export type Responsible = {
  id: string;
  name: string;
  company: string;
  department: string;
};
function localInput(value: string | null) {
  if (!value) return "";
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
export function AssignmentPanel({
  appeal,
  onUpdated,
  onReload,
}: {
  appeal: Detail;
  onUpdated: (appeal: Detail) => void;
  onReload: () => void;
}) {
  const [options, setOptions] = useState<Responsible[]>([]);
  const [responsible, setResponsible] = useState(appeal.responsible_id || "");
  const [deadline, setDeadline] = useState(localInput(appeal.next_response_at));
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setReady(false);
    setError("");
    api<Responsible[]>("/work/responsibles")
      .then((result) => {
        if (!cancelled) {
          setOptions(result);
          setReady(true);
        }
      })
      .catch((error) => {
        if (!cancelled) setError(error.message);
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);
  const changed =
    responsible !== (appeal.responsible_id || "") ||
    deadline !== localInput(appeal.next_response_at);
  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (
      !responsible ||
      !deadline ||
      !Number.isFinite(new Date(deadline).getTime())
    ) {
      setError("Выберите ответственного и дату ответа.");
      return;
    }
    const targetDate =
      deadline === localInput(appeal.next_response_at)
        ? appeal.next_response_at!
        : new Date(deadline).toISOString();
    if (new Date(targetDate).getTime() <= Date.now()) {
      setError("Дата следующего ответа должна быть в будущем.");
      return;
    }
    if (appeal.responsible_id && !reason.trim()) {
      setError("Укажите причину переназначения или изменения срока.");
      return;
    }
    setBusy(true);
    try {
      onUpdated(
        await api<Detail>(`/work/appeals/${appeal.id}/assignment`, "PATCH", {
          responsible_id: responsible,
          next_response_at: targetDate,
          expected_version: appeal.assignment_version,
          reason: reason.trim(),
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
    <section className="card assignment-panel">
      <div>
        <h2>
          {appeal.responsible_id
            ? "Ответственный и срок ответа"
            : "Назначить ответственного"}
        </h2>
        <p className="hint">
          Назначение и причина изменений сохраняются в истории, доступной
          автору.
        </p>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!ready ? (
        error ? (
          <Button
            variant="outline"
            onClick={() => setAttempt((value) => value + 1)}
          >
            Повторить загрузку сотрудников
          </Button>
        ) : (
          <div
            role="status"
            aria-label="Загружаем ответственных"
            className="thread-loading"
          >
            <Skeleton />
            <Skeleton />
          </div>
        )
      ) : options.length === 0 ? (
        <p className="warning">
          Нет активных сотрудников с ролью ответственного. Добавьте роль
          сотруднику в разделе «Управление командой».
        </p>
      ) : (
        <form onSubmit={save} aria-busy={busy}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="assignment-responsible">
                Ответственный
              </FieldLabel>

              <select
                id="assignment-responsible"
                value={responsible}
                onChange={(event) => setResponsible(event.target.value)}
                required
                disabled={busy || stale}
              >
                <option value="" disabled>
                  Выберите сотрудника
                </option>
                {appeal.responsible_id &&
                  !options.some(
                    (item) => item.id === appeal.responsible_id,
                  ) && (
                    <option value={appeal.responsible_id} disabled>
                      {appeal.responsible} (недоступен)
                    </option>
                  )}
                {options.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name} · {item.company} / {item.department}
                  </option>
                ))}
              </select>
            </Field>
            <Field>
              <FieldLabel htmlFor="assignment-deadline">
                Дата следующего ответа
              </FieldLabel>
              <Input
                id="assignment-deadline"
                type="datetime-local"
                value={deadline}
                onChange={(event) => setDeadline(event.target.value)}
                required
                disabled={busy || stale}
              />
              <FieldDescription>
                Время в вашем часовом поясе:{" "}
                {Intl.DateTimeFormat().resolvedOptions().timeZone}.
              </FieldDescription>
            </Field>
            <Field>
              <FieldLabel htmlFor="assignment-reason">
                {appeal.responsible_id
                  ? "Причина переназначения или изменения срока"
                  : "Комментарий к назначению (необязательно)"}
              </FieldLabel>
              <Textarea
                id="assignment-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                maxLength={1000}
                rows={2}
                required={Boolean(appeal.responsible_id)}
                disabled={busy || stale}
              />
            </Field>
          </FieldGroup>
          <div className="form-actions">
            {stale ? (
              <Button variant="outline" type="button" onClick={onReload}>
                Обновить карточку
              </Button>
            ) : (
              <Button
                variant="outline"
                className="primary compact"
                disabled={busy || !changed}
              >
                {busy ? "Сохраняем…" : "Сохранить назначение"}
              </Button>
            )}
          </div>
        </form>
      )}
    </section>
  );
}

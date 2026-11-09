import { Field, FieldLabel } from "./components/ui/field";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import { Skeleton } from "./components/ui/skeleton";
import { Button } from "./components/ui/button";
import { useEffect, useId, useState } from "react";
import { api } from "./api";
import type { User } from "./api";
import type { Detail } from "./appeals";
import { date } from "./appeals";

type Experiment = {
  id: string;
  hypothesis: string;
  change: string;
  success_criterion: string;
  baseline: string;
  responsible: string;
  starts_at: string;
  ends_at: string;
  status: string;
  version: number;
  planned_cost: string;
  actual_cost: string;
  actions: string;
  observations: string;
  metric: string;
  unit: string;
  before_value: number | null;
  after_value: number | null;
  quantitative_evidence: boolean;
  delta: number | null;
  author_comment: string;
  outcome: "expand" | "iterate" | "stop" | null;
  is_overdue: boolean;
};
const outcomes = {
  expand: "Внедрить шире",
  iterate: "Доработать",
  stop: "Прекратить",
};
const localTime = (value: Date) =>
  new Date(value.getTime() - value.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
function TextField({
  label,
  value,
  onChange,
  required = false,
  max = 2000,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  max?: number;
}) {
  const id = useId();
  return (
    <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Textarea
        id={id}
        required={required}
        minLength={required ? 5 : undefined}
        maxLength={max}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
  );
}

export function Experiments({
  appeal,
  user,
  onReload,
}: {
  appeal: Detail;
  user: User;
  onReload: () => void;
}) {
  const [attempt, setAttempt] = useState(0);
  const [items, setItems] = useState<Experiment[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const manager =
    user.roles.includes("coordinator") ||
    (user.roles.includes("responsible") && appeal.responsible_id === user.id);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<Experiment[]>(`/appeals/${appeal.id}/experiments`)
      .then((value) => {
        if (active) {
          setItems(value);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError((e as Error).message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [appeal.id, appeal.assignment_version, attempt]);
  return (
    <section className="card section-gap experiments">
      <h2>Проверка экспериментом</h2>
      <p className="hint">
        Проверяем небольшое изменение, фиксируем наблюдения и спрашиваем автора
        о результате.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {loading ? (
        <div
          role="status"
          aria-label="Загружаем эксперименты"
          className="thread-loading"
        >
          <Skeleton />
          <Skeleton />
        </div>
      ) : error ? (
        <Button
          variant="outline"
          onClick={() => setAttempt((value) => value + 1)}
        >
          Повторить загрузку экспериментов
        </Button>
      ) : (
        <>
          {!items.length && (
            <p className="hint">Эксперимент пока не запускали.</p>
          )}
          {items.map((item) => (
            <article className="experiment-item" key={item.id}>
              <h3>{item.hypothesis}</h3>
              <p>
                <span className="pill">
                  {item.status === "active"
                    ? "Идёт проверка"
                    : "Проверка завершена"}
                </span>
              </p>
              {item.is_overdue && (
                <p className="warning">
                  Срок эксперимента истёк. Зафиксируйте результат или остановку
                  проверки.
                </p>
              )}
              <p>
                <strong>Что меняем:</strong> {item.change}
              </p>
              <p>
                <strong>Критерий успеха:</strong> {item.success_criterion}
              </p>
              <p className="hint">
                Ответственный: {item.responsible}
                <br />С {date(item.starts_at)} до {date(item.ends_at)}
              </p>
              {item.planned_cost && (
                <p>Планируемые затраты: {item.planned_cost}</p>
              )}
              {item.baseline && (
                <p className="preserve-text">
                  Исходные наблюдения / план измерения: {item.baseline}
                </p>
              )}
              {item.status === "active" && manager && (
                <FinishForm
                  appealId={appeal.id}
                  item={item}
                  onDone={onReload}
                />
              )}
              {item.status === "completed" && (
                <>
                  <h3>Итог: {item.outcome && outcomes[item.outcome]}</h3>
                  <p className="preserve-text">
                    <strong>Выполненные действия:</strong> {item.actions}
                  </p>
                  <p className="preserve-text">
                    <strong>Наблюдения:</strong> {item.observations}
                  </p>
                  {item.actual_cost && (
                    <p>Фактические затраты: {item.actual_cost}</p>
                  )}
                  {item.quantitative_evidence ? (
                    <p className="success">
                      Измерения «{item.metric}»: {item.before_value} →{" "}
                      {item.after_value} {item.unit}. Изменение: {item.delta}{" "}
                      {item.unit}. Это введённые наблюдения; причинность
                      отдельно не проверялась.
                    </p>
                  ) : (
                    <p className="warning">
                      Количественный эффект не подтверждён: нет сопоставимых
                      измерений до и после.
                    </p>
                  )}
                  {item.author_comment ? (
                    <p className="preserve-text">
                      <strong>Комментарий автора:</strong> {item.author_comment}
                    </p>
                  ) : (
                    user.id === appeal.author_id && (
                      <AuthorComment
                        appealId={appeal.id}
                        item={item}
                        onDone={onReload}
                      />
                    )
                  )}
                </>
              )}
            </article>
          ))}
          {manager &&
            !error &&
            !items.some((x) => x.status === "active") &&
            ["reviewing", "in_progress"].includes(appeal.status) &&
            appeal.responsible_available && (
              <>
                <Button variant="outline" onClick={() => setOpen(!open)}>
                  {open ? "Скрыть план" : "Подготовить эксперимент"}
                </Button>
                {open && <PlanForm appeal={appeal} onDone={onReload} />}
              </>
            )}
        </>
      )}
    </section>
  );
}

function PlanForm({ appeal, onDone }: { appeal: Detail; onDone: () => void }) {
  const [form, setForm] = useState({
    hypothesis: "",
    change: "",
    success_criterion: "",
    baseline: "",
    planned_cost: "",
    metric: "",
    unit: "",
    before_value: "",
    starts_at: localTime(new Date()),
    ends_at: localTime(new Date(Date.now() + 7 * 86400000)),
  });
  const [clientId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [proposal, setProposal] = useState<{
    mode: string;
    suggestion: {
      hypothesis: string;
      change: string;
      success_criterion: string;
      baseline_plan: string;
    };
  }>();
  const [status, setStatus] = useState<{
    mode: string;
    available: boolean;
    model?: string | null;
    experiment_model?: string | null;
  }>();
  const [consent, setConsent] = useState(false);
  useEffect(() => {
    let active = true;
    api<{
      mode: string;
      available: boolean;
      model?: string | null;
      experiment_model?: string | null;
    }>("/ai/status")
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
  function change(key: keyof typeof form, value: string) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }
  async function ai() {
    setBusy(true);
    setError("");
    try {
      setProposal(await api(`/ai/appeals/${appeal.id}/experiment`, "POST"));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`/appeals/${appeal.id}/experiments`, "POST", {
        ...form,
        starts_at: new Date(form.starts_at).toISOString(),
        ends_at: new Date(form.ends_at).toISOString(),
        before_value:
          form.before_value === "" ? null : Number(form.before_value),
        client_id: clientId,
        expected_version: appeal.assignment_version,
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={(event) => void save(event)} className="experiment-form">
      <h3>План небольшой проверки</h3>
      <p>
        Ответственный: {appeal.responsible}. План запускается только после
        вашего подтверждения.
      </p>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {status && !status.available && (
        <p className="hint">
          Помощник недоступен. План можно заполнить самостоятельно.
        </p>
      )}
      {status?.mode === "demo" && (
        <p className="hint">Черновик по локальному шаблону, без ИИ-модели.</p>
      )}
      {["openai", "openrouter"].includes(status?.mode || "") && (
        <label className="check">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          Разрешаю передать заголовок и описание обращения{" "}
          {status?.mode === "openrouter"
            ? "сервису OpenRouter и провайдеру выбранной модели"
            : "сервису OpenAI"}{" "}
          для черновика плана.
        </label>
      )}
      <Button
        variant="outline"
        type="button"
        disabled={
          busy ||
          !status?.available ||
          (["openai", "openrouter"].includes(status.mode) && !consent)
        }
        onClick={() => void ai()}
      >
        Предложить черновик плана
      </Button>
      {proposal && (
        <div className="ai-assistant">
          <h3>Черновик для проверки</h3>
          <p>{proposal.suggestion.hypothesis}</p>
          <p>{proposal.suggestion.change}</p>
          <p>{proposal.suggestion.success_criterion}</p>
          <p>{proposal.suggestion.baseline_plan}</p>
          <Button
            variant="outline"
            type="button"
            onClick={() => {
              setForm({
                ...form,
                hypothesis: proposal.suggestion.hypothesis,
                change: proposal.suggestion.change,
                success_criterion: proposal.suggestion.success_criterion,
                baseline: proposal.suggestion.baseline_plan,
              });
              setProposal(undefined);
            }}
          >
            Проверил — заполнить план
          </Button>
        </div>
      )}
      <TextField
        label="Что хотим проверить"
        value={form.hypothesis}
        onChange={(v) => change("hypothesis", v)}
        required
      />
      <TextField
        label="Что конкретно меняем"
        value={form.change}
        onChange={(v) => change("change", v)}
        max={3000}
        required
      />
      <TextField
        label="Критерий успеха"
        value={form.success_criterion}
        onChange={(v) => change("success_criterion", v)}
        required
      />
      <label className="field">
        Дата начала
        <Input
          type="datetime-local"
          required
          value={form.starts_at}
          onChange={(e) => change("starts_at", e.target.value)}
        />
      </label>
      <label className="field">
        Дата завершения
        <Input
          type="datetime-local"
          required
          value={form.ends_at}
          onChange={(e) => change("ends_at", e.target.value)}
        />
      </label>
      <TextField
        label="Планируемые затраты (необязательно)"
        value={form.planned_cost}
        onChange={(v) => change("planned_cost", v)}
        max={1000}
      />
      <TextField
        label="Исходные наблюдения или план измерения"
        value={form.baseline}
        onChange={(v) => change("baseline", v)}
      />
      <p className="hint">
        Для численного сравнения запишите показатель, единицу и исходное
        значение. Не подставляйте предполагаемые результаты.
      </p>
      <label className="field">
        Показатель
        <Input
          maxLength={160}
          value={form.metric}
          onChange={(e) => change("metric", e.target.value)}
        />
      </label>
      <label className="field">
        Единица измерения
        <Input
          maxLength={80}
          value={form.unit}
          onChange={(e) => change("unit", e.target.value)}
        />
      </label>
      <label className="field">
        Значение до
        <Input
          type="number"
          step="any"
          value={form.before_value}
          onChange={(e) => change("before_value", e.target.value)}
        />
      </label>
      <Button variant="outline" disabled={busy} type="submit">
        {busy ? "Сохраняем…" : "Утвердить и запустить эксперимент"}
      </Button>
    </form>
  );
}

function FinishForm({
  appealId,
  item,
  onDone,
}: {
  appealId: number;
  item: Experiment;
  onDone: () => void;
}) {
  const [form, setForm] = useState({
    actions: "",
    observations: "",
    actual_cost: "",
    after_value: "",
    outcome: "iterate",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function change(key: keyof typeof form, value: string) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }
  async function finish(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`/appeals/${appealId}/experiments/${item.id}/finish`, "POST", {
        ...form,
        after_value: form.after_value === "" ? null : Number(form.after_value),
        expected_version: item.version,
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details>
      <summary>Зафиксировать итог проверки</summary>
      <form className="experiment-form" onSubmit={(e) => void finish(e)}>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <TextField
          label="Выполненные действия"
          value={form.actions}
          onChange={(v) => change("actions", v)}
          required
          max={3000}
        />
        <TextField
          label="Полученные наблюдения"
          value={form.observations}
          onChange={(v) => change("observations", v)}
          required
          max={3000}
        />
        <TextField
          label="Фактические затраты (необязательно)"
          value={form.actual_cost}
          onChange={(v) => change("actual_cost", v)}
          max={1000}
        />
        {item.metric && item.unit && (
          <label className="field">
            Значение после: {item.metric} ({item.unit})
            <Input
              type="number"
              step="any"
              value={form.after_value}
              onChange={(e) => change("after_value", e.target.value)}
            />
          </label>
        )}
        <label className="field">
          Итог эксперимента
          <select
            value={form.outcome}
            onChange={(e) => change("outcome", e.target.value)}
          >
            {Object.entries(outcomes).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <p className="hint">
          Итог эксперимента не закрывает обращение. Затем зафиксируйте решение
          для подтверждения автором.
        </p>
        <Button variant="outline" disabled={busy}>
          {busy ? "Сохраняем…" : "Завершить эксперимент"}
        </Button>
      </form>
    </details>
  );
}

function AuthorComment({
  appealId,
  item,
  onDone,
}: {
  appealId: number;
  item: Experiment;
  onDone: () => void;
}) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api(`/appeals/${appealId}/experiments/${item.id}/comment`, "POST", {
        comment,
        expected_version: item.version,
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={(e) => void save(e)}>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <label className="field">
        Ваш комментарий к проверке
        <Textarea
          required
          maxLength={2000}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      </label>
      <Button variant="outline" disabled={busy || !comment.trim()}>
        Сохранить комментарий автора
      </Button>
    </form>
  );
}

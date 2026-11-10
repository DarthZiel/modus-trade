import { useEffect, useState } from "react";
import { LoaderCircle, Sparkles, X } from "lucide-react";
import { Button } from "./components/ui/button";
import { api } from "./api";

type Suggestion = { summary: string[]; next_step: string; draft: string };
type Result = { mode: string; suggestion: Suggestion; messages_used: number };
type Status = { mode: string; available: boolean };

/** Summary of the thread and a reply draft for the responsible; the human edits and sends. */
export function ReplyAssistant({
  appealId,
  onInsert,
}: {
  appealId: number;
  onInsert: (text: string) => void;
}) {
  const [status, setStatus] = useState<Status>();
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result>();
  useEffect(() => {
    let active = true;
    api<Status>("/ai/status")
      .then((value) => active && setStatus(value))
      .catch(() => active && setStatus({ mode: "disabled", available: false }));
    return () => {
      active = false;
    };
  }, []);
  if (!status?.available) return null;
  const external = ["openai", "openrouter"].includes(status.mode);
  async function request() {
    if (busy || (external && !consent)) return;
    setBusy(true);
    setError("");
    try {
      setResult(await api<Result>(`/ai/appeals/${appealId}/reply`, "POST"));
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="reply-assistant" aria-label="ИИ-помощник ответственного">
      {!result ? (
        <div className="reply-assistant-start">
          <div>
            <strong>
              <Sparkles aria-hidden="true" />
              Сводка и черновик ответа
            </strong>
            <p className="hint">
              ИИ перескажет обращение и переписку и предложит текст. Ничего не
              отправится без вас.
            </p>
            {external && (
              <label className="check assistant-consent">
                <input
                  type="checkbox"
                  checked={consent}
                  disabled={busy}
                  onChange={(event) => setConsent(event.target.checked)}
                />
                <span>
                  Разрешаю передать описание и переписку{" "}
                  {status.mode === "openrouter"
                    ? "сервису OpenRouter и провайдеру модели"
                    : "сервису OpenAI"}
                  . Имена, профили и вложения не отправляются.
                </span>
              </label>
            )}
          </div>
          <Button
            type="button"
            variant="outline"
            disabled={busy || (external && !consent)}
            onClick={request}
          >
            {busy ? (
              <LoaderCircle className="spin" data-icon="inline-start" aria-hidden="true" />
            ) : (
              <Sparkles data-icon="inline-start" aria-hidden="true" />
            )}
            {busy ? "Готовим…" : "Подготовить"}
          </Button>
        </div>
      ) : (
        <div className="reply-assistant-result">
          <div className="reply-assistant-head">
            <span className="assistant-badge">
              <Sparkles aria-hidden="true" />
              {result.mode === "demo"
                ? "Демо-режим: шаблон без модели"
                : "Предложение ИИ — проверьте факты"}
            </span>
            <Button
              type="button"
              variant="ghost"
              aria-label="Скрыть предложение"
              onClick={() => setResult(undefined)}
            >
              <X aria-hidden="true" />
            </Button>
          </div>
          <h3>Коротко</h3>
          <ul>
            {result.suggestion.summary.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="reply-next-step">
            <strong>Возможный шаг:</strong> {result.suggestion.next_step}
          </p>
          <h3>Черновик ответа</h3>
          <blockquote className="preserve-text">{result.suggestion.draft}</blockquote>
          <div className="form-actions">
            <Button
              type="button"
              variant="ghost"
              disabled={busy}
              onClick={request}
            >
              Подготовить заново
            </Button>
            <Button
              type="button"
              onClick={() => {
                onInsert(result.suggestion.draft);
                setResult(undefined);
              }}
            >
              Вставить в сообщение
            </Button>
          </div>
          <p className="hint note">
            Учтено сообщений: {result.messages_used}. Решение и отправка — за
            вами.
          </p>
        </div>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldDescription,
} from "./components/ui/field";
import { Textarea } from "./components/ui/textarea";
import { Alert, AlertDescription } from "./components/ui/alert";
import { Badge } from "./components/ui/badge";
import { LoaderCircle, Check, ChevronDown } from "lucide-react";
import { Button } from "./components/ui/button";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";

type Proposal = {
  title: string;
  description: string;
  category: string;
  questions: string[];
};
type AssistantStatus = {
  mode: string;
  available: boolean;
  model?: string | null;
};
export function AIAssistant({
  kind,
  description,
  onApply,
}: {
  kind: string;
  description: string;
  onApply: (value: Proposal) => void;
}) {
  const [status, setStatus] = useState<AssistantStatus>();
  const [result, setResult] = useState<Proposal>();
  const [answers, setAnswers] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [consent, setConsent] = useState(false);
  const version = useRef(0);
  useEffect(() => {
    let active = true;
    api<AssistantStatus>("/ai/status")
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
  useEffect(() => {
    version.current++;
    setResult(undefined);
    setAnswers([]);
    setError("");
    setBusy(false);
  }, [kind, description]);
  async function request(withAnswers = false) {
    if (
      busy ||
      !status?.available ||
      (["openai", "openrouter"].includes(status.mode) && !consent)
    )
      return;
    const revision = version.current;
    setBusy(true);
    setError("");
    try {
      const response = await api<{ mode: string; suggestion: Proposal }>(
        "/ai/appeal",
        "POST",
        {
          kind,
          description,
          answers: withAnswers
            ? result?.questions
                .map((question, i) => ({
                  question,
                  answer: answers[i]?.trim(),
                }))
                .filter((value) => value.answer)
            : [],
        },
      );
      if (revision === version.current) {
        setResult(response.suggestion);
        setAnswers([]);
      }
    } catch (error) {
      if (revision === version.current) setError((error as Error).message);
    } finally {
      if (revision === version.current) setBusy(false);
    }
  }
  return (
    <details className="writing-assistant">
      <summary>
        <span>
          <strong>Помочь с формулировкой</strong>
          <span>Необязательно · ваш текст останется под вашим контролем</span>
        </span>
        <ChevronDown aria-hidden="true" />
      </summary>
      <div className="writing-assistant-body">
        <p className="hint">
          Помощник предложит заголовок, описание и категорию. Сначала проверьте
          предложение — форма изменится только по кнопке «Применить».
        </p>
        {!status && (
          <p className="hint" role="status">
            Проверяем доступность помощника…
          </p>
        )}
        {status?.mode === "demo" && (
          <Alert>
            <AlertDescription>
              Демонстрационный режим: локальные шаблоны без ИИ-модели. Текст не
              передаётся внешнему сервису.
            </AlertDescription>
          </Alert>
        )}
        {["openai", "openrouter"].includes(status?.mode || "") && (
          <label className="check assistant-consent">
            <input
              type="checkbox"
              checked={consent}
              disabled={busy}
              onChange={(event) => setConsent(event.target.checked)}
            />
            <span>
              Разрешаю передать описание и мои уточнения{" "}
              {status?.mode === "openrouter"
                ? "сервису OpenRouter и провайдеру выбранной модели"
                : "сервису OpenAI"}{" "}
              для подготовки предложения. Вложения и профиль сотрудника не
              отправляются.
            </span>
          </label>
        )}
        {status && !status.available && (
          <p className="hint" role="status">
            Помощник сейчас недоступен. Вы можете самостоятельно заполнить и
            отправить обращение.
          </p>
        )}
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <div className="assistant-request">
          <Button
            variant="outline"
            type="button"
            disabled={
              busy ||
              !status?.available ||
              description.trim().length < 10 ||
              (["openai", "openrouter"].includes(status.mode) && !consent)
            }
            onClick={() => void request()}
          >
            {busy && (
              <LoaderCircle
                className="action-spinner"
                data-icon="inline-start"
                aria-hidden="true"
              />
            )}
            {busy
              ? "Готовим предложение…"
              : result
                ? "Предложить другой вариант"
                : "Предложить формулировку"}
          </Button>
          {description.trim().length < 10 && (
            <p className="hint">
              Сначала опишите ситуацию: нужно хотя бы 10 символов.
            </p>
          )}
        </div>
        <p className="sr-only" role="status">
          {busy
            ? "Помощник готовит предложение"
            : result
              ? "Предложение готово для проверки"
              : ""}
        </p>
        {result && (
          <section
            className="writing-proposal"
            aria-label="Предложение для проверки"
            aria-busy={busy}
          >
            <div className="proposal-heading">
              <h3>Предложение для проверки</h3>
              <Badge variant="secondary">Ещё не применено</Badge>
            </div>
            <h4>{result.title}</h4>
            <p className="preserve-text">{result.description}</p>
            <p className="hint">
              Категория:{" "}
              {(
                {
                  warehouse: "Склад и логистика",
                  sales: "Продажи и ассортимент",
                  process: "Рабочие инструменты и процессы",
                  workplace: "Условия труда",
                  other: "Другое",
                } as Record<string, string>
              )[result.category] || result.category}
            </p>
            {!!result.questions.length && (
              <div className="assistant-questions">
                <h4>Можно добавить подробности</h4>
                <p className="hint">
                  Ответьте на подходящие вопросы или примените предложение как
                  есть.
                </p>
                <FieldGroup>
                  {result.questions.map((question, i) => (
                    <Field key={i}>
                      <FieldLabel htmlFor={`assistant-answer-${i}`}>
                        {question}
                      </FieldLabel>
                      <Textarea
                        id={`assistant-answer-${i}`}
                        maxLength={2000}
                        rows={2}
                        disabled={busy}
                        value={answers[i] || ""}
                        onChange={(event) =>
                          setAnswers((previous) => {
                            const next = [...previous];
                            next[i] = event.target.value;
                            return next;
                          })
                        }
                      />
                      <FieldDescription>
                        Необязательно. До 2 000 символов.
                      </FieldDescription>
                    </Field>
                  ))}
                </FieldGroup>
                <Button
                  variant="outline"
                  type="button"
                  disabled={
                    busy ||
                    !answers.some((value) => value.trim()) ||
                    (["openai", "openrouter"].includes(status?.mode || "") &&
                      !consent)
                  }
                  onClick={() => void request(true)}
                >
                  Учесть мои ответы
                </Button>
              </div>
            )}
            <div className="proposal-actions">
              <Button
                type="button"
                disabled={busy}
                onClick={() => {
                  onApply(result);
                  setResult(undefined);
                  setAnswers([]);
                }}
              >
                <Check data-icon="inline-start" aria-hidden="true" />
                Проверил — применить
              </Button>
              <Button
                variant="ghost"
                type="button"
                disabled={busy}
                onClick={() => {
                  setResult(undefined);
                  setAnswers([]);
                }}
              >
                Оставить мой текст
              </Button>
            </div>
          </section>
        )}
      </div>
    </details>
  );
}

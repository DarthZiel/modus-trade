import { Badge } from "./components/ui/badge";
import { Alert, AlertDescription } from "./components/ui/alert";
import { Skeleton } from "./components/ui/skeleton";
import { Send, RefreshCw, ExternalLink, Unplug } from "lucide-react";
import { Button } from "./components/ui/button";
import { useEffect, useState } from "react";
import { api, setTelegramToken } from "./api";
import type { User } from "./api";
import { navigate } from "./navigation";

type TelegramApp = {
  initData: string;
  ready: () => void;
  expand: () => void;
  BackButton: {
    show: () => void;
    hide: () => void;
    onClick: (fn: () => void) => void;
  };
};
declare global {
  interface Window {
    Telegram?: { WebApp: TelegramApp };
  }
}
let miniLogin: Promise<User | null> | undefined;

export function loginFromTelegram(): Promise<User | null> {
  if (location.pathname !== "/mini" && !location.pathname.startsWith("/mini/"))
    return Promise.resolve(null);
  if (!miniLogin)
    miniLogin = (async () => {
      if (!window.Telegram?.WebApp)
        await new Promise<void>((resolve, reject) => {
          const script = document.createElement("script");
          script.src = "https://telegram.org/js/telegram-web-app.js";
          script.onload = () => resolve();
          script.onerror = () =>
            reject(
              new Error(
                "Не удалось загрузить Telegram. Откройте кабинет в обычном браузере.",
              ),
            );
          document.head.appendChild(script);
        });
      const app = window.Telegram?.WebApp;
      if (!app?.initData)
        throw new Error(
          "Откройте Mini App кнопкой в личном чате с ботом. Для входа на сайте используйте обычный адрес без /mini.",
        );
      app.ready();
      app.expand();
      const session = await api<{ user: User; access_token: string }>(
        "/telegram/auth",
        "POST",
        {
          init_data: app.initData,
        },
      );
      setTelegramToken(session.access_token);
      const target =
        location.pathname.replace(/^\/mini(?=\/|$)/, "") || "/appeals";
      // Remove Telegram's signed launch data from the address after authentication.
      history.replaceState(null, "", target + location.search);
      navigate(target);
      app.BackButton.onClick(() => history.back());
      app.BackButton.show();
      return session.user;
    })();
  return miniLogin;
}

type Status = {
  configured: boolean;
  linked: boolean;
  delivery_enabled: boolean;
};
export function TelegramSettings() {
  const [status, setStatus] = useState<Status>();
  const [checking, setChecking] = useState(false);
  const [link, setLink] = useState<{ url: string; expires_at: string }>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  async function load() {
    setChecking(true);
    try {
      const next = await api<Status>("/telegram/status");
      setStatus(next);
      if (next.linked) setLink(undefined);
      setError("");
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setChecking(false);
    }
  }
  useEffect(() => {
    void load();
    const focus = () => void load();
    window.addEventListener("focus", focus);
    return () => window.removeEventListener("focus", focus);
  }, []);
  async function connect() {
    setBusy(true);
    setError("");
    try {
      setLink(await api("/telegram/link", "POST"));
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function disconnect() {
    setBusy(true);
    setError("");
    try {
      await api("/telegram/link", "DELETE");
      setLink(undefined);
      setConfirm(false);
      await load();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="telegram-settings">
      <Button
        variant="ghost"
        className="back-link"
        onClick={() => navigate("/appeals")}
      >
        ← Мои обращения
      </Button>
      <div className="page-heading">
        <h1>Telegram</h1>
        <p className="hint">
          Те же обращения и история. Уведомления — в личном чате с ботом.
        </p>
      </div>
      <div className="telegram-layout">
        <section
          className="card telegram-connection"
          aria-label="Подключение Telegram"
          aria-busy={busy || checking}
        >
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          {!status && !error && (
            <div
              className="employee-loading"
              role="status"
              aria-label="Проверяем подключение"
            >
              <Skeleton />
              <Skeleton />
            </div>
          )}
          {status && (
            <>
              <div className="telegram-state">
                <Send aria-hidden="true" />
                <Badge variant="secondary">
                  {status.linked
                    ? "Аккаунт привязан"
                    : status.configured
                      ? "Не подключён"
                      : "Бот не настроен"}
                </Badge>
              </div>
              <h2>
                {status.linked
                  ? "Telegram подключён"
                  : status.configured
                    ? "Получайте ответы в Telegram"
                    : "Пока пользуйтесь кабинетом"}
              </h2>
              {!status.configured && (
                <p>
                  Администратору нужно настроить бота. Обращения и уведомления
                  доступны на сайте.
                </p>
              )}
              {status.linked ? (
                <>
                  <p>Вход в Mini App доступен без пароля.</p>
                  <p className="telegram-delivery">
                    {status.delivery_enabled
                      ? "Уведомления отправляются в личный чат с ботом."
                      : "Доставка уведомлений остановлена. Разблокируйте бота, отключите текущую привязку и подключите аккаунт заново."}
                  </p>
                  <div className="telegram-disconnect">
                    <h3>Отключение аккаунта</h3>
                    <p className="hint">
                      Завершатся сеансы Mini App и удалится черновик бота. Ваши
                      обращения и история сохранятся.
                    </p>
                    {confirm ? (
                      <div className="telegram-confirm">
                        <p>Отключить Telegram от этого аккаунта?</p>
                        <div className="settings-actions">
                          <Button
                            variant="destructive"
                            disabled={busy || checking}
                            onClick={() => void disconnect()}
                          >
                            {busy ? "Отключаем…" : "Да, отключить"}
                          </Button>
                          <Button
                            variant="outline"
                            disabled={busy}
                            onClick={() => setConfirm(false)}
                          >
                            Отмена
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <Button
                        variant="outline"
                        disabled={busy || checking}
                        onClick={() => setConfirm(true)}
                      >
                        <Unplug data-icon="inline-start" aria-hidden="true" />
                        Отключить Telegram
                      </Button>
                    )}
                  </div>
                </>
              ) : (
                status.configured && (
                  <>
                    <p>
                      Создайте одноразовую ссылку, откройте бота и нажмите
                      «Старт». Пароль отправлять не нужно.
                    </p>
                    <Button
                      disabled={busy || checking}
                      onClick={() => void connect()}
                    >
                      {busy
                        ? "Создаём ссылку…"
                        : link
                          ? "Создать новую ссылку"
                          : "Создать ссылку для привязки"}
                    </Button>
                    {link && (
                      <div className="telegram-link-result" role="status">
                        <h3>Ссылка готова</h3>
                        <Button asChild>
                          <a href={link.url} target="_blank" rel="noreferrer">
                            Открыть бота
                            <ExternalLink
                              data-icon="inline-end"
                              aria-hidden="true"
                            />
                          </a>
                        </Button>
                        <p className="hint">
                          Действует до{" "}
                          {new Date(link.expires_at).toLocaleString("ru-RU")}.
                          Не пересылайте её другим людям.
                        </p>
                        <p className="hint">
                          После нажатия «Старт» вернитесь сюда и проверьте
                          подключение.
                        </p>
                      </div>
                    )}
                  </>
                )
              )}
            </>
          )}
          <Button
            variant="outline"
            disabled={busy || checking}
            onClick={() => void load()}
          >
            <RefreshCw data-icon="inline-start" aria-hidden="true" />
            {checking ? "Проверяем…" : "Проверить подключение"}
          </Button>
        </section>
        <aside className="telegram-guide">
          <h2>Как это работает</h2>
          <ol>
            <li>
              <strong>Создайте личную ссылку</strong>
              <p>Она связывает ваш кабинет с вашим Telegram.</p>
            </li>
            <li>
              <strong>Подтвердите в боте</strong>
              <p>Откройте ссылку и нажмите «Старт».</p>
            </li>
            <li>
              <strong>Продолжайте там, где удобно</strong>
              <p>Ответы и обращения общие для сайта и Mini App.</p>
            </li>
          </ol>
        </aside>
      </div>
    </section>
  );
}

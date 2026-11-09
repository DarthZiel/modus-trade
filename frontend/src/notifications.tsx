import {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "./components/ui/sheet";
import {
  Empty,
  EmptyHeader,
  EmptyTitle,
  EmptyDescription,
} from "./components/ui/empty";
import { Skeleton } from "./components/ui/skeleton";
import { Badge } from "./components/ui/badge";
import { Bell, CheckCheck, RefreshCw } from "lucide-react";
import { Button } from "./components/ui/button";
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { navigate } from "./navigation";
type Item = {
  id: string;
  title: string;
  number: string;
  appeal_title: string;
  url: string;
  created_at: string;
  read_at: string | null;
};
type Page = { items: Item[]; unread: number; total: number; page: number };
export function Notifications() {
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    async function load() {
      if (active) setLoading(true);
      try {
        const next = await api<Page>(`/notifications?page=${page}`);
        if (active) {
          setData(next);
          setError("");
        }
      } catch (error) {
        if (active) setError((error as Error).message);
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    const timer = window.setInterval(() => {
      if (!document.hidden) void load();
    }, 30000);
    window.addEventListener("focus", load);
    return () => {
      active = false;
      clearInterval(timer);
      window.removeEventListener("focus", load);
    };
  }, [page, open, attempt]);
  async function read(item?: Item) {
    setBusy(true);
    try {
      await api(
        item ? `/notifications/${item.id}/read` : "/notifications/read-all",
        "POST",
      );
      setData(await api<Page>(`/notifications?page=${page}`));
      setError("");
      if (item) {
        setOpen(false);
        navigate(item.url);
      }
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline">
          <Bell data-icon="inline-start" aria-hidden="true" />
          Уведомления
          {data?.unread ? (
            <Badge variant="secondary">{data.unread}</Badge>
          ) : null}
        </Button>
      </SheetTrigger>
      <SheetContent
        className="notifications-sheet"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          titleRef.current?.focus();
        }}
      >
        <SheetHeader>
          <SheetTitle ref={titleRef} tabIndex={-1}>
            Уведомления
          </SheetTitle>
          <SheetDescription>
            Ответы и изменения по вашим обращениям.
          </SheetDescription>
        </SheetHeader>
        <div className="notifications-toolbar">
          <span className="hint" role="status">
            {data ? `Непрочитанных: ${data.unread}` : "Загружаем…"}
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Обновить уведомления"
            disabled={loading || busy}
            onClick={() => setAttempt((value) => value + 1)}
          >
            <RefreshCw />
          </Button>
        </div>
        {!!data?.unread && (
          <Button
            variant="outline"
            className="notifications-read-all"
            disabled={busy}
            onClick={() => void read()}
          >
            <CheckCheck data-icon="inline-start" aria-hidden="true" />
            Отметить все прочитанными
          </Button>
        )}
        <div className="notifications-body" aria-busy={loading || busy}>
          {error && (
            <div className="notifications-error">
              <p role="alert" className="error">
                {error}
              </p>
              <Button
                variant="outline"
                disabled={loading}
                onClick={() => setAttempt((value) => value + 1)}
              >
                Повторить загрузку
              </Button>
            </div>
          )}
          {(!data || data.page !== page) && loading ? (
            <div
              className="employee-loading"
              role="status"
              aria-label="Загружаем уведомления"
            >
              <Skeleton />
              <Skeleton />
              <Skeleton />
            </div>
          ) : data?.items.length === 0 ? (
            <Empty>
              <EmptyHeader>
                <EmptyTitle>Пока нет уведомлений</EmptyTitle>
                <EmptyDescription>
                  Здесь появятся ответы, назначения и напоминания по обращениям.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ul className="notification-feed">
              {data?.items.map((item) => (
                <li
                  key={item.id}
                  className={item.read_at ? "" : "notification-unread"}
                >
                  <Button
                    variant="ghost"
                    disabled={busy || data.page !== page}
                    onClick={() => void read(item)}
                  >
                    <span className="notification-event">
                      {!item.read_at && (
                        <span
                          className="unread-mark"
                          aria-label="Непрочитанное"
                        />
                      )}
                      {item.title}
                    </span>
                    <span className="notification-appeal">
                      {item.number} · {item.appeal_title}
                    </span>
                    <time dateTime={item.created_at}>
                      {new Date(item.created_at).toLocaleString("ru-RU", {
                        dateStyle: "medium",
                        timeStyle: "short",
                      })}
                    </time>
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
        {data && data.total > 20 && (
          <nav
            className="notifications-pagination"
            aria-label="Страницы уведомлений"
          >
            <Button
              variant="outline"
              disabled={page === 1 || busy || loading}
              onClick={() => setPage(page - 1)}
            >
              Назад
            </Button>
            <span>
              {page} / {Math.ceil(data.total / 20)}
            </span>
            <Button
              variant="outline"
              disabled={page * 20 >= data.total || busy || loading}
              onClick={() => setPage(page + 1)}
            >
              Далее
            </Button>
          </nav>
        )}
      </SheetContent>
    </Sheet>
  );
}

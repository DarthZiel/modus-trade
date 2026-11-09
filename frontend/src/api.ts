let telegramToken: string | undefined;
export function setTelegramToken(value: string) {
  telegramToken = value;
}
export function telegramHeaders(): Record<string, string> {
  return telegramToken ? { Authorization: `Bearer ${telegramToken}` } : {};
}
export type Role = "employee" | "responsible" | "coordinator";
export type User = {
  id: string;
  name: string;
  email: string;
  company_id: string;
  department_id: string;
  roles: Role[];
  is_active: boolean;
};
export type Company = { id: string; name: string };
export type Department = Company & { company_id: string };
export type Invitation = {
  id: string;
  name: string;
  email: string;
  company_id: string;
  department_id: string;
  roles: Role[];
  expires_at: string;
  used_at: string | null;
  revoked_at: string | null;
};
export const roleNames: Record<Role, string> = {
  employee: "Сотрудник",
  responsible: "Ответственный",
  coordinator: "Координатор",
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: {
      ...(body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      "X-Modus-Request": "1",
      ...telegramHeaders(),
    },
    body:
      body instanceof FormData
        ? body
        : body === undefined
          ? undefined
          : JSON.stringify(body),
  }).catch(() => {
    throw new ApiError(
      0,
      "Не удалось связаться с сервером. Проверьте соединение и повторите попытку.",
    );
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const message =
      response.status === 413
        ? "Размер вложений превышает допустимый лимит."
        : response.status >= 500
          ? "Сервис временно недоступен. Повторите попытку позже."
          : typeof data.detail === "string"
            ? data.detail
            : "Проверьте заполненные поля и повторите попытку.";
    throw new ApiError(response.status, message);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export async function downloadAttachment(url: string, filename: string) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: telegramHeaders(),
  });
  if (!response.ok)
    throw new Error(
      "Не удалось скачать вложение. Обновите карточку и повторите.",
    );
  const href = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(href), 60000);
}

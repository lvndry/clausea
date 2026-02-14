import { auth } from "@clerk/nextjs/server";

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface HttpOptions<TBody = unknown> extends Omit<
  RequestInit,
  "body"
> {
  retry?: number;
  retryDelayMs?: number;
  log?: boolean;
  body?: TBody;
}

const DEFAULT_RETRY = 2;
const DEFAULT_RETRY_DELAY_MS = 300;

export async function http(
  input: string | URL,
  options: HttpOptions<unknown> = {},
): Promise<Response> {
  const {
    retry = DEFAULT_RETRY,
    retryDelayMs = DEFAULT_RETRY_DELAY_MS,
    log = true,
    headers,
    ...init
  } = options;

  const userAuth = await auth();
  let token: string | null | undefined = undefined;
  try {
    token = await userAuth.getToken?.({ template: "default" });
    if (!token) {
      token = await userAuth.getToken?.();
    }
  } catch (_) {
    // ignore
  }

  const mergedHeaders: HeadersInit = {
    ...(headers || {}),
  };

  if (token) {
    (mergedHeaders as Record<string, string>)["Authorization"] =
      `Bearer ${token}`;
  }

  let attempt = 0;
  let lastError: unknown;
  const url = typeof input === "string" ? input : input.toString();

  while (attempt <= retry) {
    try {
      const start = Date.now();
      const response = await fetch(url, {
        ...init,
        headers: mergedHeaders,
        body: init.body as BodyInit | null | undefined,
      });
      if (log) {
        console.log(
          `[Client HTTP] ${init.method || "GET"} ${url} -> ${response.status} in ${Date.now() - start}ms`,
        );
      }
      if (!response.ok && shouldRetry(response.status) && attempt < retry) {
        attempt += 1;
        await delay(backoff(attempt, retryDelayMs));
        continue;
      }
      return response;
    } catch (error) {
      lastError = error;
      if (log)
        console.error(
          `[Client HTTP] ${init.method || "GET"} ${url} error:`,
          error,
        );
      if (attempt < retry) {
        attempt += 1;
        await delay(backoff(attempt, retryDelayMs));
        continue;
      }
      throw error;
    }
  }
  throw lastError instanceof Error
    ? lastError
    : new Error("Client HTTP request failed");
}

function shouldRetry(status: number): boolean {
  return status >= 500 || status === 429;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function backoff(attempt: number, baseDelay: number): number {
  const jitter = Math.floor(Math.random() * 100);
  return Math.min(2000, baseDelay * Math.pow(2, attempt - 1)) + jitter;
}

export async function httpJson<T, TBody = unknown>(
  url: string,
  opts: HttpOptions<TBody> & { method?: HttpMethod } = {},
): Promise<T> {
  const { body, headers, ...rest } = opts;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const mergedHeaders: HeadersInit = isForm
    ? headers || {}
    : { "Content-Type": "application/json", ...(headers || {}) };

  const response = await http(url, {
    ...rest,
    headers: mergedHeaders,
    body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(
      `Client HTTP ${response.status} ${response.statusText}: ${text}`,
    );
  }
  return response.json() as Promise<T>;
}

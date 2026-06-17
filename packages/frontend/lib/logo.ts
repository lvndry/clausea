type MinimalItem = { logo?: string | null | undefined; domains?: string[] | undefined };
type MinimalPage<T extends MinimalItem> = { items: T[]; total: number; page: number; pages: number };

function toHostname(raw: string): string {
  try {
    return new URL(raw.startsWith("http") ? raw : `https://${raw}`).hostname;
  } catch {
    return raw.replace(/^https?:\/\//, "").split(/[/?#]/)[0];
  }
}

export function enrichLogos<T extends MinimalItem>(data: MinimalPage<T>): MinimalPage<T> {
  const token = process.env.LOGO_DEV_API_KEY;
  if (!token) return data;
  return {
    ...data,
    items: data.items.map((item): T => {
      if (item.logo || !item.domains?.length) return item;
      const hostname = toHostname(item.domains[0]);
      return { ...item, logo: `https://img.logo.dev/${hostname}?token=${token}` } as T;
    }),
  };
}

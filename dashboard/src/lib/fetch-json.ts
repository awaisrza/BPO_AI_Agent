/** Parse fetch responses safely — Next.js 500s are often plain text, not JSON. */
export async function readJsonResponse<T extends Record<string, unknown>>(
  res: Response,
): Promise<T> {
  const raw = await res.text();
  if (!raw.trim()) {
    if (!res.ok) {
      throw new Error(`Request failed (${res.status}) — empty response from server.`);
    }
    return {} as T;
  }

  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new Error(
      `Server returned invalid JSON (${res.status}). ${raw.slice(0, 240)}`,
    );
  }
}

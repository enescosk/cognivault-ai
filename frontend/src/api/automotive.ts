const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api';
export type Decision = { vehicle_id: string; customer_label: string; vehicle_label: string;
  status: 'ready' | 'review' | 'blocked' | 'not_due'; reason: string; evidence: string[]; draft: string | null };
export type Preview = { as_of: string; summary: Record<Decision['status'], number>; decisions: Decision[] };
export type Demo = { input: Record<string, unknown>; preview: Preview };
export type Outcome = 'interested' | 'already_serviced' | 'opt_out' | 'wrong_person' | 'price' | 'urgent' | 'human';
export type Rehearsal = { reply: string; required_steps: string[]; stage: string };

export async function automotiveRequest<T>(path: string, token: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE}/automotive/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'Veri okunamadı. Tarihleri, alanları ve oturumunuzu kontrol edin.');
  }
  return response.json() as Promise<T>;
}

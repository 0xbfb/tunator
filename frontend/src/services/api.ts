const apiBase = ((import.meta as any).env?.VITE_API_BASE || '').replace(/\/$/, '')

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${apiBase}${path}`
  let res: Response
  try {
    res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...init })
  } catch {
    const baseHint = apiBase || window.location.origin
    throw new Error(`Não consegui alcançar a API em ${baseHint}.`) 
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(data?.detail?.message || data?.detail?.errors?.join('; ') || data?.message || 'Request failed')
  }
  return data as T
}

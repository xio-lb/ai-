export const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')
export const API_URL = API_BASE

const TOKEN_KEY = 'atp.auth.token'

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`
}

export function getToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setToken(token: string): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage can be unavailable in private mode */
  }
}

export function clearToken(): void {
  setToken('')
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers || {})
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(apiUrl(path), { ...init, headers })
  if (response.status === 401 && getToken()) {
    clearToken()
    window.dispatchEvent(new CustomEvent('atp:unauthorized'))
  }
  return response
}

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

export type AuthUser = {
  id: string
  username: string
  email?: string
  department?: string | null
  is_system_owner: boolean
  roles: string[]
  permissions: string[]
  permission_overrides?: Record<string, boolean>
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      credentials: 'include',
      ...options,
      headers: {
        Accept: 'application/json',
        ...(options.headers ?? {}),
      },
    })
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error('Unable to reach the TETHER API. Check the backend connection and retry.')
    }
    throw error
  }

  if (response.status === 204) {
    return undefined as T
  }

  const contentType = response.headers.get('content-type') ?? ''
  const payload = contentType.includes('application/json') ? await response.json() : await response.text()

  if (!response.ok) {
    throw new Error(
      typeof payload === 'object' && payload && 'detail' in payload ? String(payload.detail) : 'Request failed',
    )
  }

  return payload as T
}

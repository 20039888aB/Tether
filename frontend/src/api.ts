export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'
export const SESSION_EXPIRED_EVENT = 'tether:session-expired'
export const MFA_SETUP_REQUIRED_EVENT = 'tether:mfa-setup-required'
export const SYSTEM_DATA_CHANGED_EVENT = 'tether:system-data-changed'
export const SYSTEM_MANUAL_REFRESH_EVENT = 'tether:system-manual-refresh'

export type SystemEvent = {
  id: number
  category: string
  action: string
  occurred_at: string
}

export type SystemSyncResponse = {
  status: 'ready'
  checked_at: string
  cursor: number
  events: SystemEvent[]
}

export type AuthUser = {
  id: string
  username: string
  email?: string
  department?: string | null
  facility_id?: number | null
  is_system_owner: boolean
  mfa_setup_required?: boolean
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
    if (response.status === 401 && path !== '/auth/login' && path !== '/auth/logout') {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
    }
    if (
      response.status === 403 &&
      typeof payload === 'object' &&
      payload &&
      'detail' in payload &&
      payload.detail === 'mfa_setup_required'
    ) {
      window.dispatchEvent(new Event(MFA_SETUP_REQUIRED_EVENT))
    }
    const detail =
      typeof payload === 'object' && payload && 'detail' in payload
        ? String(payload.detail)
        : 'Request failed'
    if (response.status === 409 && detail === 'record_changed_refresh_before_saving') {
      throw new Error(
        'This record changed after you opened it. Your unsaved changes are still here; copy them before closing and reopening the record to load the latest version.',
      )
    }
    throw new Error(detail)
  }

  return payload as T
}

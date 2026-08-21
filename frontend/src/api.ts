import type { ComposeResult, Instance, InstanceConfig } from './types'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Token 只保存在页面内存中（模块级变量），不写入任何浏览器存储
let token: string | null = null

export function setToken(value: string | null): void {
  token = value
}

function headers(): Record<string, string> {
  const h: Record<string, string> = {}
  if (token) h.Authorization = `Bearer ${token}`
  return h
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(url, { ...init, headers: { ...headers(), ...(init.headers ?? {}) } })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (body && body.detail) detail = String(body.detail)
    } catch {
      // 非 JSON 响应，保留状态文本
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export function checkAuth(): Promise<{ authenticated: boolean }> {
  return request('/api/auth/check')
}

export function listInstances(): Promise<{ instances: Instance[] }> {
  return request('/api/instances')
}

export function createInstance(name: string): Promise<Instance> {
  return request('/api/instances', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

export function getConfig(name: string): Promise<InstanceConfig> {
  return request(`/api/instances/${encodeURIComponent(name)}/config`)
}

export function saveConfig(
  name: string,
  data: { backend_port: number | string; web_client_port: number | string; conf_toml: string },
): Promise<{ success: boolean }> {
  return request(`/api/instances/${encodeURIComponent(name)}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function compose(name: string, action: string): Promise<ComposeResult> {
  return request(`/api/instances/${encodeURIComponent(name)}/compose/${action}`, {
    method: action === 'ps' ? 'GET' : 'POST',
  })
}

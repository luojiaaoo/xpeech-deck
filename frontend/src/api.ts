import type { ComposeResult, ConsoleEvent, ImagePullResult, ImageStatus, Instance, InstanceConfig } from './types'

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

export function listImages(): Promise<{ images: ImageStatus[] }> {
  return request('/api/images')
}

export function pullImage(key: string): Promise<ImagePullResult> {
  return request(`/api/images/${encodeURIComponent(key)}/pull`, { method: 'POST' })
}

export async function streamConsole(
  signal: AbortSignal,
  onEvent: (event: ConsoleEvent) => void,
  onConnected: () => void,
): Promise<void> {
  const res = await fetch('/api/console/stream', { headers: headers(), signal })
  if (!res.ok) {
    if (res.status === 404) {
      throw new ApiError(404, 'Console 接口尚未加载，请重启 Xpeech Deck 后端进程')
    }
    let detail = res.statusText
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      // 保留状态文本
    }
    throw new ApiError(res.status, detail)
  }
  if (!res.body) throw new Error('浏览器不支持流式响应')

  onConnected()
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const data = block
        .split(/\r?\n/)
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
      if (!data) continue
      try {
        onEvent(JSON.parse(data) as ConsoleEvent)
      } catch {
        // 忽略单条损坏事件，保持后续流继续读取
      }
    }
    if (done) break
  }
}

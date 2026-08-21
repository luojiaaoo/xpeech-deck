export interface Instance {
  name: string
  backend_port: number
  web_client_port: number
  path: string
}

export interface InstanceConfig {
  name: string
  backend_port: number
  web_client_port: number
  conf_toml: string
}

export interface ComposeResult {
  success: boolean
  exit_code: number
  stdout: string
  stderr: string
}

export interface ImageStatus {
  key: string
  label: string
  name: string
  status: 'available' | 'missing' | 'error'
  image_id: string | null
  size_bytes: number | null
  created_at: string | null
  message: string
}

export interface ImagePullResult extends ComposeResult {
  image: ImageStatus
}

export interface ConsoleEvent {
  sequence: number
  timestamp: string
  kind: 'command' | 'stdout' | 'stderr' | 'exit' | 'system'
  source: 'compose' | 'image'
  target: string
  cwd: string
  text: string
  exit_code: number | null
}

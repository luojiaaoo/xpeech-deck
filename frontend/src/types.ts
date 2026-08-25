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

export interface Skill {
  name: string
  description: string
  file_count: number
  size_bytes: number
}

export interface ComposeResult {
  success: boolean
  exit_code: number
  stdout: string
  stderr: string
}

export interface GitVersion {
  ref: string
  label: string
  kind: 'branch' | 'tag' | 'commit'
  commit: string
  committed_at: string | null
}

export interface InstanceVersions {
  current_ref: string
  current_label: string
  current_commit: string
  versions: GitVersion[]
}

export interface GitResult {
  success: boolean
  exit_code: number
  stdout: string
  stderr: string
}

export interface GitFetchResult extends GitResult {
  name: string
}

export interface SwitchVersionResult extends GitResult {
  current_ref: string
  current_label: string
  current_commit: string
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
  source: 'compose' | 'image' | 'git'
  target: string
  cwd: string
  text: string
  exit_code: number | null
}

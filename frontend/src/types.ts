export interface Instance {
  name: string
  backend_port: number | null
  web_client_port: number | null
  ports: string[]
  path: string
}

export interface PublicInstance {
  name: string
  web_client_port: number | null
}

export interface PublicInstanceList {
  display_name: string
  instances: PublicInstance[]
}

export interface RedirectMapping {
  redirect_to: string
  instance_name: string
}

export interface InstanceConfig {
  name: string
  env_content: string
  conf_toml: string
}

export interface Skill {
  name: string
  is_custom: boolean
  description: string
  filter: string | null
  file_count: number
  size_bytes: number
}

export interface ComposeResult {
  success: boolean
  exit_code: number
  stdout: string
  stderr: string
}

export interface ComposeServicesResult extends ComposeResult {
  services: string[]
}

export interface GitVersion {
  ref: string
  label: string
  kind: 'branch' | 'tag' | 'commit'
  commit: string
  committed_at: string | null
  branches: string[]
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

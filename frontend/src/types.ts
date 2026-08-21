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

export function getWebClientUrl(port: number): string {
  const target = new URL(window.location.href)
  target.protocol = 'http:'
  target.port = String(port)
  target.pathname = '/'
  target.search = ''
  target.hash = ''
  return target.toString()
}

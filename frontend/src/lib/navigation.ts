/** Only same-site paths are allowed as a post-login destination (no open redirects). */
export function safeNext(raw: string | null): string {
  return raw && raw.startsWith('/') && !raw.startsWith('//') ? raw : '/'
}

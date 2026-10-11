export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024
const EXTENSIONS = ['.csv', '.tsv', '.txt']

/**
 * Quick checks before sending the file. The server re-validates everything by content,
 * so this only saves a round trip for obvious mistakes.
 */
export function checkFile(file: File): string | null {
  const name = file.name.toLowerCase()
  if (!EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return 'Choose a CSV file (.csv, .tsv or .txt).'
  }
  if (file.size === 0) return 'This file is empty.'
  if (file.size > MAX_UPLOAD_BYTES) return 'Files can be at most 25 MB.'
  return null
}

export function displayName(file: File): string {
  return file.name.replace(/\.(csv|tsv|txt)$/i, '').slice(0, 120)
}

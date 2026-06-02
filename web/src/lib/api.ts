export function getApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (configured) {
      try {
        const url = new URL(configured);
        const isLocalPage = host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
        const isLocalApi = url.hostname === 'localhost' || url.hostname === '127.0.0.1' || url.hostname === '[::1]';
        if (isLocalPage && isLocalApi && url.hostname !== host) {
          url.hostname = host === '[::1]' ? 'localhost' : host;
          return url.toString().replace(/\/$/, '');
        }
      } catch {
        return configured.replace(/\/$/, '');
      }
      return configured.replace(/\/$/, '');
    }
    if (host === 'localhost' || host === '127.0.0.1' || host === '[::1]') {
      return `${window.location.protocol}//${host}:5000`;
    }
    return '';
  }
  if (configured) return configured.replace(/\/$/, '');
  return 'http://127.0.0.1:5000';
}

export function api(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${getApiBase()}${path}`, {
    credentials: 'include',
    ...init,
  });
}

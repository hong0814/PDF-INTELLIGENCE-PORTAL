import type {
  AuthUser,
  AuthConfig,
  LoginRequest,
  LoginPreAuthResponse,
  LoginResponse,
  OtpResponse,
  UploadResponse,
  SearchResponse,
  SmartSearchResponse,
  ProgressEvent,
  PdfsResponse,
  UnifiedSearchResponse,
  UnifiedSource,
} from '../types';

export const BASE = '/api';
export const AUTH_EXPIRED_EVENT = 'pdf-auth-expired';

interface ApiFetchOptions extends RequestInit {
  sessionId?: string;
}

function withSessionHeaders(sessionId?: string, headers?: HeadersInit): Headers {
  const merged = new Headers(headers);
  if (sessionId) merged.set('X-Session-ID', sessionId);
  return merged;
}

async function readError(res: Response): Promise<string> {
  const text = await res.text();
  if (!text) return `${res.status} ${res.statusText}`;
  try {
    const parsed = JSON.parse(text) as { detail?: string };
    if (typeof parsed.detail === 'string') return parsed.detail;
  } catch {
    // Fall back to the raw response body.
  }
  return text;
}

export async function apiFetch(url: string, options: ApiFetchOptions = {}): Promise<Response> {
  const { sessionId, headers, ...init } = options;
  const res = await fetch(url, {
    credentials: 'include',
    ...init,
    headers: withSessionHeaders(sessionId, headers),
  });
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
  }
  if (!res.ok) throw new Error(await readError(res));
  return res;
}

async function apiJson<T>(url: string, options: ApiFetchOptions = {}): Promise<T> {
  const res = await apiFetch(url, options);
  return res.json() as Promise<T>;
}

export async function getAuthConfig(): Promise<AuthConfig> {
  return apiJson<AuthConfig>(`${BASE}/auth/config`);
}

export async function login(body: LoginRequest): Promise<LoginPreAuthResponse> {
  return apiJson<LoginPreAuthResponse>(`${BASE}/auth/ldap`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: body.username, password: body.password }),
  });
}

export async function verifyOtp(preAuthToken: string, otpCode: string): Promise<OtpResponse> {
  return apiJson<OtpResponse>(`${BASE}/auth/otp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pre_auth_token: preAuthToken, otp: otpCode }),
  });
}

export async function touchAuth(): Promise<void> {
  await apiFetch(`${BASE}/auth/touch`, { method: 'POST' });
}

export async function getCurrentAuth(): Promise<LoginResponse> {
  return apiJson<LoginResponse>(`${BASE}/auth/me`);
}

export async function getCurrentUser(): Promise<AuthUser> {
  const data = await getCurrentAuth();
  return data.user;
}

export async function logout(): Promise<void> {
  await apiFetch(`${BASE}/auth/logout`, { method: 'POST' });
}

export async function createSession(name: string): Promise<{ session_id: string; name: string }> {
  return apiJson<{ session_id: string; name: string }>(`${BASE}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export async function updateSession(sessionId: string, name: string): Promise<import('../types').SessionInfo> {
  return apiJson<import('../types').SessionInfo>(`${BASE}/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export async function deleteSession(sessionId: string): Promise<void> {
  await apiFetch(`${BASE}/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
}

export async function uploadPdfs(files: File[], sessionId: string): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));
  const res = await apiFetch(`${BASE}/upload`, {
    method: 'POST',
    body: formData,
    sessionId,
  });
  return res.json();
}

export async function search(
  query: string,
  maxResults: number,
  sessionId: string,
  pdfNames?: string[],
): Promise<SearchResponse> {
  const body: Record<string, unknown> = { query, max_results: maxResults };
  if (pdfNames && pdfNames.length > 0) body.pdf_names = pdfNames;
  const res = await apiFetch(`${BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    sessionId,
    body: JSON.stringify(body),
  });
  return res.json();
}

export async function smartSearch(
  query: string,
  pdfName: string,
  sessionId: string,
  onProgress: (event: ProgressEvent) => void,
): Promise<SmartSearchResponse> {
  const res = await apiFetch(`${BASE}/smart-search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    sessionId,
    body: JSON.stringify({ query, pdf_name: pdfName }),
  });

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';
  let finalResult: SmartSearchResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (!data) continue;

        try {
          const parsed = JSON.parse(data);

          if (parsed.phase !== undefined) {
            onProgress(parsed as ProgressEvent);
          } else if (parsed.result !== undefined) {
            finalResult = parsed as SmartSearchResponse;
          } else if (parsed.error !== undefined) {
            throw new Error(parsed.error);
          }
        } catch {
          // skip malformed JSON lines
        }
      }
    }
  }

  if (!finalResult) throw new Error('No result received from smart search');
  return finalResult;
}

export async function askQuestion(
  question: string,
  tableHtml: string,
  tableTitle: string,
  sessionId: string,
  onToken: (token: string) => void,
): Promise<void> {
  const res = await apiFetch(`${BASE}/qa`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    sessionId,
    body: JSON.stringify({ question, table_html: tableHtml, table_title: tableTitle }),
  });

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (!data) continue;
        try {
          const parsed = JSON.parse(data);
          if (parsed.error) throw new Error(parsed.error);
          if (parsed.token) onToken(parsed.token);
        } catch (e) {
          if (e instanceof Error && !e.message.includes('JSON')) throw e;
        }
      }
    }
  }
}

export async function listPdfs(sessionId: string): Promise<PdfsResponse> {
  const res = await apiFetch(`${BASE}/pdfs`, { sessionId });
  return res.json();
}

export async function deletePdf(name: string, sessionId: string): Promise<void> {
  await apiFetch(`${BASE}/pdfs/${encodeURIComponent(name)}`, {
    method: 'DELETE',
    sessionId,
  });
}

export async function getDocumentHtml(pdfName: string, sessionId: string): Promise<string> {
  const res = await apiFetch(`${BASE}/documents/html?name=${encodeURIComponent(pdfName)}`, {
    sessionId,
  });
  return res.text();
}

export async function askDocument(
  question: string,
  sessionId: string,
  onToken: (token: string) => void,
  onSources?: (sources: { pdf: string; chunk_index: number; page_number: number; pdf_page_count: number; text: string }[]) => void,
  pdfNames?: string[],
): Promise<void> {
  const body: Record<string, unknown> = { question };
  if (pdfNames && pdfNames.length > 0) body.pdf_names = pdfNames;
  const res = await apiFetch(`${BASE}/ask-document`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    sessionId,
    body: JSON.stringify(body),
  });

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (!data) continue;
        try {
          const parsed = JSON.parse(data);
          if (parsed.error) throw new Error(parsed.error);
          if (parsed.token) onToken(parsed.token);
          if (parsed.sources && onSources) onSources(parsed.sources);
        } catch (e) {
          if (e instanceof Error && !e.message.includes('JSON')) throw e;
        }
      }
    }
  }
}

export async function confirmTableGroups(
  pdfName: string,
  confirmed: { group_id: string; table_ids: string[] }[],
  rejected: { group_id: string; table_ids: string[] }[],
  sessionId: string,
): Promise<void> {
  await apiFetch(`${BASE}/confirm-table-groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    sessionId,
    body: JSON.stringify({
      pdf_name: pdfName,
      confirmed,
      rejected,
    }),
  });
}

export async function getSessions(): Promise<import('../types').SessionsResponse> {
  const res = await apiFetch(`${BASE}/sessions`);
  return res.json();
}

export async function getSession(sessionId: string): Promise<import('../types').SessionInfo> {
  const res = await apiFetch(`${BASE}/sessions/${encodeURIComponent(sessionId)}`);
  return res.json();
}

export async function getQaResults(sessionId: string): Promise<{
  results: { qa_key: string; question: string; answer: string; done: boolean }[];
}> {
  const res = await apiFetch(`${BASE}/qa-results`, { sessionId });
  return res.json();
}

export async function getPageHtml(
  pdfName: string,
  page: number,
  sessionId: string,
): Promise<string> {
  const res = await apiFetch(
    `${BASE}/documents/page-html?name=${encodeURIComponent(pdfName)}&page=${page}`,
    { sessionId },
  );
  return res.text();
}

export async function getTranslatedPage(
  pdfName: string,
  page: number,
  sessionId: string,
): Promise<string> {
  const res = await apiFetch(
    `${BASE}/translated-page?name=${encodeURIComponent(pdfName)}&page=${page}`,
    { sessionId },
  );
  return res.text();
}

export async function startHtmlTranslation(
  pdfName: string,
  sessionId: string,
  sourceLang: string = 'ko',
  targetLang: string = 'en',
  onPageDone: (page: number, totalPages: number, originalHtml: string, translatedHtml: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await apiFetch(`${BASE}/translate-html`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    sessionId,
    body: JSON.stringify({
      pdf_name: pdfName,
      source_lang: sourceLang,
      target_lang: targetLang,
    }),
    signal,
  });

  if (!res.body) throw new Error('No response body');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let eventType = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        if (eventType === 'page_done') {
          onPageDone(data.page, data.total_pages, data.original_html, data.translated_html);
        } else if (eventType === 'error') {
          throw new Error(data.error);
        }
      }
    }
  }
}

export async function unifiedSearch(
  query: string,
  sessionId: string,
  onProgress: (event: ProgressEvent) => void,
  pdfNames?: string[],
): Promise<UnifiedSearchResponse> {
  const body: Record<string, unknown> = { query };
  if (pdfNames && pdfNames.length > 0) body.pdf_names = pdfNames;
  const res = await apiFetch(`${BASE}/unified-search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    sessionId,
    body: JSON.stringify(body),
  });

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';
  let finalResult: UnifiedSearchResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (!data) continue;
        try {
          const parsed = JSON.parse(data);
          if (parsed.phase !== undefined) {
            onProgress(parsed as ProgressEvent);
          } else if (parsed.answer !== undefined) {
            finalResult = parsed as UnifiedSearchResponse;
          } else if (parsed.error !== undefined) {
            throw new Error(parsed.error);
          }
        } catch (e) {
          if (e instanceof Error && e.message.includes('error')) throw e;
        }
      }
    }
  }

  if (!finalResult) throw new Error('No result received from unified search');
  return finalResult;
}

export async function unifiedFollowup(
  question: string,
  context: string,
  sourcesJson: string,
  sessionId: string,
  onToken: (token: string) => void,
  onSources?: (sources: UnifiedSource[]) => void,
): Promise<void> {
  const res = await apiFetch(`${BASE}/unified-followup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    sessionId,
    body: JSON.stringify({ question, context, sources_json: sourcesJson }),
  });

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim();
        if (!data) continue;
        try {
          const parsed = JSON.parse(data);
          if (parsed.error) throw new Error(parsed.error);
          if (parsed.token) onToken(parsed.token);
          if (parsed.sources && onSources) onSources(parsed.sources);
        } catch (e) {
          if (e instanceof Error && !e.message.includes('JSON')) throw e;
        }
      }
    }
  }
}

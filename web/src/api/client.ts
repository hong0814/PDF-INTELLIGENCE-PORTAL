import type {
  UploadResponse,
  SearchResponse,
  SmartSearchResponse,
  ProgressEvent,
  PdfsResponse,
  UnifiedSearchResponse,
  UnifiedSource,
} from '../types';

export const BASE = '/api';

export async function uploadPdfs(files: File[], sessionId: string): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));
  const res = await fetch(`${BASE}/upload`, {
    method: 'POST',
    body: formData,
    headers: { 'X-Session-ID': sessionId },
  });
  if (!res.ok) throw new Error(await res.text());
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
  const res = await fetch(`${BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function smartSearch(
  query: string,
  pdfName: string,
  sessionId: string,
  onProgress: (event: ProgressEvent) => void,
): Promise<SmartSearchResponse> {
  const res = await fetch(`${BASE}/smart-search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
    body: JSON.stringify({ query, pdf_name: pdfName }),
  });

  if (!res.ok) throw new Error(await res.text());

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
  const res = await fetch(`${BASE}/qa`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
    body: JSON.stringify({ question, table_html: tableHtml, table_title: tableTitle }),
  });
  if (!res.ok) throw new Error(await res.text());

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
  const res = await fetch(`${BASE}/pdfs`, { headers: { 'X-Session-ID': sessionId } });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deletePdf(name: string, sessionId: string): Promise<void> {
  const res = await fetch(`${BASE}/pdfs/${encodeURIComponent(name)}`, {
    method: 'DELETE',
    headers: { 'X-Session-ID': sessionId },
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function getDocumentHtml(pdfName: string, sessionId: string): Promise<string> {
  const res = await fetch(`${BASE}/documents/html?name=${encodeURIComponent(pdfName)}`, {
    headers: { 'X-Session-ID': sessionId },
  });
  if (!res.ok) throw new Error(await res.text());
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
  const res = await fetch(`${BASE}/ask-document`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());

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
  const res = await fetch(`${BASE}/confirm-table-groups`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
    body: JSON.stringify({
      pdf_name: pdfName,
      confirmed,
      rejected,
    }),
  });
  if (!res.ok) throw new Error(await res.text());
}

export async function getSessions(): Promise<import('../types').SessionsResponse> {
  const res = await fetch(`${BASE}/sessions`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getSession(sessionId: string): Promise<import('../types').SessionInfo> {
  const res = await fetch(`${BASE}/sessions/${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getQaResults(sessionId: string): Promise<{
  results: { qa_key: string; question: string; answer: string; done: boolean }[];
}> {
  const res = await fetch(`${BASE}/qa-results`, {
    headers: { 'X-Session-ID': sessionId },
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getPageHtml(
  pdfName: string,
  page: number,
  sessionId: string,
): Promise<string> {
  const res = await fetch(
    `${BASE}/documents/page-html?name=${encodeURIComponent(pdfName)}&page=${page}`,
    { headers: { 'X-Session-ID': sessionId } },
  );
  if (!res.ok) throw new Error(await res.text());
  return res.text();
}

export async function getTranslatedPage(
  pdfName: string,
  page: number,
  sessionId: string,
): Promise<string> {
  const res = await fetch(
    `${BASE}/translated-page?name=${encodeURIComponent(pdfName)}&page=${page}`,
    { headers: { 'X-Session-ID': sessionId } },
  );
  if (!res.ok) throw new Error(await res.text());
  return res.text();
}

export async function startHtmlTranslation(
  pdfName: string,
  sessionId: string,
  sourceLang: string = 'ko',
  targetLang: string = 'en',
  onPageDone: (page: number, totalPages: number, originalHtml: string, translatedHtml: string) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/translate-html`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Session-ID': sessionId,
    },
    body: JSON.stringify({
      pdf_name: pdfName,
      source_lang: sourceLang,
      target_lang: targetLang,
    }),
  });

  if (!res.ok) throw new Error(await res.text());
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
  const res = await fetch(`${BASE}/unified-search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
    body: JSON.stringify(body),
  });

  if (!res.ok) throw new Error(await res.text());

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
  const res = await fetch(`${BASE}/unified-followup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
    body: JSON.stringify({ question, context, sources_json: sourcesJson }),
  });
  if (!res.ok) throw new Error(await res.text());

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

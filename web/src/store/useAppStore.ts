import { create } from 'zustand';
import type { PdfInfo, TableResult, SmartSearchResponse, QAMessage, TableQAItem } from '../types';

export type TabId = 'main' | 'document' | 'search' | 'qa' | 'credit';

export interface HighlightRegion {
  documentName: string;
  pageNumber: number;
  boundingBox: number[]; // [x1, y1, x2, y2] in PDF coordinates
}

// -- localStorage helpers ----------------------------------------------------

function searchKey(sid: string) { return `pdfts_${sid}_search`; }
function qaKey(sid: string) { return `pdfts_${sid}_qa`; }
function tableQaKey(sid: string) { return `pdfts_${sid}_tableqas`; }

function saveJson(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
}
function loadJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) as T : null;
  } catch { return null; }
}

interface AppState {
  activeTab: TabId;
  sessionId: string;
  sessionName: string;
  pdfs: PdfInfo[];
  totalTables: number;
  totalPages: number;
  selectedPdfs: string[];
  lastSearchQuery: string;
  results: TableResult[];
  smartResult: SmartSearchResponse | null;
  searchTime: number;
  isLoading: boolean;
  error: string | null;
  qaMessages: QAMessage[];
  documentChunksReady: boolean;
  isUploading: boolean;
  tableQAs: Record<string, TableQAItem[]>;
  highlightRegion: HighlightRegion | null;
  setActiveTab: (tab: TabId) => void;
  setSession: (id: string, name: string) => void;
  setPdfs: (pdfs: PdfInfo[], totalTables: number, totalPages: number) => void;
  addPdfs: (newPdfs: PdfInfo[], totalTables: number, totalPages: number) => void;
  removePdf: (name: string) => void;
  setSelectedPdfs: (names: string[]) => void;
  setSearchResults: (results: TableResult[], smartResult: SmartSearchResponse | null, time: number, query?: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  addQAMessage: (msg: QAMessage) => void;
  updateQAMessage: (id: string, updates: Partial<QAMessage>) => void;
  clearQA: () => void;
  setDocumentChunksReady: (ready: boolean) => void;
  setUploading: (uploading: boolean) => void;
  addTableQA: (tableId: string, entry: TableQAItem) => void;
  updateTableQA: (tableId: string, index: number, answer: string) => void;
  setHighlightRegion: (region: HighlightRegion | null) => void;
  restoreFromStorage: (sessionId: string) => void;
  reset: () => void;
}

const SESSION_KEY = 'pdftablesearch_session_id';

function getSessionId(): string {
  const params = new URLSearchParams(window.location.search);
  const fromUrl = params.get('session');
  if (fromUrl) {
    localStorage.setItem(SESSION_KEY, fromUrl);
    return fromUrl;
  }
  return localStorage.getItem(SESSION_KEY) || '';
}

const initialSessionId = getSessionId();

export const useAppStore = create<AppState>((set) => ({
  activeTab: 'main',
  sessionId: initialSessionId,
  sessionName: '새 세션',
  pdfs: [],
  totalTables: 0,
  totalPages: 0,
  selectedPdfs: [],
  results: [],
  smartResult: null,
  searchTime: 0,
  isLoading: false,
  error: null,
  qaMessages: [],
  documentChunksReady: false,
  isUploading: false,
  tableQAs: {},
  highlightRegion: null,
  lastSearchQuery: '',

  setActiveTab: (tab) => set({ activeTab: tab }),

  setSession: (id, name) => set({ sessionId: id, sessionName: name }),

  setPdfs: (pdfs, totalTables, totalPages) => set({ pdfs, totalTables, totalPages, selectedPdfs: pdfs.map(p => p.name) }),

  addPdfs: (newPdfs, totalTables, totalPages) =>
    set((state) => {
      const existing = new Map(state.pdfs.map((p) => [p.name, p]));
      for (const pdf of newPdfs) {
        existing.set(pdf.name, pdf);
      }
      const merged = Array.from(existing.values());
      return { pdfs: merged, totalTables, totalPages, selectedPdfs: merged.map(p => p.name) };
    }),

  removePdf: (name) =>
    set((state) => ({
      pdfs: state.pdfs.filter((p) => p.name !== name),
      selectedPdfs: state.selectedPdfs.filter((n) => n !== name),
    })),

  setSelectedPdfs: (names) => set({ selectedPdfs: names }),

  setSearchResults: (results, smartResult, time, query?: string) => {
    const state = useAppStore.getState();
    saveJson(searchKey(state.sessionId), { results, smartResult, time, lastSearchQuery: query || '' });
    set({ results, smartResult, searchTime: time, lastSearchQuery: query || '' });
  },

  setLoading: (loading) => set({ isLoading: loading }),

  setError: (error) => set({ error }),

  addQAMessage: (msg) => {
    set((state) => {
      const updated = [...state.qaMessages, msg];
      saveJson(qaKey(state.sessionId), updated);
      return { qaMessages: updated };
    });
  },
  updateQAMessage: (id, updates) =>
    set((state) => {
      const updated = state.qaMessages.map((m) => (m.id === id ? { ...m, ...updates } : m));
      saveJson(qaKey(state.sessionId), updated);
      return { qaMessages: updated };
    }),
  clearQA: () => {
    const state = useAppStore.getState();
    saveJson(qaKey(state.sessionId), []);
    set({ qaMessages: [], documentChunksReady: false });
  },
  setDocumentChunksReady: (ready) => set({ documentChunksReady: ready }),

  setUploading: (uploading) => set({ isUploading: uploading }),

  addTableQA: (tableId, entry) =>
    set((state) => {
      const existing = state.tableQAs[tableId] || [];
      const updated = { ...state.tableQAs, [tableId]: [...existing, entry] };
      saveJson(tableQaKey(state.sessionId), updated);
      return { tableQAs: updated };
    }),
  updateTableQA: (tableId, index, answer) =>
    set((state) => {
      const existing = state.tableQAs[tableId] || [];
      const updated = existing.map((item, i) =>
        i === index ? { ...item, answer } : item
      );
      const result = { ...state.tableQAs, [tableId]: updated };
      saveJson(tableQaKey(state.sessionId), result);
      return { tableQAs: result };
    }),

  restoreFromStorage: (sessionId) => {
    if (!sessionId) return;
    const searchData = loadJson<{ results: TableResult[]; smartResult: SmartSearchResponse | null; time: number; lastSearchQuery: string }>(searchKey(sessionId));
    const qaData = loadJson<QAMessage[]>(qaKey(sessionId));
    const tableQaData = loadJson<Record<string, TableQAItem[]>>(tableQaKey(sessionId));
    const patch: Partial<AppState> = {};
    if (searchData) {
      patch.results = searchData.results;
      patch.smartResult = searchData.smartResult;
      patch.searchTime = searchData.time;
      if (searchData.lastSearchQuery) patch.lastSearchQuery = searchData.lastSearchQuery;
    }
    if (qaData) patch.qaMessages = qaData;
    if (tableQaData) patch.tableQAs = tableQaData;
    if (Object.keys(patch).length > 0) set(patch);
  },

  setHighlightRegion: (region) => set({ highlightRegion: region }),

  reset: () => {
    localStorage.removeItem(SESSION_KEY);
    window.location.reload();
  },
}));

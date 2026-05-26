export interface TableResult {
  table_id: string;
  document_name: string;
  page_number: number;
  table_title: string | null;
  table_html: string | null;
  table_markdown: string | null;
  relevance_score: number;
  rerank_score: number | null;
  bounding_box: number[];
  table_type?: string;
  group_id?: string;
  merged_table_html?: string;
  group_table_ids?: string[];
}

export interface PdfInfo {
  name: string;
  table_count: number;
  page_count?: number;
}

export interface UploadResponse {
  session_id: string;
  pdfs: Record<string, { table_count: number; page_count: number }>;
  total_tables: number;
  total_pages?: number;
  table_group_suggestions: TableGroupSuggestion[];
}

export interface TableGroupItem {
  pdf_name: string;
  table_a_id: string;
  table_b_id: string;
  group_id: string;
}

export interface TableGroupSuggestion {
  pdf_name: string;
  group_id: string;
  chain_length: number;
  same_cols: boolean;
  pair_cols: [boolean, number, number][];
  tables: {
    table_id: string;
    page_number: number;
    bounding_box: number[];
    table_title: string | null;
    table_html: string;
  }[];
}

export interface SearchResponse {
  results: TableResult[];
  total: number;
  time_seconds: number;
}

export interface SmartSearchResponse {
  result: TableResult;
  vector_results: TableResult[];
}

export interface QAResponse {
  answer: string;
}

export interface ProgressEvent {
  phase: string;
  message: string;
  pct: number;
}

export interface PdfsResponse {
  pdfs: { name: string; table_count: number; page_count: number }[];
  total_tables: number;
  total_pages: number;
}

export interface SessionInfo {
  session_id: string;
  name: string;
  created_at: string;
  last_activity: string;
  pdf_count: number;
  total_pages: number;
  total_tables: number;
  search_count: number;
  qa_count: number;
  pdf_names: string[];
}

export interface SessionsResponse {
  sessions: SessionInfo[];
  total: number;
}

export interface TableQAItem {
  question: string;
  answer: string;
}

export interface QAMessage {
  id: string;
  role: 'user' | 'ai';
  content: string;
  sources?: { pdf: string; chunk_index: number; page_number: number; pdf_page_count: number; paragraph_id?: string; text: string }[];
  isLoading?: boolean;
}

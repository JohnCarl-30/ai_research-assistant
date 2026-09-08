export type ApiStatus = "checking" | "online" | "offline";

export interface Job {
  id: string;
  title: string;
  url: string;
  source: string;
  location: string | null;
  salary_range: string | null;
  is_easy_apply: boolean;
  company_name: string | null;
  created_at: string;
}

export interface JobsResponse {
  items: Job[];
  total: number;
  limit: number;
  offset: number;
}

export interface Tag {
  tag: string;
  count: number;
  last_seen_at: string;
  source_counts: Record<string, unknown> | null;
  type_counts: Record<string, unknown> | null;
}

export interface TagsResponse {
  items: Tag[];
  total: number;
}

export interface ScanRequest {
  query: string;
  location: string;
  skills: string[];
}

export interface ScanResponse {
  scan_id: string | null;
  jobs_found: number;
  new_jobs: number;
  top_tags: Record<string, unknown>[];
  status: string;
  error: string | null;
}

export interface SearchResult {
  job_id: string;
  job_title: string;
  company_name: string | null;
  job_url: string;
  section: string;
  content: string;
  score: number;
  dense_rank: number | null;
  sparse_rank: number | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
}

export interface CoverLetterResponse {
  cover_letter: string;
  job_title: string;
  company_name: string;
}

import type {
  CoverLetterResponse,
  JobsResponse,
  ScanRequest,
  ScanResponse,
  SearchResponse,
  TagsResponse,
} from "@/lib/types";

const API_BASE_PATH = "/scout-api";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function errorMessage(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object") return fallback;

  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (!item || typeof item !== "object") return String(item);
        const message = (item as { msg?: unknown }).msg;
        return typeof message === "string" ? message : "Invalid request";
      })
      .join(". ");
  }

  return fallback;
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_PATH}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(
      "Could not reach the Scout API. Make sure the FastAPI server is running.",
    );
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(
      errorMessage(payload, `Scout returned ${response.status}.`),
      response.status,
    );
  }

  return response.json() as Promise<T>;
}

export const scoutApi = {
  health: (signal?: AbortSignal) =>
    apiRequest<{ status: string }>("/health", { signal }),

  jobs: (signal?: AbortSignal) =>
    apiRequest<JobsResponse>("/api/jobs?limit=8", { signal }),

  trendingTags: (signal?: AbortSignal) =>
    apiRequest<TagsResponse>("/api/tags/trending?days=7&limit=8", {
      signal,
    }),

  scan: (request: ScanRequest) =>
    apiRequest<ScanResponse>("/api/scan", {
      method: "POST",
      body: JSON.stringify(request),
    }),

  search: (query: string) =>
    apiRequest<SearchResponse>(
      `/api/rag/search?q=${encodeURIComponent(query)}&top_k=6&hybrid=true`,
    ),

  coverLetter: (request: {
    jobTitle: string;
    companyName: string;
    jobDescription: string;
    skills: string;
  }) => {
    const params = new URLSearchParams({
      job_title: request.jobTitle,
      company_name: request.companyName,
      job_description: request.jobDescription,
      skills: request.skills,
    });
    return apiRequest<CoverLetterResponse>(`/api/cover-letter?${params}`);
  },
};

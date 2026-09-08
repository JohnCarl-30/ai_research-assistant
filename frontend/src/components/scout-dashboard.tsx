"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { ApiError, scoutApi } from "@/lib/api";
import type {
  ApiStatus,
  Job,
  ScanResponse,
  SearchResult,
  Tag,
} from "@/lib/types";

const navItems = [
  { label: "Overview", href: "#overview", icon: "grid" },
  { label: "Opportunities", href: "#opportunities", icon: "briefcase" },
  { label: "AI search", href: "#search", icon: "spark" },
  { label: "Cover letters", href: "#cover-letter", icon: "document" },
] as const;

const sourceColors: Record<string, string> = {
  greenhouse: "bg-emerald-50 text-emerald-700 ring-emerald-600/10",
  lever: "bg-violet-50 text-violet-700 ring-violet-600/10",
  ashby: "bg-sky-50 text-sky-700 ring-sky-600/10",
};

function Icon({ name, className = "h-5 w-5" }: { name: string; className?: string }) {
  const paths: Record<string, React.ReactNode> = {
    grid: <path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z" />,
    briefcase: <path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7m-9 0h12a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Zm-2 5h16M9 12v2h6v-2" />,
    spark: <path d="m12 3 1.4 4.1L17.5 8.5l-4.1 1.4L12 14l-1.4-4.1-4.1-1.4 4.1-1.4L12 3Zm6 10 .8 2.2L21 16l-2.2.8L18 19l-.8-2.2L15 16l2.2-.8L18 13ZM6 14l1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3Z" />,
    document: <path d="M7 3h7l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm7 0v5h5M9 13h6M9 17h6" />,
    arrow: <path d="m9 18 6-6-6-6" />,
    search: <path d="m20 20-4.5-4.5m2.5-5A7.5 7.5 0 1 1 3 10.5a7.5 7.5 0 0 1 15 0Z" />,
    location: <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Zm-8-3a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z" />,
    external: <path d="M14 4h6v6M20 4l-9 9M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6" />,
    refresh: <path d="M20 6v5h-5M4 18v-5h5m10.2-4A8 8 0 0 0 5.3 6M4.8 15A8 8 0 0 0 18.7 18" />,
    check: <path d="m5 12 4 4L19 6" />,
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    close: <path d="m6 6 12 12M18 6 6 18" />,
  };

  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

function Logo() {
  return (
    <div className="flex items-center gap-3">
      <div className="relative flex h-10 w-10 items-center justify-center rounded-2xl bg-[#17352d] text-white shadow-sm">
        <span className="absolute h-4 w-4 -translate-x-1 -translate-y-1 rounded-full border-2 border-[#a7df5f]" />
        <span className="h-4 w-4 translate-x-1 translate-y-1 rounded-full border-2 border-white" />
      </div>
      <div>
        <div className="text-lg font-bold tracking-[-0.04em] text-[#17352d]">Scout</div>
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#8a958e]">Job intelligence</div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: ApiStatus }) {
  const copy = {
    checking: "Checking API",
    online: "System online",
    offline: "API offline",
  }[status];

  return (
    <div className="flex items-center gap-2 rounded-full border border-[#dce4dd] bg-white px-3 py-1.5 text-xs font-semibold text-[#536159] shadow-sm">
      <span
        className={`h-2 w-2 rounded-full ${
          status === "online"
            ? "bg-[#72bd45] shadow-[0_0_0_3px_rgba(114,189,69,0.15)]"
            : status === "offline"
              ? "bg-rose-500"
              : "animate-pulse bg-amber-400"
        }`}
      />
      {copy}
    </div>
  );
}

function SourceBadge({ source }: { source: string }) {
  const normalized = source.toLowerCase();
  const colors =
    Object.entries(sourceColors).find(([key]) => normalized.includes(key))?.[1] ??
    "bg-slate-50 text-slate-600 ring-slate-500/10";

  return (
    <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold capitalize ring-1 ring-inset ${colors}`}>
      {source}
    </span>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-40 items-center justify-center rounded-2xl border border-dashed border-[#d5ddd6] bg-[#fbfcfa] px-6 text-center text-sm leading-6 text-[#758078]">
      {children}
    </div>
  );
}

function JobCard({ job }: { job: Job }) {
  return (
    <a
      href={job.url}
      target="_blank"
      rel="noreferrer"
      className="group grid gap-4 rounded-2xl border border-[#e0e6e0] bg-white p-4 transition-all hover:-translate-y-0.5 hover:border-[#b7c8b8] hover:shadow-[0_14px_35px_rgba(24,53,45,0.08)] sm:grid-cols-[auto_1fr_auto] sm:items-center"
    >
      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#edf4ea] text-sm font-extrabold text-[#2d604c]">
        {(job.company_name ?? job.title).slice(0, 2).toUpperCase()}
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="truncate font-bold tracking-[-0.02em] text-[#1d2e27] group-hover:text-[#347153]">
            {job.title}
          </h3>
          {job.is_easy_apply && (
            <span className="rounded-full bg-[#eef8dd] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[#527b29]">
              Easy apply
            </span>
          )}
        </div>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-[#6d7971]">
          <span>{job.company_name ?? "Company not listed"}</span>
          <span className="hidden h-1 w-1 rounded-full bg-[#c4ccc5] sm:block" />
          <span className="flex items-center gap-1">
            <Icon name="location" className="h-3.5 w-3.5" />
            {job.location ?? "Location flexible"}
          </span>
          {job.salary_range && <span>{job.salary_range}</span>}
        </p>
      </div>
      <div className="flex items-center justify-between gap-3 sm:justify-end">
        <SourceBadge source={job.source} />
        <span className="flex h-9 w-9 items-center justify-center rounded-full border border-[#e0e6e0] text-[#516059] transition-colors group-hover:border-[#347153] group-hover:bg-[#347153] group-hover:text-white">
          <Icon name="external" className="h-4 w-4" />
        </span>
      </div>
    </a>
  );
}

function SearchResultCard({ result }: { result: SearchResult }) {
  const score = Math.max(0, Math.min(100, Math.round(result.score * 100)));

  return (
    <a
      href={result.job_url}
      target="_blank"
      rel="noreferrer"
      className="block rounded-2xl border border-[#e0e6e0] bg-white p-4 transition hover:border-[#a9bcae] hover:shadow-sm"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-bold text-[#1d2e27]">{result.job_title}</h3>
          <p className="mt-1 text-sm text-[#6d7971]">
            {result.company_name ?? "Company not listed"} · {result.section}
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-[#edf6e8] px-2.5 py-1 text-xs font-bold text-[#4e792e]">
          {score}% match
        </span>
      </div>
      <p className="mt-3 line-clamp-2 text-sm leading-6 text-[#59675f]">{result.content}</p>
    </a>
  );
}

function SectionHeading({ eyebrow, title, action }: { eyebrow: string; title: string; action?: React.ReactNode }) {
  return (
    <div className="mb-5 flex items-end justify-between gap-4">
      <div>
        <p className="mb-1 text-[11px] font-bold uppercase tracking-[0.2em] text-[#76a255]">{eyebrow}</p>
        <h2 className="text-2xl font-bold tracking-[-0.04em] text-[#1b3027]">{title}</h2>
      </div>
      {action}
    </div>
  );
}

export default function ScoutDashboard() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobTotal, setJobTotal] = useState(0);
  const [tags, setTags] = useState<Tag[]>([]);
  const [dataLoading, setDataLoading] = useState(true);
  const [jobsError, setJobsError] = useState("");
  const [tagsError, setTagsError] = useState("");
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  const [query, setQuery] = useState("AI engineer");
  const [location, setLocation] = useState("Remote");
  const [skills, setSkills] = useState("Python, TypeScript, LLMs");
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState("");
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [hasSearched, setHasSearched] = useState(false);

  const [letterTitle, setLetterTitle] = useState("");
  const [letterCompany, setLetterCompany] = useState("");
  const [letterDescription, setLetterDescription] = useState("");
  const [letterSkills, setLetterSkills] = useState("");
  const [letterLoading, setLetterLoading] = useState(false);
  const [letterError, setLetterError] = useState("");
  const [letter, setLetter] = useState("");
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied" | "error">("idle");

  const refreshData = useCallback(async (signal?: AbortSignal) => {
    setDataLoading(true);
    const [healthResult, jobsResult, tagsResult] = await Promise.allSettled([
      scoutApi.health(signal),
      scoutApi.jobs(signal),
      scoutApi.trendingTags(signal),
    ]);

    if (healthResult.status === "fulfilled") setApiStatus("online");
    else if (!signal?.aborted) setApiStatus("offline");

    if (jobsResult.status === "fulfilled") {
      setJobs(jobsResult.value.items);
      setJobTotal(jobsResult.value.total);
      setJobsError("");
    } else if (!signal?.aborted) {
      setJobsError("Recent opportunities could not be loaded.");
    }

    if (tagsResult.status === "fulfilled") {
      setTags(tagsResult.value.items);
      setTagsError("");
    } else if (!signal?.aborted) {
      setTagsError("Trending skills could not be loaded.");
    }

    if (!signal?.aborted) setDataLoading(false);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => {
      void refreshData(controller.signal);
    }, 0);

    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [refreshData]);

  function closeMobileNav() {
    setMobileNavOpen(false);
    window.requestAnimationFrame(() => menuButtonRef.current?.focus());
  }

  function handleDrawerKeyDown(event: React.KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      closeMobileNav();
      return;
    }
    if (event.key !== "Tab") return;

    const focusable = Array.from(
      event.currentTarget.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    );
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function handleCopyLetter() {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(letter);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("error");
    }
  }

  async function handleScan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) return;

    setScanning(true);
    setScanError("");
    setScanResult(null);
    try {
      const result = await scoutApi.scan({
        query: query.trim(),
        location: location.trim(),
        skills: skills
          .split(",")
          .map((skill) => skill.trim())
          .filter(Boolean),
      });
      if (result.status === "failed") {
        throw new ApiError(result.error ?? "The scan could not be completed.");
      }
      setScanResult(result);
      await refreshData();
    } catch (error) {
      setScanError(error instanceof Error ? error.message : "The scan could not be completed.");
    } finally {
      setScanning(false);
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!searchQuery.trim()) return;

    setSearching(true);
    setHasSearched(true);
    setSearchError("");
    try {
      const response = await scoutApi.search(searchQuery.trim());
      setSearchResults(response.results);
    } catch (error) {
      setSearchResults([]);
      setSearchError(error instanceof Error ? error.message : "Search failed.");
    } finally {
      setSearching(false);
    }
  }

  function prepareCoverLetter(job: Job) {
    setLetterTitle(job.title);
    setLetterCompany(job.company_name ?? "");
    setLetterDescription("");
    setLetterSkills(skills);
    setCopyStatus("idle");
    document.querySelector("#cover-letter")?.scrollIntoView({ behavior: "smooth" });
  }

  async function handleCoverLetter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!letterTitle.trim() || !letterCompany.trim()) return;

    setLetterLoading(true);
    setLetterError("");
    setLetter("");
    setCopyStatus("idle");
    try {
      const response = await scoutApi.coverLetter({
        jobTitle: letterTitle.trim(),
        companyName: letterCompany.trim(),
        jobDescription: letterDescription.trim(),
        skills: letterSkills.trim(),
      });
      setLetter(response.cover_letter);
    } catch (error) {
      setLetterError(error instanceof Error ? error.message : "Cover letter generation failed.");
    } finally {
      setLetterLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#f4f6f1] text-[#1d2e27]">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] flex-col border-r border-[#dce4dc] bg-[#f9faf7] px-5 py-6 lg:flex">
        <Logo />
        <nav className="mt-12 space-y-1" aria-label="Main navigation">
          {navItems.map((item, index) => (
            <a
              key={item.label}
              href={item.href}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors ${
                index === 0
                  ? "bg-[#e8f0e3] text-[#275a45]"
                  : "text-[#6b786f] hover:bg-[#edf1eb] hover:text-[#2a4d3d]"
              }`}
            >
              <Icon name={item.icon} className="h-[18px] w-[18px]" />
              {item.label}
            </a>
          ))}
        </nav>
        <div className="mt-auto rounded-2xl bg-[#17352d] p-4 text-white shadow-[0_12px_30px_rgba(23,53,45,0.16)]">
          <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl bg-white/10 text-[#bde985]">
            <Icon name="spark" className="h-5 w-5" />
          </div>
          <p className="text-sm font-bold">Powered by your data</p>
          <p className="mt-1 text-xs leading-5 text-white/60">Scout learns from every indexed opportunity.</p>
          <a href="#search" className="mt-3 inline-flex items-center gap-1 text-xs font-bold text-[#bde985]">
            Explore with AI <Icon name="arrow" className="h-3.5 w-3.5" />
          </a>
        </div>
      </aside>

      {mobileNavOpen && (
        <div className="fixed inset-0 z-50 bg-[#11271f]/35 backdrop-blur-sm lg:hidden" onClick={closeMobileNav}>
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Main navigation"
            className="h-full w-[280px] bg-[#f9faf7] p-6 shadow-2xl"
            onClick={(event) => event.stopPropagation()}
            onKeyDown={handleDrawerKeyDown}
          >
            <div className="flex items-center justify-between">
              <Logo />
              <button autoFocus className="rounded-lg p-2 text-[#607068]" onClick={closeMobileNav} aria-label="Close navigation">
                <Icon name="close" />
              </button>
            </div>
            <nav className="mt-10 space-y-2">
              {navItems.map((item) => (
                <a key={item.label} href={item.href} onClick={closeMobileNav} className="flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold text-[#536159] hover:bg-[#e8f0e3]">
                  <Icon name={item.icon} className="h-[18px] w-[18px]" /> {item.label}
                </a>
              ))}
            </nav>
          </aside>
        </div>
      )}

      <div className="lg:pl-[248px]">
        <header className="sticky top-0 z-30 border-b border-[#dce4dc]/80 bg-[#f4f6f1]/90 backdrop-blur-xl">
          <div className="mx-auto flex h-[72px] max-w-[1480px] items-center justify-between px-4 sm:px-7 lg:px-10">
            <button ref={menuButtonRef} className="rounded-xl border border-[#dce4dd] bg-white p-2.5 text-[#45574e] lg:hidden" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation">
              <Icon name="menu" />
            </button>
            <div className="hidden lg:block">
              <p className="text-xs font-medium text-[#89948d]">Workspace</p>
              <p className="text-sm font-bold text-[#294538]">My job search</p>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge status={apiStatus} />
              <button
                type="button"
                onClick={() => void refreshData()}
                className="flex h-9 w-9 items-center justify-center rounded-full border border-[#dce4dd] bg-white text-[#59685f] shadow-sm transition hover:bg-[#edf2ea]"
                aria-label="Refresh dashboard"
              >
                <Icon name="refresh" className="h-4 w-4" />
              </button>
              <div className="hidden h-9 w-9 items-center justify-center rounded-full bg-[#d4e6c3] text-xs font-extrabold text-[#315643] sm:flex">ME</div>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-[1480px] px-4 py-8 sm:px-7 lg:px-10 lg:py-10">
          <section id="overview" className="scroll-mt-24">
            <div className="mb-7">
              <p className="mb-2 text-sm font-semibold text-[#6e7b73]">Your next role is out there.</p>
              <h1 className="max-w-3xl text-4xl font-bold leading-[1.05] tracking-[-0.055em] text-[#163126] sm:text-5xl">
                Find the work that <span className="font-serif italic font-medium text-[#5f8c43]">fits you.</span>
              </h1>
            </div>

            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(300px,0.7fr)]">
              <form onSubmit={handleScan} className="relative overflow-hidden rounded-[26px] bg-[#17352d] p-5 text-white shadow-[0_18px_50px_rgba(23,53,45,0.16)] sm:p-7">
                <div className="pointer-events-none absolute -right-12 -top-20 h-64 w-64 rounded-full border-[46px] border-white/[0.035]" />
                <div className="relative">
                  <div className="mb-6 flex items-start justify-between gap-5">
                    <div>
                      <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#bde985]">New discovery</p>
                      <h2 className="mt-2 text-2xl font-bold tracking-[-0.035em]">Start a focused job scan</h2>
                      <p className="mt-1 max-w-xl text-sm leading-6 text-white/55">Search target boards, research companies, and index the best matches in one run.</p>
                    </div>
                    <div className="hidden h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-white/10 text-[#bde985] sm:flex">
                      <Icon name="spark" />
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block sm:col-span-2">
                      <span className="mb-1.5 block text-xs font-semibold text-white/65">Role or search query</span>
                      <input value={query} onChange={(event) => setQuery(event.target.value)} required className="h-12 w-full rounded-xl border border-white/10 bg-white/[0.08] px-4 text-sm text-white outline-none transition placeholder:text-white/30 focus:border-[#a7df5f] focus:bg-white/[0.11]" placeholder="e.g. AI engineer" />
                    </label>
                    <label className="block">
                      <span className="mb-1.5 block text-xs font-semibold text-white/65">Location</span>
                      <input value={location} onChange={(event) => setLocation(event.target.value)} className="h-12 w-full rounded-xl border border-white/10 bg-white/[0.08] px-4 text-sm text-white outline-none transition placeholder:text-white/30 focus:border-[#a7df5f] focus:bg-white/[0.11]" placeholder="Remote or city" />
                    </label>
                    <label className="block">
                      <span className="mb-1.5 block text-xs font-semibold text-white/65">Skills</span>
                      <input value={skills} onChange={(event) => setSkills(event.target.value)} className="h-12 w-full rounded-xl border border-white/10 bg-white/[0.08] px-4 text-sm text-white outline-none transition placeholder:text-white/30 focus:border-[#a7df5f] focus:bg-white/[0.11]" placeholder="Python, React, LLMs" />
                    </label>
                  </div>

                  <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-xs text-white/40">A full scan can take a few minutes.</p>
                    <button disabled={scanning || !query.trim()} className="inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-[#b8e879] px-5 text-sm font-extrabold text-[#18352c] transition hover:bg-[#c8f28f] disabled:cursor-not-allowed disabled:opacity-60">
                      {scanning ? <><Icon name="refresh" className="h-4 w-4 animate-spin" /> Scouting the web…</> : <>Start scouting <Icon name="arrow" className="h-4 w-4" /></>}
                    </button>
                  </div>

                  {scanError && <p role="alert" className="mt-4 rounded-xl border border-rose-300/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">{scanError}</p>}
                  {scanResult && (
                    <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-[#b8e879]/20 bg-[#b8e879]/10 px-4 py-3 text-sm text-[#e1f7c5]">
                      <span className="flex items-center gap-1.5 font-bold"><Icon name="check" className="h-4 w-4" /> Scan complete</span>
                      <span>{scanResult.jobs_found} found</span>
                      <span>{scanResult.new_jobs} new opportunities</span>
                    </div>
                  )}
                </div>
              </form>

              <div className="rounded-[26px] border border-[#dce4dc] bg-[#fbfcf9] p-5 sm:p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-[#7c8c82]">This week</p>
                    <h2 className="mt-1 text-xl font-bold tracking-[-0.03em] text-[#213a2f]">Trending skills</h2>
                  </div>
                  <span className="rounded-full bg-[#edf4e8] px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-[#63854a]">Live</span>
                </div>
                <div className="mt-5 space-y-3">
                  {tagsError ? (
                    <EmptyState>{tagsError}</EmptyState>
                  ) : tags.length > 0 ? tags.slice(0, 5).map((tag, index) => {
                    const maxCount = Math.max(...tags.map((item) => item.count), 1);
                    return (
                      <div key={tag.tag}>
                        <div className="mb-1.5 flex items-center justify-between text-sm">
                          <span className="font-semibold text-[#344d41]">{tag.tag}</span>
                          <span className="text-xs tabular-nums text-[#869188]">{tag.count}</span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-[#e8ede6]"><div className="h-full rounded-full bg-[#8cbd66] transition-all" style={{ width: `${Math.max(12, (tag.count / maxCount) * 100 - index * 2)}%` }} /></div>
                      </div>
                    );
                  }) : (
                    <EmptyState>{dataLoading ? "Reading skill signals…" : "Run a scan to reveal trending skills."}</EmptyState>
                  )}
                </div>
                {tags.length > 0 && <a href="#search" className="mt-6 flex items-center justify-between border-t border-[#e5eae4] pt-4 text-xs font-bold text-[#527446]">Use skills in AI search <Icon name="arrow" className="h-4 w-4" /></a>}
              </div>
            </div>
          </section>

          <section id="opportunities" className="mt-14 scroll-mt-24">
            <SectionHeading
              eyebrow="Fresh matches"
              title="Recent opportunities"
              action={<span className="text-sm font-semibold text-[#7b877f]">{jobTotal} saved</span>}
            />
            {jobsError && <p className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">{jobsError}</p>}
            <div className="grid gap-3 xl:grid-cols-2">
              {jobs.length > 0 ? jobs.slice(0, 6).map((job) => (
                <div key={job.id} className="group relative">
                  <JobCard job={job} />
                  <button type="button" onClick={() => prepareCoverLetter(job)} className="absolute bottom-3 right-16 z-10 rounded-lg bg-white px-2.5 py-1.5 text-[10px] font-bold text-[#487057] shadow-sm ring-1 ring-[#dce4dd] transition hover:bg-[#edf4e9] sm:bottom-2.5" aria-label={`Draft a cover letter for ${job.title}`}>Draft letter</button>
                </div>
              )) : (
                <div className="xl:col-span-2"><EmptyState>{jobsError ? "Recent opportunities are temporarily unavailable." : dataLoading ? "Loading recent opportunities…" : "No opportunities yet. Start your first scan above."}</EmptyState></div>
              )}
            </div>
          </section>

          <section id="search" className="mt-14 scroll-mt-24 rounded-[28px] border border-[#dce4dc] bg-[#fafbf8] p-5 sm:p-7">
            <SectionHeading eyebrow="Indexed intelligence" title="Search beyond job titles" />
            <p className="-mt-3 max-w-2xl text-sm leading-6 text-[#6f7b73]">Describe the work, team, or technology you want. Scout searches inside indexed job descriptions to find the closest matches.</p>
            <form onSubmit={handleSearch} className="mt-6 flex flex-col gap-3 sm:flex-row">
              <label className="relative flex-1">
                <span className="sr-only">Semantic job search</span>
                <Icon name="search" className="absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-[#849088]" />
                <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} required className="h-13 w-full rounded-xl border border-[#d9e1da] bg-white pl-12 pr-4 text-sm text-[#263a31] outline-none transition placeholder:text-[#9aa39d] focus:border-[#79a65c] focus:ring-3 focus:ring-[#8cbd66]/10" placeholder="e.g. Build LLM products with a small remote team" />
              </label>
              <button disabled={searching || !searchQuery.trim()} className="inline-flex h-13 items-center justify-center gap-2 rounded-xl bg-[#285640] px-6 text-sm font-bold text-white transition hover:bg-[#204936] disabled:opacity-60">
                {searching ? <Icon name="refresh" className="h-4 w-4 animate-spin" /> : <Icon name="spark" className="h-4 w-4" />}
                {searching ? "Searching…" : "Search with AI"}
              </button>
            </form>
            {searchError && <p role="alert" className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{searchError}</p>}
            {hasSearched && !searching && !searchError && (
              <div className="mt-6 grid gap-3 lg:grid-cols-2">
                {searchResults.length > 0 ? searchResults.map((result) => <SearchResultCard key={`${result.job_id}-${result.section}`} result={result} />) : <div className="lg:col-span-2"><EmptyState>No indexed matches found. Run a scan, then try a broader description.</EmptyState></div>}
              </div>
            )}
          </section>

          <section id="cover-letter" className="mt-14 scroll-mt-24 pb-12">
            <SectionHeading eyebrow="Application studio" title="Turn a match into a strong introduction" />
            <div className="grid overflow-hidden rounded-[28px] border border-[#dce4dc] bg-white lg:grid-cols-2">
              <form onSubmit={handleCoverLetter} className="border-b border-[#e0e6e0] p-5 sm:p-7 lg:border-b-0 lg:border-r">
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="block">
                    <span className="mb-1.5 block text-xs font-bold text-[#526159]">Job title</span>
                    <input value={letterTitle} onChange={(event) => setLetterTitle(event.target.value)} required className="h-11 w-full rounded-xl border border-[#d9e1da] bg-[#fbfcfa] px-3.5 text-sm outline-none focus:border-[#79a65c]" placeholder="Product engineer" />
                  </label>
                  <label className="block">
                    <span className="mb-1.5 block text-xs font-bold text-[#526159]">Company</span>
                    <input value={letterCompany} onChange={(event) => setLetterCompany(event.target.value)} required className="h-11 w-full rounded-xl border border-[#d9e1da] bg-[#fbfcfa] px-3.5 text-sm outline-none focus:border-[#79a65c]" placeholder="Acme" />
                  </label>
                  <label className="block sm:col-span-2">
                    <span className="mb-1.5 block text-xs font-bold text-[#526159]">Relevant skills</span>
                    <input value={letterSkills} onChange={(event) => setLetterSkills(event.target.value)} className="h-11 w-full rounded-xl border border-[#d9e1da] bg-[#fbfcfa] px-3.5 text-sm outline-none focus:border-[#79a65c]" placeholder="Python, product strategy, AI" />
                  </label>
                  <label className="block sm:col-span-2">
                    <span className="mb-1.5 block text-xs font-bold text-[#526159]">Job description <span className="font-normal text-[#9aa39d]">(optional)</span></span>
                    <textarea value={letterDescription} onChange={(event) => setLetterDescription(event.target.value)} rows={5} className="w-full resize-none rounded-xl border border-[#d9e1da] bg-[#fbfcfa] px-3.5 py-3 text-sm leading-6 outline-none focus:border-[#79a65c]" placeholder="Paste the parts of the role you care about most…" />
                  </label>
                </div>
                {letterError && <p role="alert" className="mt-4 rounded-xl bg-rose-50 px-4 py-3 text-sm text-rose-700">{letterError}</p>}
                <button disabled={letterLoading || !letterTitle.trim() || !letterCompany.trim()} className="mt-5 inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-[#285640] px-5 text-sm font-bold text-white transition hover:bg-[#204936] disabled:opacity-60">
                  {letterLoading ? <Icon name="refresh" className="h-4 w-4 animate-spin" /> : <Icon name="document" className="h-4 w-4" />}
                  {letterLoading ? "Writing your draft…" : "Generate cover letter"}
                </button>
              </form>

              <div className="relative min-h-[420px] bg-[#f8faf6] p-5 sm:p-7">
                <div className="mb-5 flex items-center justify-between border-b border-[#dfe6de] pb-4">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#7d8c82]">Draft preview</p>
                    <p className="mt-1 text-sm font-semibold text-[#385244]">Personal, clear, and ready to edit</p>
                  </div>
                  {letter && (
                    <div className="flex items-center gap-2">
                      <span aria-live="polite" className={`text-xs ${copyStatus === "error" ? "text-rose-600" : "text-[#66805f]"}`}>
                        {copyStatus === "copied" ? "Copied" : copyStatus === "error" ? "Copy failed" : ""}
                      </span>
                      <button type="button" onClick={() => void handleCopyLetter()} className="rounded-lg border border-[#d5ded6] bg-white px-3 py-1.5 text-xs font-bold text-[#52705f] hover:bg-[#edf3ea]">
                        {copyStatus === "copied" ? "Copy again" : "Copy"}
                      </button>
                    </div>
                  )}
                </div>
                {letter ? (
                  <div className="whitespace-pre-wrap font-serif text-[15px] leading-7 text-[#34453c]">{letter}</div>
                ) : (
                  <div className="flex min-h-72 flex-col items-center justify-center text-center">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#e9f2e3] text-[#5f8b47]"><Icon name="document" /></div>
                    <p className="mt-4 font-bold text-[#45594d]">Your draft will appear here</p>
                    <p className="mt-1 max-w-xs text-sm leading-6 text-[#879189]">Choose a job above or add the details to create a tailored starting point.</p>
                  </div>
                )}
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

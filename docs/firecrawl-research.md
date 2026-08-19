# Firecrawl Research: Web Scraping Job Boards

*Research compiled: August 2026*

---

## 1. What is Firecrawl?

Firecrawl is an open-source "context API" to search, scrape, and interact with the web at scale. It turns websites into clean, LLM-ready data (markdown, structured JSON, screenshots) with a single API call.

- **GitHub:** 165K+ stars — one of the top 100 repos on GitHub
- **Users:** 1.25M+ developers, 150K+ companies
- **Customers:** Apple, Shopify, Canva, Replit, DoorDash, Zapier, Alibaba
- **Backed by:** Y Combinator
- **SOC 2 Type 2** certified
- **Open source:** MIT license — self-hostable

**Core capabilities:**
- `/search` — Search the web and get full-page content for every result
- `/scrape` — Get clean markdown, HTML, screenshots, or structured JSON from any URL
- `/crawl` — Follow links from a starting URL and scrape entire sites/sections
- `/map` — Discover all URLs on a site
- `/interact` — Click, fill forms, navigate multi-step flows (browser automation)
- `/extract` — Pass a JSON schema and get structured data back
- `/agent` — Natural language prompt → structured data (preview)

> Source: https://firecrawl.dev, https://docs.firecrawl.dev

---

## 2. Scraping Job Boards (LinkedIn, Indeed, Glassdoor)

### The Reality

Firecrawl's own documentation and blog explicitly address this:

> "The same schema approach works on any page Firecrawl can render, but large aggregators put listings behind logins, heavy rate limits, and terms that restrict automated access. This guide targets company career pages and the ATS they link to, which are public and built to be crawled."
> — https://www.firecrawl.dev/blog/scrape-job-boards-firecrawl-openai

**Key insight:** Company career pages are just indexes. The real job data lives on third-party **Applicant Tracking Systems (ATS)** like Ashby, Greenhouse, and Lever. One extraction schema reads roles from any ATS with no per-site CSS selectors.

### Practical Approach

1. **Scrape company career pages** (public, not behind login)
2. **Follow links to ATS pages** (Greenhouse, Ashby, Lever, Workday)
3. **Use structured extraction** with a Pydantic schema for job title, location, URL, description
4. **Rank against a resume** using an LLM

### LinkedIn / Indeed / Glassdoor — Can Firecrawl Do It?

| Platform | Firecrawl Capability | Notes |
|---|---|---|
| **Company career pages** | ✅ Full support | Public pages, works great |
| **ATS pages (Greenhouse, Ashby, etc.)** | ✅ Full support | Same schema works across all |
| **LinkedIn job listings** | ⚠️ Limited | Behind login, heavy anti-bot, ToS restrictions |
| **Indeed** | ⚠️ Limited | Rate limits, anti-scraping measures |
| **Glassdoor** | ⚠️ Limited | Login walls, aggressive bot detection |

**Recommendation:** Focus Firecrawl on company career pages + ATS systems. For LinkedIn/Indeed/Glassdoor, consider official APIs, data partnerships, or specialized tools.

> Source: https://www.firecrawl.dev/blog/scrape-job-boards-firecrawl-openai

---

## 3. Python SDK Installation and Setup

### Install

```bash
pip install firecrawl-py
```

Current version: **4.34.0** (as of July 31, 2026)
Requires: Python 3.8+
License: MIT

### Basic Setup

```python
import os
from firecrawl import Firecrawl
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("FIRECRAWL_API_KEY")
if not api_key:
    raise ValueError("Set FIRECRAWL_API_KEY in your .env file")

app = Firecrawl(api_key=api_key)
```

### Keyless Mode (No API Key)

```python
from firecrawl import Firecrawl

# No API key needed — rate-limited per IP
app = Firecrawl()
result = app.scrape("https://example.com", formats=["markdown"])
```

### Environment Variable

You can set `FIRECRAWL_API_KEY` as an env var instead of passing it directly:

```bash
export FIRECRAWL_API_KEY="fc-YOUR_API_KEY"
```

> Source: https://docs.firecrawl.dev/sdks/python, https://pypi.org/project/firecrawl-py

---

## 4. Key Features

### Scrape (1 credit/page)

```python
result = app.scrape("https://company.com/careers", formats=["markdown", "html"])
print(result.markdown)
```

Returns: markdown, HTML, metadata, screenshots, structured JSON.

### Crawl (1 credit/page)

```python
job = app.crawl(
    url="https://company.com/careers",
    limit=100,
    scrape_options={"formats": ["markdown"]}
)
for doc in job.data:
    print(doc.metadata.source_url)
```

### Batch Scrape (1 credit/page)

```python
job = app.batch_scrape([
    "https://company1.com/careers",
    "https://company2.com/careers",
    "https://company3.com/careers"
], formats=["markdown"])
for doc in job.data:
    print(doc.metadata.source_url)
```

### Map (1 credit/page)

```python
result = app.map("https://company.com", search="careers")
print(result)
```

### Structured Extraction (extract endpoint)

```python
from pydantic import BaseModel
from typing import List, Optional

class Job(BaseModel):
    title: str
    location: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None

class JobBoard(BaseModel):
    jobs: List[Job]

result = app.scrape(
    "https://company.com/careers",
    formats=["markdown"],
    extract={"schema": JobBoard}
)
```

### Search (2 credits/10 results)

```python
results = app.search("python engineer jobs San Francisco", limit=5)
for result in results.web:
    print(result.title, result.url)
```

### Interact (2 credits/browser minute)

```python
result = app.scrape(
    "https://example.com",
    actions=[{"type": "click", "selector": "a[href='/jobs']"}]
)
```

### Async Support

```python
import asyncio
from firecrawl import AsyncFirecrawl

async def main():
    firecrawl = AsyncFirecrawl(api_key="fc-YOUR-API-KEY")
    doc = await firecrawl.scrape("https://example.com", formats=["markdown"])

asyncio.run(main())
```

> Source: https://docs.firecrawl.dev/sdks/python, https://github.com/firecrawl/firecrawl

---

## 5. Pricing and Limits

### Plan Tiers (as of August 2026)

| Plan | Price | Credits/mo | Concurrent Requests | Extra Credits |
|---|---|---|---|---|
| **Free** | $0 | 1,000 | 2 | — |
| **Hobby** | $16/mo | 5,000 | 5 | $9 per 1,500 |
| **Standard** | $83/mo | 100,000 | 50 | $47 per 35,000 |
| **Growth** | $333/mo | 500,000 | 100 | Contact sales |
| **Scale** | $599/mo | 1,000,000 | 150 | Contact sales |
| **Enterprise** | Custom | Custom | Custom | Dedicated SLA |

Annual billing saves ~17-19% on each tier.

### Credit Costs per Endpoint

| Endpoint | Credits |
|---|---|
| Scrape | 1/page |
| Crawl | 1/page |
| Map | 1/page |
| Search | 2/10 results |
| Interact | 2/browser minute |
| Monitor | 1/page/check |
| Agent (preview) | 5 free daily runs, then dynamic |

**Advanced features** (JSON format, Enhanced Mode, etc.) cost additional credits.

### Limits to Note

- **No credit rollover** on self-serve plans (Scale/Enterprise only)
- **Failed requests are NOT charged**
- **Job retention:** 24h (Hobby), 7 days (Standard), 30 days (Growth), configurable (Enterprise)
- **Per-minute caps:** ~100 RPM (Hobby), ~1,000 RPM (Standard), ~5,000 RPM (Growth)

> Source: https://www.firecrawl.dev/pricing, https://affinco.com/firecrawl-pricing/

---

## 6. Comparison to Other Scraping Tools

### Firecrawl vs BeautifulSoup + Requests

| Aspect | Firecrawl | BeautifulSoup + Requests |
|---|---|---|
| JavaScript rendering | ✅ Built-in | ❌ No |
| Anti-bot handling | ✅ Proxy rotation, smart waits | ❌ Manual |
| Output format | Markdown, JSON, structured | Raw HTML only |
| Maintenance | Low (managed) | High (you maintain everything) |
| Cost | Credit-based pricing | Free (but time is money) |
| Best for | AI pipelines, dynamic sites | Static HTML, simple parsing |

### Firecrawl vs Playwright

| Aspect | Firecrawl | Playwright |
|---|---|---|
| Setup | One API call | Browser installation + code |
| JavaScript rendering | ✅ Automatic | ✅ Full browser |
| Anti-bot | ✅ Built-in proxy rotation | ❌ Manual (stealth plugins) |
| Structured extraction | ✅ Schema-based | ❌ Manual CSS selectors |
| Browser control | ✅ Interact endpoint | ✅ Full programmatic control |
| Cost | Credits per page | Free (self-managed infra) |
| Best for | Data extraction pipelines | Full browser automation, testing |

### Firecrawl vs Selenium

| Aspect | Firecrawl | Selenium |
|---|---|---|
| Speed | Faster (managed infra) | Slower (legacy architecture) |
| JavaScript | ✅ Automatic | ✅ With WebDriver |
| Anti-bot | ✅ Built-in | ❌ Manual |
| Setup | pip install firecrawl-py | WebDriver + config |
| Maintenance | Low | High |
| Best for | Data extraction | Legacy enterprise QA, testing |

### When to Use What

| Scenario | Recommended Tool |
|---|---|
| Static HTML, simple parsing | `requests` + `selectolax` or BeautifulSoup |
| JS-rendered page, no anti-bot | Playwright |
| JS-rendered + anti-bot (Cloudflare) | Playwright + stealth plugins + residential proxies |
| Clean data for AI/LLM pipelines | **Firecrawl** |
| Full browser automation/workflows | Playwright or Firecrawl Interact |
| Legacy enterprise apps | Selenium |

> Source: https://zackproser.com/blog/best-web-scraping-api-2026, https://fuadaliyev.net/en/blog/python-web-scraping-playwright-vs-selenium-vs-beautifulsoup

---

## 7. FastAPI Integration

### Service Layer

```python
# services/job_scraper.py
import os
from firecrawl import Firecrawl
from pydantic import BaseModel
from typing import List, Optional

class Job(BaseModel):
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None

class JobBoard(BaseModel):
    jobs: List[Job]

class JobScraper:
    def __init__(self):
        self.app = Firecrawl(api_key=os.getenv("FIRECRAWL_API_KEY"))

    def scrape_career_page(self, url: str) -> List[Job]:
        result = self.app.scrape(
            url,
            formats=["markdown"],
            extract={"schema": JobBoard}
        )
        return result.extract.jobs if result.extract else []

    def search_jobs(self, query: str, limit: int = 10) -> List[dict]:
        results = self.app.search(query, limit=limit)
        return [{"title": r.title, "url": r.url} for r in results.web]
```

### FastAPI Endpoint

```python
# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from services.job_scraper import JobScraper, Job

app = FastAPI()
scraper = JobScraper()

class ScrapeRequest(BaseModel):
    url: str

class SearchRequest(BaseModel):
    query: str
    limit: int = 10

@app.post("/scrape-jobs", response_model=List[Job])
async def scrape_jobs(req: ScrapeRequest):
    try:
        jobs = scraper.scrape_career_page(req.url)
        return jobs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search-jobs")
async def search_jobs(req: SearchRequest):
    try:
        return scraper.search_jobs(req.query, req.limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Async Version

```python
# services/job_scraper_async.py
import asyncio
from firecrawl import AsyncFirecrawl

class AsyncJobScraper:
    def __init__(self):
        self.app = AsyncFirecrawl(api_key=os.getenv("FIRECRAWL_API_KEY"))

    async def scrape_batch(self, urls: List[str]) -> List[dict]:
        results = await asyncio.gather(
            *[self.app.scrape(url, formats=["markdown"]) for url in urls]
        )
        return results

    async def scrape_batch_optimized(self, urls: List[str]):
        job = await self.app.batch_scrape(urls, formats=["markdown"])
        return job
```

### Dependencies (requirements.txt)

```
firecrawl-py>=4.34.0
fastapi>=0.100.0
uvicorn>=0.23.0
python-dotenv>=1.0.0
```

> Source: https://docs.firecrawl.dev/sdks/python

---

## 8. Best Practices for Scraping Job Boards Without Getting Blocked

### 1. Target Public Career Pages + ATS Systems

Most companies route applications through ATS providers (Greenhouse, Ashby, Lever, Workday). These are:
- Public by design (they want candidates to apply)
- Structured consistently across companies
- Less likely to block automated access

### 2. Use Firecrawl's Built-in Anti-Bot Features

Firecrawl handles:
- **Proxy rotation** (residential and datacenter)
- **JavaScript rendering** (for SPAs like React/Next.js career pages)
- **Smart waits** (intelligently waits for content to load)
- **User-agent rotation**
- **TLS fingerprint management**

### 3. Rate Limiting and Throttling

- Respect the concurrency limits of your plan
- Add delays between requests when scraping manually
- Use batch scraping for multiple URLs
- Cache results to avoid re-scraping

### 4. Respect robots.txt

Firecrawl respects `robots.txt` rules for the `FirecrawlAgent` directive. Always check and honor robots.txt for your target sites.

### 5. Session Management

- Warm up sessions before heavy scraping
- Rotate sessions every 50-100 requests
- Use browser profiles for persistent sessions when needed

### 6. Request Headers

Firecrawl automatically manages headers, but if scraping manually:
- Rotate User-Agent strings (Chrome, Safari, Firefox, mobile variants)
- Include Accept-Language, Accept-Encoding headers
- Match geographic location to the target site's region

### 7. Retry Logic with Backoff

```python
import time

def scrape_with_retry(url, max_retries=3, base_delay=1):
    for attempt in range(max_retries):
        try:
            return app.scrape(url, formats=["markdown"])
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
```

### 8. Data Retention and Compliance

- Don't store scraped data longer than necessary
- Check the site's Terms of Service
- Scraping public job postings for analysis is generally low risk, but varies by jurisdiction
- Provide opt-out mechanisms if scraping someone else's platform
- Don't redistribute scraped content without attribution

### 9. Cost Optimization

- **Cache results** — avoid re-scraping the same pages
- **Skip JS rendering** when the page is static (saves credits)
- **Use the extract endpoint** with schemas to get structured data in one pass
- **Batch scrape** multiple URLs instead of sequential requests

### 10. Monitoring

- Log all scraping activity
- Track success/failure rates
- Monitor response times
- Set up alerts for blocked requests

> Sources: https://dataimpulse.com/blog/web-scraping-job-postings/, https://www.scrapingbee.com/blog/web-scraping-best-practices/, https://www.scraperapi.com/web-scraping/best-practices/

---

## Summary: Firecrawl for Job Board Scraping

| Question | Answer |
|---|---|
| **Can Firecrawl scrape LinkedIn/Indeed/Glassdoor?** | Limited — these platforms have aggressive anti-bot and login walls. Focus on company career pages + ATS systems instead. |
| **Best use case?** | Scraping public company career pages and ATS listings (Greenhouse, Ashby, Lever) with structured extraction. |
| **Cost for a job board project?** | Free tier (1K pages/mo) for testing. Standard plan ($83/mo, 100K pages) for production. |
| **Python integration difficulty?** | Low — `pip install firecrawl-py`, 10 lines of code. |
| **vs. building custom scrapers?** | Firecrawl saves significant maintenance time. No proxy management, no browser updates, no anti-bot headaches. |
| **Legal considerations?** | Public job postings are generally low risk. Check ToS for each target. Career pages and ATS listings are built to be indexed. |

---

*All sources cited inline. Last verified: August 2026.*

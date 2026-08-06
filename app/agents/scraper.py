import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.config import get_settings


@dataclass
class ScrapedJob:
    title: str
    url: str
    company: str
    location: str | None = None
    description: str | None = None
    salary: str | None = None
    source: str = "unknown"
    is_easy_apply: bool = False
    source_tags: list[str] = field(default_factory=list)


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

GLASSDOOR_SEARCH_PATTERNS = [
    "https://www.glassdoor.com/Job/jobs.htm",
    "https://www.glassdoor.com/Job/search",
]


class JobScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": _USER_AGENT,
            "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
            "Accept-Language": "en-US,en;q=0.5",
        }
        self.settings = get_settings()

    async def scrape_indeed(
        self, query: str, location: str = "", max_results: int = 25
    ) -> list[ScrapedJob]:
        jobs = []
        url = f"https://www.indeed.com/jobs?q={quote_plus(query)}&l={quote_plus(location)}"

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers=self.headers, timeout=30)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "lxml")
                    job_cards = soup.find_all("div", class_="job_seen_beacon")

                    for card in job_cards[:max_results]:
                        title_elem = card.find("h2", class_="jobTitle")
                        company_elem = card.find("span", class_="companyName")
                        location_elem = card.find("div", class_="companyLocation")
                        link_elem = card.find("a", id=re.compile(r"^job_"))

                        if title_elem and company_elem:
                            base = "https://www.indeed.com"
                            job_url = f"{base}{link_elem['href']}" if link_elem else ""
                            loc_text = location_elem.get_text(strip=True) if location_elem else None
                            jobs.append(
                                ScrapedJob(
                                    title=title_elem.get_text(strip=True),
                                    url=job_url,
                                    company=company_elem.get_text(strip=True),
                                    location=loc_text,
                                    source="indeed",
                                )
                            )
        except Exception:
            pass

        return jobs

    async def scrape_linkedin(
        self, query: str, location: str = "", max_results: int = 25
    ) -> list[ScrapedJob]:
        jobs = []
        url = (
            "https://www.linkedin.com/jobs/search"
            f"?keywords={quote_plus(query)}"
            f"&location={quote_plus(location)}"
        )

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.settings.headless_browser)
                context = await browser.new_context(
                    user_agent=self.headers["User-Agent"],
                    viewport={"width": 1920, "height": 1080},
                )
                page = await context.new_page()

                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_selector(".base-card", timeout=15000)

                cards = await page.query_selector_all(".base-card")

                for card in cards[:max_results]:
                    title_el = await card.query_selector("h3.base-search-card__title")
                    company_el = await card.query_selector("h4.base-search-card__subtitle")
                    location_el = await card.query_selector("span.job-search-card__location")
                    link_el = await card.query_selector("a.base-card__full-link")

                    if title_el and company_el:
                        title = (await title_el.inner_text()).strip()
                        company = (await company_el.inner_text()).strip()
                        loc = None
                        if location_el:
                            loc = (await location_el.inner_text()).strip()
                        href = ""
                        if link_el:
                            href = await link_el.get_attribute("href") or ""

                        jobs.append(
                            ScrapedJob(
                                title=title,
                                url=href,
                                company=company,
                                location=loc,
                                source="linkedin",
                            )
                        )

                await browser.close()
        except Exception:
            pass

        return jobs

    async def scrape_remote_ok(self, query: str, max_results: int = 25) -> list[ScrapedJob]:
        jobs = []
        url = f"https://remoteok.com/remote-{quote_plus(query)}-jobs"

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(url, headers=self.headers, timeout=30)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "lxml")
                    cards = soup.find_all("tr", class_="job")

                    for card in cards[:max_results]:
                        title_el = card.find("h2", class_="companyPosition")
                        company_el = card.find("span", class_="company")
                        location_el = card.find("span", class_="remote-location")
                        link_el = card.find("a", class_="job-link")
                        tags_el = card.find_all("span", class_="tag")

                        if title_el and company_el:
                            href = ""
                            if link_el:
                                href = "https://remoteok.com" + link_el.get("href", "")
                            tags = [t.get_text(strip=True).lower() for t in tags_el]
                            jobs.append(
                                ScrapedJob(
                                    title=title_el.get_text(strip=True),
                                    url=href,
                                    company=company_el.get_text(strip=True),
                                    location=(
                                        location_el.get_text(strip=True)
                                        if location_el
                                        else "Remote"
                                    ),
                                    source="remote_ok",
                                    source_tags=tags,
                                )
                            )
        except Exception:
            pass

        return jobs

    async def scrape_weworkremotely(self, query: str, max_results: int = 25) -> list[ScrapedJob]:
        jobs = []
        url = "https://weworkremotely.com/remote-jobs/search"

        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                params = {"term": query}
                response = await client.get(url, params=params, headers=self.headers, timeout=30)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "lxml")
                    cards = soup.find_all("li", class_="feature")

                    for card in cards[:max_results]:
                        title_el = card.find("span", class_="title")
                        company_el = card.find("span", class_="company")
                        link_el = card.find("a", href=True)
                        tag_els = card.find_all("span", class_="tag")

                        if title_el and company_el:
                            href = ""
                            if link_el:
                                href = link_el["href"]
                                if href.startswith("/"):
                                    href = "https://weworkremotely.com" + href
                            tags = [t.get_text(strip=True).lower() for t in tag_els]
                            jobs.append(
                                ScrapedJob(
                                    title=title_el.get_text(strip=True),
                                    url=href,
                                    company=company_el.get_text(strip=True),
                                    location="Remote",
                                    source="weworkremotely",
                                    source_tags=tags,
                                )
                            )
        except Exception:
            pass

        return jobs

    async def scrape_glassdoor(
        self, query: str, location: str = "", max_results: int = 25
    ) -> tuple[list[ScrapedJob], list[dict], list[dict]]:
        jobs: list[ScrapedJob] = []
        reviews: list[dict] = []
        salaries: list[dict] = []

        search_url = None
        params = {"sc.keyword": query}
        if location:
            params["locT"] = ""
            params["locKeyword"] = location

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.settings.headless_browser)
                context = await browser.new_context(
                    user_agent=self.headers["User-Agent"],
                    viewport={"width": 1920, "height": 1080},
                )
                page = await context.new_page()

                for pattern in GLASSDOOR_SEARCH_PATTERNS:
                    try:
                        resp = await page.goto(
                            pattern,
                            params=params,
                            wait_until="domcontentloaded",
                            timeout=15000,
                        )
                        if resp and resp.status == 200:
                            search_url = pattern
                            break
                    except Exception:
                        continue

                if not search_url:
                    await browser.close()
                    return jobs, reviews, salaries

                try:
                    await page.wait_for_selector("[data-test='jobListing']", timeout=10000)
                except Exception:
                    try:
                        await page.wait_for_selector(".job-card", timeout=5000)
                    except Exception:
                        await browser.close()
                        return jobs, reviews, salaries

                cards = await page.query_selector_all("[data-test='jobListing'], .job-card")

                company_urls: dict[str, str] = {}

                for card in cards[:max_results]:
                    title_el = await card.query_selector("[data-test='job-title'], .jobTitle")
                    company_el = await card.query_selector(
                        "[data-test='employer-short-name'], .employerShortName"
                    )
                    location_el = await card.query_selector(
                        "[data-test='emp-location'], .jobLocation"
                    )
                    salary_el = await card.query_selector("[data-test='detailSalary'], .salary")
                    link_el = await card.query_selector("a[href*='/job/']")

                    if title_el and company_el:
                        title = (await title_el.inner_text()).strip()
                        company = (await company_el.inner_text()).strip()
                        loc = None
                        if location_el:
                            loc = (await location_el.inner_text()).strip()
                        salary = None
                        if salary_el:
                            salary = (await salary_el.inner_text()).strip()
                        href = ""
                        if link_el:
                            href = await link_el.get_attribute("href") or ""
                            if href.startswith("/"):
                                href = "https://www.glassdoor.com" + href

                        jobs.append(
                            ScrapedJob(
                                title=title,
                                url=href,
                                company=company,
                                location=loc,
                                salary=salary,
                                source="glassdoor",
                            )
                        )

                        if company and href:
                            company_urls[company] = href

                for company_name, job_url in list(company_urls.items())[:5]:
                    try:
                        company_slug = re.search(
                            r"/job/[^/]+/?(?:salary\?)?.*?employer=(\d+)",
                            job_url,
                        )
                        if not company_slug:
                            continue

                        salary_page = await page.goto(
                            f"https://www.glassdoor.com/Salary/"
                            f"{quote_plus(company_name)}-Salaries-E",
                            wait_until="domcontentloaded",
                            timeout=10000,
                        )

                        if salary_page and salary_page.status == 200:
                            salary_cards = await page.query_selector_all(
                                ".salary-row, [data-test='salary-row']"
                            )
                            for sc in salary_cards[:3]:
                                role_el = await sc.query_selector(
                                    ".job-title, [data-test='job-title']"
                                )
                                min_el = await sc.query_selector(
                                    ".salary-min, [data-test='salary-min']"
                                )
                                max_el = await sc.query_selector(
                                    ".salary-max, [data-test='salary-max']"
                                )
                                if role_el and min_el and max_el:
                                    role = (await role_el.inner_text()).strip()
                                    s_min = (await min_el.inner_text()).strip()
                                    s_max = (await max_el.inner_text()).strip()
                                    salaries.append(
                                        {
                                            "company": company_name,
                                            "job_title": role,
                                            "salary_min": s_min,
                                            "salary_max": s_max,
                                            "source": "glassdoor",
                                        }
                                    )
                    except Exception:
                        pass

                for company_name in list(company_urls.keys())[:3]:
                    try:
                        review_url = (
                            "https://www.glassdoor.com/Reviews/"
                            f"{quote_plus(company_name)}-Reviews-E"
                        )
                        await page.goto(
                            review_url,
                            wait_until="domcontentloaded",
                            timeout=10000,
                        )
                        await page.wait_for_selector(
                            ".review-card, [data-test='ReviewCard']",
                            timeout=5000,
                        )
                        review_cards = await page.query_selector_all(
                            ".review-card, [data-test='ReviewCard']"
                        )
                        for rc in review_cards[:10]:
                            rating_el = await rc.query_selector(
                                ".rating, [data-test='reviewRating']"
                            )
                            pros_el = await rc.query_selector(".pros, [data-test='reviewPros']")
                            cons_el = await rc.query_selector(".cons, [data-test='reviewCons']")
                            job_title_el = await rc.query_selector(
                                ".job-title, [data-test='reviewJobTitle']"
                            )
                            status_el = await rc.query_selector(
                                ".employment-status, [data-test='reviewEmploymentStatus']"
                            )
                            date_el = await rc.query_selector(".date, [data-test='reviewDate']")

                            rating = 0
                            if rating_el:
                                rating_text = (await rating_el.inner_text()).strip()
                                try:
                                    rating = int(re.search(r"(\d)", rating_text).group(1))
                                except (AttributeError, ValueError):
                                    rating = 0

                            reviews.append(
                                {
                                    "company": company_name,
                                    "rating": rating,
                                    "pros": (
                                        (await pros_el.inner_text()).strip() if pros_el else None
                                    ),
                                    "cons": (
                                        (await cons_el.inner_text()).strip() if cons_el else None
                                    ),
                                    "job_title": (
                                        (await job_title_el.inner_text()).strip()
                                        if job_title_el
                                        else None
                                    ),
                                    "employment_status": (
                                        (await status_el.inner_text()).strip()
                                        if status_el
                                        else None
                                    ),
                                    "review_date": (
                                        (await date_el.inner_text()).strip() if date_el else None
                                    ),
                                    "source": "glassdoor",
                                }
                            )
                    except Exception:
                        pass

                await browser.close()
        except Exception:
            pass

        return jobs, reviews, salaries

    async def scrape_all(
        self, query: str, location: str = "", max_results: int = 25
    ) -> tuple[list[ScrapedJob], list[dict], list[dict]]:
        all_jobs: list[ScrapedJob] = []
        all_reviews: list[dict] = []
        all_salaries: list[dict] = []

        linkedin_jobs = await self.scrape_linkedin(query, location, max_results)
        all_jobs.extend(linkedin_jobs)

        indeed_jobs = await self.scrape_indeed(query, location, max_results)
        all_jobs.extend(indeed_jobs)

        remote_ok_jobs = await self.scrape_remote_ok(query, max_results)
        all_jobs.extend(remote_ok_jobs)

        wwr_jobs = await self.scrape_weworkremotely(query, max_results)
        all_jobs.extend(wwr_jobs)

        gd_jobs, gd_reviews, gd_salaries = await self.scrape_glassdoor(query, location, max_results)
        all_jobs.extend(gd_jobs)
        all_reviews.extend(gd_reviews)
        all_salaries.extend(gd_salaries)

        return all_jobs, all_reviews, all_salaries

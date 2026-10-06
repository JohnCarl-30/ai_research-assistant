"""Structured company facts from Wikidata: website, founding, size, HQ, GitHub.

Matching is the hard part. A name search for "Linear" returns a chipmaker
(Linear Technology), an Italian insurer and "Linear Labs", and none of them is
Linear the issue tracker. So an item is only accepted when:

- its official website (P856) is the company's domain, or
- no domain is known and exactly one company is named exactly that.

Anything else is reported as no match or as ambiguous, never guessed.
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Literal
from urllib.parse import quote, urlencode

from scout_mcp.github import _domain_root
from scout_mcp.sources.http import DAY, Fetcher

API = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"

# Instance-of classes that mark an item as a company.
COMPANY_CLASSES = [
    "Q4830453",  # business
    "Q783794",  # company
    "Q6881511",  # enterprise
    "Q891723",  # public company
    "Q1058914",  # software company
    "Q18388277",  # technology company
    "Q2085381",  # publisher
    "Q210167",  # video game developer
]

_LEGAL_SUFFIXES = re.compile(
    r"[,.]?\s+(inc|llc|ltd|limited|corp|corporation|co|gmbh|plc|s\.?a|ag|b\.?v)\.?$", re.I
)
_QID = re.compile(r"^Q\d+$")

Match = Literal["website", "name"]


@dataclass
class CompanyFacts:
    wikidata_id: str
    name: str
    description: str | None = None
    website: str | None = None
    founded: str | None = None
    employees: int | None = None
    employees_as_of: str | None = None
    headquarters: list[str] = field(default_factory=list)
    country: list[str] = field(default_factory=list)
    industry: list[str] = field(default_factory=list)
    parent: list[str] = field(default_factory=list)
    github: str | None = None
    ticker: list[str] = field(default_factory=list)
    match: Match = "website"

    @property
    def url(self) -> str:
        return f"https://www.wikidata.org/wiki/{self.wikidata_id}"

    def to_dict(self) -> dict:
        return {**asdict(self), "url": self.url}


@dataclass
class Lookup:
    facts: CompanyFacts | None = None
    ambiguous: list[str] = field(default_factory=list)  # candidate names, when ambiguous


def normalize_name(name: str) -> str:
    name = _LEGAL_SUFFIXES.sub("", name.strip())
    return re.sub(r"\s+", " ", name).casefold()


def website_variants(domain: str) -> list[str]:
    """P856 values are stored as written, so try the common spellings."""
    return [
        f"{scheme}://{www}{domain}{slash}"
        for scheme in ("https", "http")
        for www in ("", "www.")
        for slash in ("/", "")
    ]


async def _search(fetcher: Fetcher, query: str, limit: int = 8) -> list[str]:
    params = {
        "action": "query", "list": "search", "format": "json",
        "srsearch": query, "srlimit": limit, "srprop": "",
    }
    data = await fetcher.get_json(f"{API}?{urlencode(params)}", ttl=7 * DAY)
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]


def _facts_query(qids: list[str]) -> str:
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""
SELECT ?item ?itemLabel ?itemDescription ?website ?inception ?employees ?employeesDate
       ?hqLabel ?countryLabel ?industryLabel ?parentLabel ?github ?ticker WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item wdt:P856 ?website }}
  OPTIONAL {{ ?item wdt:P571 ?inception }}
  OPTIONAL {{ ?item p:P1128 ?st . ?st ps:P1128 ?employees .
             OPTIONAL {{ ?st pq:P585 ?employeesDate }} }}
  OPTIONAL {{ ?item wdt:P159 ?hq }}
  OPTIONAL {{ ?item wdt:P17 ?country }}
  OPTIONAL {{ ?item wdt:P452 ?industry }}
  OPTIONAL {{ ?item wdt:P749 ?parent }}
  OPTIONAL {{ ?item wdt:P2037 ?github }}
  OPTIONAL {{ ?item p:P414/pq:P249 ?ticker }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""


def parse_facts(sparql_json: dict) -> dict[str, CompanyFacts]:
    """Merge SPARQL rows (one per combination of multi-valued fields) into facts."""
    out: dict[str, CompanyFacts] = {}
    best_employees: dict[str, tuple[str, int]] = {}
    for row in sparql_json.get("results", {}).get("bindings", []):
        def v(name: str) -> str | None:
            return row.get(name, {}).get("value")

        qid = v("item").rsplit("/", 1)[-1]
        facts = out.setdefault(qid, CompanyFacts(wikidata_id=qid, name=v("itemLabel") or qid))
        facts.description = facts.description or v("itemDescription")
        facts.website = facts.website or v("website")
        facts.github = facts.github or v("github")
        if v("inception"):
            facts.founded = v("inception")[:4]
        for name, target in [
            ("hqLabel", facts.headquarters), ("countryLabel", facts.country),
            ("industryLabel", facts.industry), ("parentLabel", facts.parent),
            ("ticker", facts.ticker),
        ]:
            value = v(name)
            # Items without an English label come back as their bare Q-id.
            if value and not _QID.match(value) and value not in target:
                target.append(value)
        if v("employees"):
            dated = (v("employeesDate") or "", int(float(v("employees"))))
            if qid not in best_employees or dated > best_employees[qid]:
                best_employees[qid] = dated

    for qid, (date, count) in best_employees.items():
        out[qid].employees = count
        out[qid].employees_as_of = date[:10] or None
    return out


async def _facts(fetcher: Fetcher, qids: list[str]) -> dict[str, CompanyFacts]:
    if not qids:
        return {}
    data = await fetcher.get_json(
        f"{SPARQL}?format=json&query={quote(_facts_query(qids))}", ttl=7 * DAY
    )
    return parse_facts(data)


async def lookup(fetcher: Fetcher, company: str, domain: str | None) -> Lookup:
    if domain:
        statements = "|".join(f"P856={url}" for url in website_variants(domain))
        qids = await _search(fetcher, f"haswbstatement:{statements}", limit=3)
        facts = await _facts(fetcher, qids)
        for f in facts.values():
            if _domain_root(f.website) == domain:
                f.match = "website"
                if _QID.match(f.name):  # no English label
                    f.name = company
                return Lookup(facts=f)
        return Lookup()

    classes = "|".join(f"P31={c}" for c in COMPANY_CLASSES)
    qids = await _search(fetcher, f"{company} haswbstatement:P856 haswbstatement:{classes}")
    candidates = await _facts(fetcher, qids)
    exact = [f for f in candidates.values() if normalize_name(f.name) == normalize_name(company)]
    if len(exact) == 1:
        exact[0].match = "name"
        return Lookup(facts=exact[0])
    if len(exact) > 1:
        return Lookup(ambiguous=[f"{f.name} ({f.website})" for f in exact])
    return Lookup()

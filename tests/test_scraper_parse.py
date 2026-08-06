from bs4 import BeautifulSoup

LINKEDIN_FIXTURE = """
<html>
<body>
<div class="base-card">
  <h3 class="base-search-card__title">Senior Python Developer</h3>
  <h4 class="base-search-card__subtitle">Acme Corp</h4>
  <span class="job-search-card__location">San Francisco, CA</span>
  <a class="base-card__full-link" href="https://linkedin.com/jobs/view/123"></a>
</div>
<div class="base-card">
  <h3 class="base-search-card__title">Backend Engineer</h3>
  <h4 class="base-search-card__subtitle">TechStart</h4>
  <span class="job-search-card__location">Remote</span>
  <a class="base-card__full-link" href="https://linkedin.com/jobs/view/456"></a>
</div>
</body>
</html>
"""


def test_parse_linkedin_html():
    soup = BeautifulSoup(LINKEDIN_FIXTURE, "lxml")
    cards = soup.find_all("div", class_="base-card")
    assert len(cards) == 2

    first = cards[0]
    title = first.find("h3", class_="base-search-card__title").get_text(strip=True)
    company = first.find("h4", class_="base-search-card__subtitle").get_text(strip=True)
    location = first.find("span", class_="job-search-card__location").get_text(strip=True)
    link = first.find("a", class_="base-card__full-link")

    assert title == "Senior Python Developer"
    assert company == "Acme Corp"
    assert location == "San Francisco, CA"
    assert link["href"] == "https://linkedin.com/jobs/view/123"


def test_parse_linkedin_extracts_all_jobs():
    soup = BeautifulSoup(LINKEDIN_FIXTURE, "lxml")
    cards = soup.find_all("div", class_="base-card")

    titles = [c.find("h3").get_text(strip=True) for c in cards]
    assert titles == ["Senior Python Developer", "Backend Engineer"]


def test_parse_linkedin_empty():
    soup = BeautifulSoup("<html><body></body></html>", "lxml")
    cards = soup.find_all("div", class_="base-card")
    assert cards == []

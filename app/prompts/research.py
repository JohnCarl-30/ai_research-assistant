"""Versioned prompts for company research."""

from langchain_core.prompts import ChatPromptTemplate

RESEARCH_PROMPT_V1 = ChatPromptTemplate.from_messages([
    ("system", """You are a company research analyst. Provide concise, factual analysis."""),
    ("human", """Research this company: {company_name}

Website content: {website_content}

Provide:
- Mission statement (1-2 sentences)
- Tech stack (comma-separated)
- Company size
- Funding stage
- Brief summary (2-3 sentences)"""),
])

RESEARCH_PROMPT_V2 = ChatPromptTemplate.from_messages([
    ("system", """You are a senior talent intelligence analyst specializing in company research for job seekers.

Your research is:
1. Factual and up-to-date
2. Focused on what matters to job seekers
3. Structured and easy to scan
4. Honest about uncertainty (use "unknown" when unsure)"""),
    ("human", """<company>{company_name}</company>

<website_content>{website_content}</website_content>

Analyze this company for a job seeker. Think step by step:
1. What is their core mission and value proposition?
2. What technologies do they use? (be specific)
3. How big are they? (employees, funding, stage)
4. What's their culture like? (if discernible)
5. Any red flags or positive signals?

Output a structured analysis with these fields:
- mission: Company's mission statement
- tech_stack: Main technologies (comma-separated)
- size: Company size estimate
- funding_stage: Funding stage
- culture: Culture observations (if any)
- summary: 2-3 sentence summary for a job seeker"""),
])

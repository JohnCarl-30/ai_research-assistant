"""Versioned prompts for cover letter generation."""

from langchain_core.prompts import ChatPromptTemplate

COVER_LETTER_PROMPT_V1 = ChatPromptTemplate.from_messages([
    ("system", """You are a professional cover letter writer. Write a concise, compelling cover letter."""),
    ("human", """Write a cover letter for:

Job Title: {job_title}
Company: {company_name}
Job Description: {job_description}

My Skills: {skills_text}

Write a 3-4 paragraph cover letter. Be professional but personable."""),
])

COVER_LETTER_PROMPT_V2 = ChatPromptTemplate.from_messages([
    ("system", """You are an expert technical recruiter and cover letter writer.

Your cover letters are:
1. Concise (3-4 paragraphs max)
2. Tailored to the specific role
3. Highlight relevant skills with concrete examples
4. Show genuine enthusiasm for the company
5. Include a clear call to action

Never use placeholder text like [Your Name]. Write as if ready to send."""),
    ("human", """<job_posting>
Title: {job_title}
Company: {company_name}
Description: {job_description}
</job_posting>

<candidate_profile>
Skills: {skills_text}
</candidate_profile>

Write a compelling cover letter for this role. Think step by step about:
1. Which skills match the job requirements
2. What makes this candidate unique
3. How to show enthusiasm for this specific company

Then write the final cover letter."""),
])

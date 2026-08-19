"""Versioned prompts for job-candidate matching with Chain-of-Thought."""

from langchain_core.prompts import ChatPromptTemplate

MATCHING_PROMPT_V1 = ChatPromptTemplate.from_messages([
    ("system", """You are a technical recruiter. Analyze the match between a candidate and job."""),
    ("human", """Candidate skills: {candidate_skills}
Job requirements: {job_requirements}

Rate the match from 0-100 and list matched/missing skills."""),
])

MATCHING_PROMPT_V2 = ChatPromptTemplate.from_messages([
    ("system", """You are a senior technical recruiter with 10+ years of experience.

You provide honest, detailed match assessments. You:
1. Identify exact skill matches
2. Recognize transferable skills
3. Flag seniority mismatches
4. Consider both required AND nice-to-have skills
5. Give actionable advice

Output structured JSON with scores and reasoning."""),
    ("human", """<candidate_profile>
Skills: {candidate_skills}
</candidate_profile>

<job_posting>
Requirements: {job_requirements}
</job_posting>

Analyze this match step by step:

1. SKILL ANALYSIS:
   - Which required skills does the candidate have?
   - Which required skills are missing?
   - Which nice-to-have skills are present?

2. TRANSFERABLE SKILLS:
   - What adjacent experience might be relevant?

3. SENIORITY CHECK:
   - Does the candidate's level match the role?

4. GAP ANALYSIS:
   - What's the biggest skill gap?
   - How could it be addressed?

5. OVERALL ASSESSMENT:
   - Match score (0-100)
   - Top 3 strengths
   - Top 3 areas to improve
   - Recommendation (apply, upskill first, consider similar roles)

Output as JSON:
{
  "match_score": int,
  "matched_skills": [str],
  "missing_skills": [str],
  "transferable_skills": [str],
  "seniority_match": bool,
  "strengths": [str],
  "improvements": [str],
  "recommendation": str,
  "reasoning": str
}"""),
])

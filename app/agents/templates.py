from langchain_core.prompts import ChatPromptTemplate

COVER_LETTER_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a professional cover letter writer. "
            "Write concise, compelling cover letters that highlight "
            "relevant skills and show enthusiasm for the role. "
            "Do NOT use placeholder text like [Your Name] — "
            "write it as if ready to send.",
        ),
        (
            "human",
            "Write a cover letter for this job application.\n\n"
            "Job Title: {job_title}\n"
            "Company: {company_name}\n"
            "Job Description: {job_description}\n"
            "Requirements: {requirements}\n"
            "My Skills: {skills_text}\n\n"
            "Guidelines:\n"
            "1. Keep it concise (3-4 paragraphs)\n"
            "2. Address the hiring manager\n"
            "3. Highlight relevant skills that match the job\n"
            "4. Show enthusiasm for the role and company\n"
            "5. Include a call to action\n"
            "6. Use a professional but personable tone\n\n"
            "Write the cover letter:",
        ),
    ]
)

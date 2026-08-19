from app.rag.chunking import chunk_job


def test_overview_chunk_is_always_first():
    chunks = chunk_job(title="Senior Go Engineer", company="Acme")

    assert len(chunks) == 1
    assert chunks[0].section == "overview"
    assert chunks[0].index == 0
    assert "Senior Go Engineer at Acme" in chunks[0].text


def test_header_is_repeated_on_every_chunk():
    chunks = chunk_job(
        title="Backend Engineer",
        company="Globex",
        location="Remote",
        salary="$150k-$180k",
        description="We build payment rails.\n\nYou will own the ledger service.",
    )

    assert len(chunks) > 1
    for chunk in chunks:
        assert "Backend Engineer at Globex" in chunk.text
        assert "Location: Remote" in chunk.text
        assert "Salary: $150k-$180k" in chunk.text


def test_chunk_indices_are_sequential():
    chunks = chunk_job(
        title="Data Engineer",
        company="Initech",
        description="\n\n".join(f"Paragraph number {i} about pipelines." for i in range(40)),
        requirements="\n\n".join(f"Requirement {i}: SQL and Python." for i in range(40)),
    )

    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_sections_are_labelled():
    chunks = chunk_job(
        title="ML Engineer",
        company="Hooli",
        description="Train ranking models.",
        requirements="5+ years of PyTorch.",
    )

    sections = {c.section for c in chunks}
    assert sections == {"overview", "description", "requirements"}


def test_body_content_survives_chunking():
    body = "\n\n".join(f"Bullet {i} covering distinct topic {i}." for i in range(30))
    chunks = chunk_job(title="SRE", company="Acme", description=body)

    combined = " ".join(c.text for c in chunks)
    for i in range(30):
        assert f"distinct topic {i}" in combined


def test_oversized_paragraph_is_split_not_dropped():
    wall = " ".join(f"word{i}" for i in range(2000))
    chunks = chunk_job(title="Dev", company="Acme", description=wall)

    assert len(chunks) > 2
    body_chunks = [c for c in chunks if c.section == "description"]
    assert body_chunks
    # Every chunk stays near the budget rather than one giant chunk swallowing all.
    assert all(len(c.text) <= 1500 for c in body_chunks)


def test_empty_body_produces_only_overview():
    chunks = chunk_job(title="Dev", company="Acme", description="   \n\n  ", requirements=None)

    assert len(chunks) == 1
    assert chunks[0].section == "overview"


def test_missing_company_still_chunks():
    chunks = chunk_job(title="Contractor", description="Short-term React work.")

    assert chunks[0].text.startswith("Contractor")
    assert any("React" in c.text for c in chunks)

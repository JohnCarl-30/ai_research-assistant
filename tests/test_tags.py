from app.services.tags import extract_source_tags, extract_tags


def test_extract_tags_python():
    tags = extract_tags("We need a Python developer with Django experience")
    assert "python" in tags
    assert "django" in tags


def test_extract_tags_case_insensitive():
    tags = extract_tags("PYTHON and React developer")
    assert "python" in tags
    assert "react" in tags


def test_extract_tags_phrases_first():
    tags = extract_tags("Machine learning engineer with deep learning")
    assert "machine learning" in tags
    assert "deep learning" in tags
    assert "learning" not in tags


def test_extract_tags_empty():
    assert extract_tags("") == []
    assert extract_tags(None) == []


def test_extract_tags_no_matches():
    tags = extract_tags("Looking for a people person with soft skills")
    assert tags == []


def test_extract_tags_deduplication():
    tags = extract_tags("Python python PYTHON")
    assert tags.count("python") == 1


def test_extract_tags_multiple():
    tags = extract_tags("Full stack: React, Node.js, PostgreSQL, Docker, AWS")
    assert "react" in tags
    assert "node.js" in tags
    assert "postgresql" in tags
    assert "docker" in tags
    assert "aws" in tags


def test_extract_source_tags():
    tags = extract_source_tags(["Python", "React", "AWS"])
    assert tags == ["python", "react", "aws"]


def test_extract_source_tags_empty():
    assert extract_source_tags([]) == []
    assert extract_source_tags(None) == []


def test_extract_source_tags_strips_whitespace():
    tags = extract_source_tags(["  Python  ", " React "])
    assert tags == ["python", "react"]

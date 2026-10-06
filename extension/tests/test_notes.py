from scout_mcp.notes import Notebook, fts_query


def test_save_search_and_delete(tmp_path):
    nb = Notebook(tmp_path / "sub" / "notes.db")
    stripe = nb.save("Stripe tech stack", "Ruby monolith, moving parts to Java.",
                     url="https://stripe.com/blog", tags=["Stripe", " payments ", ""])
    nb.save("Linear culture", "Small team, high craft, remote.", tags=["linear"])

    assert stripe.tags == ["payments", "stripe"]
    hits = nb.search("ruby stack")
    assert [n.title for n, _ in hits] == ["Stripe tech stack"]
    assert "**" in hits[0][1]  # highlighted snippet

    assert [n.title for n in nb.recent(tag="linear")] == ["Linear culture"]
    assert [n.title for n in nb.recent()] == ["Linear culture", "Stripe tech stack"]

    assert nb.delete(stripe.id) is True
    assert nb.search("ruby") == []
    assert nb.delete(stripe.id) is False
    assert nb.get(stripe.id) is None


def test_fts_query_neutralises_operators():
    # Unquoted, these would be FTS5 syntax (column filters, NEAR, NOT) or errors.
    assert fts_query('title: NOT "x" NEAR(') == '"title" OR "NOT" OR "x" OR "NEAR"'
    assert fts_query("!!!") is None


def test_search_with_syntax_characters_does_not_raise(tmp_path):
    nb = Notebook(tmp_path / "notes.db")
    nb.save("C++ at Acme", "They use C++ and Rust.")
    assert [n.title for n, _ in nb.search('c++ "rust')] == ["C++ at Acme"]

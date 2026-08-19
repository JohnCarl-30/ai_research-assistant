import uuid

import pytest

from app.rag.matcher import _mentions, build_profile_query
from app.rag.qa import assemble_posting
from app.rag.retriever import RRF_K, reciprocal_rank_fusion, tokenize
from app.rag.vector_store import ScoredChunk, cosine_similarity


def make_chunk(content: str = "chunk", score: float = 0.0) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        job_title="Engineer",
        company_name="Acme",
        job_url="https://example.com/job",
        section="description",
        content=content,
        score=score,
    )


class TestCosineSimilarity:
    def test_identical_vectors_score_one(self):
        assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0

    def test_orthogonal_vectors_score_zero(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_opposite_vectors_score_negative_one(self):
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0

    def test_magnitude_does_not_matter(self):
        assert cosine_similarity([1.0, 1.0], [5.0, 5.0]) == pytest.approx(1.0)

    def test_zero_vector_is_safe(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_mismatched_lengths_are_safe(self):
        assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0

    def test_empty_is_safe(self):
        assert cosine_similarity([], []) == 0.0


class TestTokenize:
    def test_strips_stopwords(self):
        assert "the" not in tokenize("the engineer")

    def test_keeps_technical_punctuation(self):
        tokens = tokenize("C++ and C# and Node.js")
        assert "c++" in tokens
        assert "c#" in tokens
        assert "node.js" in tokens

    def test_lowercases(self):
        assert tokenize("PYTHON") == ["python"]

    def test_all_stopword_query_is_empty(self):
        assert tokenize("what are the jobs") == []


class TestReciprocalRankFusion:
    def test_chunk_in_both_arms_outranks_single_arm_leader(self):
        both = make_chunk("in both")
        dense_only = make_chunk("dense only")

        # dense_only leads the dense list; `both` is second there but first in sparse.
        fused = reciprocal_rank_fusion(
            dense=[dense_only, both],
            sparse=[both],
            limit=10,
        )

        assert fused[0].chunk.chunk_id == both.chunk_id

    def test_scores_use_rrf_formula(self):
        chunk = make_chunk()
        fused = reciprocal_rank_fusion(dense=[chunk], sparse=[chunk], limit=10)

        expected = 2.0 * (1.0 / (RRF_K + 1))
        assert fused[0].score == expected

    def test_records_rank_provenance(self):
        dense_only = make_chunk("dense")
        sparse_only = make_chunk("sparse")

        fused = reciprocal_rank_fusion(dense=[dense_only], sparse=[sparse_only], limit=10)
        by_id = {f.chunk.chunk_id: f for f in fused}

        assert by_id[dense_only.chunk_id].dense_rank == 0
        assert by_id[dense_only.chunk_id].sparse_rank is None
        assert by_id[sparse_only.chunk_id].sparse_rank == 0
        assert by_id[sparse_only.chunk_id].dense_rank is None

    def test_deduplicates_across_arms(self):
        chunk = make_chunk()
        fused = reciprocal_rank_fusion(dense=[chunk], sparse=[chunk], limit=10)
        assert len(fused) == 1

    def test_respects_limit(self):
        chunks = [make_chunk(f"c{i}") for i in range(10)]
        fused = reciprocal_rank_fusion(dense=chunks, sparse=[], limit=3)
        assert len(fused) == 3

    def test_results_are_sorted_descending(self):
        chunks = [make_chunk(f"c{i}") for i in range(5)]
        fused = reciprocal_rank_fusion(dense=chunks, sparse=chunks[:2], limit=10)
        scores = [f.score for f in fused]
        assert scores == sorted(scores, reverse=True)

    def test_empty_arms_yield_nothing(self):
        assert reciprocal_rank_fusion(dense=[], sparse=[], limit=5) == []


class TestSkillMentions:
    def test_matches_whole_token(self):
        assert _mentions("we use go and kubernetes", "go")

    def test_does_not_match_inside_another_word(self):
        assert not _mentions("we use django heavily", "go")

    def test_single_letter_skill_is_not_a_substring_match(self):
        assert not _mentions("experience with react", "r")
        assert _mentions("statistics in r and python", "r")

    def test_handles_regex_metacharacters(self):
        assert _mentions("strong c++ background", "c++")

    def test_multiword_skill(self):
        assert _mentions("applied machine learning at scale", "machine learning")


class FakeChunk:
    def __init__(self, content: str):
        self.content = content


class TestAssemblePosting:
    HEADER = "Senior Rust Engineer at Acme\nLocation: Remote"

    def test_header_appears_once(self):
        posting = assemble_posting(
            [
                FakeChunk(self.HEADER),
                FakeChunk(f"{self.HEADER}\n\nBuild the proxy."),
                FakeChunk(f"{self.HEADER}\n\nRequires Tokio."),
            ]
        )

        assert posting.count("Senior Rust Engineer at Acme") == 1

    def test_all_bodies_are_kept(self):
        posting = assemble_posting(
            [
                FakeChunk(self.HEADER),
                FakeChunk(f"{self.HEADER}\n\nBuild the proxy."),
                FakeChunk(f"{self.HEADER}\n\nRequires Tokio."),
            ]
        )

        assert "Build the proxy." in posting
        assert "Requires Tokio." in posting

    def test_identical_bodies_are_collapsed(self):
        posting = assemble_posting(
            [
                FakeChunk(self.HEADER),
                FakeChunk(f"{self.HEADER}\n\nSame text."),
                FakeChunk(f"{self.HEADER}\n\nSame text."),
            ]
        )

        assert posting.count("Same text.") == 1

    def test_overview_only_posting_is_just_the_header(self):
        assert assemble_posting([FakeChunk(self.HEADER)]) == self.HEADER

    def test_empty_input_is_safe(self):
        assert assemble_posting([]) == ""


class TestProfileQuery:
    def test_includes_every_skill(self):
        query = build_profile_query(["python", "fastapi"], role="backend engineer")
        assert "python" in query
        assert "fastapi" in query
        assert "backend engineer" in query

    def test_defaults_the_role(self):
        assert "software engineer" in build_profile_query(["rust"])

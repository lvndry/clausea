"""Policy corpus dimensions — retrieval model stays aligned with Clausea doc scope."""

from src.prompts.policy_understanding_prompts import (
    POLICY_CORPUS_DIMENSIONS,
    iter_policy_corpus_retrieval_queries,
)


def test_each_dimension_has_stable_id_and_query():
    ids: set[str] = set()
    for dim in POLICY_CORPUS_DIMENSIONS:
        assert dim.id, "dimension must have id"
        assert dim.id not in ids, f"duplicate dimension id: {dim.id}"
        ids.add(dim.id)
        assert dim.covers.strip(), f"{dim.id} should document what it covers"
        assert dim.queries, f"{dim.id} must have at least one retrieval query"
        for q in dim.queries:
            assert len(q) > 20, f"{dim.id} query should be substantive for embedding"


def test_iter_policy_corpus_retrieval_queries_matches_flatten():
    flat = iter_policy_corpus_retrieval_queries()
    expected = [q for d in POLICY_CORPUS_DIMENSIONS for q in d.queries]
    assert flat == expected
    assert len(flat) == sum(len(d.queries) for d in POLICY_CORPUS_DIMENSIONS)

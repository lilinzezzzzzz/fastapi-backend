from __future__ import annotations

import asyncio

from pkg.vectors.contracts import RetrievalMode, SearchHit
from pkg.vectors.post_retrieval import (
    CollapseConfig,
    DedupConfig,
    DedupKeepStrategy,
    PostRetrievalConfig,
    PostRetrievalPipeline,
    ScoreAggregation,
)


def _hit(
    *,
    hit_id: int,
    text: str,
    doc_id: int | None,
    score: float,
) -> SearchHit:
    metadata = {}
    if doc_id is not None:
        metadata["doc_id"] = doc_id
    return SearchHit(
        id=hit_id,
        text=text,
        metadata=metadata,
        payload={},
        retrieval_mode=RetrievalMode.HYBRID,
        relevance_score=score,
        raw_score=score,
    )


def test_post_retrieval_deduplicates_by_best_score():
    pipeline = PostRetrievalPipeline(
        config=PostRetrievalConfig(
            dedup=DedupConfig(
                enabled=True,
                key_fields=["text"],
                keep_strategy=DedupKeepStrategy.BEST_SCORE,
            ),
            collapse=CollapseConfig(enabled=False),
        )
    )

    result = asyncio.run(
        pipeline.run(
            hits=[
                _hit(hit_id=1, text="duplicate", doc_id=None, score=0.5),
                _hit(hit_id=2, text="duplicate", doc_id=None, score=0.9),
                _hit(hit_id=3, text="unique", doc_id=None, score=0.6),
            ]
        )
    )

    assert [hit.id for hit in result.hits] == [2, 3]
    assert result.stats.input_hit_count == 3
    assert result.stats.deduped_hit_count == 2


def test_post_retrieval_collapses_hits_to_documents():
    pipeline = PostRetrievalPipeline(
        config=PostRetrievalConfig(
            collapse=CollapseConfig(
                key_fields=["metadata.doc_id"],
                max_chunks_per_document=2,
                score_aggregation=ScoreAggregation.MAX,
            )
        )
    )

    result = asyncio.run(
        pipeline.run(
            hits=[
                _hit(hit_id=1, text="doc 10 chunk 1", doc_id=10, score=0.95),
                _hit(hit_id=2, text="doc 10 chunk 2", doc_id=10, score=0.80),
                _hit(hit_id=3, text="doc 10 chunk 3", doc_id=10, score=0.60),
                _hit(hit_id=4, text="doc 20 chunk 1", doc_id=20, score=0.90),
            ]
        )
    )

    assert [document.document_key for document in result.documents] == [10, 20]
    assert result.documents[0].primary_hit_id == 1
    assert result.documents[0].chunk_ids == [1, 2]
    assert result.documents[0].hit_count == 3
    assert result.documents[0].relevance_score == 0.95
    assert result.stats.document_count == 2


def test_post_retrieval_document_reranker_can_reorder_documents():
    async def rerank_documents(**kwargs):
        documents = list(kwargs["documents"])
        return list(reversed(documents))

    pipeline = PostRetrievalPipeline(
        config=PostRetrievalConfig(
            collapse=CollapseConfig(
                key_fields=["metadata.doc_id"],
            )
        ),
        document_reranker=rerank_documents,
    )

    result = asyncio.run(
        pipeline.run(
            hits=[
                _hit(hit_id=1, text="doc 10", doc_id=10, score=0.95),
                _hit(hit_id=2, text="doc 20", doc_id=20, score=0.90),
            ]
        )
    )

    assert [document.document_key for document in result.documents] == [20, 10]


def test_post_retrieval_falls_back_to_chunk_id_when_no_document_key():
    pipeline = PostRetrievalPipeline(
        config=PostRetrievalConfig(
            collapse=CollapseConfig(
                key_fields=["metadata.doc_id"],
                fallback_to_chunk_id=True,
            )
        )
    )

    result = asyncio.run(
        pipeline.run(
            hits=[
                _hit(hit_id=1, text="chunk a", doc_id=None, score=0.95),
                _hit(hit_id=2, text="chunk b", doc_id=None, score=0.90),
            ]
        )
    )

    assert [document.document_key for document in result.documents] == ["hit:1", "hit:2"]

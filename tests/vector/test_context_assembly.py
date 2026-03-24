from __future__ import annotations

from pkg.vectors.context_assembly import (
    ContextAssemblyConfig,
    ContextBudgetConfig,
    ContextWindowConfig,
    DocumentContextAssembler,
)
from pkg.vectors.contracts import RetrievalMode, SearchHit
from pkg.vectors.post_retrieval import CollapsedSearchHit


def _chunk(
    *,
    chunk_id: int,
    text: str,
    chunk_index: int | None,
    doc_id: int,
    section: str | None = None,
    page: int | None = None,
) -> SearchHit:
    metadata = {"doc_id": doc_id}
    if chunk_index is not None:
        metadata["chunk_index"] = chunk_index
    if section is not None:
        metadata["section"] = section
    if page is not None:
        metadata["page"] = page
    return SearchHit(
        id=chunk_id,
        text=text,
        metadata=metadata,
        payload={},
        retrieval_mode=RetrievalMode.HYBRID,
        relevance_score=0.9,
        raw_score=0.9,
    )


def _document(*, doc_id: int, chunks: list[SearchHit]) -> CollapsedSearchHit:
    return CollapsedSearchHit(
        document_key=doc_id,
        primary_hit_id=chunks[0].id,
        hit_count=len(chunks),
        chunk_ids=[chunk.id for chunk in chunks],
        text=chunks[0].text,
        metadata={"doc_id": doc_id, "title": "RAG Guide", "source": "/docs/rag.md"},
        payload={},
        retrieval_mode=RetrievalMode.HYBRID,
        relevance_score=0.95,
        raw_score=0.95,
        chunks=chunks,
    )


def test_context_assembly_orders_chunks_and_merges_adjacent_windows():
    assembler = DocumentContextAssembler()

    result = assembler.assemble(
        documents=[
            _document(
                doc_id=10,
                chunks=[
                    _chunk(chunk_id=102, text="Chunk two", chunk_index=2, doc_id=10),
                    _chunk(chunk_id=104, text="Chunk four", chunk_index=4, doc_id=10),
                    _chunk(chunk_id=101, text="Chunk one", chunk_index=1, doc_id=10),
                ],
            )
        ]
    )

    document = result.documents[0]

    assert len(document.windows) == 2
    assert document.windows[0].chunk_ids == [101, 102]
    assert document.windows[1].chunk_ids == [104]
    assert document.chunk_ids == [101, 102, 104]
    assert document.header == "[Document 1 | key=10 | title=RAG Guide | source=/docs/rag.md]"
    assert document.text.index("Chunk one") < document.text.index("Chunk two")
    assert document.text.index("Chunk two") < document.text.index("Chunk four")
    assert result.context_text == document.text


def test_context_assembly_can_emit_window_headers():
    assembler = DocumentContextAssembler(
        config=ContextAssemblyConfig(
            window=ContextWindowConfig(
                include_headers=True,
            )
        )
    )

    result = assembler.assemble(
        documents=[
            _document(
                doc_id=10,
                chunks=[
                    _chunk(chunk_id=101, text="Chunk one", chunk_index=1, doc_id=10, section="Intro", page=1),
                    _chunk(chunk_id=102, text="Chunk two", chunk_index=2, doc_id=10, section="Intro", page=1),
                ],
            )
        ]
    )

    window = result.documents[0].windows[0]

    assert window.header == "[Window 1 | chunks=101,102 | section=Intro | page=1]"
    assert window.text.startswith(window.header)


def test_context_assembly_respects_char_budget_and_marks_truncation():
    assembler = DocumentContextAssembler(
        config=ContextAssemblyConfig(
            budget=ContextBudgetConfig(max_total_chars=90),
        )
    )

    result = assembler.assemble(
        documents=[
            _document(
                doc_id=10,
                chunks=[
                    _chunk(
                        chunk_id=101,
                        text="A" * 120,
                        chunk_index=1,
                        doc_id=10,
                    )
                ],
            )
        ]
    )

    document = result.documents[0]

    assert len(result.context_text) <= 90
    assert document.truncated is True
    assert document.windows[0].truncated is True
    assert result.stats.truncated_document_count == 1
    assert result.stats.truncated_window_count == 1

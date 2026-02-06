"""Knowledge test page for testing retrieval before going live."""

from __future__ import annotations

import json
import time

import streamlit as st

from admin.components.auth import require_auth
from src.db.models import KnowledgeCategory
from src.db.repositories.businesses import BusinessRepository, KnowledgeItemRepository
from src.db.session import get_sync_session
from src.services.knowledge.chromadb_store import get_chromadb_store
from src.services.knowledge.embeddings import get_embedding_service

st.set_page_config(page_title="Knowledge Test | Vartalaap", page_icon="V", layout="wide")

# Default business fallback when DB is empty
BUSINESS_ID = "himalayan_kitchen"


def _select_business_id() -> str:
    """Render business selector and persist selected business in session state."""
    with get_sync_session() as session:
        business_repo = BusinessRepository(session)
        businesses = business_repo.list_all()

    business_ids = [b.id for b in businesses] or [BUSINESS_ID]
    current = st.session_state.get("selected_business_id", business_ids[0])
    if current not in business_ids:
        current = business_ids[0]

    selected = st.selectbox(
        "Business",
        business_ids,
        index=business_ids.index(current),
        key="knowledge_test_business_selector",
    )
    st.session_state.selected_business_id = selected
    return selected


@require_auth
def main() -> None:
    st.title("Knowledge Test")
    st.caption("Test knowledge retrieval before going live with voice calls")

    global BUSINESS_ID

    # Sidebar stats
    with st.sidebar:
        BUSINESS_ID = _select_business_id()
        st.caption(f"Testing: `{BUSINESS_ID}`")
        st.divider()

        st.subheader("Index Stats")
        _display_index_stats()

        st.divider()
        st.subheader("Actions")
        if st.button("Reindex All Items", type="primary"):
            _reindex_all()

        if st.button("Clear Index", type="secondary"):
            _clear_index()

    # Main content
    tab1, tab2, tab3 = st.tabs(["Test Queries", "Prompt Preview", "Batch Test"])

    with tab1:
        _test_queries_tab()

    with tab2:
        _prompt_preview_tab()

    with tab3:
        _batch_test_tab()


def _display_index_stats() -> None:
    """Display ChromaDB index statistics."""
    try:
        store = get_chromadb_store()
        stats = store.get_collection_stats(BUSINESS_ID)
        st.metric("Indexed Items", stats["count"])

        # Count by category in database
        with get_sync_session() as session:
            repo = KnowledgeItemRepository(session)
            for cat in KnowledgeCategory:
                items = repo.list_by_business(BUSINESS_ID, category=cat)
                st.write(f"- {cat.value}: {len(items)}")

    except Exception as e:
        st.error(f"Failed to get stats: {e}")


def _test_queries_tab() -> None:
    """Interactive query testing."""
    st.subheader("Test Query")

    # Sample queries for quick testing
    st.write("**Quick Test Queries:**")
    sample_queries = [
        "Momos kitne ke hain?",
        "What are your opening hours?",
        "Do you have vegetarian options?",
        "Can I book a table for 8 people?",
        "Aaj special kya hai?",
        "Delivery available hai?",
    ]

    col1, col2 = st.columns([2, 1])

    with col1:
        query = st.text_input(
            "Enter test query",
            placeholder="Momos kitne ke hain?",
            key="test_query",
        )

    with col2:
        # Quick query buttons
        for sample in sample_queries[:3]:
            if st.button(sample, key=f"sample_{sample}"):
                st.session_state.test_query = sample
                st.rerun()

    # Category filter
    category_filter = st.multiselect(
        "Filter by category",
        [cat.value for cat in KnowledgeCategory],
        default=[],
        help="Leave empty to search all categories",
    )

    # Number of results
    max_results = st.slider("Max results", min_value=1, max_value=20, value=5)

    # Minimum score
    min_score = st.slider(
        "Minimum similarity score",
        min_value=0.0,
        max_value=1.0,
        value=0.3,
        step=0.05,
        help="Items with lower scores will be filtered out",
    )

    if st.button("Search", type="primary") or query:
        if not query:
            st.warning("Please enter a query")
        else:
            _run_search(query, category_filter, max_results, min_score)


def _run_search(
    query: str,
    category_filter: list[str],
    max_results: int,
    min_score: float,
) -> None:
    """Run a search and display results."""
    st.divider()
    st.subheader("Results")

    start_time = time.perf_counter()

    try:
        store = get_chromadb_store()

        # Convert category filter
        categories = None
        if category_filter:
            categories = [KnowledgeCategory(c) for c in category_filter]

        results = store.search(
            BUSINESS_ID,
            query,
            max_results=max_results,
            categories=categories,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Display timing
        st.write(f"**Query:** {query}")
        st.write(f"**Time:** {elapsed_ms:.1f}ms")
        st.write(f"**Results:** {len(results)}")

        if not results:
            st.info("No results found. Try a different query or lower the minimum score.")
            return

        # Display results
        for i, result in enumerate(results, 1):
            score = result["score"]

            # Skip low scores
            if score < min_score:
                continue

            metadata = result.get("metadata", {})
            category = metadata.get("category", "unknown")
            title = metadata.get("title", "Untitled")

            # Score indicator
            if score >= 0.7:
                score_color = "green"
            elif score >= 0.5:
                score_color = "orange"
            else:
                score_color = "red"

            with st.expander(
                f"#{i} [{category}] {title} (score: {score:.3f})",
                expanded=i == 1,
            ):
                st.markdown(f"**Relevance Score:** :{score_color}[{score:.3f}]")
                st.write(f"**Document:** {result.get('document', 'N/A')}")
                st.write(f"**ID:** {result['id']}")

                # Show metadata
                st.write("**Metadata:**")
                st.json(metadata)

    except Exception as e:
        st.error(f"Search failed: {e}")


def _prompt_preview_tab() -> None:
    """Preview how knowledge appears in LLM prompt."""
    st.subheader("Prompt Preview")
    st.caption("See how retrieved knowledge will be injected into the LLM prompt")

    query = st.text_input(
        "Enter test query",
        placeholder="What momos do you have?",
        key="preview_query",
    )

    if st.button("Generate Preview", type="primary"):
        if not query:
            st.warning("Please enter a query")
        else:
            _generate_prompt_preview(query)


def _generate_prompt_preview(query: str) -> None:
    """Generate and display prompt preview."""
    try:
        store = get_chromadb_store()
        results = store.search(BUSINESS_ID, query, max_results=5)

        if not results:
            st.info("No results found for this query")
            return

        # Load full items from database for proper formatting
        with get_sync_session() as session:
            repo = KnowledgeItemRepository(session)

            # Build prompt section manually
            lines = ["## Relevant Information"]
            by_category: dict[str, list] = {}

            for result in results:
                if result["score"] < 0.3:
                    continue

                item = repo.get_by_id(result["id"])
                if not item:
                    continue

                cat = item.category.value
                by_category.setdefault(cat, []).append(item)

            # Format by category
            if "menu_item" in by_category:
                lines.append("\n### Menu Items")
                for item in by_category["menu_item"]:
                    metadata = {}
                    if item.metadata_json:
                        try:
                            metadata = json.loads(item.metadata_json)
                        except json.JSONDecodeError:
                            pass
                    price = metadata.get("price", "N/A")
                    veg = " (Veg)" if metadata.get("is_vegetarian") else ""
                    lines.append(f"- {item.title}{veg}: {item.content} - Rs.{price}")

            if "faq" in by_category:
                lines.append("\n### Frequently Asked Questions")
                for item in by_category["faq"]:
                    lines.append(f"Q: {item.title}\nA: {item.content}")

            if "policy" in by_category:
                lines.append("\n### Policies")
                for item in by_category["policy"]:
                    lines.append(f"Policy - {item.title}: {item.content}")

            if "announcement" in by_category:
                lines.append("\n### Current Announcements")
                for item in by_category["announcement"]:
                    lines.append(f"Note: {item.content}")

            prompt_section = "\n".join(lines)

            st.subheader("Prompt Injection Preview")
            st.code(prompt_section, language="markdown")

            # Show full system prompt context
            st.subheader("Full System Prompt Context")
            st.markdown("""
This section will be injected into the LLM system prompt, appearing after
the business context (hours, rules) and before the conversation guidelines.

The LLM will use this information to answer the user's query accurately.
            """)

    except Exception as e:
        st.error(f"Failed to generate preview: {e}")


def _batch_test_tab() -> None:
    """Batch testing with multiple queries."""
    st.subheader("Batch Test")
    st.caption("Test multiple queries at once to verify coverage")

    # Default test queries
    default_queries = """Momos kitne ke hain?
What are your opening hours?
Do you have vegetarian options?
Can I make a reservation?
Is delivery available?
What's your cancellation policy?
Menu mein kya kya hai?
Party booking ke liye kitne log allowed hain?
Aaj special kya hai?
Payment methods?"""

    queries_text = st.text_area(
        "Test queries (one per line)",
        value=default_queries,
        height=200,
    )

    if st.button("Run Batch Test", type="primary"):
        queries = [q.strip() for q in queries_text.split("\n") if q.strip()]
        _run_batch_test(queries)


def _run_batch_test(queries: list[str]) -> None:
    """Run batch test and display results."""
    st.divider()
    st.subheader("Batch Results")

    store = get_chromadb_store()
    results_data = []

    progress = st.progress(0)
    for i, query in enumerate(queries):
        try:
            start = time.perf_counter()
            results = store.search(BUSINESS_ID, query, max_results=3)
            elapsed = (time.perf_counter() - start) * 1000

            top_score = results[0]["score"] if results else 0
            top_title = results[0]["metadata"].get("title", "N/A") if results else "N/A"

            results_data.append({
                "Query": query,
                "Results": len(results),
                "Top Score": f"{top_score:.3f}",
                "Top Match": top_title,
                "Time (ms)": f"{elapsed:.1f}",
                "Status": "Pass" if top_score >= 0.4 else "Weak" if top_score >= 0.25 else "Miss",
            })

        except Exception as e:
            results_data.append({
                "Query": query,
                "Results": 0,
                "Top Score": "Error",
                "Top Match": str(e),
                "Time (ms)": "N/A",
                "Status": "Error",
            })

        progress.progress((i + 1) / len(queries))

    # Display as table
    import pandas as pd

    df = pd.DataFrame(results_data)

    # Color code status
    def highlight_status(val):
        if val == "Pass":
            return "background-color: #90EE90"
        elif val == "Weak":
            return "background-color: #FFE4B5"
        elif val == "Miss":
            return "background-color: #FFB6C1"
        elif val == "Error":
            return "background-color: #FF6B6B"
        return ""

    st.dataframe(
        df.style.applymap(highlight_status, subset=["Status"]),
        use_container_width=True,
    )

    # Summary stats
    passes = sum(1 for r in results_data if r["Status"] == "Pass")
    weak = sum(1 for r in results_data if r["Status"] == "Weak")
    misses = sum(1 for r in results_data if r["Status"] == "Miss")
    errors = sum(1 for r in results_data if r["Status"] == "Error")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Pass", passes, help="Score >= 0.4")
    col2.metric("Weak", weak, help="Score 0.25-0.4")
    col3.metric("Miss", misses, help="Score < 0.25")
    col4.metric("Error", errors)


def _reindex_all() -> None:
    """Reindex all knowledge items."""
    st.info("Reindexing all items...")

    try:
        store = get_chromadb_store()

        # Clear existing
        store.delete_collection(BUSINESS_ID)

        # Get all active items
        with get_sync_session() as session:
            repo = KnowledgeItemRepository(session)
            items = repo.list_by_business(BUSINESS_ID, active_only=True)

            progress = st.progress(0)
            indexed = 0

            for i, item in enumerate(items):
                try:
                    store.add_item(BUSINESS_ID, item)
                    indexed += 1
                except Exception as e:
                    st.warning(f"Failed to index {item.title}: {e}")

                progress.progress((i + 1) / len(items))

            st.success(f"Reindexed {indexed}/{len(items)} items")

    except Exception as e:
        st.error(f"Reindex failed: {e}")


def _clear_index() -> None:
    """Clear the ChromaDB index."""
    try:
        store = get_chromadb_store()
        store.delete_collection(BUSINESS_ID)
        st.success("Index cleared")
    except Exception as e:
        st.error(f"Failed to clear index: {e}")


if __name__ == "__main__":
    main()

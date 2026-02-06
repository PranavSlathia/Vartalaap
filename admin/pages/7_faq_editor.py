"""FAQ editor page for managing frequently asked questions."""

from __future__ import annotations

import json

import streamlit as st

from admin.components.auth import require_auth
from src.db.models import KnowledgeCategory, KnowledgeItem
from src.db.repositories.businesses import BusinessRepository, KnowledgeItemRepository
from src.db.session import get_sync_session
from src.services.knowledge.chromadb_store import get_chromadb_store

st.set_page_config(page_title="FAQ Editor | Vartalaap", page_icon="V", layout="wide")

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
        key="faq_editor_business_selector",
    )
    st.session_state.selected_business_id = selected
    return selected

# Common FAQ topics
FAQ_TOPICS = [
    "Hours & Location",
    "Reservations",
    "Menu & Dietary",
    "Delivery & Takeaway",
    "Payment",
    "Events & Parties",
    "Other",
]


def parse_metadata(item: KnowledgeItem) -> dict:
    """Parse metadata JSON from knowledge item."""
    if item.metadata_json:
        try:
            return json.loads(item.metadata_json)
        except json.JSONDecodeError:
            pass
    return {}


@require_auth
def main() -> None:
    st.title("FAQ Editor")
    st.caption("Manage frequently asked questions for knowledge-based retrieval")

    global BUSINESS_ID

    # Sidebar for topics filter
    with st.sidebar:
        BUSINESS_ID = _select_business_id()
        st.caption(f"Editing: `{BUSINESS_ID}`")
        st.divider()

        st.subheader("Topics")
        topics = ["All"] + FAQ_TOPICS
        selected_topic = st.radio("Filter by topic:", topics)

        st.divider()
        st.subheader("Quick Stats")
        _display_stats()

    # Main content
    tab1, tab2, tab3 = st.tabs(["FAQs", "Add New FAQ", "Policies & Announcements"])

    with tab1:
        _display_faqs(selected_topic)

    with tab2:
        _add_faq_form()

    with tab3:
        _manage_policies()


def _display_stats() -> None:
    """Display FAQ statistics in sidebar."""
    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)

        faqs = repo.list_by_business(BUSINESS_ID, category=KnowledgeCategory.faq)
        policies = repo.list_by_business(BUSINESS_ID, category=KnowledgeCategory.policy)
        announcements = repo.list_by_business(
            BUSINESS_ID, category=KnowledgeCategory.announcement
        )

        st.metric("FAQs", len(faqs))
        st.metric("Policies", len(policies))
        st.metric("Announcements", len(announcements))


def _display_faqs(topic_filter: str) -> None:
    """Display FAQs with edit/delete actions."""
    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        items = repo.list_by_business(
            BUSINESS_ID,
            category=KnowledgeCategory.faq,
            active_only=False,
        )

        # Filter by topic if specified
        if topic_filter != "All":
            items = [
                item for item in items
                if parse_metadata(item).get("topic", "").lower() == topic_filter.lower()
            ]

        if not items:
            st.info("No FAQs found. Add some using the 'Add New FAQ' tab.")
            return

        # Display as expandable cards
        for item in items:
            metadata = parse_metadata(item)
            topic = metadata.get("topic", "Other")
            active_indicator = "" if item.is_active else " (Inactive)"

            with st.expander(
                f"Q: {item.title}{active_indicator}",
                expanded=False,
            ):
                st.write(f"**Answer:** {item.content}")

                if item.content_hindi:
                    st.write(f"**Answer (Hindi):** {item.content_hindi}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Topic:** {topic}")
                with col2:
                    st.write(f"**Priority:** {item.priority}")
                with col3:
                    st.write(f"**Active:** {'Yes' if item.is_active else 'No'}")

                # Question variants for better retrieval
                variants = metadata.get("variants", [])
                if variants:
                    st.write("**Question Variants:**")
                    for v in variants:
                        st.write(f"  - {v}")

                st.divider()

                col_edit, col_delete = st.columns(2)
                with col_edit:
                    if st.button("Edit", key=f"edit_{item.id}"):
                        st.session_state.editing_faq = item.id
                        st.rerun()
                with col_delete:
                    if st.button("Delete", key=f"delete_{item.id}", type="secondary"):
                        _delete_item(item.id)

                # Edit form if this item is being edited
                if st.session_state.get("editing_faq") == item.id:
                    _edit_faq_form(item)


def _add_faq_form() -> None:
    """Form to add a new FAQ."""
    st.subheader("Add FAQ")

    with st.form("add_faq"):
        question = st.text_input(
            "Question *",
            placeholder="What are your opening hours?",
        )
        question_hindi = st.text_input(
            "Question (Hindi)",
            placeholder="आपके खुलने का समय क्या है?",
        )

        answer = st.text_area(
            "Answer *",
            placeholder="We are open Tuesday to Sunday, 11:00 AM to 10:30 PM. We are closed on Mondays.",
        )
        answer_hindi = st.text_area(
            "Answer (Hindi)",
            placeholder="हम मंगलवार से रविवार, सुबह 11:00 बजे से रात 10:30 बजे तक खुले हैं। सोमवार को बंद।",
        )

        col1, col2 = st.columns(2)
        with col1:
            topic = st.selectbox("Topic *", FAQ_TOPICS)
            is_active = st.checkbox("Active", value=True)
        with col2:
            priority = st.slider(
                "Priority",
                min_value=0,
                max_value=100,
                value=50,
                help="Higher priority FAQs are shown first",
            )

        variants = st.text_area(
            "Question Variants (one per line)",
            placeholder="When are you open?\nOpening times?\nकब खुलते हो?",
            help="Alternative ways users might ask this question",
        )

        submitted = st.form_submit_button("Add FAQ", type="primary")

        if submitted:
            if not question or not answer:
                st.error("Question and Answer are required")
            else:
                variant_list = [v.strip() for v in variants.split("\n") if v.strip()]
                _create_faq(
                    question=question,
                    question_hindi=question_hindi or None,
                    answer=answer,
                    answer_hindi=answer_hindi or None,
                    topic=topic,
                    priority=priority,
                    is_active=is_active,
                    variants=variant_list,
                )


def _edit_faq_form(item: KnowledgeItem) -> None:
    """Form to edit an existing FAQ."""
    st.subheader("Edit FAQ")
    metadata = parse_metadata(item)

    with st.form(f"edit_faq_{item.id}"):
        question = st.text_input("Question *", value=item.title)
        question_hindi = st.text_input(
            "Question (Hindi)",
            value=item.title_hindi or "",
        )

        answer = st.text_area("Answer *", value=item.content)
        answer_hindi = st.text_area(
            "Answer (Hindi)",
            value=item.content_hindi or "",
        )

        col1, col2 = st.columns(2)
        with col1:
            current_topic = metadata.get("topic", "Other")
            topic_index = FAQ_TOPICS.index(current_topic) if current_topic in FAQ_TOPICS else -1
            topic = st.selectbox(
                "Topic *",
                FAQ_TOPICS,
                index=topic_index if topic_index >= 0 else len(FAQ_TOPICS) - 1,
            )
            is_active = st.checkbox("Active", value=item.is_active)
        with col2:
            priority = st.slider(
                "Priority",
                min_value=0,
                max_value=100,
                value=item.priority,
            )

        variants = st.text_area(
            "Question Variants (one per line)",
            value="\n".join(metadata.get("variants", [])),
        )

        col_save, col_cancel = st.columns(2)
        with col_save:
            save = st.form_submit_button("Save Changes", type="primary")
        with col_cancel:
            cancel = st.form_submit_button("Cancel")

        if save:
            variant_list = [v.strip() for v in variants.split("\n") if v.strip()]
            _update_faq(
                item_id=item.id,
                question=question,
                question_hindi=question_hindi or None,
                answer=answer,
                answer_hindi=answer_hindi or None,
                topic=topic,
                priority=priority,
                is_active=is_active,
                variants=variant_list,
            )

        if cancel:
            st.session_state.pop("editing_faq", None)
            st.rerun()


def _manage_policies() -> None:
    """Manage policies and announcements."""
    st.subheader("Policies")

    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        policies = repo.list_by_business(
            BUSINESS_ID, category=KnowledgeCategory.policy, active_only=False
        )

        for policy in policies:
            with st.expander(f"Policy: {policy.title}", expanded=False):
                st.write(policy.content)
                if st.button("Delete", key=f"del_policy_{policy.id}"):
                    _delete_item(policy.id)

    # Add policy form
    with st.form("add_policy"):
        st.write("**Add New Policy**")
        policy_title = st.text_input("Policy Title", placeholder="Cancellation Policy")
        policy_content = st.text_area(
            "Policy Content",
            placeholder="Reservations can be cancelled up to 2 hours before the booking time...",
        )
        if st.form_submit_button("Add Policy"):
            if policy_title and policy_content:
                _create_policy(policy_title, policy_content)

    st.divider()
    st.subheader("Current Announcements")

    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        announcements = repo.list_by_business(
            BUSINESS_ID, category=KnowledgeCategory.announcement, active_only=False
        )

        for ann in announcements:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"**{ann.title}:** {ann.content}")
            with col2:
                if st.button("Remove", key=f"del_ann_{ann.id}"):
                    _delete_item(ann.id)

    # Add announcement form
    with st.form("add_announcement"):
        st.write("**Add New Announcement**")
        ann_title = st.text_input("Title", placeholder="Special Offer")
        ann_content = st.text_area(
            "Content",
            placeholder="20% off on all momos this week!",
        )
        if st.form_submit_button("Add Announcement"):
            if ann_title and ann_content:
                _create_announcement(ann_title, ann_content)


def _create_faq(
    question: str,
    answer: str,
    topic: str,
    priority: int,
    is_active: bool,
    question_hindi: str | None = None,
    answer_hindi: str | None = None,
    variants: list[str] | None = None,
) -> None:
    """Create a new FAQ and index it with transactional consistency."""
    metadata = {
        "topic": topic,
        "variants": variants or [],
    }

    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        item = repo.create(
            business_id=BUSINESS_ID,
            category=KnowledgeCategory.faq,
            title=question,
            title_hindi=question_hindi,
            content=answer,
            content_hindi=answer_hindi,
            metadata_json=json.dumps(metadata),
            is_active=is_active,
            priority=priority,
        )
        # Flush to get the ID, but don't commit yet
        session.flush()

        # Index in ChromaDB BEFORE committing DB
        if is_active:
            try:
                store = get_chromadb_store()
                store.add_item(BUSINESS_ID, item)
            except Exception as e:
                # Rollback DB if ChromaDB fails for consistency
                session.rollback()
                st.error(f"Failed to add FAQ: {e}")
                return

        # Commit only after ChromaDB succeeds
        session.commit()

        if is_active:
            st.success("Added FAQ and indexed for retrieval")
        else:
            st.success("Added FAQ (inactive, not indexed)")

        st.rerun()


def _update_faq(
    item_id: str,
    question: str,
    answer: str,
    topic: str,
    priority: int,
    is_active: bool,
    question_hindi: str | None = None,
    answer_hindi: str | None = None,
    variants: list[str] | None = None,
) -> None:
    """Update an existing FAQ and reindex with transactional consistency."""
    metadata = {
        "topic": topic,
        "variants": variants or [],
    }

    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        item = repo.update(
            item_id,
            title=question,
            title_hindi=question_hindi,
            content=answer,
            content_hindi=answer_hindi,
            metadata_json=json.dumps(metadata),
            is_active=is_active,
            priority=priority,
        )

        if not item:
            st.error("FAQ not found")
            return

        # Flush changes but don't commit yet
        session.flush()

        # Reindex in ChromaDB BEFORE committing
        store = get_chromadb_store()
        try:
            if is_active:
                store.add_item(BUSINESS_ID, item)
            else:
                store.remove_item(BUSINESS_ID, item_id)
        except Exception as e:
            # Rollback DB if ChromaDB fails for consistency
            session.rollback()
            st.error(f"Failed to update FAQ: {e}")
            return

        # Commit only after ChromaDB succeeds
        session.commit()

        if is_active:
            st.success("Updated FAQ and reindexed")
        else:
            st.success("Updated FAQ (inactive, removed from index)")

        st.session_state.pop("editing_faq", None)
        st.rerun()


def _create_policy(title: str, content: str) -> None:
    """Create a new policy with transactional consistency."""
    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        item = repo.create(
            business_id=BUSINESS_ID,
            category=KnowledgeCategory.policy,
            title=title,
            content=content,
            is_active=True,
            priority=70,  # Policies have higher priority
        )
        # Flush to get the ID, but don't commit yet
        session.flush()

        # Index in ChromaDB BEFORE committing
        try:
            store = get_chromadb_store()
            store.add_item(BUSINESS_ID, item)
        except Exception as e:
            session.rollback()
            st.error(f"Failed to add policy: {e}")
            return

        # Commit only after ChromaDB succeeds
        session.commit()
        st.success("Added policy and indexed")
        st.rerun()


def _create_announcement(title: str, content: str) -> None:
    """Create a new announcement with transactional consistency."""
    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        item = repo.create(
            business_id=BUSINESS_ID,
            category=KnowledgeCategory.announcement,
            title=title,
            content=content,
            is_active=True,
            priority=90,  # Announcements have highest priority
        )
        # Flush to get the ID, but don't commit yet
        session.flush()

        # Index in ChromaDB BEFORE committing
        try:
            store = get_chromadb_store()
            store.add_item(BUSINESS_ID, item)
        except Exception as e:
            session.rollback()
            st.error(f"Failed to add announcement: {e}")
            return

        # Commit only after ChromaDB succeeds
        session.commit()
        st.success("Added announcement and indexed")
        st.rerun()


def _delete_item(item_id: str) -> None:
    """Delete a knowledge item and remove from index."""
    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        if repo.delete(item_id):
            session.commit()

            try:
                store = get_chromadb_store()
                store.remove_item(BUSINESS_ID, item_id)
            except Exception:
                pass

            st.success("Item deleted")
            st.rerun()
        else:
            st.error("Failed to delete item")


if __name__ == "__main__":
    main()

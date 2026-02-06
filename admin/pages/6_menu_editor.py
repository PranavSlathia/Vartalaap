"""Menu editor page for managing menu items in the knowledge base."""

from __future__ import annotations

import csv
import io
import json

import streamlit as st

from admin.components.auth import require_auth
from src.db.models import KnowledgeCategory, KnowledgeItem
from src.db.repositories.businesses import BusinessRepository, KnowledgeItemRepository
from src.db.session import get_sync_session
from src.services.knowledge.chromadb_store import get_chromadb_store

st.set_page_config(page_title="Menu Editor | Vartalaap", page_icon="V", layout="wide")

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
        key="menu_editor_business_selector",
    )
    st.session_state.selected_business_id = selected
    return selected


def parse_metadata(item: KnowledgeItem) -> dict:
    """Parse metadata JSON from knowledge item."""
    if item.metadata_json:
        try:
            return json.loads(item.metadata_json)
        except json.JSONDecodeError:
            pass
    return {}


def format_price(metadata: dict) -> str:
    """Format price for display."""
    price = metadata.get("price")
    if price:
        return f"Rs.{price}"
    return "N/A"


@require_auth
def main() -> None:
    st.title("Menu Editor")
    st.caption("Manage menu items for knowledge-based retrieval during calls")

    global BUSINESS_ID

    # Sidebar for categories
    with st.sidebar:
        BUSINESS_ID = _select_business_id()
        st.caption(f"Editing: `{BUSINESS_ID}`")
        st.divider()

        st.subheader("Categories")
        categories = ["All", "Appetizers", "Momos", "Main Course", "Beverages", "Desserts"]
        selected_category = st.radio("Filter by category:", categories)

        st.divider()
        st.subheader("Bulk Import")
        uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
        if uploaded_file and st.button("Import CSV"):
            _import_csv(uploaded_file)

    # Main content
    tab1, tab2 = st.tabs(["Menu Items", "Add New Item"])

    with tab1:
        _display_menu_items(selected_category)

    with tab2:
        _add_item_form()


def _display_menu_items(category_filter: str) -> None:
    """Display menu items with edit/delete actions."""
    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        items = repo.list_by_business(
            BUSINESS_ID,
            category=KnowledgeCategory.menu_item,
            active_only=False,
        )

        # Filter by category if specified
        if category_filter != "All":
            items = [
                item for item in items
                if parse_metadata(item).get("category", "").lower() == category_filter.lower()
            ]

        if not items:
            st.info("No menu items found. Add some using the 'Add New Item' tab.")
            return

        # Display as cards in columns
        for item in items:
            metadata = parse_metadata(item)
            is_veg = metadata.get("is_vegetarian", False)

            with st.expander(
                f"{'🥬' if is_veg else '🍗'} {item.title} - {format_price(metadata)}",
                expanded=False,
            ):
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.write(f"**Description:** {item.content}")
                    if item.title_hindi:
                        st.write(f"**Hindi:** {item.title_hindi}")
                    st.write(f"**Category:** {metadata.get('category', 'N/A')}")
                    st.write(f"**Active:** {'Yes' if item.is_active else 'No'}")
                    st.write(f"**Priority:** {item.priority}")

                with col2:
                    if st.button("Edit", key=f"edit_{item.id}"):
                        st.session_state.editing_item = item.id
                        st.rerun()

                    if st.button("Delete", key=f"delete_{item.id}", type="secondary"):
                        _delete_item(item.id)

                # Edit form if this item is being edited
                if st.session_state.get("editing_item") == item.id:
                    _edit_item_form(item)


def _add_item_form() -> None:
    """Form to add a new menu item."""
    st.subheader("Add Menu Item")

    with st.form("add_menu_item"):
        col1, col2 = st.columns(2)

        with col1:
            title = st.text_input("Item Name *", placeholder="Veg Steam Momos")
            title_hindi = st.text_input("Name (Hindi)", placeholder="वेज स्टीम मोमोज")
            category = st.selectbox(
                "Category *",
                ["Appetizers", "Momos", "Main Course", "Beverages", "Desserts"],
            )
            price = st.number_input("Price (Rs.)", min_value=0, max_value=10000, value=0)

        with col2:
            content = st.text_area(
                "Description *",
                placeholder="Steamed vegetable dumplings served with spicy tomato chutney",
            )
            content_hindi = st.text_area(
                "Description (Hindi)",
                placeholder="मसालेदार टमाटर चटनी के साथ भाप में पकाए गए सब्जी मोमोज",
            )
            is_vegetarian = st.checkbox("Vegetarian", value=True)
            is_active = st.checkbox("Active", value=True)
            priority = st.slider("Priority", min_value=0, max_value=100, value=50)

        keywords = st.text_input(
            "Keywords (comma-separated)",
            placeholder="dumpling, steamed, veg",
            help="Additional keywords for better search retrieval",
        )

        submitted = st.form_submit_button("Add Item", type="primary")

        if submitted:
            if not title or not content:
                st.error("Name and Description are required")
            else:
                _create_item(
                    title=title,
                    title_hindi=title_hindi or None,
                    content=content,
                    content_hindi=content_hindi or None,
                    category=category,
                    price=price,
                    is_vegetarian=is_vegetarian,
                    is_active=is_active,
                    priority=priority,
                    keywords=keywords,
                )


def _edit_item_form(item: KnowledgeItem) -> None:
    """Form to edit an existing menu item."""
    st.subheader("Edit Item")
    metadata = parse_metadata(item)

    with st.form(f"edit_form_{item.id}"):
        col1, col2 = st.columns(2)

        with col1:
            title = st.text_input("Item Name *", value=item.title)
            title_hindi = st.text_input("Name (Hindi)", value=item.title_hindi or "")
            category = st.selectbox(
                "Category *",
                ["Appetizers", "Momos", "Main Course", "Beverages", "Desserts"],
                index=["Appetizers", "Momos", "Main Course", "Beverages", "Desserts"].index(
                    metadata.get("category", "Appetizers")
                ) if metadata.get("category") in ["Appetizers", "Momos", "Main Course", "Beverages", "Desserts"] else 0,
            )
            price = st.number_input(
                "Price (Rs.)",
                min_value=0,
                max_value=10000,
                value=int(metadata.get("price", 0)),
            )

        with col2:
            content = st.text_area("Description *", value=item.content)
            content_hindi = st.text_area(
                "Description (Hindi)",
                value=item.content_hindi or "",
            )
            is_vegetarian = st.checkbox(
                "Vegetarian",
                value=metadata.get("is_vegetarian", False),
            )
            is_active = st.checkbox("Active", value=item.is_active)
            priority = st.slider(
                "Priority",
                min_value=0,
                max_value=100,
                value=item.priority,
            )

        keywords = st.text_input(
            "Keywords (comma-separated)",
            value=",".join(metadata.get("keywords", [])),
        )

        col_save, col_cancel = st.columns(2)
        with col_save:
            save = st.form_submit_button("Save Changes", type="primary")
        with col_cancel:
            cancel = st.form_submit_button("Cancel")

        if save:
            _update_item(
                item_id=item.id,
                title=title,
                title_hindi=title_hindi or None,
                content=content,
                content_hindi=content_hindi or None,
                category=category,
                price=price,
                is_vegetarian=is_vegetarian,
                is_active=is_active,
                priority=priority,
                keywords=keywords,
            )

        if cancel:
            st.session_state.pop("editing_item", None)
            st.rerun()


def _create_item(
    title: str,
    content: str,
    category: str,
    price: int,
    is_vegetarian: bool,
    is_active: bool,
    priority: int,
    title_hindi: str | None = None,
    content_hindi: str | None = None,
    keywords: str = "",
) -> None:
    """Create a new menu item and index it with transactional consistency."""
    metadata = {
        "category": category,
        "price": price,
        "is_vegetarian": is_vegetarian,
        "keywords": [k.strip() for k in keywords.split(",") if k.strip()],
    }

    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        item = repo.create(
            business_id=BUSINESS_ID,
            category=KnowledgeCategory.menu_item,
            title=title,
            title_hindi=title_hindi,
            content=content,
            content_hindi=content_hindi,
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
                st.error(f"Failed to add '{title}': {e}")
                return

        # Commit only after ChromaDB succeeds
        session.commit()

        if is_active:
            st.success(f"Added '{title}' and indexed for retrieval")
        else:
            st.success(f"Added '{title}' (inactive, not indexed)")

        st.rerun()


def _update_item(
    item_id: str,
    title: str,
    content: str,
    category: str,
    price: int,
    is_vegetarian: bool,
    is_active: bool,
    priority: int,
    title_hindi: str | None = None,
    content_hindi: str | None = None,
    keywords: str = "",
) -> None:
    """Update an existing menu item and reindex with transactional consistency."""
    metadata = {
        "category": category,
        "price": price,
        "is_vegetarian": is_vegetarian,
        "keywords": [k.strip() for k in keywords.split(",") if k.strip()],
    }

    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        item = repo.update(
            item_id,
            title=title,
            title_hindi=title_hindi,
            content=content,
            content_hindi=content_hindi,
            metadata_json=json.dumps(metadata),
            is_active=is_active,
            priority=priority,
        )

        if not item:
            st.error("Item not found")
            return

        # Flush changes but don't commit yet
        session.flush()

        # Reindex in ChromaDB BEFORE committing
        store = get_chromadb_store()
        try:
            if is_active:
                store.add_item(BUSINESS_ID, item)
            else:
                # Remove from index if inactive
                store.remove_item(BUSINESS_ID, item_id)
        except Exception as e:
            # Rollback DB if ChromaDB fails for consistency
            session.rollback()
            st.error(f"Failed to update '{title}': {e}")
            return

        # Commit only after ChromaDB succeeds
        session.commit()

        if is_active:
            st.success(f"Updated '{title}' and reindexed")
        else:
            st.success(f"Updated '{title}' (inactive, removed from index)")

        st.session_state.pop("editing_item", None)
        st.rerun()


def _delete_item(item_id: str) -> None:
    """Delete a menu item and remove from index."""
    with get_sync_session() as session:
        repo = KnowledgeItemRepository(session)
        if repo.delete(item_id):
            session.commit()

            # Remove from ChromaDB
            try:
                store = get_chromadb_store()
                store.remove_item(BUSINESS_ID, item_id)
            except Exception:
                pass

            st.success("Item deleted")
            st.rerun()
        else:
            st.error("Failed to delete item")


def _import_csv(uploaded_file) -> None:
    """Import menu items from CSV with transactional consistency."""
    try:
        content = uploaded_file.getvalue().decode("utf-8")
        reader = csv.DictReader(io.StringIO(content))

        items_data = []
        for row in reader:
            metadata = {
                "category": row.get("category", ""),
                "price": int(row.get("price", 0)),
                "is_vegetarian": row.get("is_vegetarian", "").lower() == "true",
                "keywords": [k.strip() for k in row.get("keywords", "").split(",") if k.strip()],
            }

            items_data.append({
                "business_id": BUSINESS_ID,
                "category": KnowledgeCategory.menu_item,
                "title": row.get("name", ""),
                "title_hindi": row.get("name_hindi") or None,
                "content": row.get("description", ""),
                "content_hindi": row.get("description_hindi") or None,
                "metadata_json": json.dumps(metadata),
                "is_active": True,
                "priority": int(row.get("priority", 50)),
            })

        with get_sync_session() as session:
            repo = KnowledgeItemRepository(session)
            created = repo.bulk_create(items_data)
            # Flush to get IDs, but don't commit yet
            session.flush()

            # Index all items BEFORE committing
            store = get_chromadb_store()
            indexed = 0
            failed = 0
            for item in created:
                try:
                    store.add_item(BUSINESS_ID, item)
                    indexed += 1
                except Exception:
                    failed += 1

            # Only commit if at least some items were indexed
            if indexed > 0:
                session.commit()
                if failed > 0:
                    st.warning(f"Imported {len(created)} items, indexed {indexed} ({failed} failed)")
                else:
                    st.success(f"Imported {len(created)} items, indexed {indexed}")
                st.rerun()
            else:
                session.rollback()
                st.error("Import failed: could not index any items in ChromaDB")

    except Exception as e:
        st.error(f"Import failed: {e}")


if __name__ == "__main__":
    main()

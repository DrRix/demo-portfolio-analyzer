"""Ticker Search tab: search instruments and manage the selection."""

import pandas as pd
import streamlit as st

from core import session

from .search import search_tickers

COLUMNS = ["symbol", "name", "exchange", "type"]


def render() -> None:
    st.header("Ticker Search")

    left, right = st.columns([3, 2], gap="large")
    with left:
        _render_search()
    with right:
        _render_selection()


def _render_search() -> None:
    for msg, icon in st.session_state.pop("_ticker_search_toasts", []):
        st.toast(msg, icon=icon)

    with st.form("ticker_search_form", border=False):
        col_q, col_btn = st.columns([4, 1], vertical_alignment="bottom")
        query = col_q.text_input(
            "Search by company name or symbol. Use commas to seperate ",
            placeholder="e.g. Apple, MSFT, SPY",
            key="ticker_search_query",
        )
        col_btn.form_submit_button("Search", width="stretch")

    if st.session_state.get("_ticker_search_last_query") != query:
        st.session_state.pop("ticker_search_results", None)
        st.session_state["_ticker_search_last_query"] = query

    if not query.strip():
        st.info("Type a name or symbol and press **Search**.")
        return

    try:
        with st.spinner("Searching..."):
            results = search_tickers(query)
    except Exception:
        st.error("Search is unavailable right now. Please try again in a moment.")
        return

    if not results:
        st.warning(f"No results for **{query}**.")
        return

    df = pd.DataFrame(results, columns=COLUMNS)
    event = st.dataframe(
        df,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="multi-row",
        key="ticker_search_results",
        column_config={
            "symbol": "Symbol",
            "name": "Name",
            "exchange": "Exchange",
            "type": "Type",
        },
    )

    picked_rows = event.selection.rows
    col_add_sel, col_add_all = st.columns([1, 1])

    if col_add_sel.button(
        f"Add {len(picked_rows)} selected" if picked_rows else "Add selected",
        icon=":material/add:",
        disabled=not picked_rows,
        type="primary",
        width="stretch",
    ):
        added = [r for r in picked_rows if session.add_ticker(results[r])]
        skipped = len(picked_rows) - len(added)
        toasts = st.session_state.setdefault("_ticker_search_toasts", [])
        if added:
            toasts.append((f"Added {len(added)} ticker(s).", ":material/check_circle:"))
        if skipped:
            toasts.append((
                f"Skipped {skipped} (already selected or limit of "
                f"{session.MAX_TICKERS} reached).",
                ":material/info:",
            ))
        st.rerun()

    if col_add_all.button(
        f"Add all ({len(results)})",
        icon=":material/playlist_add:",
        disabled=not results,
        width="stretch",
    ):
        added = [i for i, r in enumerate(results) if session.add_ticker(r)]
        skipped = len(results) - len(added)
        toasts = st.session_state.setdefault("_ticker_search_toasts", [])
        if added:
            toasts.append((f"Added {len(added)} ticker(s).", ":material/check_circle:"))
        if skipped:
            toasts.append((
                f"Skipped {skipped} (already selected or limit of "
                f"{session.MAX_TICKERS} reached).",
                ":material/info:",
            ))
        st.rerun()


def _render_selection() -> None:
    selected = session.get_selected_tickers()
    st.subheader(f"My Selection ({len(selected)}/{session.MAX_TICKERS})")

    if not selected:
        st.caption("No tickers selected yet.")
        return

    for t in selected:
        col_info, col_rm = st.columns([5, 1], vertical_alignment="center")
        col_info.markdown(f"**{t['symbol']}** · {t['name']}  \n"
                          f":gray[{t['exchange']} · {t['type']}]")
        col_rm.button(
            "",
            icon=":material/close:",
            key=f"remove_{t['symbol']}",
            help=f"Remove {t['symbol']}",
            on_click=session.remove_ticker,
            args=(t["symbol"],),
        )

    st.button("Clear all", icon=":material/delete:", on_click=session.clear_tickers)

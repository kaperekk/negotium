"""
watchlist.py — bottom-of-page watchlist

Lets the user paste a Yahoo Finance link or raw ticker symbol. Each entry shows
the current price, the % change over the visible window, and a tiny sparkline.
The list persists per project in the project registry (``projects.json``).
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import plotly.graph_objects as go
import streamlit as st

import storage
from ticker_data import (
    get_all_time_high,
    get_next_earnings,
    get_recent_prices,
    get_ticker_currency,
    get_ticker_name,
)
from ui.colors import (
    ACCENT,
    AXIS_TICK_FONT_SIZE,
    HOVER_LABEL_SIZE,
    NEGATIVE,
    POSITIVE,
)


def _parse_symbol(raw: str) -> str | None:
    """Extract a ticker symbol from free text or a Yahoo Finance URL."""
    raw = (raw or "").strip()
    if not raw:
        return None
    if "yahoo" in raw.lower():
        m = re.search(r"/quote/([^/?#]+)", raw)
        if not m:
            return None
        sym = m.group(1)
    else:
        sym = raw.split()[0]
    sym = sym.upper().strip()
    return sym or None


_REMOVE_SVG = (
    '<svg width="10" height="10" viewBox="0 0 10 10" '
    'xmlns="http://www.w3.org/2000/svg" style="stroke:currentColor">'
    '<path d="M9 1L5 5M1 9L5 5M5 5L1 1M5 5L9 9" stroke-width="2" '
    'stroke-linecap="round"></path></svg>'
)


def _handle_wl_remove() -> None:
    """Process a ?wl_remove=SYM click (set by the inline-SVG remove control)."""
    sym = None
    try:
        qp = st.query_params
        val = qp.get("wl_remove")
        if val:
            sym = val[0] if isinstance(val, list) else val
    except Exception:
        pass
    if not sym:
        try:
            val = st.experimental_get_query_params().get("wl_remove")
            if val:
                sym = val[0] if isinstance(val, list) else val
        except Exception:
            pass
    if not sym:
        return
    storage.set_watchlist([s for s in storage.get_watchlist() if s != sym])
    try:
        st.query_params.clear()
    except Exception:
        try:
            st.experimental_set_query_params()
        except Exception:
            pass
    st.rerun()


def _watchlist_window_days() -> int:
    """Translate the global Range selector into a trailing-window day count."""
    cs = st.session_state.get("chart_start")
    ce = st.session_state.get("chart_end")
    if isinstance(cs, date) and isinstance(ce, date):
        span = (ce - cs).days
        return max(20, min(span, 3650))
    return 60


def _render_dnd_list(watch: list[str], T: dict[str, str]) -> None:
    """Render a drag-to-reorder list; on drop it navigates to ?wl_dnd=..."""
    rows = "".join(
        f'<div class="wl-item" draggable="true" data-sym="{s}">'
        f'<span class="g">⠿</span>&nbsp;{s}'
        f'&nbsp;<span style="color:{T["text_muted"]}">'
        f'{get_ticker_name(s)}</span></div>'
        for s in watch
    )
    html = f"""
    <style>
      #wl-dnd {{ display:flex; flex-direction:column; gap:6px; }}
      #wl-dnd .wl-item {{
        padding:8px 12px; background:{T['card_bg']};
        border:1px solid {T['border']}; border-radius:10px;
        cursor:grab; font-size:16px; color:{T['text']};
      }}
      #wl-dnd .wl-item:active {{ cursor:grabbing; }}
      #wl-dnd .wl-item .g {{ color:{T['text_muted']}; }}
    </style>
    <div id="wl-dnd">{rows}</div>
    <script>
    (function() {{
      var container = document.getElementById('wl-dnd');
      if (!container) return;
      var dragEl = null;
      function getAfter(y) {{
        var els = [].slice.call(container.querySelectorAll('.wl-item')).filter(function(e){{return e!==dragEl;}});
        var closest = {{offset:-Infinity, element:null}};
        els.forEach(function(el){{
          var box = el.getBoundingClientRect();
          var offset = y - box.top - box.height/2;
          if (offset < 0 && offset > closest.offset) {{ closest = {{offset:offset, element:el}}; }}
        }});
        return closest.element;
      }}
      [].slice.call(container.querySelectorAll('.wl-item')).forEach(function(el){{
        el.addEventListener('dragstart', function(){{ dragEl = el; setTimeout(function(){{el.style.opacity='0.4';}},0); }});
        el.addEventListener('dragend', function(){{ el.style.opacity='1'; applyOrder(); }});
        el.addEventListener('dragover', function(e){{
          e.preventDefault();
          var after = getAfter(e.clientY);
          if (after == null) container.appendChild(dragEl);
          else container.insertBefore(dragEl, after);
        }});
      }});
      function applyOrder() {{
        var order = [].slice.call(container.querySelectorAll('.wl-item')).map(function(e){{return e.dataset.sym;}});
        var u = new URL(window.location.href);
        u.searchParams.set('wl_dnd', order.join(','));
        window.location.search = u.search;
      }}
    }})();
    </script>
    """
    st.html(html, unsafe_allow_javascript=True)


def _prefetch_watchlist_data(watch: list[str], days: int, max_workers: int = 5) -> None:
    """Warm the network-backed watchlist caches in parallel.

    The watchlist renderer fetches several Yahoo resources per symbol (name,
    recent prices, trading currency, ATH, next earnings) — on a cold visit that
    can mean dozens of serial HTTP round-trips. Fetching them concurrently
    collapses wall-clock time from O(n·rt) to O(ceil(n/max_workers)·rt).
    ``st.cache_data`` for the per-card dict is intentionally not used here
    (it's session/thread aware); instead we warm the underlying module-level
    TTL caches that every renderer already consults.
    """
    if not watch:
        return

    def _warm_one(sym: str) -> None:
        try:
            get_ticker_name(sym)
            get_recent_prices(sym, days=max(days, 504))
            get_ticker_currency(sym)
            get_all_time_high(sym)
            get_next_earnings(sym)
        except Exception:
            pass  # each card still falls back to graceful "No data" rendering

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_warm_one, sym) for sym in watch]
        for _ in as_completed(futures):
            pass  # fill caches; errors are swallowed above


def render_watchlist(T: dict[str, str]) -> None:
    _handle_wl_remove()
    watch = list(storage.get_watchlist())

    # Apply a pending reorder passed via ?wl_dnd= and clear it.
    dnd = st.query_params.get("wl_dnd")
    if dnd:
        raw = dnd[0] if isinstance(dnd, list) else dnd
        wanted = [s for s in str(raw).split(",") if s]
        new_order = [s for s in wanted if s in watch] + [s for s in watch if s not in wanted]
        if new_order != watch:
            storage.set_watchlist(new_order)
        try:
            del st.query_params["wl_dnd"]
        except Exception:
            try:
                st.query_params.clear()
            except Exception:
                pass
        st.rerun()

    st.subheader("🔎  Watchlist")

    with st.form("watchlist_add", clear_on_submit=True):
        link = st.text_input(
            "Add ticker",
            placeholder="AAPL or https://finance.yahoo.com/quote/AAPL/",
            label_visibility="collapsed",
        )
        if st.form_submit_button("Add", width='content') and link:
            sym = _parse_symbol(link)
            if sym:
                if sym not in watch:
                    watch.append(sym)
                    storage.set_watchlist(watch)
                st.rerun()

    if not watch:
        st.caption("No tickers yet — paste a Yahoo link or symbol above.")
        return

    wl_days = _watchlist_window_days()

    # Warm Yahoo-derived caches concurrently so the cards below render without
    # sitting through a serial HTTP round-trip per symbol.
    _prefetch_watchlist_data(watch, wl_days)

    cols = st.columns(min(len(watch), 2))
    for i, sym in enumerate(watch):
        with cols[i % len(cols)]:
            with st.container(border=True):
                _render_card(T, sym, wl_days)

    with st.expander("↕  Reorder — drag to move", expanded=False):
        st.caption("Hold and drag a ticker to change its position.")
        _render_dnd_list(watch, T)


@st.cache_data(ttl=900, show_spinner=False)
def _watchlist_card_data(sym: str, days: int) -> dict:
    """Fetch and compose all watchlist card data once; cached per (ticker, range)."""
    name = get_ticker_name(sym)
    try:
        # Single fetch of the longest window we display — derive everything else
        # from this one series (avoids 5 separate ensure/download calls).
        recent_all, latest, _ = get_recent_prices(sym, days=max(days, 504))
    except Exception:
        recent_all, latest = {}, None

    # Slice the sparkline window down to the chart range used for this card.
    if recent_all:
        sorted_dates = sorted(recent_all)
        recent = {d: recent_all[d] for d in sorted_dates[-days:]}
    else:
        recent = {}

    ccy = get_ticker_currency(sym)
    ath, ath_date = get_all_time_high(sym)
    earn = get_next_earnings(sym)

    period_changes: dict[str, float | None] = {}
    if latest is not None and recent_all:
        sorted_all = sorted(recent_all)
        for lbl, d in (("1M", 21), ("6M", 126), ("1Y", 252), ("2Y", 504)):
            if len(sorted_all) < 2:
                period_changes[lbl] = None
                continue
            # The window start price is the value ≍d trading days before latest.
            idx = -min(d - 1, len(sorted_all) - 1) - 1
            pprev = recent_all[sorted_all[idx]]
            period_changes[lbl] = (latest / pprev - 1.0) * 100.0 if pprev else 0.0
    else:
        period_changes = {lbl: None for lbl, _ in (("1M", 21), ("6M", 126), ("1Y", 252), ("2Y", 504))}

    return {
        "name": name, "recent": recent, "latest": latest, "ccy": ccy,
        "ath": ath, "ath_date": ath_date, "earn": earn,
        "period_changes": period_changes,
    }


def _render_card(T: dict[str, str], sym: str, days: int = 60) -> None:
    data = _watchlist_card_data(sym, days)
    name = data["name"]
    recent = data["recent"]
    latest = data["latest"]
    ccy = data["ccy"]
    ath, ath_date = data["ath"], data["ath_date"]
    earn = data["earn"]
    period_changes = data["period_changes"]

    # Header row: ticker/name on the left, tiny SVG "X" remove control top-right
    head = st.columns([0.86, 0.14])
    with head[0]:
        st.markdown(
            f"<div style='font-size:2rem;font-weight:700;line-height:1.1'>{sym}</div>"
            f"<div style='font-size:1rem;color:{T['text_muted']};line-height:1.2'>"
            f"{name}</div>",
            unsafe_allow_html=True,
        )
    with head[1]:
        st.markdown(
            f'<a href="?wl_remove={sym}" title="Remove {sym}" '
            f'style="display:inline-flex;justify-content:flex-end;width:100%;'
            f'color:#8b949e;opacity:0.65;text-decoration:none;" '
            f'onmouseover="this.style.color=\'#ef4444\';this.style.opacity=1;" '
            f'onmouseout="this.style.color=\'#8b949e\';this.style.opacity=0.65;">'
            f'{_REMOVE_SVG}</a>',
            unsafe_allow_html=True,
        )

    if latest is None or not recent:
        st.error("No data", icon="⚠️")
        return

    price_col, drop_col = st.columns([0.5, 0.5])
    with price_col:
        st.markdown(
            f"<div style='font-size:1.35rem;font-weight:700;line-height:1.2'>"
            f"<span style='font-size:0.78rem;font-weight:600;color:{T['text_muted']};"
            f"text-transform:uppercase;letter-spacing:0.03em'> Trading Price: </span>"
            f"{latest:,.2f} "
            f"<span style='font-size:0.78rem;font-weight:600;color:{T['text_muted']}'>"
            f"{ccy}</span></div>",
            unsafe_allow_html=True,
        )
    with drop_col:
        if ath is None:
            st.error("No data", icon="⚠️")
        else:
            dist = (latest / ath - 1.0) * 100.0
            color = POSITIVE if dist >= 0 else NEGATIVE
            st.markdown(
                f"<div style='font-size:1.35rem;font-weight:700;line-height:1.2'>"
                f"<span style='font-size:0.78rem;font-weight:600;color:{T['text_muted']};"
                f"text-transform:uppercase;letter-spacing:0.03em'>Drop from ATH: </span>"
                f"<span style='color:{color}'>{dist:+.1f}%</span></div>",
                unsafe_allow_html=True,
            )

    periods = [("1M", 21), ("6M", 126), ("1Y", 252), ("2Y", 504)]
    head_cells = "".join(
        f"<td style='padding:2px 4px;color:{T['text_muted']};"
        f"font-size:0.72rem;font-weight:600'>{lbl}</td>"
        for lbl, _ in periods
    )
    body_cells = ""
    for lbl, _ in periods:
        pchg = period_changes.get(lbl)
        if pchg is None:
            body_cells += (
                f"<td style='padding:2px 4px;color:{T['text_muted']};"
                f"font-size:0.9rem;font-weight:600'>—</td>"
            )
            continue
        pcolor = POSITIVE if pchg >= 0 else NEGATIVE
        body_cells += (
            f"<td style='padding:2px 4px;color:{pcolor};"
            f"font-size:0.9rem;font-weight:600'>{pchg:+.1f}%</td>"
        )
    st.markdown(
        f"<table style='width:100%;border-collapse:collapse;margin-top:6px'>"
        f"<tr>{head_cells}</tr>"
        f"<tr>{body_cells}</tr>"
        f"</table>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"<div style='color:{T['text_muted']};font-size:0.85rem;margin-top:2px'>"
        f"Next earnings: {earn or '—'}</div>",
        unsafe_allow_html=True,
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(recent.keys()), y=list(recent.values()),
        mode="lines", showlegend=False,
        line=dict(color=ACCENT, width=1.5),
        hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>",
    ))
    fig.update_layout(
        height=260,
        margin=dict(l=4, r=4, t=6, b=6),
        paper_bgcolor=T["chart_bg"],
        plot_bgcolor=T["chart_bg"],
            hoverlabel=dict(font=dict(size=HOVER_LABEL_SIZE, color=T["hover_text"]),
                            bgcolor=T["chart_bg"]),
            xaxis=dict(
                visible=True,
                showticklabels=False,
                ticks="",
                tickfont=dict(size=AXIS_TICK_FONT_SIZE, color=T["text_muted"]),
            ),
            yaxis=dict(
                visible=True,
                showticklabels=False,
                ticks="",
                tickformat=".0f",
                tickfont=dict(size=AXIS_TICK_FONT_SIZE, color=T["text_muted"]),
            ),
    )
    st.plotly_chart(fig, width='stretch', config={"displayModeBar": False})

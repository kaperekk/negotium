from __future__ import annotations

import html
import json
from datetime import date, datetime, timedelta

import streamlit as st

import config as cfg_module
from bossa_import import import_bossa
from manual_import import import_manual
from ui.styles import render_project_banner
from xtb_import import import_xtb

BROKERS = ["XTB", "BOSSA", "Custom"]
BROKER_CURRENCIES = {"XTB": ["EUR", "PLN", "USD"], "BOSSA": ["EUR", "PLN", "Many"]}


def render_sidebar(cfg, storage, T, today, start_date_cfg, detect_currency):
    with st.sidebar:
        project_name = html.escape(storage.get_current_project())
        st.markdown(render_project_banner(project_name, T), unsafe_allow_html=True)

        projects = storage.list_projects()
        current = storage.get_current_project()

        if current and current in projects:
            idx = projects.index(current)
        else:
            idx = 0

        selected = st.selectbox(
            "Project",
            options=projects + ["➕ New project"],
            index=idx,
            key="project_select",
        )

        if selected == "➕ New project":
            @st.dialog("Create new project")
            def _create_dialog():
                name = st.text_input("Project name", placeholder="e.g. Retirement, Savings")
                if st.button("Create", use_container_width=True):
                    if name and name.strip():
                        try:
                            storage.create_project(name.strip())
                            st.session_state.clear()
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
                    else:
                        st.error("Enter a name.")
            _create_dialog()
        elif selected != current:
            storage.set_current_project(selected)
            st.session_state.clear()
            st.rerun()

        st.caption("Currency")
        ccy_options = ["PLN", "EUR", "USD"]
        ccy_default = ccy_options.index(cfg.get("default_currency", "PLN"))
        ccy_cols = st.columns(3)
        base_ccy = None
        for i, ccy in enumerate(ccy_options):
            with ccy_cols[i]:
                is_active = st.session_state.get("base_ccy_idx", ccy_default) == i
                if st.button(
                    ccy,
                    key=f"ccy_btn_{ccy}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state["base_ccy_idx"] = i
                    base_ccy = ccy
                    st.rerun()
        if base_ccy is None:
            base_ccy = ccy_options[st.session_state.get("base_ccy_idx", ccy_default)]

        _range_opts = ["All time", "This year", "Last 12 months", "Last 3 months", "Custom"]
        if "_range" not in st.session_state:
            st.session_state["_range"] = "All time"

        def _on_range_change():
            st.session_state["_range"] = st.session_state["range_widget"]

        range_option = st.session_state["_range"]
        if range_option == "All time":
            chart_start, chart_end = start_date_cfg, today
        elif range_option == "This year":
            chart_start, chart_end = date(today.year, 1, 1), today
        elif range_option == "Last 12 months":
            chart_start, chart_end = today - timedelta(days=365), today
        elif range_option == "Last 3 months":
            chart_start, chart_end = today - timedelta(days=90), today
        else:
            ca, cb = st.columns(2)
            with ca:
                chart_start = st.date_input(
                    "From",
                    value=start_date_cfg,
                    min_value=start_date_cfg,
                    max_value=today,
                    key="range_from",
                )
            with cb:
                chart_end = st.date_input(
                    "To",
                    value=today,
                    min_value=start_date_cfg,
                    max_value=today,
                    key="range_to",
                )

        st.session_state["chart_start"] = chart_start
        st.session_state["chart_end"] = chart_end

        with st.expander("⚙️ Settings"):
            st.subheader("Appearance")
            current_theme = st.session_state.get("theme", "dark")
            light_on = st.toggle(
                "Light mode",
                value=(current_theme == "light"),
                key="theme_toggle",
            )
            new_theme = "light" if light_on else "dark"
            if new_theme != current_theme:
                st.session_state["theme"] = new_theme
                cfg_module.save_theme(new_theme)
                st.rerun()

            st.subheader("Ticker rules")
            rules_text = st.text_area(
                "Rules",
                value="\\n".join(cfg.get("ticker_rules", [])),
                height=200,
                key="ticker_rules_text",
                label_visibility="collapsed",
                placeholder="AMZN.DE=AMZ.DE\\n*.PL=*.WA\\n.US=",
            )
            if st.button("Save ticker rules"):
                new_rules = [line.strip() for line in rules_text.strip().splitlines() if line.strip()]
                cfg["ticker_rules"] = new_rules
                cfg_module.save(cfg)
                st.success("Rules saved!")
                st.rerun()

            st.subheader("Project")
            rename_val = st.text_input("Rename project to", value=storage.get_current_project() or "", key="rename_proj_input")
            if st.button("Rename", key="rename_proj_btn"):
                if rename_val and rename_val.strip() and rename_val.strip() != storage.get_current_project():
                    try:
                        storage.rename_project(storage.get_current_project(), rename_val.strip())
                        st.session_state.clear()
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

        with st.expander("➕ Add transaction"):
            with st.form("add_tx", clear_on_submit=True):
                tx_date = st.date_input("Date", value=today, max_value=today)
                st.caption("Negative amount = sell / cash out.")

                rows = []
                for idx in range(1, 3):
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        t = st.text_input(
                            f"Ticker {idx}",
                            placeholder="AAPL / QDVE.DE / USD / PLN",
                            key=f"t{idx}",
                        ).strip().upper()
                    with c2:
                        a = st.number_input(
                            f"Amount {idx}",
                            value=0.0,
                            format="%.4f",
                            step=0.001,
                            key=f"a{idx}",
                        )
                    rows.append((t, a))

                is_account_op = st.checkbox(
                    "Account operation (deposit/withdrawal)",
                    key="ao_new",
                    help="Marks this transaction as invested capital",
                )

                if st.form_submit_button("Add transaction", width="stretch"):
                    entries = [{
                        "ticker": t,
                        "amount": a,
                        **({"account_operation": True} if is_account_op else {})
                    } for t, a in rows if t and abs(a) > 1e-9]
                    if not entries:
                        st.error("Enter at least one ticker and amount.")
                    else:
                        custom_dir = storage.IMPORTS_DIR / "custom"
                        custom_dir.mkdir(parents=True, exist_ok=True)
                        tx_doc = [{"date": tx_date.isoformat(), "entries": entries}]
                        tx_path = custom_dir / f"{tx_date.isoformat()}_{datetime.now().strftime('%H%M%S')}.json"
                        tx_path.write_text(json.dumps(tx_doc, indent=2), encoding="utf-8")
                        result = __import__("manual_import").import_manual(str(tx_path))
                        if result["success"]:
                            st.success(f"Added for {tx_date}.")
                        else:
                            st.error(result["error"])
                        st.session_state.pop(f"snapshots_{base_ccy}_D", None)
                        st.rerun()

        with st.expander("📥 Import statement"):
            storage.IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

            broker = st.selectbox("Broker", BROKERS, key="broker_select")
            broker_dir = storage.IMPORTS_DIR / broker.lower()
            broker_dir.mkdir(parents=True, exist_ok=True)

            if broker == "XTB":
                st.info("ℹ️ Name your file starting with the currency code, e.g. `EUR_history.xlsx` — the currency is auto-detected from the prefix.")

            file_types = ["csv"] if broker == "BOSSA" else ["json"] if broker == "Custom" else ["xlsx"]
            uploaded_files = st.file_uploader(
                f"Upload {broker} files",
                type=file_types,
                accept_multiple_files=True,
                key=f"{broker}_upload",
                label_visibility="collapsed",
            )

            if uploaded_files:
                for uf in uploaded_files:
                    dest = broker_dir / uf.name
                    dest.write_bytes(uf.getvalue())
                    detected = detect_currency(uf.name)
                    if broker == "BOSSA":
                        ccy = "Many"
                        with st.spinner(f"Importing {uf.name}…"):
                            result = __import__("bossa_import").import_bossa(str(dest), ccy)
                    elif broker == "Custom":
                        with st.spinner(f"Importing {uf.name}…"):
                            result = __import__("manual_import").import_manual(str(dest))
                    else:
                        ccy_options = BROKER_CURRENCIES.get(broker, ["EUR", "PLN", "USD"])
                        if detected not in ccy_options:
                            detected = ccy_options[0]
                        with st.spinner(f"Importing {uf.name}…"):
                            result = __import__("xtb_import").import_xtb(str(dest), detected)
                    if result["success"]:
                        n = result["imported"]
                        s = result["skipped"]
                        msg = f"**{uf.name}** — {n} imported"
                        if s:
                            msg += f", {s} skipped (duplicates)"
                        st.success(msg)
                    else:
                        st.error(f"**{uf.name}** — {result['error']}")
                st.session_state.pop(f"snapshots_{base_ccy}_D", None)
                st.rerun()

            broker_files = sorted(broker_dir.glob("*.xlsx")) + sorted(broker_dir.glob("*.csv")) + sorted(broker_dir.glob("*.json"))
            if broker_files:
                for fpath in broker_files:
                    st.caption(f"📄 {fpath.name}")
            else:
                st.caption("No files uploaded yet.")

        if st.button("📈  Refresh market data", width="stretch"):
            all_files = []
            for b in BROKERS:
                bdir = storage.IMPORTS_DIR / b.lower()
                if not bdir.exists():
                    continue
                for fpath in sorted(bdir.glob("*.xlsx")):
                    all_files.append(("xtb", fpath))
                for fpath in sorted(bdir.glob("*.csv")):
                    all_files.append(("bossa", fpath))
                for fpath in sorted(bdir.glob("*.json")):
                    all_files.append(("custom", fpath))

            if all_files:
                bar = st.progress(0, text="Importing…")
                total_imported = 0
                for idx, (kind, fpath) in enumerate(all_files):
                    ccy = detect_currency(fpath.name)
                    bar.progress(idx / len(all_files), text=f"Importing {fpath.name}…")
                    if kind == "bossa":
                        result = __import__("bossa_import").import_bossa(str(fpath), ccy)
                    elif kind == "custom":
                        result = __import__("manual_import").import_manual(str(fpath))
                    else:
                        result = __import__("xtb_import").import_xtb(str(fpath), ccy)
                    if result["success"]:
                        total_imported += result["imported"]
                bar.progress(1.0, text="Done")
                bar.empty()
                st.success(f"Refreshed from {len(all_files)} files — {total_imported} transactions imported.")
            else:
                st.info("No import files found.")

            storage.invalidate_portfolio_from((today - timedelta(days=1)).isoformat())
            st.session_state.pop(f"snapshots_{base_ccy}_D", None)
            for k in list(st.session_state.keys()):
                if k.startswith("benchmarks_"):
                    st.session_state.pop(k)
            st.session_state["force_refresh"] = True
            st.rerun()

    return base_ccy

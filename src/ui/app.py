"""Streamlit UI — the product front-end for the social support workflow.

Bilingual (EN/AR) with four tabs: Apply, Status, Chat, Decisions. The sidebar
integrates with the government citizen registry: one click prefills the
application form from the registry profile, another attaches the citizen's
five documents from the registry document store. Everything stays editable
after prefill.
"""

from __future__ import annotations

import base64
import datetime as dt
import os
import time

import httpx
import streamlit as st


def _default_api_base() -> str:
    # Inside Docker the API is reachable by service name, not localhost.
    if os.path.exists("/.dockerenv"):
        return "http://api:8000"
    return "http://localhost:8000"


API_BASE = os.environ.get("API_BASE") or _default_api_base()
API_USER = os.environ.get("API_USERNAME", "reviewer")
API_PASS = os.environ.get("API_PASSWORD", "change_me_in_prod")

DEMO_NAME = "Ahmed Al Mansoori"
DEMO_EID = "784-1988-6612345-1"

LANGUAGES = {"English": "EN", "العربية": "AR"}
EMPLOYMENT_OPTIONS = ["Unemployed", "Underemployed", "Employed"]
EDUCATION_OPTIONS = ["Primary", "Secondary", "Diploma", "Bachelor", "Master", "PhD"]
RELATION_OPTIONS = ["spouse", "son", "daughter", "father", "mother", "brother", "sister"]
DOC_TYPES = ["bank_statement", "credit_report", "emirates_id", "resume", "assets_liabilities"]
DOC_ICONS = {
    "bank_statement": "🏦",
    "credit_report": "📊",
    "emirates_id": "🪪",
    "resume": "📄",
    "assets_liabilities": "📈",
}
STATUS_BADGES = {
    "approve": "✅",
    "soft_decline": "🟡",
    "human_review": "🟠",
    "submitted": "⏳",
    "error": "🔴",
}


def _auth():
    return (API_USER, API_PASS)


def _api_post(path: str, data: dict) -> dict:
    resp = httpx.post(f"{API_BASE}{path}", json=data, auth=_auth(), timeout=300.0)
    resp.raise_for_status()
    return resp.json()


def _api_get(path: str) -> dict | list:
    resp = httpx.get(f"{API_BASE}{path}", auth=_auth(), timeout=60.0)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=120)
def _registry_citizens() -> list[dict]:
    try:
        return _api_get("/v1/registry")
    except Exception:
        return []


def _prefill_from_registry(profile: dict):
    """Push a registry profile into the form widgets' session state."""
    st.session_state["applicant_name"] = profile["applicant_name"]
    st.session_state["emirates_id"] = profile["emirates_id"]
    st.session_state["address"] = profile["address"]
    st.session_state["employment"] = profile["employment_status"]
    st.session_state["education"] = profile["education_level"]
    st.session_state["years_exp"] = float(profile.get("years_experience") or 0.0)
    try:
        st.session_state["dob"] = dt.date.fromisoformat(profile["dob"])
    except (ValueError, TypeError):
        pass
    members = profile.get("family_members") or []
    st.session_state["family_count"] = len(members) + 1
    for i, m in enumerate(members):
        st.session_state[f"fm_name_{i}"] = m.get("name", "")
        st.session_state[f"fm_dob_{i}"] = m.get("dob", "")
        if m.get("relation") in RELATION_OPTIONS:
            st.session_state[f"fm_rel_{i}"] = m["relation"]


def _lookup_query() -> str:
    eid = (st.session_state.get("emirates_id") or "").strip()
    name = (st.session_state.get("applicant_name") or "").strip()
    return eid or name


def _set_session(key: str, value):
    """Button callback: safe to mutate widget state before the rerun."""
    st.session_state[key] = value


def _reset_form(pick_placeholder: str):
    """Button callback: return the Apply tab to its initial state.

    Values are set, not popped — Streamlit re-syncs a live widget's old value
    if its key is merely deleted.
    """
    for key in list(st.session_state):
        if key.startswith(("fm_name_", "fm_dob_", "fm_rel_")):
            st.session_state.pop(key)
    st.session_state.update(
        {
            "applicant_name": DEMO_NAME,
            "emirates_id": DEMO_EID,
            "address": "",
            "employment": None,
            "education": None,
            "dob": None,
            "years_exp": 0.0,
            "family_count": 1,
            "idem_key": "",
            "citizen_pick": pick_placeholder,
        }
    )
    st.session_state.pop("fetched_docs", None)
    st.session_state.pop("_last_pick", None)
    # New uploader keys -> empty upload slots
    st.session_state["upload_gen"] = st.session_state.get("upload_gen", 0) + 1


def _render_sidebar(t: dict):
    """Sidebar: language, registry integrations, registry browser."""
    st.sidebar.title("🏛️ " + t["sidebar_title"])
    st.sidebar.divider()
    st.sidebar.subheader("🔗 " + t["integrations"])
    st.sidebar.caption(t["integrations_hint"])

    citizens = _registry_citizens()
    if citizens:
        labels = [t["pick_placeholder"]] + [f"{c['full_name']} — {c['emirates_id']}" for c in citizens]
        pick = st.sidebar.selectbox(t["pick_citizen"], labels, key="citizen_pick")
        if pick != t["pick_placeholder"]:
            picked = citizens[labels.index(pick) - 1]
            if st.session_state.get("_last_pick") != pick:
                st.session_state["_last_pick"] = pick
                st.session_state["applicant_name"] = picked["full_name"]
                st.session_state["emirates_id"] = picked["emirates_id"]
                st.rerun()

    if st.sidebar.button("📇 " + t["get_details"], key="btn_get_details", use_container_width=True):
        query = _lookup_query()
        if not query:
            st.sidebar.warning(t["need_name_or_eid"])
        else:
            try:
                profile = _api_get(f"/v1/registry/{query}")
                _prefill_from_registry(profile)
                st.sidebar.success(t["details_fetched"].format(name=profile["applicant_name"]))
            except httpx.HTTPStatusError as e:
                st.sidebar.error(t["not_in_registry"] if e.response.status_code == 404 else f"{t['error']}: {e}")
            except Exception as e:
                st.sidebar.error(f"{t['error']}: {e}")

    if st.sidebar.button("📂 " + t["get_docs"], key="btn_get_docs", use_container_width=True):
        query = _lookup_query()
        if not query:
            st.sidebar.warning(t["need_name_or_eid"])
        else:
            try:
                docs = _api_get(f"/v1/registry/{query}/documents")
                st.session_state["fetched_docs"] = {d["doc_type"]: d for d in docs}
                st.sidebar.success(t["docs_fetched"].format(n=len(docs)))
            except httpx.HTTPStatusError as e:
                st.sidebar.error(t["not_in_registry"] if e.response.status_code == 404 else f"{t['error']}: {e}")
            except Exception as e:
                st.sidebar.error(f"{t['error']}: {e}")

    fetched = st.session_state.get("fetched_docs") or {}
    if fetched:
        st.sidebar.caption(t["docs_attached"].format(n=len(fetched)))
        if st.sidebar.button("🗑️ " + t["clear_docs"], key="btn_clear_docs", use_container_width=True):
            st.session_state.pop("fetched_docs", None)
            st.rerun()

    st.sidebar.divider()
    with st.sidebar.expander("🗂️ " + t["registry_browser"]):
        if citizens:
            st.dataframe(
                [{t["col_name"]: c["full_name"], t["col_eid"]: c["emirates_id"]} for c in citizens],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption(t["registry_empty"])

    st.sidebar.divider()
    try:
        _api_get("/health")
        st.sidebar.caption(f"🟢 API `{API_BASE}`")
    except Exception:
        st.sidebar.caption(f"🔴 API `{API_BASE}`")


def main():
    st.set_page_config(page_title="Social Support Workflow", page_icon="🏛️", layout="wide")

    # Demo defaults: a registry citizen is prefilled so reviewers can click
    # "Get User Details" right away. Everything else starts empty on purpose.
    st.session_state.setdefault("applicant_name", DEMO_NAME)
    st.session_state.setdefault("emirates_id", DEMO_EID)

    lang = st.sidebar.selectbox("Language / اللغة", list(LANGUAGES.keys()), key="lang")
    t = _translations(LANGUAGES[lang] == "AR")

    role = st.sidebar.radio(t["view_as"], [t["role_user"], t["role_admin"]], key="role", horizontal=True)
    is_admin = role == t["role_admin"]
    if is_admin:
        st.sidebar.caption("🛠️ " + t["admin_hint"])

    _render_sidebar(t)

    st.title("🏛️ " + t["title"])
    st.caption(t["subtitle"])

    tab_labels = ["📝 " + t["tab_apply"], "🔍 " + t["tab_status"], "💬 " + t["tab_chat"], "📊 " + t["tab_dash"]]
    if is_admin:
        tab_labels.append("📈 " + t["tab_eval"])
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        _render_apply_tab(t, is_admin)
    with tabs[1]:
        _render_status_tab(t, is_admin)
    with tabs[2]:
        _render_chat_tab(t, is_admin)
    with tabs[3]:
        _render_dashboard_tab(t, is_admin)
    if is_admin:
        with tabs[4]:
            _render_eval_tab(t)


def _render_apply_tab(t: dict, is_admin: bool = False):
    st.subheader(t["apply_header"])
    st.caption(t["apply_hint"])

    col1, col2 = st.columns(2)
    with col1:
        applicant_name = st.text_input(t["name"], key="applicant_name")
    with col2:
        emirates_id = st.text_input(t["eid"], key="emirates_id", placeholder="784-YYYY-XXXXXXX-X")

    with st.expander(t["form_details"], expanded=True):
        fc1, fc2 = st.columns(2)
        with fc1:
            address = st.text_input(t["address"], key="address")
            employment = st.selectbox(
                t["employment"], EMPLOYMENT_OPTIONS, key="employment", index=None, placeholder=t["select_placeholder"]
            )
            years_exp = st.number_input(t["years_exp"], 0.0, 50.0, key="years_exp")
        with fc2:
            dob = st.date_input(t["dob"], key="dob", value=None, min_value=dt.date(1940, 1, 1), max_value=dt.date.today())
            education = st.selectbox(t["education"], EDUCATION_OPTIONS, key="education", index=None, placeholder=t["select_placeholder"])
            family_count = st.number_input(t["family_count"], 1, 12, key="family_count")

        family_members = []
        if family_count > 1:
            st.markdown(f"**{t['family_section']}**")
        for i in range(int(family_count) - 1):
            fm1, fm2, fm3 = st.columns([2, 1, 1])
            with fm1:
                fm_name = st.text_input(f"{t['member_name']} {i + 1}", key=f"fm_name_{i}")
            with fm2:
                fm_dob = st.text_input(f"{t['member_dob']} {i + 1}", key=f"fm_dob_{i}", placeholder="YYYY-MM-DD")
            with fm3:
                fm_rel = st.selectbox(f"{t['relation']} {i + 1}", RELATION_OPTIONS, key=f"fm_rel_{i}")
            if fm_name:
                family_members.append({"name": fm_name, "dob": fm_dob or "1990-01-01", "relation": fm_rel})

    st.markdown(f"##### {t['uploads']}")
    st.caption(t["uploads_hint"])
    fetched = st.session_state.get("fetched_docs") or {}
    doc_uploads: dict[str, dict] = {}

    upload_gen = st.session_state.get("upload_gen", 0)

    def _doc_uploader(doc_type: str):
        label = f"{DOC_ICONS[doc_type]} {t[doc_type]}"
        uploaded = st.file_uploader(label, key=f"upload_{doc_type}_{upload_gen}", type=["png", "jpg", "jpeg", "pdf", "txt", "xlsx"])
        if uploaded:
            content = uploaded.read()
            doc_uploads[doc_type] = {
                "doc_type": doc_type,
                "filename": uploaded.name,
                "content_b64": base64.b64encode(content).decode(),
            }
            st.caption("✅ " + t["manual_upload"].format(name=uploaded.name))
        elif doc_type in fetched:
            doc_uploads[doc_type] = {
                "doc_type": doc_type,
                "filename": fetched[doc_type]["filename"],
                "content_b64": fetched[doc_type]["content_b64"],
            }
            st.caption("📎 " + t["from_registry"].format(name=fetched[doc_type]["filename"]))

    up_left, up_right = st.columns(2)
    with up_left:
        for doc_type in ("bank_statement", "credit_report", "emirates_id"):
            _doc_uploader(doc_type)
    with up_right:
        for doc_type in ("resume", "assets_liabilities"):
            _doc_uploader(doc_type)

    with st.expander(t["advanced"]):
        idempotency_key = st.text_input(t["idempotency"], key="idem_key", help=t["idempotency_help"])
        st.caption(t["idempotency_help"])

    submit_col, reset_col = st.columns([4, 1])
    reset_col.button(
        "🧹 " + t["reset_form"], key="btn_reset_form", on_click=_reset_form, args=(t["pick_placeholder"],), use_container_width=True
    )
    if submit_col.button("🚀 " + t["submit"], key="btn_submit", type="primary", use_container_width=True):
        if not applicant_name or not emirates_id:
            st.error(t["need_name_or_eid"])
            return
        if not address or not dob or employment is None or education is None:
            st.error(t["need_details"])
            return
        payload = {
            "applicant_name": applicant_name,
            "emirates_id": emirates_id,
            "application_form": {
                "applicant_name": applicant_name,
                "emirates_id": emirates_id,
                "dob": str(dob),
                "address": address,
                "employment_status": employment,
                "education_level": education,
                "years_experience": years_exp,
                "family_members": family_members,
            },
            "documents": list(doc_uploads.values()),
            "idempotency_key": idempotency_key or None,
        }
        started = time.time()
        try:
            if is_admin:
                with st.status(t["processing"], expanded=True) as progress:
                    st.write("① " + t["stage_extraction"])
                    st.write("② " + t["stage_validation"])
                    st.write("③ " + t["stage_eligibility"])
                    st.write("④ " + t["stage_decision"])
                    result = _api_post("/v1/apply", payload)
                    progress.update(label=t["done_in"].format(s=time.time() - started), state="complete")
            else:
                with st.spinner(t["processing"]):
                    result = _api_post("/v1/apply", payload)
        except httpx.HTTPStatusError as e:
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = str(e)
            st.error(f"{t['error']}: {detail}")
            return
        except Exception as e:
            st.error(f"{t['error']}: {e}")
            return
        new_id = result.get("application_id")
        st.session_state["last_app_id"] = new_id
        # Point the Status and Chat tabs at this submission (their widgets
        # render after this tab, so their state can still be set here).
        st.session_state["status_app_id"] = new_id or ""
        st.session_state["chat_app_id"] = new_id or ""
        _render_decision_summary(t, result)
        if is_admin and new_id:
            _render_processing_log(t, new_id, elapsed=time.time() - started)


def _render_decision_summary(t: dict, result: dict):
    rec = result.get("recommendation") or "submitted"
    app_id = result.get("application_id", "N/A")
    st.success(f"{t['app_id']}: **{app_id}**")
    if result.get("message"):
        st.caption(result["message"])

    c1, c2, c3 = st.columns(3)
    c1.metric(t["recommendation"], f"{STATUS_BADGES.get(rec, '')} {t.get(rec, rec)}")
    if result.get("confidence") is not None:
        c2.metric(t["confidence"], f"{result['confidence']:.2%}")
    if result.get("enablement"):
        c3.metric(t["enablement"], ", ".join(t.get(e, e) for e in result["enablement"]))

    if rec == "approve":
        st.balloons()
    elif rec == "human_review":
        st.warning(t["human_review_note"])


def _render_processing_log(t: dict, app_id: str, elapsed: float | None = None):
    """Admin diagnostics for one application: audit trail, flags, features, SHAP."""
    with st.expander("🛠️ " + t["processing_log"], expanded=True):
        if elapsed is not None:
            st.caption(t["done_in"].format(s=elapsed))
        try:
            decision = _api_get(f"/v1/decision/{app_id}")
        except Exception:
            decision = None
        try:
            audit = _api_get(f"/v1/applications/{app_id}/audit")
        except Exception:
            audit = []

        if audit:
            st.markdown(f"**{t['audit_trail']}**")
            st.dataframe(
                [{"time": a["created_at"], "action": a["action"], "actor": a["actor"], "detail": json_str(a.get("detail"))} for a in audit],
                hide_index=True,
                use_container_width=True,
            )
        if decision:
            st.markdown(f"**{t['validation_flags_label']}**")
            flags = decision.get("validation_flags") or []
            if flags:
                st.dataframe(flags, hide_index=True, use_container_width=True)
            else:
                st.caption(t["no_flags"])

            fcol, scol = st.columns(2)
            with fcol:
                st.markdown(f"**{t['features_label']}**")
                st.json(decision.get("features") or {})
            with scol:
                st.markdown(f"**{t['classifier_label']}**")
                st.write(
                    {
                        "prediction": decision.get("recommendation"),
                        "probability": decision.get("confidence"),
                        "shap_values": decision.get("shap_values"),
                    }
                )


def json_str(value) -> str:
    import json as _json

    return _json.dumps(value, default=str) if value else ""


def _render_status_tab(t: dict, is_admin: bool = False):
    st.subheader(t["status_header"])
    st.caption(t["status_hint"])
    app_id = st.text_input(t["app_id_input"], key="status_app_id", help=t["status_hint"], placeholder="APP-XXXXXXXX")

    check_col, latest_col, clear_col, _ = st.columns([1.2, 1.4, 1, 2.4])
    if st.session_state.get("last_app_id"):
        latest_col.button(
            "↺ " + t["load_latest"],
            key="btn_status_latest",
            on_click=_set_session,
            args=("status_app_id", st.session_state["last_app_id"]),
            use_container_width=True,
        )
    clear_col.button("🗑️ " + t["clear"], key="btn_status_clear", on_click=_set_session, args=("status_app_id", ""), use_container_width=True)
    if check_col.button(t["check_status"], key="btn_check_status", type="primary", use_container_width=True) and app_id:
        try:
            result = _api_get(f"/v1/status/{app_id.strip()}")
        except httpx.HTTPStatusError as e:
            st.error(t["not_found"] if e.response.status_code == 404 else f"{t['error']}: {e}")
            return
        except Exception as e:
            st.error(f"{t['error']}: {e}")
            return
        status = result.get("status", "unknown")
        st.metric(t["status_label"], f"{STATUS_BADGES.get(status, '')} {t.get(status, status)}")
        decision = result.get("decision")
        if decision:
            st.markdown(f"**{t['rationale']}:** {decision.get('rationale', '—')}")
            if decision.get("enablement"):
                st.markdown(f"**{t['enablement']}:** {', '.join(t.get(e, e) for e in decision['enablement'])}")
        with st.expander(t["raw_response"]):
            st.json(result)
        if is_admin:
            _render_processing_log(t, app_id.strip())


def _render_chat_tab(t: dict, is_admin: bool = False):
    st.subheader(t["chat_header"])
    st.caption(t["chat_hint"])
    app_id = st.text_input(t["app_id_input"], key="chat_app_id", placeholder="APP-XXXXXXXX")

    # A conversation belongs to one application — switching cases starts fresh
    if st.session_state.get("chat_for") != app_id:
        st.session_state["chat_msgs"] = []
        st.session_state["chat_for"] = app_id

    if not app_id:
        st.info(t["chat_needs_app"])
    clear_slot = st.empty()  # filled at the end, once this run's messages are known

    if is_admin and app_id:
        with st.expander("🛠️ " + t["grounding_context"]):
            st.caption(t["grounding_hint"])
            try:
                decision = _api_get(f"/v1/decision/{app_id.strip()}")
                st.json(
                    {
                        "recommendation": decision.get("recommendation"),
                        "confidence": decision.get("confidence"),
                        "rationale": decision.get("rationale"),
                        "validation_flags": decision.get("validation_flags"),
                        "shap_top_features": (decision.get("shap_values") or [])[:5],
                        "eligibility_features": decision.get("features"),
                        "enablement_types": decision.get("enablement"),
                    }
                )
            except Exception:
                st.caption(t["no_decision"])

    if "chat_msgs" not in st.session_state:
        st.session_state["chat_msgs"] = []

    for msg in st.session_state["chat_msgs"]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    user_msg = st.chat_input(t["chat_placeholder"])
    if user_msg and app_id:
        st.session_state["chat_msgs"].append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.write(user_msg)
        with st.chat_message("assistant"), st.spinner(t["thinking"]):
            started = time.time()
            try:
                result = _api_post("/v1/chat", {"application_id": app_id.strip(), "message": user_msg})
                response = result.get("response", "")
            except httpx.HTTPStatusError as e:
                response = t["not_found"] if e.response.status_code == 404 else f"{t['error']}: {e}"
            except Exception as e:
                response = f"{t['error']}: {e}"
            st.write(response)
            if is_admin:
                st.caption(t["llm_response_time"].format(s=time.time() - started))
        st.session_state["chat_msgs"].append({"role": "assistant", "content": response})

    if st.session_state.get("chat_msgs"):
        with clear_slot:
            st.button("🗑️ " + t["clear_chat"], key="btn_clear_chat", on_click=_set_session, args=("chat_msgs", []))


def _render_dashboard_tab(t: dict, is_admin: bool = False):
    st.subheader(t["dash_header"])
    try:
        stats = _api_get("/v1/applications/stats")
        apps = _api_get("/v1/applications")
    except Exception as e:
        st.error(f"{t['error']}: {e}")
        return
    if not apps:
        st.info(t["no_apps"])
        return

    by_status = stats.get("by_status", {})
    total = stats.get("total", 0)
    decided = ("approve", "soft_decline", "human_review")
    pending = total - sum(by_status.get(s, 0) for s in decided)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric(t["total_apps"], total)
    m2.metric("✅ " + t["approve"], by_status.get("approve", 0))
    m3.metric("🟡 " + t["soft_decline"], by_status.get("soft_decline", 0))
    m4.metric("🟠 " + t["human_review"], by_status.get("human_review", 0))
    m5.metric("⏳ " + t["pending_other"], pending)

    status_filter = st.selectbox(t["filter_status"], [t["all"], *decided], key="dash_filter")
    shown = [a for a in apps if status_filter == t["all"] or a["status"] == status_filter]
    st.caption(t["showing_latest"].format(n=min(len(shown), 20), total=total))

    for app in shown[:20]:
        badge = STATUS_BADGES.get(app["status"], "")
        with st.expander(f"{badge} {app['id']} — {app['applicant_name']} ({t.get(app['status'], app['status'])})"):
            try:
                decision = _api_get(f"/v1/decision/{app['id']}")
            except Exception:
                st.caption(t["no_decision"])
                continue
            col1, col2 = st.columns(2)
            with col1:
                rec = decision.get("recommendation", "—")
                st.markdown(f"**{t['recommendation']}:** {STATUS_BADGES.get(rec, '')} {t.get(rec, rec)}")
                st.markdown(f"**{t['confidence']}:** {decision.get('confidence', 0):.2%}")
                st.markdown(f"**{t['rationale']}:** {decision.get('rationale', '—')}")
                if decision.get("enablement"):
                    st.markdown(f"**{t['enablement']}:** {', '.join(t.get(e, e) for e in decision['enablement'])}")
            with col2:
                st.markdown(f"**{t['explainability']}**")
                shap_vals = decision.get("shap_values") or []
                if shap_vals:
                    st.bar_chart({s["feature"]: s["shap_value"] for s in shap_vals[:5]}, horizontal=True, height=200)
                else:
                    st.caption(t["no_shap"])
            if is_admin:
                flags = decision.get("validation_flags") or []
                st.markdown(f"**{t['validation_flags_label']}**")
                if flags:
                    st.dataframe(flags, hide_index=True, use_container_width=True)
                else:
                    st.caption(t["no_flags"])
                with st.popover(t["features_label"]):
                    st.json(decision.get("features") or {})


def _render_eval_tab(t: dict):
    """Admin-only: model metrics, fairness slices, and the full evaluation report."""
    st.subheader(t["eval_header"])
    st.caption(t["eval_hint"])
    try:
        metrics = _api_get("/v1/admin/metrics")
    except Exception as e:
        st.error(f"{t['error']}: {e}")
        return

    cv = metrics.get("cv_metrics")
    if cv:
        st.markdown(f"##### {t['eval_classifier']}")
        rows = []
        for metric in ("f1", "accuracy", "precision", "recall", "roc_auc"):
            gb = cv.get(f"gradient_boosting_{metric}_mean")
            if gb is None:
                continue
            rows.append(
                {
                    "metric": metric.upper(),
                    "GradientBoosting": f"{gb:.3f} ± {cv.get(f'gradient_boosting_{metric}_std', 0):.3f}",
                    "LogisticRegression (baseline)": f"{cv.get(f'logistic_regression_{metric}_mean', 0):.3f}",
                }
            )
        st.dataframe(rows, hide_index=True, use_container_width=True)
        st.caption(
            f"{cv.get('n_samples')} samples · {cv.get('n_features')} features · "
            f"label noise {cv.get('label_noise_rate', 0):.0%} · 5-fold stratified CV"
        )
        importances = cv.get("feature_importances") or {}
        if importances:
            st.markdown(f"##### {t['eval_importances']}")
            st.bar_chart(importances, horizontal=True, height=280)

    bias = metrics.get("bias_report")
    if bias:
        st.markdown(f"##### {t['eval_fairness']}")
        st.dataframe(
            [{"slice": k, "approval_rate": f"{v['approval_rate']:.1%}", "n": v["count"]} for k, v in bias.get("slices", {}).items()],
            hide_index=True,
            use_container_width=True,
        )
        st.caption(t["eval_disparity"].format(d=bias.get("max_disparity", 0)))

    report = metrics.get("evaluation_report_md")
    if report:
        st.markdown(f"##### {t['eval_full_report']}")
        st.caption(t["eval_report_hint"])
        st.markdown(report)
    else:
        st.info(t["eval_no_report"])


def _translations(is_ar: bool) -> dict:
    if is_ar:
        return {
            "sidebar_title": "الدعم الاجتماعي",
            "view_as": "عرض كـ",
            "role_user": "مقدم الطلب",
            "role_admin": "مسؤول",
            "admin_hint": "وضع المسؤول: سجلات مفصلة ومقاييس التقييم مرئية",
            "tab_eval": "التقييم",
            "processing_log": "سجل المعالجة",
            "audit_trail": "سجل التدقيق",
            "validation_flags_label": "نتائج التحقق",
            "no_flags": "لا توجد ملاحظات — اجتازت جميع الفحوصات",
            "features_label": "خصائص الأهلية",
            "classifier_label": "مخرجات المصنف",
            "stage_extraction": "استخراج المستندات (pypdf / OCR / pandas)",
            "stage_validation": "التحقق من الاتساق بين المستندات (+ فحص الرسم البياني)",
            "stage_eligibility": "حساب الأهلية (القواعد + النموذج اللغوي)",
            "stage_decision": "التوصية (المصنف + SHAP + التوجيه)",
            "done_in": "اكتمل في {s:.1f} ثانية",
            "grounding_context": "سياق التأسيس المرسل إلى النموذج",
            "grounding_hint": "سجل القرار الذي تُبنى عليه إجابات المحادثة",
            "llm_response_time": "زمن استجابة النموذج: {s:.1f} ثانية",
            "eval_header": "مقاييس التقييم",
            "eval_hint": "مقاييس النموذج والاستخراج والتوجيه والتقييم بواسطة نموذج لغوي كحكم",
            "eval_classifier": "مصنف الأهلية (تحقق متقاطع)",
            "eval_importances": "أهمية الخصائص",
            "eval_fairness": "الإنصاف — معدلات الموافقة حسب الشريحة",
            "eval_disparity": "أقصى تفاوت: {d:.1%}",
            "eval_full_report": "تقرير التقييم الكامل",
            "eval_report_hint": "يُعاد إنشاؤه بأمر make eval — يشمل دقة الاستخراج وصحة التوجيه وتقييم النموذج كحكم",
            "eval_no_report": "لا يوجد تقرير بعد — شغّل make eval",
            "reset_form": "إعادة تعيين",
            "load_latest": "أحدث طلب",
            "clear": "مسح",
            "clear_chat": "مسح المحادثة",
            "title": "أتمتة سير عمل الدعم الاجتماعي",
            "subtitle": "قرارات دعم اجتماعي خلال دقائق — مدعومة بنماذج ذكاء اصطناعي محلية",
            "integrations": "التكاملات",
            "integrations_hint": "اجلب البيانات والمستندات من سجل المواطنين الحكومي",
            "pick_citizen": "اختر مواطنًا (تجريبي)",
            "pick_placeholder": "— اختر —",
            "get_details": "جلب بيانات المستخدم",
            "get_docs": "جلب مستندات المستخدم",
            "clear_docs": "مسح المستندات المجلوبة",
            "docs_fetched": "تم جلب {n} مستندات من السجل",
            "docs_attached": "📎 {n} مستندات مرفقة من السجل",
            "details_fetched": "تم تعبئة النموذج لـ {name}",
            "not_in_registry": "غير موجود في السجل",
            "need_name_or_eid": "أدخل الاسم أو رقم الهوية أولاً",
            "need_details": 'أكمل تفاصيل الطلب أولاً — أو اضغط "جلب بيانات المستخدم" في الشريط الجانبي لتعبئتها تلقائيًا',
            "select_placeholder": "— اختر —",
            "idempotency_help": (
                "حماية اختيارية من الطلبات المكررة: أدخل أي نص فريد. إذا أُرسل الطلب نفسه مرة أخرى بنفس المفتاح "
                "(نقرة مزدوجة أو إعادة محاولة)، يعيد النظام الطلب الأصلي بدلاً من إنشاء نسخة مكررة."
            ),
            "status_hint": "كل طلب مُرسل يحصل على معرف (مثل APP-1A2B3C4D) يظهر بعد الإرسال ويُعبأ هنا تلقائيًا.",
            "chat_hint": (
                "اسأل عن طلب مُرسل — لماذا تمت الموافقة أو الرفض، أو ما البرامج التدريبية والوظائف المناسبة. الإجابات من نموذج لغوي محلي."
            ),
            "registry_browser": "سجل المواطنين",
            "registry_empty": "السجل غير متاح",
            "col_name": "الاسم",
            "col_eid": "رقم الهوية",
            "tab_apply": "تقديم الطلب",
            "tab_status": "الحالة",
            "tab_chat": "المحادثة",
            "tab_dash": "لوحة القرارات",
            "apply_header": "تقديم طلب دعم اجتماعي",
            "apply_hint": "املأ النموذج يدويًا أو استخدم أزرار التكامل في الشريط الجانبي",
            "name": "الاسم",
            "eid": "رقم الهوية",
            "address": "العنوان",
            "dob": "تاريخ الميلاد",
            "employment": "الوضع الوظيفي",
            "education": "المستوى التعليمي",
            "years_exp": "سنوات الخبرة",
            "family_count": "عدد أفراد الأسرة",
            "family_section": "أفراد الأسرة",
            "member_name": "اسم الفرد",
            "member_dob": "تاريخ الميلاد",
            "relation": "صلة القرابة",
            "form_details": "تفاصيل الطلب",
            "uploads": "المستندات المرفقة",
            "uploads_hint": "ارفع المستندات يدويًا أو اجلبها من السجل عبر الشريط الجانبي",
            "bank_statement": "كشف حساب بنكي",
            "credit_report": "تقرير ائتماني",
            "emirates_id": "صورة الهوية",
            "resume": "السيرة الذاتية",
            "assets_liabilities": "الأصول والخصوم (Excel)",
            "manual_upload": "مرفوع يدويًا: {name}",
            "from_registry": "من السجل: {name}",
            "advanced": "خيارات متقدمة",
            "idempotency": "مفتاح Idempotency (اختياري)",
            "submit": "إرسال الطلب",
            "processing": "جاري تشغيل سير العمل...",
            "app_id": "معرف الطلب",
            "recommendation": "التوصية",
            "confidence": "الثقة",
            "approve": "موافقة",
            "soft_decline": "رفض مبدئي",
            "human_review": "مراجعة بشرية",
            "submitted": "قيد المعالجة",
            "error": "خطأ",
            "human_review_note": "حُوّل الطلب إلى قائمة المراجعة البشرية بسبب حالة حدّية أو تعارض في المستندات",
            "upskilling": "تطوير المهارات",
            "job_matching": "مطابقة الوظائف",
            "career_counseling": "الإرشاد المهني",
            "enablement": "التمكين الاقتصادي",
            "status_header": "حالة الطلب",
            "status_label": "الحالة",
            "app_id_input": "معرف الطلب",
            "check_status": "تحقق من الحالة",
            "not_found": "الطلب غير موجود",
            "raw_response": "الاستجابة الكاملة",
            "chat_header": "المحادثة التفاعلية",
            "chat_needs_app": "أدخل معرف طلب لبدء المحادثة",
            "chat_placeholder": "اكتب رسالتك...",
            "thinking": "جاري التفكير...",
            "dash_header": "لوحة القرارات",
            "no_apps": "لا توجد طلبات",
            "total_apps": "إجمالي الطلبات",
            "pending_other": "قيد المعالجة / أخرى",
            "showing_latest": "عرض أحدث {n} من أصل {total} طلبًا",
            "filter_status": "تصفية حسب الحالة",
            "all": "الكل",
            "rationale": "السبب",
            "explainability": "تفسير القرار (SHAP)",
            "no_shap": "لا توجد بيانات SHAP",
            "no_decision": "لا يوجد قرار بعد",
        }
    return {
        "sidebar_title": "Social Support",
        "view_as": "View as",
        "role_user": "Application User",
        "role_admin": "Admin",
        "admin_hint": "Admin mode: detailed logs and evaluation metrics are visible",
        "tab_eval": "Evaluation",
        "processing_log": "Processing log",
        "audit_trail": "Audit trail",
        "validation_flags_label": "Validation findings",
        "no_flags": "No findings — all checks passed",
        "features_label": "Eligibility features",
        "classifier_label": "Classifier output",
        "stage_extraction": "Extracting documents (pypdf / vision OCR / pandas)",
        "stage_validation": "Cross-document validation (+ family-graph check)",
        "stage_eligibility": "Eligibility scoring (rubric + LLM)",
        "stage_decision": "Recommendation (classifier + SHAP + routing)",
        "done_in": "Completed in {s:.1f}s",
        "grounding_context": "LLM grounding context",
        "grounding_hint": "The decision record every chat answer is grounded in",
        "llm_response_time": "LLM response time: {s:.1f}s",
        "eval_header": "Evaluation Metrics",
        "eval_hint": "Model, extraction, routing, and LLM-as-judge measurements for this deployment",
        "eval_classifier": "Eligibility classifier (5-fold cross-validation)",
        "eval_importances": "Feature importances",
        "eval_fairness": "Fairness — approval rate per demographic slice",
        "eval_disparity": "Max disparity: {d:.1%}",
        "eval_full_report": "Full evaluation report",
        "eval_report_hint": "Regenerated by `make eval` — includes extraction accuracy, routing correctness, and LLM-as-judge scores",
        "eval_no_report": "No report yet — run `make eval`",
        "reset_form": "Reset form",
        "load_latest": "Latest submission",
        "clear": "Clear",
        "clear_chat": "Clear chat",
        "title": "Social Support Workflow Automation",
        "subtitle": "Social support decisions in minutes — powered by locally hosted AI models",
        "integrations": "Integrations",
        "integrations_hint": "Pull details and documents from the government citizen registry",
        "pick_citizen": "Sample citizen (demo)",
        "pick_placeholder": "— select —",
        "get_details": "Get User Details",
        "get_docs": "Get User Documents",
        "clear_docs": "Clear fetched documents",
        "docs_fetched": "Fetched {n} documents from the registry",
        "docs_attached": "📎 {n} documents attached from the registry",
        "details_fetched": "Form prefilled for {name}",
        "not_in_registry": "Not found in the citizen registry",
        "need_name_or_eid": "Enter a name or Emirates ID first",
        "need_details": "Complete the application details first — or click Get User Details in the sidebar to autofill them.",
        "select_placeholder": "— select —",
        "idempotency_help": (
            "Optional safeguard against duplicate submissions. Enter any unique text (e.g. my-application-001): "
            "if the same application is submitted again with the same key — a double-click or a network retry — "
            "the system returns the original application instead of creating a duplicate."
        ),
        "status_hint": (
            "Every submission returns an application ID (like APP-1A2B3C4D). It shows on the Apply tab "
            "after you submit and is prefilled here automatically."
        ),
        "chat_hint": (
            "Ask about a submitted application — why it was approved or declined, or which training programs "
            "and jobs fit. Answers come from the locally hosted LLM, grounded in the applicant's own data."
        ),
        "registry_browser": "Citizen registry",
        "registry_empty": "Registry unavailable",
        "col_name": "Name",
        "col_eid": "Emirates ID",
        "tab_apply": "Apply",
        "tab_status": "Status",
        "tab_chat": "Chat",
        "tab_dash": "Decisions",
        "apply_header": "Submit a Social Support Application",
        "apply_hint": "Fill the form manually, or use the integration buttons in the sidebar.",
        "name": "Applicant Name",
        "eid": "Emirates ID",
        "address": "Address",
        "dob": "Date of Birth",
        "employment": "Employment Status",
        "education": "Education Level",
        "years_exp": "Years of Experience",
        "family_count": "Family Size",
        "family_section": "Family Members",
        "member_name": "Member Name",
        "member_dob": "Member DOB",
        "relation": "Relation",
        "form_details": "Application Details",
        "uploads": "Documents",
        "uploads_hint": "Upload manually, or fetch from the registry via the sidebar.",
        "bank_statement": "Bank Statement",
        "credit_report": "Credit Report",
        "emirates_id": "Emirates ID (Image)",
        "resume": "Resume",
        "assets_liabilities": "Assets/Liabilities (Excel)",
        "manual_upload": "Manual upload: {name}",
        "from_registry": "From registry: {name}",
        "advanced": "Advanced",
        "idempotency": "Idempotency Key (optional)",
        "submit": "Submit Application",
        "processing": "Running the agentic workflow — extraction → validation → eligibility → decision...",
        "app_id": "Application ID",
        "recommendation": "Recommendation",
        "confidence": "Confidence",
        "approve": "Approve",
        "soft_decline": "Soft Decline",
        "human_review": "Human Review",
        "submitted": "Processing",
        "error": "Error",
        "human_review_note": "Routed to the human-review queue — borderline score or unresolved cross-document conflict.",
        "upskilling": "Upskilling",
        "job_matching": "Job Matching",
        "career_counseling": "Career Counseling",
        "enablement": "Economic Enablement",
        "status_header": "Application Status",
        "status_label": "Status",
        "app_id_input": "Application ID",
        "check_status": "Check Status",
        "not_found": "Application not found",
        "raw_response": "Full response",
        "chat_header": "Interactive Chat",
        "chat_needs_app": "Enter an application ID to start chatting about enablement options.",
        "chat_placeholder": "Type your message...",
        "thinking": "Thinking...",
        "dash_header": "Decision Dashboard",
        "no_apps": "No applications yet",
        "total_apps": "Total Applications",
        "pending_other": "Pending / Other",
        "showing_latest": "Showing the latest {n} of {total} applications",
        "filter_status": "Filter by status",
        "all": "All",
        "rationale": "Rationale",
        "explainability": "Explainability (SHAP)",
        "no_shap": "No SHAP data",
        "no_decision": "No decision yet",
    }


if __name__ == "__main__":
    main()

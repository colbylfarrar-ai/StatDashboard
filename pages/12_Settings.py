"""
8_Settings.py — App-wide preferences.

Three controls, all persisted to the app_settings key/value table:
  • Wide Mode      — page layout (wide vs centered)         → wide_mode
  • Appearance     — dark style preset + accent colour      → app_style / accent_color
  • Default Team   — team pre-selected across other pages    → default_team

All read/write goes through helpers/settings_utils.py.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from database.db import query, execute
from helpers.settings_utils import (
    set_setting, get_setting, ACCENT_PRESETS, STYLE_PRESETS, DEFAULTS,
)
from helpers.ui import page_chrome, team_color
import helpers.auth as AUTH

_cfg, _ = page_chrome("Settings")


st.title("Settings")
st.caption("Changes are saved immediately — other pages pick them up automatically "
           "the next time they load.")


# ══════════════════════════════════════════════════════════════════════════════
#  LAYOUT — Wide Mode
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Layout")

wide_now = _cfg.get("wide_mode", DEFAULTS["wide_mode"]) == "1"
wide = st.toggle(
    "Wide mode",
    value=wide_now,
    help="Use the full browser width. Off centers content in a narrower column.",
)
if wide != wide_now:
    set_setting("wide_mode", "1" if wide else "0")
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  APPEARANCE — Dark style + accent
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Appearance")

style_names = list(STYLE_PRESETS.keys())
style_labels = [STYLE_PRESETS[n]["label"] for n in style_names]
cur_style = _cfg.get("app_style", DEFAULTS["app_style"])
if cur_style not in style_names:
    cur_style = DEFAULTS["app_style"]

c1, c2 = st.columns(2)

with c1:
    new_style_label = st.selectbox(
        "Dark theme",
        style_labels,
        index=style_names.index(cur_style),
        help="Background and card colour scheme. All presets are dark themes.",
    )
    new_style = style_names[style_labels.index(new_style_label)]
    if new_style != cur_style:
        set_setting("app_style", new_style)
        st.rerun()

with c2:
    accent_names = list(ACCENT_PRESETS.keys())
    cur_scheme = _cfg.get("color_scheme", DEFAULTS["color_scheme"])
    if cur_scheme not in accent_names:
        cur_scheme = DEFAULTS["color_scheme"]
    new_scheme = st.selectbox(
        "Accent colour",
        accent_names,
        index=accent_names.index(cur_scheme),
        help="Highlight colour for values, winners and the #1 rank.",
    )
    if new_scheme != cur_scheme:
        set_setting("color_scheme", new_scheme)
        set_setting("accent_color", ACCENT_PRESETS[new_scheme])
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  DEFAULT TEAM
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Default Team")

teams = query("SELECT name FROM teams ORDER BY name")
team_names = [t["name"] for t in teams]

if not team_names:
    st.info("No teams yet — add teams in the Input Hub to set a default.")
else:
    options = ["(none)"] + team_names
    cur_team = _cfg.get("default_team", DEFAULTS["default_team"])
    idx = options.index(cur_team) if cur_team in options else 0
    new_team = st.selectbox(
        "Pre-selected team",
        options,
        index=idx,
        help="This team is highlighted/selected by default on other pages.",
    )
    saved = "" if new_team == "(none)" else new_team
    if saved != cur_team:
        set_setting("default_team", saved)
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  TEAM COLOURS
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Team colours")
st.caption("Give a team its own identity colour — used in its charts and the box "
           "score. Auto derives a stable colour from the team name; switch on "
           "Custom to override it.")

_tc_rows = query("SELECT id, name FROM teams ORDER BY name")
if not _tc_rows:
    st.info("No teams yet — add teams in the Input Hub first.")
else:
    tc1, tc2 = st.columns([3, 2])
    with tc1:
        _tc_team = st.selectbox("Team", _tc_rows, format_func=lambda r: r["name"],
                                key="tc_team")
    _tid = _tc_team["id"]
    _key = f"team_color::{_tid}"
    _cur = get_setting(_key, "")
    _auto = team_color(_tc_team["name"])
    with tc2:
        _use_custom = st.toggle("Custom colour", value=bool(_cur), key="tc_custom",
                                help="Off = Auto (derived from the team name).")
    if _use_custom:
        _picked = st.color_picker("Pick a colour", value=_cur or _auto, key="tc_pick")
        if _picked != _cur:
            set_setting(_key, _picked)
            st.rerun()
    elif _cur:                       # toggled off → clear the override
        set_setting(_key, "")
        st.rerun()
    st.markdown(
        f"<span style='display:inline-block;width:16px;height:16px;border-radius:4px;"
        f"background:{_cur or _auto};vertical-align:middle;margin-right:8px'></span>"
        f"<span style='color:var(--subtext)'>"
        f"{'Custom' if _cur else 'Auto'} · {_cur or _auto}</span>",
        unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  ACCOUNT & USERS  (login is enabled by [auth] in .streamlit/secrets.toml)
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Account & users")

_me = AUTH.current_user()

if not AUTH.auth_enabled():
    st.info(
        "Sign-in is currently **off** — anyone who can reach this app can use "
        "it. That's fine while it runs only on your own computer, but turn "
        "sign-in on before sharing it with other coaches. Setup instructions "
        "for the app owner: copy `.streamlit/secrets.toml.example` to "
        "`.streamlit/secrets.toml`, fill in the Google OAuth credentials, and "
        "see `AUTH_SETUP.md`.")
elif _me["role"] != "admin":
    st.caption(f"Signed in as **{_me['email']}** ({_me['role']}). "
               "Only the admin can manage users.")
    if st.button("Log out", key="au_logout"):
        st.logout()
else:
    st.caption(f"Signed in as **{_me['email']}** (admin).")
    if st.button("Log out", key="au_logout"):
        st.logout()

    _team_rows = query("SELECT id, name FROM teams ORDER BY name")
    _team_opts = [None] + [r["id"] for r in _team_rows]
    _team_name = {r["id"]: r["name"] for r in _team_rows}

    def _team_label(i):
        return "(no team)" if i is None else _team_name.get(i, f"#{i}")

    for _u in AUTH.list_users():
        _email = _u["email"]
        _is_self = _email == _me["email"]
        _plan = _u["plan"] if _u["plan"] in AUTH.PLANS else "free"
        _hdr = (f"{_email} · {_u['role']} · {_plan}"
                + (f" · {_team_label(_u['team_id'])}" if _u["team_id"] else ""))
        with st.expander(_hdr):
            mc1, mc2 = st.columns(2)
            _role = mc1.selectbox(
                "Role", AUTH.ROLES, index=AUTH.ROLES.index(_u["role"]),
                key=f"role_{_email}", disabled=_is_self,
                help="You can't change your own role." if _is_self else None)
            if not _is_self and _role != _u["role"]:
                AUTH.add_user(_email, _role)         # upserts role only
                st.rerun()
            _newplan = mc2.selectbox(
                "Plan", AUTH.PLANS, index=AUTH.PLANS.index(_plan),
                key=f"plan_{_email}",
                help="Paid unlocks tracked depth + the mobile tracker app.")
            if _newplan != _plan:
                AUTH.set_plan(_email, _newplan)
                st.rerun()
            _curteam = _u["team_id"] if _u["team_id"] in _team_opts else None
            _newteam = st.selectbox(
                "Team", _team_opts, index=_team_opts.index(_curteam),
                format_func=_team_label, key=f"team_{_email}",
                help="The coach's own team — defines their own-data scope.")
            if _newteam != _u["team_id"]:
                AUTH.set_team(_email, _newteam)
                st.rerun()

            st.markdown("**Mobile tracker token**")
            _tok = AUTH.get_tracker_token(_email)
            if _tok:
                st.code(_tok, language=None)
                if st.button("Revoke token", key=f"tokrm_{_email}"):
                    AUTH.clear_tracker_token(_email)
                    st.rerun()
            else:
                _can_token = (_newplan == "paid") or (_role == "admin")
                if st.button("Issue token", key=f"tokgen_{_email}",
                             disabled=not _can_token,
                             help=None if _can_token else "Paid/admin only."):
                    AUTH.set_tracker_token(_email)
                    st.rerun()
                st.caption("The coach pastes this into the mobile tracker (Paid/admin only).")

            if st.button("Remove user", key=f"rm_{_email}", disabled=_is_self,
                         help="You can't remove yourself." if _is_self else None):
                AUTH.remove_user(_email)
                st.rerun()

    with st.form("au_add", clear_on_submit=True):
        _a1, _a2, _a3 = st.columns([4, 2, 1])
        _new_email = _a1.text_input("Email", placeholder="coach@gmail.com",
                                    label_visibility="collapsed")
        _new_role = _a2.selectbox("Role", AUTH.ROLES, index=1,
                                  label_visibility="collapsed")
        if _a3.form_submit_button("Add", type="primary"):
            try:
                AUTH.add_user(_new_email, _new_role, added_by=_me["email"])
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    st.caption("Add a coach by email, then set their plan, team and tracker token "
               "above. Re-adding an email updates its role.")

    # ── league pool (reciprocity toggle) ─────────────────────────────────────
    st.markdown("**League pool**")
    st.caption("A team in the pool shares its tracked games with other pooled "
               "coaches and can scout the pool in return (reciprocity).")
    _pool_rows = query("SELECT id, name, in_pool FROM teams ORDER BY name")
    if _pool_rows:
        _pt = st.selectbox("Pool team", _pool_rows,
                           format_func=lambda r: r["name"], key="pool_team",
                           label_visibility="collapsed")
        _on = st.toggle("In league pool", value=bool(_pt["in_pool"]),
                        key="pool_toggle")
        if _on != bool(_pt["in_pool"]):
            execute("UPDATE teams SET in_pool=? WHERE id=?",
                    (1 if _on else 0, _pt["id"]))
            st.rerun()

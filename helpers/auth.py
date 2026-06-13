"""
auth.py — login gate + role lookup for the Streamlit app.

Uses Streamlit's native OIDC auth (st.login / st.user, Streamlit >= 1.42,
requires Authlib). The gate is enabled ONLY when .streamlit/secrets.toml has
an [auth] section (see .streamlit/secrets.toml.example) — without it the app
runs open, which is today's local single-coach behavior. NEVER expose the
Streamlit app to the internet without configuring [auth].

Who gets in: emails in the app_users table, managed from the Settings page.
Bootstrap: the FIRST person to sign in while app_users is empty becomes the
admin — that's you; add coaches afterwards.

OIDC provides authentication only; roles live here in SQLite:
  admin — everything + manage users on the Settings page
  coach — everything except user management
"""
from __future__ import annotations

import secrets

import streamlit as st

from database.db import execute, query

ROLES = ("admin", "coach")

# Local/owner identity when auth is off: full access (matches today's open
# single-coach behavior) — admin role + paid plan so every gate passes.
_LOCAL_IDENTITY = {"email": "", "name": "Local", "role": "admin",
                   "plan": "paid", "paid_until": "", "team_id": None}


def auth_enabled() -> bool:
    """True when an [auth] block exists in secrets — the deploy-time switch."""
    try:
        return "auth" in st.secrets
    except Exception:
        return False


# ── user table (pure DB — testable without streamlit) ───────────────────────────
def lookup_role(email: str):
    rows = query("SELECT role FROM app_users WHERE email=?",
                 ((email or "").strip().lower(),))
    return rows[0]["role"] if rows else None


def lookup_user(email: str):
    """Full allowlist row (role, plan, team_id, paid_until) or None."""
    rows = query("SELECT email, role, name, plan, paid_until, team_id "
                 "FROM app_users WHERE email=?",
                 ((email or "").strip().lower(),))
    return rows[0] if rows else None


def list_users():
    return query("SELECT email, role, name, plan, team_id, added_at "
                 "FROM app_users ORDER BY role, email")


def add_user(email: str, role: str = "coach", name: str = "",
             added_by: str = ""):
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("valid email required")
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    execute("""INSERT INTO app_users (email, role, name, added_by)
               VALUES (?,?,?,?)
               ON CONFLICT(email) DO UPDATE SET role=excluded.role""",
            (email, role, name, added_by))


def remove_user(email: str):
    execute("DELETE FROM app_users WHERE email=?",
            ((email or "").strip().lower(),))


# ── per-coach tracker tokens (mobile API auth) ─────────────────────────────────
def gen_tracker_token() -> str:
    return secrets.token_urlsafe(24)


def set_tracker_token(email: str) -> str:
    """Generate + store a fresh tracker token for this coach; returns it.
    The coach pastes it into the PWA; the API resolves it back to this user."""
    tok = gen_tracker_token()
    execute("UPDATE app_users SET tracker_token=? WHERE email=?",
            (tok, (email or "").strip().lower()))
    return tok


def clear_tracker_token(email: str):
    execute("UPDATE app_users SET tracker_token='' WHERE email=?",
            ((email or "").strip().lower(),))


def get_tracker_token(email: str) -> str:
    rows = query("SELECT tracker_token FROM app_users WHERE email=?",
                 ((email or "").strip().lower(),))
    return rows[0]["tracker_token"] if rows else ""


def bootstrap_admin_if_empty(email: str, name: str = ""):
    """First sign-in on an empty user table becomes admin (one-time setup).
    Returns 'admin' if the bootstrap happened, else None."""
    if query("SELECT email FROM app_users LIMIT 1"):
        return None
    add_user(email, "admin", name, added_by="bootstrap")
    return "admin"


# ── the gate ─────────────────────────────────────────────────────────────────────
def require_login() -> dict:
    """Call once per page run, after set_page_config. Returns the identity
    {'email','name','role'} — or renders a sign-in / not-authorized screen and
    st.stop()s. With auth not configured, returns a local admin identity."""
    if not auth_enabled():
        st.session_state["auth_user"] = _LOCAL_IDENTITY
        return _LOCAL_IDENTITY

    if not getattr(st.user, "is_logged_in", False):
        st.title("🏀 APP5 Analytics")
        st.write("Sign in to continue.")
        if st.button("Sign in", type="primary"):
            st.login()
        st.stop()

    email = (getattr(st.user, "email", "") or "").strip().lower()
    name = getattr(st.user, "name", "") or email
    role = lookup_role(email) or bootstrap_admin_if_empty(email, name)
    if role is None:
        st.title("Not authorized")
        st.write(f"**{email}** isn't on the coach list. "
                 "Ask the admin to add you on the Settings page.")
        if st.button("Log out"):
            st.logout()
        st.stop()

    u = lookup_user(email) or {}
    ident = {"email": email, "name": name, "role": role,
             "plan": u.get("plan", "free"),
             "paid_until": u.get("paid_until", ""),
             "team_id": u.get("team_id")}
    st.session_state["auth_user"] = ident
    return ident


def current_user() -> dict:
    """Identity stored by require_login() this run (local admin when auth off)."""
    return st.session_state.get("auth_user", _LOCAL_IDENTITY)


# ── entitlement (plan gating) ──────────────────────────────────────────────────
def has_tracked_access(ident: dict | None = None) -> bool:
    """True if this user may see tracked play-by-play depth (Paid tier).

    Admin always qualifies; otherwise plan == 'paid', or a paid_until date that
    hasn't passed. INERT until wired into the has_tracked render guards — adding
    it here changes no behavior yet."""
    ident = ident or current_user()
    if ident.get("role") == "admin":
        return True
    if ident.get("plan") == "paid":
        return True
    pu = (ident.get("paid_until") or "").strip()
    if pu:
        from datetime import date
        try:
            return pu >= date.today().isoformat()
        except Exception:
            return False
    return False

import { useEffect, useState } from "react"
import App from "./App.jsx"
import InvestmentDashboard from "./InvestmentDashboard.jsx"
import InvestAuth from "./InvestAuth.jsx"
import AdminPanel from "./AdminPanel.jsx"
import {
  isAdmin,
  loadAuthSession,
  logoutInvest,
  refreshAuthSession,
} from "./investApi"
import "./Investment.css"

const VIEW_KEY = "jm_fx_view"

function initialView() {
  try {
    const params = new URLSearchParams(window.location.search)
    const q = params.get("view")
    if (q === "admin" || q === "invest" || q === "referral" || q === "trading") {
      return q
    }
    const stored = localStorage.getItem(VIEW_KEY)
    if (stored === "admin" || stored === "invest" || stored === "referral" || stored === "trading") {
      return stored
    }
  } catch {
    /* ignore */
  }
  const session = loadAuthSession()
  if (session?.user?.role === "investor") return "invest"
  if (session?.user?.role === "admin") return "admin"
  return "trading"
}

function ShellNav({ view, switchView, auth, admin, onLogout }) {
  const loggedIn = Boolean(auth?.user)
  return (
    <nav className="shell-nav">
      <div className="shell-nav-inner">
        <button
          type="button"
          className={`shell-tab${view === "invest" ? " active" : ""}`}
          onClick={() => switchView("invest")}
        >
          My Investment
        </button>
        <button
          type="button"
          className={`shell-tab${view === "referral" ? " active" : ""}`}
          onClick={() => switchView("referral")}
        >
          Referral Link
        </button>
        {admin && (
          <button
            type="button"
            className={`shell-tab${view === "admin" ? " active" : ""}`}
            onClick={() => switchView("admin")}
          >
            Admin Panel
          </button>
        )}
        <button
          type="button"
          className={`shell-tab${view === "trading" ? " active" : ""}`}
          onClick={() => switchView("trading")}
        >
          Trading Desk
        </button>
        {loggedIn ? (
          <button type="button" className="shell-tab shell-logout" onClick={onLogout}>
            Logout
          </button>
        ) : (
          <button
            type="button"
            className={`shell-tab${view === "invest" ? " active" : ""}`}
            onClick={() => switchView("invest")}
          >
            Login
          </button>
        )}
        {auth?.user && (
          <span className="shell-user">
            {auth.user.full_name || auth.user.email}
            {admin ? " · Admin" : ""}
          </span>
        )}
      </div>
    </nav>
  )
}

export default function Shell() {
  const [view, setView] = useState(initialView)
  const [auth, setAuth] = useState(() => loadAuthSession())
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let alive = true
    ;(async () => {
      const session = await refreshAuthSession()
      if (alive) {
        setAuth(session)
        setChecking(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  function switchView(next) {
    setView(next)
    try {
      localStorage.setItem(VIEW_KEY, next)
    } catch {
      /* ignore */
    }
  }

  function handleAuthSuccess(res) {
    setAuth(res)
    if (res.user?.role === "admin") {
      switchView("admin")
    } else {
      switchView("invest")
    }
  }

  function handleLogout() {
    logoutInvest()
    setAuth(null)
    switchView("trading")
  }

  const admin = isAdmin()
  const loggedIn = Boolean(auth?.user)

  if (checking && view !== "trading") {
    return (
      <div className="invest-app">
        <p className="invest-loading">Loading…</p>
      </div>
    )
  }

  if (!auth && (view === "invest" || view === "admin" || view === "referral")) {
    return (
      <>
        <ShellNav
          view={view}
          switchView={switchView}
          auth={auth}
          admin={admin}
          onLogout={handleLogout}
        />
        <InvestAuth
          onSuccess={handleAuthSuccess}
          initialMode={view === "admin" ? "login" : undefined}
          showAdminHint={view === "admin"}
        />
      </>
    )
  }

  return (
    <>
      <ShellNav
        view={view}
        switchView={switchView}
        auth={auth}
        admin={admin}
        onLogout={handleLogout}
      />
      {view === "admin" && admin && <AdminPanel />}
      {(view === "invest" || view === "referral") && loggedIn && (
        <InvestmentDashboard focusReferral={view === "referral"} />
      )}
      {view === "trading" && <App />}
    </>
  )
}

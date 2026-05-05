import React from "react";
import { Link, useLocation } from "react-router-dom";
import "./Navigation.css";

export default function Navigation() {
  const location = useLocation();

  const isActive = (path: string) => location.pathname === path;

  return (
    <nav className="nav-bar">
      <div className="nav-brand">
        <span className="nav-logo">🛰️</span>
        <span className="nav-title">AREG Remote Control</span>
      </div>
      <div className="nav-links">
        <Link
          to="/areg800a"
          className={`nav-link ${isActive("/areg800a") ? "active" : ""}`}
        >
          AREG 800A Control
        </Link>
        <Link
          to="/tcv907"
          className={`nav-link ${isActive("/tcv907") ? "active" : ""}`}
        >
          TCV907 Radar Validation
        </Link>
      </div>
    </nav>
  );
}

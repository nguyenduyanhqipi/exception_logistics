import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Truck,
  LayoutDashboard,
  History as HistoryIcon,
  BarChart3,
  Settings as SettingsIcon,
  User as UserIcon,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(() => {
    return localStorage.getItem("sidebar_collapsed") === "true";
  });

  function toggleSidebar() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebar_collapsed", String(next));
      return next;
    });
  }

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${collapsed ? "collapsed" : ""}`}>
        <div className="sidebar-header">
          <NavLink to="/" className="sidebar-brand" title="Exception Logistics">
            <span className="sidebar-brand-icon">
              <Truck size={17} />
            </span>
            <span className="sidebar-brand-name">Exception Logistics</span>
          </NavLink>
          <button
            type="button"
            className="sidebar-toggle"
            onClick={toggleSidebar}
            title={collapsed ? "Mở rộng thanh điều hướng" : "Thu gọn thanh điều hướng"}
            aria-label={collapsed ? "Mở rộng menu" : "Thu gọn menu"}
          >
            {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
          </button>
        </div>

        <nav className="sidebar-nav">
          <NavLink
            to="/"
            end
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            title="Dashboard"
          >
            <span className="nav-icon">
              <LayoutDashboard size={18} />
            </span>
            <span className="nav-label">Dashboard</span>
          </NavLink>

          <NavLink
            to="/operations"
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            title="Xe & Kế hoạch"
          >
            <span className="nav-icon">
              <Truck size={18} />
            </span>
            <span className="nav-label">Xe &amp; Kế hoạch</span>
          </NavLink>

          <NavLink
            to="/history"
            className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
            title="Lịch sử"
          >
            <span className="nav-icon">
              <HistoryIcon size={18} />
            </span>
            <span className="nav-label">Lịch sử</span>
          </NavLink>

          {user?.role === "manager" && (
            <>
              <NavLink
                to="/manager"
                className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
                title="Báo cáo"
              >
                <span className="nav-icon">
                  <BarChart3 size={18} />
                </span>
                <span className="nav-label">Báo cáo</span>
              </NavLink>

              <NavLink
                to="/settings"
                className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}
                title="Cài đặt"
              >
                <span className="nav-icon">
                  <SettingsIcon size={18} />
                </span>
                <span className="nav-label">Cài đặt</span>
              </NavLink>
            </>
          )}
        </nav>

        <div className="sidebar-footer">
          {collapsed && (
            <button
              type="button"
              className="btn-logout"
              onClick={() => setCollapsed(false)}
              title="Mở rộng menu"
              style={{ marginBottom: 4 }}
            >
              <ChevronRight size={14} />
            </button>
          )}
          <div
            className="sidebar-user"
            title={user?.role === "manager" ? "Quản lý" : "Điều phối viên"}
          >
            <div className="sidebar-user-avatar">
              <UserIcon size={15} />
            </div>
            <div className="sidebar-user-info">
              <span className="user-info">
                {user?.role === "manager" ? "Quản lý" : "Điều phối viên"}
              </span>
              <span className="user-role-badge">
                {user?.role === "manager" ? "Toàn quyền hệ thống" : "Vận hành tuyến xe"}
              </span>
            </div>
          </div>
          <button
            type="button"
            className="btn-logout"
            onClick={handleLogout}
            title="Đăng xuất khỏi hệ thống"
          >
            <LogOut size={15} />
            <span>Đăng xuất</span>
          </button>
        </div>
      </aside>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}

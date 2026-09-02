import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <nav>
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/exceptions/new">Nhập ngoại lệ mới</NavLink>
          <NavLink to="/schedules/new">Nhập kế hoạch</NavLink>
          <NavLink to="/excel-upload">Upload Excel</NavLink>
          {user?.role === "manager" && (
            <>
              <NavLink to="/manager">Báo cáo</NavLink>
              <NavLink to="/settings">Cài đặt</NavLink>
            </>
          )}
        </nav>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className="user-info">
            {user?.role === "manager" ? "Quản lý" : "Điều phối viên"}
          </span>
          <button onClick={handleLogout}>Đăng xuất</button>
        </div>
      </header>
      <main style={{ flex: 1 }}>
        <Outlet />
      </main>
    </div>
  );
}

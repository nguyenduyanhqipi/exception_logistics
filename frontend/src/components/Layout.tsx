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
          {/* "Nhập ngoại lệ mới" KHÔNG còn ở nav (2026-09-04): route
              /exceptions/new vẫn giữ, vào bằng nút "+ Ngoại lệ" trên Dashboard
              — nơi đã biết sẵn xe nào, đỡ phải tự chọn lại chuyến.
              "Lịch sử" đứng ngay TRƯỚC khối Báo cáo/Cài đặt; với điều phối
              viên (không có 2 mục đó) nó là mục cuối. */}
          <NavLink to="/" end>
            Dashboard
          </NavLink>
          <NavLink to="/operations">Xe &amp; Kế hoạch</NavLink>
          <NavLink to="/history">Lịch sử</NavLink>
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

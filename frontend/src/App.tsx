import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { Dashboard } from "./pages/Dashboard";
import { NewException } from "./pages/NewException";
import { ExceptionDetail } from "./pages/ExceptionDetail";
import { ExceptionGroup } from "./pages/ExceptionGroup";
import { ManagerDashboard } from "./pages/ManagerDashboard";
import { Settings } from "./pages/Settings";
import { ScheduleInput } from "./pages/ScheduleInput";
import { ExcelUpload } from "./pages/ExcelUpload";

const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<Dashboard />} />
              <Route path="/exceptions/new" element={<NewException />} />
              <Route path="/exceptions/:exceptionId" element={<ExceptionDetail />} />
              <Route path="/exception-groups/:groupId" element={<ExceptionGroup />} />
              <Route path="/schedules/new" element={<ScheduleInput />} />
              <Route path="/excel-upload" element={<ExcelUpload />} />
              <Route path="/manager" element={<ManagerDashboard />} />
              <Route path="/settings" element={<Settings />} />
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;

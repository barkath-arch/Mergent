import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Layout from "./components/Layout";
import Discover from "./pages/Discover";
import { Login, Register, Forgot } from "./pages/Auth";
import Marketplace from "./pages/Marketplace";
import SolutionDetail from "./pages/SolutionDetail";
import BuilderDetail from "./pages/BuilderDetail";
import AIMatch from "./pages/AIMatch";
import Messages from "./pages/Messages";
import { TransactionList, TransactionDetail } from "./pages/Transactions";
import { DeploymentList, DeploymentDetail } from "./pages/Deployments";
import Settings from "./pages/Settings";
import RequirementForm from "./pages/RequirementForm";
import Saved from "./pages/Saved";
import NotificationSettings from "./pages/NotificationSettings";
import {
  BuilderShell, BuilderOverview, BuilderSolutions,
  BuilderSales, BuilderEarnings, BuilderStats,
} from "./pages/Builder";
import "./App.css";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div style={{ minHeight: "100vh", display: "grid", placeItems: "center", color: "var(--text-muted)" }}>Loading…</div>;
  if (!user) return <Navigate to="/auth/login" replace />;
  return children;
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster theme="dark" position="top-right" richColors closeButton />
        <Routes>
          <Route path="/auth/login" element={<Login />} />
          <Route path="/auth/register" element={<Register />} />
          <Route path="/auth/forgot" element={<Forgot />} />

          <Route element={<Protected><Layout /></Protected>}>
            <Route path="/" element={<Discover />} />
            <Route path="/marketplace" element={<Marketplace />} />
            <Route path="/solutions/:id" element={<SolutionDetail />} />
            <Route path="/builders/:id" element={<BuilderDetail />} />
            <Route path="/ai-match" element={<AIMatch />} />
            <Route path="/messages" element={<Messages />} />
            <Route path="/transactions" element={<TransactionList />} />
            <Route path="/transactions/:id" element={<TransactionDetail />} />
            <Route path="/deployments" element={<DeploymentList />} />
            <Route path="/deployments/:id" element={<DeploymentDetail />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/settings/notifications" element={<NotificationSettings />} />
            <Route path="/requirements/new" element={<RequirementForm />} />
            <Route path="/saved" element={<Saved />} />

            {/* Builder Hub (Phase 6) */}
            <Route path="/builder" element={<BuilderShell />}>
              <Route index element={<BuilderOverview />} />
              <Route path="solutions" element={<BuilderSolutions />} />
              <Route path="sales" element={<BuilderSales />} />
              <Route path="earnings" element={<BuilderEarnings />} />
              <Route path="stats" element={<BuilderStats />} />
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;

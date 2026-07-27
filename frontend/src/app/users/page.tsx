"use client";

import { useEffect, useState } from "react";
import { AppLayout, PageHeader } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { RequireAuth } from "@/lib/auth";
import { fetchJson } from "@/lib/api";
import { toast } from "sonner";
import { UserPlus, Shield, Trash2, Key, MoreVertical } from "lucide-react";
import { cn } from "@/lib/utils";

interface TeamUser {
  id: number;
  username: string;
  email: string;
  role: string;
  display_name: string | null;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string | null;
}

const ROLE_COLORS: Record<string, string> = {
  admin: "bg-red-500/10 text-red-400 border-red-500/20",
  manager: "bg-amber-500/10 text-amber-400 border-amber-500/20",
  analyst: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  viewer: "bg-zinc-500/10 text-zinc-400 border-zinc-500/20",
};

function UsersContent() {
  const [users, setUsers] = useState<TeamUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newUser, setNewUser] = useState({ username: "", email: "", password: "", role: "viewer" });

  const loadUsers = async () => {
    try {
      const data = await fetchJson<any>("/api/auth/users");
      setUsers(data.users || []);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadUsers(); }, []);

  const createUser = async () => {
    if (!newUser.username || !newUser.email || !newUser.password) return;
    try {
      await fetchJson("/api/auth/users", { method: "POST", body: JSON.stringify(newUser) });
      toast.success(`User ${newUser.username} created`);
      setNewUser({ username: "", email: "", password: "", role: "viewer" });
      setShowCreate(false);
      loadUsers();
    } catch (e: any) { toast.error(e.message); }
  };

  const toggleUser = async (id: number, active: boolean) => {
    try {
      await fetchJson(`/api/auth/users/${id}`, { method: "PATCH", body: JSON.stringify({ is_active: !active }) });
      toast.success(active ? "User disabled" : "User enabled");
      loadUsers();
    } catch (e: any) { toast.error(e.message); }
  };

  const changeRole = async (id: number, role: string) => {
    try {
      await fetchJson(`/api/auth/users/${id}`, { method: "PATCH", body: JSON.stringify({ role }) });
      toast.success("Role updated");
      loadUsers();
    } catch (e: any) { toast.error(e.message); }
  };

  const deleteUser = async (id: number, username: string) => {
    if (!confirm(`Delete user "${username}"? This cannot be undone.`)) return;
    try {
      await fetchJson(`/api/auth/users/${id}`, { method: "DELETE" });
      toast.success(`User ${username} deleted`);
      loadUsers();
    } catch (e: any) { toast.error(e.message); }
  };

  const resetPassword = async (id: number, username: string) => {
    const newPass = prompt(`Enter new password for ${username}:`);
    if (!newPass || newPass.length < 6) { toast.error("Password must be 6+ characters"); return; }
    try {
      await fetchJson(`/api/auth/users/${id}/reset-password`, { method: "POST", body: JSON.stringify({ new_password: newPass }) });
      toast.success("Password reset");
    } catch (e: any) { toast.error(e.message); }
  };

  return (
    <>
      <PageHeader title="Team Members" description="Manage users and roles"
        actions={<Button onClick={() => setShowCreate(v => !v)}><UserPlus className="w-4 h-4" /> Invite User</Button>}
      />

      {/* Create User Form */}
      {showCreate && (
        <div className="rounded-2xl border border-border bg-card p-5 mb-6 animate-slide-up">
          <h3 className="text-sm font-semibold mb-4">Invite New Team Member</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 mb-4">
            <Input label="Username" value={newUser.username} onChange={e => setNewUser(p => ({...p, username: e.target.value}))} placeholder="john" />
            <Input label="Email" type="email" value={newUser.email} onChange={e => setNewUser(p => ({...p, email: e.target.value}))} placeholder="john@team.com" />
            <Input label="Password" type="password" value={newUser.password} onChange={e => setNewUser(p => ({...p, password: e.target.value}))} placeholder="Min 6 chars" />
            <Select label="Role" value={newUser.role} onChange={e => setNewUser(p => ({...p, role: e.target.value}))} options={[
              { value: "viewer", label: "Viewer" },
              { value: "analyst", label: "Analyst" },
              { value: "manager", label: "Manager" },
              { value: "admin", label: "Admin" },
            ]} />
            <div className="flex items-end"><Button onClick={createUser} className="w-full">Create</Button></div>
          </div>
        </div>
      )}

      {/* Users Table */}
      <div className="rounded-2xl border border-border bg-card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              {["User", "Role", "Status", "Last Login", "Actions"].map(h => (
                <th key={h} className="text-left px-5 py-3 text-2xs font-medium uppercase tracking-wider text-muted-foreground">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5} className="px-5 py-12 text-center text-sm text-muted-foreground">Loading...</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={5} className="px-5 py-12 text-center text-sm text-muted-foreground">No users found</td></tr>
            ) : users.map(u => (
              <tr key={u.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                <td className="px-5 py-3">
                  <div>
                    <p className="text-sm font-medium">{u.display_name || u.username}</p>
                    <p className="text-2xs text-muted-foreground">{u.email}</p>
                  </div>
                </td>
                <td className="px-5 py-3">
                  <select
                    value={u.role}
                    onChange={e => changeRole(u.id, e.target.value)}
                    className={cn("text-xs px-2 py-1 rounded-lg border font-medium bg-transparent cursor-pointer", ROLE_COLORS[u.role] || "")}
                  >
                    <option value="admin">Admin</option>
                    <option value="manager">Manager</option>
                    <option value="analyst">Analyst</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </td>
                <td className="px-5 py-3">
                  <button onClick={() => toggleUser(u.id, u.is_active)}
                    className={cn("text-xs px-2 py-1 rounded-lg border font-medium", u.is_active ? "bg-success/10 text-success border-success/20" : "bg-destructive/10 text-destructive border-destructive/20")}>
                    {u.is_active ? "Active" : "Disabled"}
                  </button>
                </td>
                <td className="px-5 py-3 text-xs text-muted-foreground">
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}
                </td>
                <td className="px-5 py-3">
                  <div className="flex items-center gap-1">
                    <button onClick={() => resetPassword(u.id, u.username)} className="p-1.5 rounded-lg hover:bg-muted transition-colors" title="Reset Password">
                      <Key className="w-3.5 h-3.5 text-muted-foreground" />
                    </button>
                    <button onClick={() => deleteUser(u.id, u.username)} className="p-1.5 rounded-lg hover:bg-destructive/10 transition-colors" title="Delete">
                      <Trash2 className="w-3.5 h-3.5 text-destructive" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function UsersPage() {
  return (
    <AppLayout>
      <RequireAuth>
        <UsersContent />
      </RequireAuth>
    </AppLayout>
  );
}

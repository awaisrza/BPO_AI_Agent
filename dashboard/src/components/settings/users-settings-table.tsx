"use client";

import { useEffect, useState } from "react";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRow,
} from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/skeleton";
import { createClient, isSupabaseConfigured, supabaseConfigHelp } from "@/lib/supabase/client";
import { formatSupabaseError } from "@/lib/errors";
import { getOrgId } from "@/lib/get-org-id";

type TeamMember = {
  id: string;
  name: string;
  email: string;
  role: string;
};

export function UsersSettingsTable() {
  const [users, setUsers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      if (!isSupabaseConfigured()) {
        setError(supabaseConfigHelp());
        setLoading(false);
        return;
      }

      try {
        const supabase = createClient();
        const orgId = await getOrgId(supabase);
        const { data, error: loadError } = await supabase
          .from("profiles")
          .select("id, name, email, role")
          .eq("org_id", orgId)
          .order("name", { ascending: true });

        if (loadError) throw loadError;

        setUsers(
          (data ?? []).map((row) => ({
            id: row.id,
            name: row.name?.trim() || row.email,
            email: row.email,
            role: row.role,
          })),
        );
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : formatSupabaseError(err, "Could not load team members."),
        );
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, []);

  return (
    <Card>
      <CardHeader
        title="Team members"
        action={
          <Button variant="secondary" size="sm" disabled>
            Invite user
          </Button>
        }
      />
      <CardBody className="px-0 pb-0 pt-0">
        {loading && <TableSkeleton rows={3} cols={3} />}

        {error && (
          <div className="p-5">
            <Alert variant="error">{error}</Alert>
          </div>
        )}

        {!loading && !error && users.length === 0 && (
          <p className="p-5 text-sm text-foreground-muted">No team members found.</p>
        )}

        {!loading && !error && users.length > 0 && (
          <Table>
            <TableHead>
              <TableHeaderCell>Name</TableHeaderCell>
              <TableHeaderCell>Email</TableHeaderCell>
              <TableHeaderCell>Role</TableHeaderCell>
            </TableHead>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-medium text-foreground">{u.name}</TableCell>
                  <TableCell className="text-foreground-muted">{u.email}</TableCell>
                  <TableCell className="text-foreground-muted capitalize">{u.role}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardBody>
    </Card>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Card, CardBody } from "@/components/ui/card";
import { ProgressBar } from "@/components/ui/progress-bar";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

export function BotsUsage() {
  const [active, setActive] = useState(0);
  const [included, setIncluded] = useState(10);
  const [plan, setPlan] = useState("Pilot");

  useEffect(() => {
    if (!isSupabaseConfigured()) return;

    async function load() {
      const supabase = createClient();
      const { count } = await supabase
        .from("bots")
        .select("*", { count: "exact", head: true });

      setActive(count ?? 0);

      const { data: profile } = await supabase
        .from("profiles")
        .select("org_id")
        .maybeSingle();

      if (profile?.org_id) {
        const { data: org } = await supabase
          .from("organizations")
          .select("plan, bots_included")
          .eq("id", profile.org_id)
          .single();

        if (org) {
          setPlan(org.plan ?? "Pilot");
          setIncluded(org.bots_included ?? 10);
        }
      }
    }

    load();
  }, []);

  return (
    <Card className="mb-6">
      <CardBody>
        <ProgressBar
          value={active}
          max={included}
          label={`${plan} plan usage`}
          sublabel={`${Math.max(0, included - active)} available`}
        />
      </CardBody>
    </Card>
  );
}

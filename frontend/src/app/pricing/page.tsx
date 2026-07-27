"use client";

import Link from "next/link";
import { AppLayout, PageHeader } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const plans = [
  {
    name: "Free",
    price: "$0",
    period: "forever",
    description: "For hobbyists and testing",
    features: ["1,000 API calls/day", "3 API keys", "Basic filters", "TXT/CSV/JSON export", "Community support"],
    cta: "Get Started",
    href: "/register",
    popular: false,
  },
  {
    name: "Pro",
    price: "$19",
    period: "/month",
    description: "For developers and small teams",
    features: ["Unlimited API calls", "10 API keys", "All filters + speed tiers", "Proxy rotation endpoint", "Webhook notifications", "Telegram/Discord alerts", "Scheduled exports", "Priority support"],
    cta: "Upgrade to Pro",
    href: "/register",
    popular: true,
  },
  {
    name: "Enterprise",
    price: "$99",
    period: "/month",
    description: "For businesses at scale",
    features: ["Everything in Pro", "100 API keys", "Multi-region checking", "Proxy chain builder", "Custom check targets", "IP reputation API", "Dedicated support", "SLA guarantee"],
    cta: "Contact Sales",
    href: "/register",
    popular: false,
  },
];

export default function PricingPage() {
  return (
    <AppLayout>
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-12">
          <h1 className="text-3xl font-bold tracking-tight mb-3">Simple, transparent pricing</h1>
          <p className="text-muted-foreground max-w-md mx-auto">
            Start free, upgrade when you need more. No hidden fees.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={cn(
                "rounded-xl border p-6 transition-all duration-300 relative",
                plan.popular
                  ? "border-emerald-500/30 bg-emerald-500/[0.03] shadow-lg shadow-emerald-500/5"
                  : "border-white/[0.06] bg-white/[0.02] hover:border-white/[0.1]"
              )}
            >
              {plan.popular && (
                <Badge variant="success" size="md" className="absolute -top-2.5 left-1/2 -translate-x-1/2">
                  Most Popular
                </Badge>
              )}
              <div className="mb-5">
                <h3 className="text-sm font-semibold mb-1">{plan.name}</h3>
                <div className="flex items-baseline gap-1">
                  <span className="text-3xl font-bold">{plan.price}</span>
                  <span className="text-sm text-muted-foreground">{plan.period}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">{plan.description}</p>
              </div>
              <ul className="space-y-2 mb-6">
                {plan.features.map((f, i) => (
                  <li key={i} className="flex items-center gap-2 text-xs text-gray-300">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" className="text-emerald-400 flex-shrink-0">
                      <path d="M5 12l5 5L20 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    {f}
                  </li>
                ))}
              </ul>
              <Link href={plan.href}>
                <Button variant={plan.popular ? "primary" : "secondary"} className="w-full" size="md">
                  {plan.cta}
                </Button>
              </Link>
            </div>
          ))}
        </div>
      </div>
    </AppLayout>
  );
}

import { cn } from "@/lib/utils";

export function Card({
  children,
  className,
  hover = true,
}: {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border border-white/[0.06] bg-white/[0.02] backdrop-blur-sm p-5",
        "transition-all duration-300",
        hover && "hover:bg-white/[0.04] hover:border-white/[0.1] hover:shadow-lg hover:shadow-black/20",
        className
      )}
    >
      {children}
    </div>
  );
}

export function StatCard({
  label,
  value,
  change,
  icon,
  color = "text-foreground",
}: {
  label: string;
  value: string | number;
  change?: string;
  icon?: React.ReactNode;
  color?: string;
}) {
  return (
    <Card className="relative overflow-hidden group">
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
          <p className={cn("text-2xl font-semibold tracking-tight", color)}>
            {value}
          </p>
          {change && (
            <p className={cn(
              "text-xs font-medium",
              change.startsWith("+") ? "text-emerald-400" : change.startsWith("-") ? "text-red-400" : "text-muted-foreground"
            )}>
              {change}
            </p>
          )}
        </div>
        {icon && (
          <div className="text-muted-foreground/50 group-hover:text-muted-foreground transition-colors">
            {icon}
          </div>
        )}
      </div>
      <div className="absolute inset-0 bg-gradient-to-br from-white/[0.02] to-transparent pointer-events-none" />
    </Card>
  );
}

export function GlowCard({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn(
      "relative rounded-xl border border-white/[0.08] bg-white/[0.02] p-6",
      "before:absolute before:inset-0 before:rounded-xl before:bg-gradient-to-b before:from-emerald-500/5 before:to-transparent before:pointer-events-none",
      className
    )}>
      <div className="relative">{children}</div>
    </div>
  );
}

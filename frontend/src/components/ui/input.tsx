import { cn } from "@/lib/utils";
import { forwardRef } from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  icon?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, icon, className, ...props }, ref) => {
    return (
      <div className="space-y-1.5">
        {label && (
          <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </label>
        )}
        <div className="relative">
          {icon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
              {icon}
            </div>
          )}
          <input
            ref={ref}
            className={cn(
              "w-full h-9 rounded-lg bg-white/[0.03] border border-white/[0.08] text-sm text-foreground",
              "placeholder:text-muted-foreground/60",
              "focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500/40",
              "transition-all duration-200",
              icon ? "pl-9 pr-3" : "px-3",
              error && "border-red-500/40 focus:ring-red-500/20",
              className
            )}
            {...props}
          />
        </div>
        {error && <p className="text-[11px] text-red-400">{error}</p>}
      </div>
    );
  }
);

Input.displayName = "Input";

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: { value: string; label: string }[];
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, options, className, ...props }, ref) => {
    return (
      <div className="space-y-1.5">
        {label && (
          <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </label>
        )}
        <select
          ref={ref}
          className={cn(
            "w-full h-9 rounded-lg bg-white/[0.03] border border-white/[0.08] text-sm text-foreground",
            "focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500/40",
            "transition-all duration-200 px-3 appearance-none",
            "bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOCIgdmlld0JveD0iMCAwIDEyIDgiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0iTTEgMS41TDYgNi41TDExIDEuNSIgc3Ryb2tlPSIjNmI3MjgwIiBzdHJva2Utd2lkdGg9IjEuNSIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+PC9zdmc+')] bg-[length:12px] bg-[right_12px_center] bg-no-repeat",
            className
          )}
          {...props}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} className="bg-[#111]">
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    );
  }
);

Select.displayName = "Select";

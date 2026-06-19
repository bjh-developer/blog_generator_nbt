import Link from "next/link";

const ITEMS = [
  { label: "Home", href: "/" },
  { label: "Breakdowns", href: "/breakdowns" },
];

export function PillNav({ active = "Breakdowns" }: { active?: string }) {
  return (
    <nav className="sticky top-4 z-50 mx-auto mt-4 flex w-fit items-center gap-1 rounded-pill bg-white px-2 py-2 shadow-md">
      {ITEMS.map((it) => {
        const on = it.label === active;
        return (
          <Link
            key={it.label}
            href={it.href}
            className={`rounded-pill px-5 py-2 text-sm font-bold transition-colors ${
              on ? "bg-orange text-white" : "text-ink hover:bg-ink/5"
            }`}
          >
            {it.label}
          </Link>
        );
      })}
    </nav>
  );
}

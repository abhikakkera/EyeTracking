"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, loading, logout } = useAuth();

  // Hide the chrome during the full-screen activity.
  if (pathname?.startsWith("/run/")) return null;

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname?.startsWith(href);

  const loggedOut = [
    { href: "/about", label: "About" },
    { href: "/research", label: "Research" },
  ];
  const loggedIn = [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/history", label: "Results" },
    { href: "/about", label: "About" },
  ];
  const links = user ? loggedIn : loggedOut;

  function handleLogout() {
    logout();
    router.push("/");
  }

  return (
    <header className="nav">
      <div className="container nav-inner">
        <Link href={user ? "/dashboard" : "/"} className="brand">
          <span className="brand-mark" aria-hidden />
          Ocula
        </Link>

        <nav className="nav-links" aria-label="Primary">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`nav-link${isActive(l.href) ? " active" : ""}`}
            >
              {l.label}
            </Link>
          ))}

          {loading ? null : user ? (
            <>
              <Link href="/account" className="nav-link">
                Account
              </Link>
              <button className="nav-link always" onClick={handleLogout}>
                Log out
              </button>
              <Link className="btn btn-primary nav-cta" href="/test">
                Start session
              </Link>
            </>
          ) : (
            <>
              <Link href="/login" className="nav-link">
                Log in
              </Link>
              <Link className="btn btn-primary nav-cta" href="/signup">
                Sign up
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}

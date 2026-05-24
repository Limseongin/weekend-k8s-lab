import { Link, Outlet } from "react-router";
import { CameraIcon } from "./CameraIcon";

export function Layout() {
  return (
    <div className="app">
      <div className="promo-bar">
        Free worldwide shipping on orders over $500
      </div>
      <header className="site-header">
        <div className="site-header-inner">
          <Link to="/" className="brand">
            <span className="brand-mark">
              <CameraIcon />
            </span>
            <span className="brand-name">Aperture</span>
            <span className="brand-tagline">Pro Cameras &amp; Lenses</span>
          </Link>
          <nav className="site-nav" aria-label="Primary">
            <a href="#">Cameras</a>
            <a href="#">Lenses</a>
            <a href="#">Accessories</a>
          </nav>
        </div>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
      <footer className="site-footer">
        &copy; 2026 Aperture &middot; Built on a weekend k8s lab
      </footer>
    </div>
  );
}

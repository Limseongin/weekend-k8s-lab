import { useEffect, useState } from "react";
import { Link } from "react-router";
import { fetchProducts } from "../api";
import type { Product } from "../types";

export function Catalog() {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchProducts().then(setProducts).catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="error">Error: {error}</div>;
  if (!products) return <div className="loading">Loading…</div>;

  return (
    <div className="catalog">
      <h1>Cameras ({products.length})</h1>
      <div className="grid">
        {products.map((p) => (
          <Link key={p.id} to={`/products/${p.id}`} className="card">
            <img src={p.thumbnail} alt={p.name} loading="lazy" />
            <h2>{p.name}</h2>
            <p className="price">${(p.price_cents / 100).toFixed(2)}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}

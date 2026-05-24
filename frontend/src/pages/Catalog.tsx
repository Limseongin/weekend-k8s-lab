import { useEffect, useState } from "react";
import { Link } from "react-router";
import { fetchProducts } from "../api";
import { CameraIcon } from "../components/CameraIcon";
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
      <div className="catalog-header">
        <h1>All Cameras</h1>
        <span className="count">{products.length} products</span>
      </div>
      <div className="grid">
        {products.map((p) => (
          <Link key={p.id} to={`/products/${p.id}`} className="card">
            <div className="product-thumb">
              <CameraIcon />
            </div>
            <div className="card-body">
              <h2>{p.name}</h2>
              <p className="price">${(p.price_cents / 100).toFixed(2)}</p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { fetchProduct } from "../api";
import type { ProductDetail } from "../types";

export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setProduct(null);
    setError(null);
    fetchProduct(id)
      .then(setProduct)
      .catch((e) => setError(String(e)));
  }, [id]);

  if (error) return <div className="error">Error: {error}</div>;
  if (!product) return <div className="loading">Loading…</div>;

  return (
    <div className="detail">
      <Link to="/" className="back">← Back to catalog</Link>
      <div className="detail-main">
        <img src={product.thumbnail} alt={product.name} />
        <div>
          <h1>{product.name}</h1>
          <p className="price">${(product.price_cents / 100).toFixed(2)}</p>
          <p className="description">
            {product.description || <em>No description yet.</em>}
          </p>
        </div>
      </div>

      <section className="specs">
        <h2>Specs</h2>
        {product.specs.length === 0 ? (
          <p><em>No specs yet.</em></p>
        ) : (
          <div className="specs-grid">
            {product.specs.map((s) => (
              <div className="spec" key={s.key}>
                <span className="spec-key">{s.key}</span>
                <span className="spec-value">{s.value}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="reviews">
        <h2>Reviews ({product.reviews.length})</h2>
        {product.reviews.length === 0 ? (
          <p><em>No reviews yet.</em></p>
        ) : (
          <ul>
            {product.reviews.map((r, i) => (
              <li key={i}>
                <strong>{r.author}</strong> <span aria-label={`${r.rating} stars`}>★{r.rating}</span>
                <p>{r.body}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

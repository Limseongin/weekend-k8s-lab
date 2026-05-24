import type { Product, ProductDetail } from "./types";

export async function fetchProducts(): Promise<Product[]> {
  const r = await fetch("/api/products");
  if (!r.ok) throw new Error(`GET /api/products → ${r.status}`);
  return r.json();
}

export async function fetchProduct(id: string): Promise<ProductDetail> {
  const r = await fetch(`/api/products/${id}`);
  if (!r.ok) throw new Error(`GET /api/products/${id} → ${r.status}`);
  return r.json();
}

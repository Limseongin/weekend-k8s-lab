export type Product = {
  id: string;
  name: string;
  price_cents: number;
  thumbnail: string;
};

export type Spec = {
  key: string;
  value: string;
};

export type Review = {
  author: string;
  rating: number;
  body: string;
};

export type ProductDetail = Product & {
  description: string;
  specs: Spec[];
  reviews: Review[];
};

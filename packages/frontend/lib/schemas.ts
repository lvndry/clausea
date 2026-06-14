import { z } from "zod";

const verdictSchema = z.enum([
  "very_user_friendly",
  "user_friendly",
  "moderate",
  "pervasive",
  "very_pervasive",
]);

export const productSchema = z.looseObject({
  id: z.string(),
  name: z.string(),
  slug: z.string(),
  company_name: z.string().nullish(),
  description: z.string().nullish(),
  logo: z.string().nullish(),
  domains: z.array(z.string()).optional(),
  categories: z.array(z.string()).optional(),
});

export const productsPageSchema = z.object({
  items: z.array(productSchema),
  total: z.number(),
  page: z.number(),
  pages: z.number(),
});

export const productOverviewSchema = z.looseObject({
  product_name: z.string(),
  product_slug: z.string(),
  company_name: z.string().nullish(),
  verdict: verdictSchema,
  risk_score: z.number(),
  one_line_summary: z.string(),
});

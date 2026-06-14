import { z } from "zod";

export const verdictSchema = z.enum([
  "very_user_friendly",
  "user_friendly",
  "moderate",
  "pervasive",
  "very_pervasive",
]);
export type Verdict = z.infer<typeof verdictSchema>;

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
export type ProductSchema = z.infer<typeof productSchema>;

export const productsPageSchema = z.object({
  items: z.array(productSchema),
  total: z.number(),
  page: z.number(),
  pages: z.number(),
});
export type ProductsPageSchema = z.infer<typeof productsPageSchema>;

export const productOverviewSchema = z.looseObject({
  product_name: z.string(),
  product_slug: z.string(),
  company_name: z.string().nullish(),
  verdict: verdictSchema,
  risk_score: z.number(),
  one_line_summary: z.string(),
});
export type ProductOverviewSchema = z.infer<typeof productOverviewSchema>;

export const documentSummarySchema = z.looseObject({
  id: z.string(),
  title: z.string().nullish(),
  doc_type: z.string(),
  url: z.string(),
  verdict: verdictSchema.nullish(),
  risk_score: z.number().nullish(),
});
export type DocumentSummarySchema = z.infer<typeof documentSummarySchema>;

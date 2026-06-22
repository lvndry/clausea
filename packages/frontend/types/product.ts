export interface Product {
  id: string;
  name: string;
  company_name?: string | null;
  slug: string;
  description?: string | null;
  website?: string | null;
  logo?: string | null;
  categories?: string[];
  documentsCount?: number;
  domains?: string[];
  crawl_base_urls?: string[];
}

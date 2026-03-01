export interface Product {
  id: string;
  name: string;
  company_name?: string;
  slug: string;
  description?: string;
  website?: string;
  categories?: string[];
  documentsCount?: number;
  logo?: string;
  domains?: string[];
  crawl_base_urls?: string[];
}

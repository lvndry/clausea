import CompanyPage from "./product-page-client";
import { fetchProductPageCore } from "./product-page-server";

export default async function ProductPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { product, overview } = await fetchProductPageCore(slug);

  return (
    <CompanyPage
      key={slug}
      initialProduct={product}
      initialData={overview}
      initialExplainer={null}
      initialDocuments={[]}
      initialTopics={null}
    />
  );
}

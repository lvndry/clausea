import nextVitals from "eslint-config-next/core-web-vitals";
import eslintPluginReact from "eslint-plugin-react";
import { defineConfig, globalIgnores } from "eslint/config";

const eslintConfig = defineConfig([
  ...nextVitals,
  {
    plugins: {
      react: eslintPluginReact,
    },
    rules: {
      "react/no-unescaped-entities": "warn",
    },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);

export default eslintConfig;

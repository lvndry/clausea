module.exports = {
  trailingComma: "all",
  singleQuote: false,
  printWidth: 80,
  importOrder: ["^react$", "^react-dom$", "^@.(.*)$", "^[./]"],
  importOrderSeparation: true,
  importOrderSortSpecifiers: true,
  importOrderGroupNamespaceSpecifiers: true,
  plugins: ["@trivago/prettier-plugin-sort-imports"],
};

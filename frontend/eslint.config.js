import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // vite-plugin-react's fast refresh only survives a module that
      // exports components — flag the (usually accidental) mix of a
      // component and other exports in the same file.
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // This codebase's established convention for "deliberately unused"
      // (matches Python's leading-underscore convention, e.g. agent.py's
      // `lambda _ctx: ...`) — most often a prop that must be destructured
      // out before spreading the rest, or a key dropped via rest
      // destructuring (`const { [k]: _drop, ...rest } = obj`).
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", ignoreRestSiblings: true },
      ],
    },
  },
);

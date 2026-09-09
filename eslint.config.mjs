import tseslint from 'typescript-eslint';
export default tseslint.config({ignores:['node_modules/**','dist/**','.cache/**','.venv/**']}, ...tseslint.configs.recommended, {files:['**/*.ts','**/*.tsx'],rules:{'@typescript-eslint/no-unused-vars':['error',{argsIgnorePattern:'^_'}]}});

import { defineConfig } from 'vitest/config';

const headers = {
  'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' ws://127.0.0.1:5173 ws://127.0.0.1:8000 http://127.0.0.1:8000; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
  'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
};
export default defineConfig({root:'apps/web',  server:{host:'127.0.0.1',port:5173,strictPort:true,headers,fs:{allow:['../..']}},preview:{host:'127.0.0.1',port:5173,strictPort:true,headers},build:{outDir:'../../dist/web',emptyOutDir:true},test:{root:'.',include:['tests/unit/**/*.test.ts'],maxWorkers:1}});

import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'tests/e2e',timeout:70000,expect:{timeout:15000},workers:1,retries:0,reporter:[['list'],['json',{outputFile:'logs/playwright.json'}]],use:{baseURL:'http://127.0.0.1:5173',channel:'msedge',headless:true,viewport:{width:1440,height:1100},screenshot:'only-on-failure',trace:'retain-on-failure'},outputDir:'test-results'});


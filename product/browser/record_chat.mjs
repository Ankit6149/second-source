// Raw chat-flow recording: type a real instruction in the product chat,
// submit it, and show the genuine next step the app produces.
import { spawn } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const OUT = resolve('../.runs/ui-videos/chat');
await mkdir(OUT, { recursive: true });
const server = spawn('npx', ['vite', 'preview', '--port', '4174', '--host', '127.0.0.1'],
  { shell: true, stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
await sleep(5000);
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: OUT, size: { width: 1280, height: 720 } },
});
const page = await ctx.newPage();
await page.goto('http://127.0.0.1:4174/', { waitUntil: 'networkidle' });
await sleep(3000);
const input = page.locator('#promptInput');
await input.click();
await input.pressSequentially(
  'Investigate this application, understand its workflows and permissions, rebuild the supported functionality, and give me the code and an analysis report.',
  { delay: 34 });
await sleep(2000);
await input.press('Enter');
await sleep(6000);
await page.screenshot({ path: resolve(OUT, '../chat.png') });
await ctx.close();
await browser.close();
server.kill();
console.log('CHAT_RECORDED');

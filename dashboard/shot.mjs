import { chromium } from "playwright";

const browser = await chromium.launch();

const shots = [
  { path: "/", name: "overview-dark-desktop", width: 1440, height: 900 },
  { path: "/", name: "overview-dark-mobile", width: 390, height: 844 },
  { path: "/login", name: "login-dark-desktop", width: 1440, height: 900 },
];

for (const { path, name, width, height } of shots) {
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript(() => localStorage.setItem("theme", "dark"));
  const page = await context.newPage();
  await page.goto(`http://localhost:3000${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.screenshot({ path: `/tmp/screens/${name}.png` });
  await context.close();
}

await browser.close();
console.log("done");

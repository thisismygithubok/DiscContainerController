const puppeteer = require('puppeteer');
const path = require('path');

(async () => {
  // Launch headless Chrome
  const browser = await puppeteer.launch();

  // Open a new page
  const page = await browser.newPage();

  // Resolve the full file path to your generated HTML file (htop.html)
  const htmlPath = path.resolve(__dirname, '../htop.html');

  // Navigate to the local file URL
  await page.goto(`file://${htmlPath}`, { waitUntil: 'networkidle0' });

  // Take a full-page screenshot and save as htop.png
  await page.screenshot({ path: '../htop.png', fullPage: true });

  // Close the browser
  await browser.close();

  console.log('Screenshot taken and saved as htop.png');
})();

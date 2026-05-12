const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  // Ensure evidence directory exists
  if (!fs.existsSync('.sisyphus/evidence')) {
    fs.mkdirSync('.sisyphus/evidence', { recursive: true });
  }

  console.log('Navigating to page...');
  await page.goto('http://localhost:8000');
  
  // Wait for graph to load
  await page.waitForSelector('#cy canvas');
  await page.waitForTimeout(2000); // Wait for layout and edges

  // Scenario 4: Child count badges
  // We can't easily read canvas text, but we can take a screenshot
  console.log('Taking screenshot for Scenario 4 (Child count badges)...');
  await page.screenshot({ path: '.sisyphus/evidence/task-7-child-count-badges.png' });

  // Scenario 1: Sidebar opens
  console.log('Clicking a module node...');
  // We need to click a node. We can evaluate JS to trigger a tap on a code node.
  await page.evaluate(() => {
    const codeNodes = cy.nodes('[type="code"]');
    if (codeNodes.length > 0) {
      // Find one with children if possible
      let target = codeNodes[0];
      for (let i = 0; i < codeNodes.length; i++) {
        if (codeNodes[i].data('metadata') && codeNodes[i].data('metadata').total_children > 0) {
          target = codeNodes[i];
          break;
        }
      }
      target.emit('tap');
    }
  });
  
  await page.waitForSelector('#moduleSidebar.visible');
  await page.waitForTimeout(1000); // Wait for API fetch and render
  console.log('Taking screenshot for Scenario 1 (Sidebar opens)...');
  await page.screenshot({ path: '.sisyphus/evidence/task-7-sidebar-opens.png' });

  // Scenario 2: Highlight connections
  console.log('Clicking a function in sidebar...');
  await page.evaluate(() => {
    const fnItem = document.querySelector('.module-item');
    if (fnItem) fnItem.click();
  });
  await page.waitForTimeout(500); // Wait for highlight animation
  console.log('Taking screenshot for Scenario 2 (Highlight connections)...');
  await page.screenshot({ path: '.sisyphus/evidence/task-7-highlight-connections.png' });

  // Scenario 3: Sidebar closes
  console.log('Pressing Escape...');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500); // Wait for transition
  console.log('Taking screenshot for Scenario 3 (Sidebar closes)...');
  await page.screenshot({ path: '.sisyphus/evidence/task-7-sidebar-closes.png' });

  // Scenario 5: No regressions (Search)
  console.log('Testing search...');
  await page.fill('#searchInput', 'mimir');
  await page.click('button:has-text("Search")');
  await page.waitForSelector('#resultsPanel.visible');
  await page.waitForTimeout(1000);
  console.log('Taking screenshot for Scenario 5 (No regressions)...');
  await page.screenshot({ path: '.sisyphus/evidence/task-7-no-regressions.png' });

  await browser.close();
  console.log('Done!');
})();

import { expect, test } from '@playwright/test';

const diagnostics: string[] = [];

test.beforeEach(async ({ page }) => {
  diagnostics.length = 0;
  page.on('console', (message) => {
    if (message.type() === 'error') diagnostics.push(`console: ${message.text()}`);
  });
  page.on('pageerror', (error) => diagnostics.push(`pageerror: ${error.message}`));
  page.on('requestfailed', (request) => {
    diagnostics.push(`requestfailed: ${request.method()} ${request.url()} ${request.failure()?.errorText ?? ''}`);
  });
  page.on('response', (response) => {
    if (response.url().includes('/api/') && response.status() >= 400) {
      diagnostics.push(`HTTP ${response.status()}: ${response.request().method()} ${response.url()}`);
    }
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Evidence, in context.' })).toBeVisible();
  await expect(page.getByLabel('Sample scenario')).toBeEnabled();
});

test.afterEach(async ({}, testInfo) => {
  console.log(`[browser-diagnostics: ${testInfo.title}] ${diagnostics.length ? diagnostics.join(' | ') : 'No console errors, uncaught exceptions, failed requests, or API HTTP failures observed.'}`);
  await testInfo.attach('browser-diagnostics', {
    body: diagnostics.length ? diagnostics.join('\n') : 'No console errors, uncaught exceptions, failed requests, or API HTTP failures observed.',
    contentType: 'text/plain',
  });
});

test('core upload and audit workflow works with external browser requests blocked', async ({ page }, testInfo) => {
  const blocked: string[] = [];
  const succeeded: string[] = [];
  const requestsSeen: string[] = [];
  page.on('response', response => {
    const url = new URL(response.url());
    const appOrigin = new URL(testInfo.project.use.baseURL as string).origin;
    if (url.origin !== appOrigin && url.origin !== 'http://127.0.0.1:8001') succeeded.push(response.url());
  });
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    requestsSeen.push(`${route.request().method()} ${url.href} (${route.request().resourceType()})`);
    const appOrigin = new URL(testInfo.project.use.baseURL as string).origin;
    const local = url.origin === appOrigin || url.origin === 'http://127.0.0.1:8001';
    if (!local) { blocked.push(route.request().url()); await route.abort('blockedbyclient'); return; }
    await route.continue();
  });
  await page.reload();
  await expect(page.getByLabel('Sample scenario')).toBeEnabled();
  await page.getByLabel('Answer under review').fill('The garden trial ended after four weeks.');
  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Upload documents' }).click();
  await (await chooserPromise).setFiles('e2e/fixtures/evidence.pdf');
  await expect(page.getByLabel('Source text evidence.pdf')).toHaveValue(/The garden trial ended after four weeks\./);
  const audit = page.waitForResponse(r => r.url().includes('/api/audit') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run audit' }).click();
  expect((await audit).status()).toBe(200);
  await expect(page.locator('.summary-stats .stat.supported strong')).toHaveText('1');
  expect(succeeded).toEqual([]);
  expect(requestsSeen.some(request => request.includes('/api/extract-document'))).toBeTruthy();
  expect(requestsSeen.some(request => request.includes('/api/audit'))).toBeTruthy();
  console.log(`[network-isolation] browser requests observed: ${requestsSeen.length}; successful external requests: ${succeeded.length}; blocked external attempts: ${blocked.length}`);
});

test('Phase 5C mutation, receipt, pending evaluation, repair refusal and compare workflows', async ({ page }) => {
  await page.getByLabel('Answer under review').fill('The report lists 48 volunteers.');
  await page.getByLabel(/^Source text /).first().fill('The report lists 48 volunteers.');
  await page.getByRole('button', { name: 'Run audit' }).click();
  await expect(page.getByRole('heading', { name: 'Custom input review' })).toBeVisible();
  const mutation = page.getByLabel('Mutation', { exact: true });
  await expect(mutation.locator('option', { hasText: 'Change claim number' })).toHaveCount(1);
  await mutation.selectOption('number.claim');
  await page.getByLabel('Exact text to change').fill('48');
  await page.getByLabel('Replacement text').fill('84');
  await page.getByRole('button', { name: 'Preview and run mutation' }).click();
  await expect(page.getByRole('heading', { name: 'Change claim number' })).toBeVisible();
  await expect(page.locator('.outcome-badge')).toHaveText('EXPECTED OBSERVED');
  await expect(page.getByText(/claim-1: CONTRADICTED/)).toBeVisible();
  await page.getByRole('button', { name: 'Load Blind-Spot Map' }).click();
  await expect(page.getByText(/Independently authored held-out cases are pending/)).toBeVisible();
  await page.getByRole('button', { name: 'Check safe repair' }).click();
  await expect(page.getByRole('heading', { name: 'Conservative repair preview' })).toBeVisible();
  await expect(page.getByText(/did not establish a localized numeric\/date contradiction/)).toBeVisible();
  await page.getByRole('button', { name: 'Re-run and compare' }).click();
  await expect(page.getByRole('heading', { name: 'Re-run comparison' })).toBeVisible();
  page.once('dialog', dialog => dialog.accept());
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export audit receipt' }).click();
  expect((await download).suggestedFilename()).toBe('refutella-audit-receipt.json');
});

test('claim challenge uses the declared comparison and reset clears session tally', async ({ page }) => {
  await page.getByLabel('Answer under review').fill('The report lists 48 volunteers.');
  await page.getByLabel(/^Source text /).first().fill('The report lists 48 volunteers.');
  await page.getByRole('button', { name: 'Run audit' }).click();
  await page.getByLabel('Mutation', { exact: true }).selectOption('number.claim');
  await page.getByLabel('Exact text to change').fill('48');
  await page.getByLabel('Replacement text').fill('84');
  await page.getByRole('button', { name: 'Preview and run mutation' }).click();
  await expect(page.locator('.scoreboard')).toContainText('1');
  await expect(page.locator('.score-total')).toContainText('1');
  await expect(page.locator('.scoreboard')).toContainText('Completed runs');
  await expect(page.getByRole('list', { name: 'Challenge history' }).getByText(/CAUGHT/)).toBeVisible();
  await page.getByRole('button', { name: 'Reset challenge session' }).click();
  await expect(page.locator('.score-total')).toContainText('0');
  await expect(page.locator('.scoreboard')).toContainText('Completed runs');
});

test('curated false support and untestable challenge runs earn no points and reset clears all history', async ({ page }) => {
  await page.getByLabel('Answer under review').fill('The report lists 48 volunteers.');
  await page.getByLabel(/^Source text /).first().fill('The report lists 48 volunteers.');
  await page.getByRole('button', { name: 'Run audit' }).click();
  await page.getByRole('button', { name: 'Run challenge' }).nth(2).click();
  await expect(page.locator('.scoreboard')).toContainText('FALSE_SUPPORT');
  await expect(page.locator('.score-total')).toContainText('0');
  await expect(page.locator('.scoreboard')).toContainText('Completed runs');
  await expect(page.getByText(/claim-1: SUPPORTED/)).toBeVisible();

  await page.getByLabel('Mutation', { exact: true }).selectOption('paraphrase.claim');
  await page.getByLabel('Replacement claim').fill('A newly worded statement with unknown meaning.');
  await page.getByRole('button', { name: 'Preview and run mutation' }).click();
  await expect(page.locator('.mutation-result')).toContainText('UNTESTABLE');
  await expect(page.locator('.score-total')).toContainText('0');
  await expect(page.getByRole('list', { name: 'Challenge history' }).getByText(/FALSE_SUPPORT/)).toBeVisible();
  await expect(page.getByRole('list', { name: 'Challenge history' }).getByText(/UNTESTABLE/)).toBeVisible();

  await page.getByRole('button', { name: 'Reset challenge session' }).click();
  await expect(page.locator('.score-total')).toContainText('0');
  await expect(page.getByRole('list', { name: 'Challenge history' })).toHaveCount(0);
});

test('mutation challenge cards stay distinct and fit a narrow viewport', async ({ page }) => {
  await expect(page.getByRole('heading', { name: 'Mutation & Reliability' })).toBeVisible();
  await expect(page.getByText('Select a mutation to see its description, preconditions, and controls.')).toBeVisible();
  await expect(page.locator('.challenge-card')).toHaveCount(3);
  await expect(page.locator('.challenge-card').nth(0)).toContainText('Expected');
  await expect(page.locator('.challenge-card').nth(0)).toContainText('Not run');
  await page.setViewportSize({ width: 390, height: 844 });
  const widths = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: document.documentElement.clientWidth }));
  expect(widths.document).toBeLessThanOrEqual(widths.viewport);
  await expect(page.locator('.challenge-card')).toHaveCount(3);
});

test('preview-bound repair approval applies only the proposed answer and clears old audit', async ({ page }) => {
  await page.getByLabel('Answer under review').fill('The report lists 84 volunteers.');
  await page.getByLabel(/^Source text /).first().fill('The report lists 48 volunteers.');
  await page.getByRole('button', { name: 'Run audit' }).click();
  await page.getByRole('button', { name: 'Check safe repair' }).click();
  await expect(page.getByRole('heading', { name: 'Conservative repair preview' })).toBeVisible();
  await expect(page.getByText('After: 48')).toBeVisible();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Approve and apply repair' }).click();
  await expect(page.getByLabel('Answer under review')).toHaveValue('The report lists 48 volunteers.');
  await expect(page.getByText('Your findings will appear here')).toBeVisible();
  await expect(page.getByRole('button', { name: /Run audit/ })).toBeEnabled();
});

test('captures reviewed demo screenshots at laptop and mobile sizes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: '../docs/qa-screenshots/after-initial-workspace-1440.png', fullPage: true });

  await page.getByLabel('Answer under review').fill('The garden trial ended after four weeks.');
  await page.getByLabel(/^Source text /).first().fill('The garden trial ended after four weeks. The field was close to the river.');
  await page.getByRole('button', { name: 'Run audit' }).click();
  await expect(page.getByRole('heading', { name: 'Custom input review' })).toBeVisible();
  await page.getByRole('button', { name: /The garden trial ended after four weeks/ }).click();
  await page.screenshot({ path: '../docs/qa-screenshots/after-custom-evidence-trace-1440.png', fullPage: true });

  await page.getByRole('button', { name: '+ Add source' }).click();
  await page.getByLabel('Source title').last().fill('Second field note');
  await page.getByLabel(/^Source text /).last().fill('An independent field note with no duration detail.');
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.screenshot({ path: '../docs/qa-screenshots/after-source-management-1280.png', fullPage: true });

  await page.getByLabel('Sample scenario').selectOption({ label: 'Harbor field study' });
  while (await page.getByRole('button', { name: /^Remove source/ }).count()) {
    await page.getByRole('button', { name: /^Remove source/ }).first().click();
  }
  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Upload documents' }).click();
  await (await chooserPromise).setFiles('e2e/fixtures/evidence.pdf');
  await expect(page.getByLabel('Source text evidence.pdf')).toHaveValue(/The garden trial ended after four weeks\./);
  await page.screenshot({ path: '../docs/qa-screenshots/after-uploaded-document-1280.png', fullPage: true });
  await page.getByLabel('Answer under review').fill('The garden trial ended after four weeks.');
  await page.getByRole('button', { name: 'Run audit' }).click();
  await page.getByRole('heading', { name: 'Evidence Stress Lab' }).scrollIntoViewIfNeeded();
  await page.getByRole('combobox', { name: 'Source' }).selectOption({ index: 1 });
  await page.getByRole('combobox', { name: 'Change' }).selectOption('REMOVE_PASSAGE');
  await page.getByRole('combobox', { name: 'Retrieved passage' }).selectOption({ index: 1 });
  await page.getByRole('button', { name: 'Run experiment' }).click();
  await expect(page.locator('.stress-results')).toBeVisible();
  await page.screenshot({ path: '../docs/qa-screenshots/after-stress-lab-1280.png', fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: '../docs/qa-screenshots/after-mobile-workspace-390.png', fullPage: true });
});

test('all scenarios load canonical fixture inputs and consistent claim totals', async ({ page }) => {
  const scenarios = ['Harbor field study', 'Library notice', 'Garden trial summary'];
  const selector = page.getByLabel('Sample scenario');
  for (const scenario of scenarios) {
    await selector.selectOption({ label: scenario });
    await expect(page.getByText(`Canonical fixture: ${scenario}`)).toBeVisible();
    await expect(page.getByText('Fixture mode', { exact: true }).first()).toBeVisible();
    const claims = page.locator('.claim-row');
    const claimCount = await claims.count();
    expect(claimCount).toBeGreaterThan(0);
    const totals = await page.locator('.summary-stats .stat strong').allTextContents();
    expect(totals.reduce((sum, value) => sum + Number(value), 0)).toBe(claimCount);
    const expectedTotals: Record<string, string[]> = {
      'Harbor field study': ['1', '1', '1', '0', '0'],
      'Library notice': ['1', '1', '1', '0', '0'],
      'Garden trial summary': ['1', '0', '0', '1', '0'],
    };
    expect(totals).toEqual(expectedTotals[scenario]);
    await claims.last().click();
    await expect(page.getByRole('heading', { name: 'Why this finding?' })).toBeVisible();
    await expect(page.getByText('Quote validation checks that text exists at these offsets. It does not prove the claim is true.')).toBeVisible();
  }
  await page.reload();
  await expect(page.getByText('Canonical fixture: Harbor field study')).toBeVisible();
  await page.getByLabel('Answer under review').fill('Edited for restore check.');
  await page.getByRole('button', { name: 'Restore scenario' }).click();
  await expect(page.getByText('Canonical fixture: Harbor field study')).toBeVisible();
  await expect(page.getByLabel('Answer under review')).toHaveValue(/The study began on 12 June 2025/);
});

test('empty added sources disable audit; populated sources work through the documented eight-source limit', async ({ page }) => {
  const add = page.getByRole('button', { name: '+ Add source' });
  const run = page.getByRole('button', { name: 'Run audit' });
  const sourceCount = page.locator('.source-count');
  let count = 1;
  for (let target = 2; target <= 8; target++) {
    await add.click();
    count++;
    await expect(sourceCount).toHaveText(`${count} / 8 sources`);
    await expect(run).toBeDisabled();
    if (target === 2) await expect(page.getByRole('status')).toHaveText('Source 2 is missing its text.');
    const sourceFields = page.getByLabel(/^Source text /);
    if (target === 2) {
      await sourceFields.last().fill('   ');
      await expect(run).toBeDisabled();
      await expect(page.getByRole('status')).toHaveText('Source 2 is missing its text.');
    }
    await sourceFields.last().fill(`Additional test document ${target} has no relevant details.`);
    await expect(run).toBeEnabled();
    if (target === 2) await expect(page.getByRole('status')).toHaveCount(0);
  }
  await expect(add).toBeDisabled();
  await run.click();
  await expect(page.getByRole('heading', { name: 'Custom input review' })).toBeVisible();
  await expect(page.getByText('Evidence-based baseline', { exact: true }).first()).toBeVisible();
  expect(diagnostics.filter((line) => line.includes('POST') && line.includes('/api/audit'))).toHaveLength(0);
});

test('custom audit supports claim inspection and all three stress operations', async ({ page }) => {
  await page.getByLabel('Answer under review').fill('The garden trial ended after four weeks.');
  await page.getByLabel(/^Source text /).fill('The garden trial ended after four weeks. The site was near the river.');
  const auditResponsePromise = page.waitForResponse((response) => response.url().includes('/api/audit') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run audit' }).click();
  const auditResponse = await auditResponsePromise;
  expect(auditResponse.status()).toBe(200);
  const audit = await auditResponse.json();
  expect(audit.execution_mode).toBe('BASELINE');
  expect(audit.summary.total_claims).toBe(audit.claims.length);
  expect(audit.summary.supported + audit.summary.contradicted + audit.summary.insufficient_evidence + audit.summary.ambiguous).toBe(audit.claims.length);
  for (const item of audit.claims) {
    expect(audit.answer.slice(item.start_offset, item.end_offset)).toBe(item.claim_text);
    for (const evidence of item.evidence) {
      const sourceDoc = audit.sources.find((sourceItem: { source_id: string }) => sourceItem.source_id === evidence.source_id);
      expect(sourceDoc.text.slice(evidence.start_offset, evidence.end_offset)).toBe(evidence.quote);
      expect(evidence.quotation_validated).toBe(true);
    }
  }
  await expect(page.getByRole('heading', { name: 'Custom input review' })).toBeVisible();
  const claim = page.getByRole('button', { name: /The garden trial ended after four weeks/ });
  await expect(claim).toContainText('Supported');
  await claim.click();
  await expect(page.locator('.quote-card blockquote').first()).toContainText('The garden trial ended after four weeks.');

  const runExperiment = page.getByRole('button', { name: 'Run experiment' });
  await page.getByRole('heading', { name: 'Evidence Stress Lab' }).scrollIntoViewIfNeeded();
  await page.getByRole('combobox', { name: 'Source' }).selectOption({ index: 1 });
  await page.getByRole('combobox', { name: 'Change' }).selectOption('REMOVE_PASSAGE');
  await page.getByRole('combobox', { name: 'Retrieved passage' }).selectOption({ index: 1 });
  await runExperiment.click();
  await expect(page.getByText('Removed passage', { exact: false }).first()).toBeVisible();
  await expect(page.getByText(/Baseline evidence/)).toBeVisible();
  await expect(page.locator('.stress-verdict')).toContainText('UNRESOLVED');

  await page.getByRole('combobox', { name: 'Change' }).selectOption('EDIT_PASSAGE');
  await page.getByLabel('Replacement text').fill('The trial lasted around one month.');
  await runExperiment.click();
  await expect(page.locator('.stress-change')).toContainText('The trial lasted around one month.');
  await expect(page.locator('.stress-verdict')).toContainText('UNRESOLVED');

  await page.getByRole('combobox', { name: 'Change' }).selectOption('REMOVE_SOURCE');
  await runExperiment.click();
  await expect(page.getByText(/Removed source/)).toBeVisible();
  await expect(page.locator('.stress-verdict')).toContainText('NOT_COMPARABLE');
  expect(diagnostics.some((line) => line.startsWith('pageerror:'))).toBeFalsy();
});

test('input edits clear stale results and whitespace blocks submission', async ({ page }) => {
  const answer = page.getByLabel('Answer under review');
  const run = page.getByRole('button', { name: 'Run audit' });
  await answer.fill('   ');
  await expect(run).toBeDisabled();
  await expect(page.getByRole('heading', { name: 'Your findings will appear here' })).toBeVisible();
  await answer.fill('A Unicode example: café 🌱.');
  await expect(run).toBeEnabled();
  await run.click();
  await expect(page.getByRole('heading', { name: 'Custom input review' })).toBeVisible();
  await expect(page.getByRole('button', { name: /A Unicode example/ })).toBeVisible();
  await page.getByLabel('Source title').fill('Renamed note');
  await expect(page.getByRole('heading', { name: 'Your findings will appear here' })).toBeVisible();
  await expect(run).toBeEnabled();
  await answer.fill('!!!');
  await expect(run).toBeEnabled();
  await run.click();
  await expect(page.locator('.claim-row')).toHaveCount(1);
  await expect(page.locator('.claim-row').first()).toContainText('!!!');
  await expect(page.locator('.summary-stats .stat.insufficient_evidence strong')).toHaveText('1');
});

test('conflicting, contradictory, exact, and missing custom claims follow the documented baseline rules', async ({ page }) => {
  const answer = page.getByLabel('Answer under review');
  const sourceTexts = page.getByLabel(/^Source text /);
  const run = page.getByRole('button', { name: 'Run audit' });
  await answer.fill('The office is open on Monday.');
  await sourceTexts.first().fill('The office is open on Monday.');
  await page.getByRole('button', { name: '+ Add source' }).click();
  await sourceTexts.last().fill('The office is not open on Monday.');
  await run.click();
  await expect(page.locator('.summary-stats .stat.ambiguous strong')).toHaveText('1');

  await answer.fill('The review was completed in 2025.');
  await sourceTexts.first().fill('The review was completed in 2024.');
  await sourceTexts.last().fill('The review was completed in 2024.');
  await run.click();
  await expect(page.locator('.summary-stats .stat.contradicted strong')).toHaveText('1');

  await answer.fill('The notice lists the reviewer’s favorite color.');
  await sourceTexts.first().fill('The review was completed in 2024.');
  await sourceTexts.last().fill('The review was completed in 2024.');
  await run.click();
  await expect(page.locator('.summary-stats .stat.insufficient_evidence strong')).toHaveText('1');
  await expect(page.getByText('Lexical retrieval discovers passages; it does not prove claims. No model was used.')).toBeVisible();
});

test('workspace header labels are noninteractive and layout remains usable at laptop width', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await expect(page.getByLabel('Answer under review')).toBeVisible();
  await expect(page.getByText('Workspace', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Project menu' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'refutella.' })).toHaveCount(0);
  await expect(page.getByText('Claim order · original answer')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Evidence, in context.' })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await expect(page.getByLabel('Answer under review')).toBeVisible();
});

test('native chooser uploads TXT, PDF and DOCX into editable audit sources', async ({ page }) => {
  const scenario = page.getByLabel('Sample scenario');
  await scenario.selectOption({ label: 'Harbor field study' });
  while (await page.getByRole('button', { name: /^Remove source/ }).count()) {
    await page.getByRole('button', { name: /^Remove source/ }).first().click();
  }
  const answer = page.getByLabel('Answer under review');
  await answer.fill('The garden trial ended after four weeks.');

  for (const [filename, type] of [
    ['evidence.txt', 'TXT'],
    ['evidence.pdf', 'PDF'],
    ['evidence.docx', 'DOCX'],
  ]) {
    const chooserPromise = page.waitForEvent('filechooser');
    await page.getByRole('button', { name: 'Upload documents' }).click();
    const chooser = await chooserPromise;
    await chooser.setFiles(`e2e/fixtures/${filename}`);
    const sourceText = page.getByLabel(`Source text ${filename}`);
    await expect(sourceText).toHaveValue(/The garden trial ended after four weeks\./);
    await expect(page.locator('.source-id').filter({ hasText: type })).toBeVisible();
    await sourceText.fill('The garden trial ended after four weeks. The fieldwork ended in June.');
    await page.getByRole('button', { name: '+ Add source' }).click();
    await page.getByLabel('Source title').last().fill('Manual corroboration');
    await page.getByLabel(/^Source text /).last().fill('The fieldwork was documented near the river.');
    await expect(page.locator('.source-count')).toHaveText('2 / 8 sources');
    const auditResponsePromise = page.waitForResponse(response => response.url().includes('/api/audit') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Run audit' }).click();
    const auditResponse = await auditResponsePromise;
    expect(auditResponse.status()).toBe(200);
    const audit = await auditResponse.json();
    expect(audit.execution_mode).toBe('BASELINE');
    expect(audit.sources[0].title).toBe(filename);
    expect(audit.sources[0].text).toContain('The garden trial ended after four weeks.');
    await expect(page.locator('.summary-stats .stat.supported strong')).toHaveText('1');
    await page.getByRole('button', { name: `Remove source ${filename}` }).click();
    await expect(page.locator('.source-count')).toHaveText('1 / 8 sources');
    await expect(page.getByLabel('Source title').first()).toHaveValue('Manual corroboration');
    await page.getByRole('button', { name: /^Remove source Manual corroboration$/ }).click();
    await expect(page.locator('.source-count')).toHaveText('0 / 8 sources');
    await expect(page.getByRole('heading', { name: 'Your findings will appear here' })).toBeVisible();
  }
});

test('drag and drop and multi-file selection add documents sequentially', async ({ page }) => {
  await page.getByLabel('Sample scenario').selectOption({ label: 'Harbor field study' });
  while (await page.getByRole('button', { name: /^Remove source/ }).count()) {
    await page.getByRole('button', { name: /^Remove source/ }).first().click();
  }
  await page.getByLabel('Answer under review').fill('The garden trial ended after four weeks.');
  await page.locator('.upload-dropzone').evaluate((zone, text) => {
    const transfer = new DataTransfer();
    transfer.items.add(new File([text], 'dropped.txt', { type: 'text/plain' }));
    zone.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: transfer }));
  }, 'The garden trial ended after four weeks.');
  await expect(page.getByLabel('Source text dropped.txt')).toHaveValue('The garden trial ended after four weeks.');
  await page.getByRole('button', { name: /^Remove source dropped.txt$/ }).click();
  await page.getByLabel('Upload source documents').setInputFiles(['e2e/fixtures/evidence.txt', 'e2e/fixtures/evidence.pdf']);
  await expect(page.locator('.source-count')).toHaveText('2 / 8 sources');
  await expect(page.getByLabel('Source text evidence.txt')).toHaveValue(/The garden trial ended after four weeks\./);
  await expect(page.getByLabel('Source text evidence.pdf')).toHaveValue(/The garden trial ended after four weeks\./);
});

test('switching scenarios clears uploaded documents and restores fixture sources', async ({ page }) => {
  await page.getByLabel('Sample scenario').selectOption({ label: 'Library notice' });
  await page.getByLabel('Sample scenario').selectOption({ label: 'Harbor field study' });
  while (await page.getByRole('button', { name: /^Remove source/ }).count()) {
    await page.getByRole('button', { name: /^Remove source/ }).first().click();
  }
  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Upload documents' }).click();
  await (await chooserPromise).setFiles('e2e/fixtures/evidence.txt');
  await expect(page.getByLabel('Source title')).toHaveValue('evidence.txt');
  await page.getByLabel('Sample scenario').selectOption({ label: 'Garden trial summary' });
  await expect(page.getByText('Canonical fixture: Garden trial summary')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Remove source evidence.txt' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Restore scenario' })).toHaveCount(0);
  await expect(page.getByText('Fixture mode', { exact: true }).first()).toBeVisible();
});

test('invalid upload keeps current sources and reports a useful error', async ({ page }) => {
  const existingText = await page.getByLabel(/^Source text /).first().inputValue();
  const failure = page.waitForResponse(response => response.url().includes('/api/extract-document') && response.status() === 415);
  await page.getByLabel('Upload source documents').setInputFiles('e2e/fixtures/unsupported.rtf');
  expect((await failure).status()).toBe(415);
  await expect(page.getByRole('alert')).toContainText('Upload a .txt, .pdf, or .docx file.');
  await expect(page.getByLabel(/^Source text /).first()).toHaveValue(existingText);
  await expect(page.getByRole('heading', { name: 'Harbor field study' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run audit' })).toBeEnabled();
});

test('manual and uploaded sources share the eight-source limit', async ({ page }) => {
  await page.getByLabel('Sample scenario').selectOption({ label: 'Harbor field study' });
  while (await page.getByRole('button', { name: /^Remove source/ }).count()) {
    await page.getByRole('button', { name: /^Remove source/ }).first().click();
  }
  await page.getByLabel('Answer under review').fill('A custom source claim.');
  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Upload documents' }).click();
  await (await chooserPromise).setFiles('e2e/fixtures/evidence.txt');
  for (let index = 2; index <= 8; index++) {
    await page.getByRole('button', { name: '+ Add source' }).click();
    await page.getByLabel('Source title').last().fill(`Manual ${index}`);
    await page.getByLabel(/^Source text /).last().fill(`Manual evidence document ${index}.`);
  }
  await expect(page.locator('.source-count')).toHaveText('8 / 8 sources');
  await expect(page.getByRole('button', { name: 'Upload documents' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '+ Add source' })).toBeDisabled();
});

test('real API validation returns 422 details and the UI reports transport failure', async ({ page }) => {
  const health = await page.evaluate(async () => {
    const response = await fetch('/api/health');
    return { status: response.status, body: await response.json() };
  });
  expect(health.status).toBe(200);
  expect(health.body.service).toBe('refutella-api');
  expect(health.body.phase).toBe(5);
  expect(health.body.subphase).toBe('5C');
  const invalid = await page.evaluate(async () => {
    const response = await fetch('/api/audit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer: '   ', sources: [{ source_id: 'valid', title: 'Note', text: 'Some text.' }] }),
    });
    return { status: response.status, body: await response.json() };
  });
  expect(invalid.status).toBe(422);
  expect(invalid.body.detail).toBeTruthy();

  const duplicate = await page.evaluate(async () => {
    const source = { source_id: 'same', title: 'Note', text: 'Some text.' };
    const response = await fetch('/api/audit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer: 'A claim.', sources: [source, source] }),
    });
    return { status: response.status, body: await response.json() };
  });
  expect(duplicate.status).toBe(422);

  const sourceBoundaries = await page.evaluate(async () => {
    const sources = Array.from({ length: 8 }, (_, index) => ({
      source_id: `source-${index + 1}`, title: `Source ${index + 1}`, text: `Document ${index + 1}.`,
    }));
    async function auditCount(selected: typeof sources) {
      const response = await fetch('/api/audit', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer: 'A claim.', sources: selected }),
      });
      return response.status;
    }
    return { eight: await auditCount(sources), nine: await auditCount([...sources, { source_id: 'source-9', title: 'Source 9', text: 'Document 9.' }]) };
  });
  expect(sourceBoundaries.eight).toBe(200);
  expect(sourceBoundaries.nine).toBe(422);

  const tooLong = await page.evaluate(async () => {
    const response = await fetch('/api/audit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer: 'x'.repeat(20_001), sources: [{ source_id: 'one', title: 'Note', text: 'A note.' }] }),
    });
    return response.status;
  });
  expect(tooLong).toBe(422);

  const badStress = await page.evaluate(async () => {
    const auditResponse = await fetch('/api/audit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer: 'The garden trial ended after four weeks.', sources: [{ source_id: 'valid', title: 'Note', text: 'The garden trial ended after four weeks.' }] }),
    });
    const baseline = await auditResponse.json();
    const response = await fetch('/api/stress-experiment', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ baseline, operation: 'REMOVE_SOURCE', source_id: 'missing' }),
    });
    return { status: response.status, body: await response.json() };
  });
  expect(badStress.status).toBe(422);
  expect(badStress.body.detail).toContain('Unknown source_id');

  await page.route('**/api/audit', (route) => route.abort());
  await page.getByLabel('Answer under review').fill('A network error recovery check.');
  await page.getByRole('button', { name: 'Run audit' }).click();
  await expect(page.getByRole('alert')).toContainText('Refutella API is unavailable');
  await expect(page.getByRole('button', { name: 'Run audit' })).toBeEnabled();
  await page.unroute('**/api/audit');
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Custom input review' })).toBeVisible();
});

test('claim triage is visible, overridable, and source labels are readable', async ({ page }) => {
  await page.getByLabel('Sample scenario').selectOption({ label: 'Garden trial summary' });
  await page.getByLabel('Answer under review').fill('What color was the garden?');
  await page.getByRole('button', { name: 'Run audit' }).click();
  await expect(page.locator('.claim-row')).toContainText('Not assessed');
  await expect(page.locator('.triage-reason')).toContainText('Question detected; no factual assertion was evaluated.');
  await expect(page.getByText('S1', { exact: true }).first()).toBeVisible();
  await page.getByText('Include in audit').click();
  await expect(page.locator('.claim-row')).not.toContainText('Not assessed');
});

test('evidence matrix switches claims and receipt can select exact source offsets', async ({ page }) => {
  await page.getByLabel('Answer under review').fill('The café opened in 2024.');
  await page.getByLabel(/^Source text /).first().fill('The café opened in 2023.');
  await page.getByRole('button', { name: 'Run audit' }).click();
  await expect(page.getByRole('heading', { name: 'Evidence matrix' })).toBeVisible();
  await expect(page.getByText('Search Receipt · RETRIEVED')).toBeVisible();
  await expect(page.getByText('Localized mismatch')).toBeVisible();
  await page.getByText('Localized mismatch').click();
  await page.getByRole('button', { name: 'Show source mismatch' }).click();
  await expect(page.locator('.mismatch-localization mark').first()).toHaveText('2024');
  const source = page.getByLabel(/^Source text /).first();
  const sourceSelection = await source.evaluate((element: HTMLTextAreaElement) => element.value.slice(element.selectionStart, element.selectionEnd));
  expect(sourceSelection).toBe('2023');
  await page.getByText('Search Receipt · RETRIEVED').click();
  await expect(page.getByText('CONTRADICTION_RULE')).toBeVisible();
  await page.screenshot({ path: '../docs/qa-screenshots/phase5b-search-receipt-matrix-1440.png', fullPage: true });
  const show = page.getByRole('button', { name: 'Show in source' }).first();
  await show.click();
  const sourceText = page.getByLabel(/^Source text /).first();
  const selection = await sourceText.evaluate((element: HTMLTextAreaElement) => element.value.slice(element.selectionStart, element.selectionEnd));
  expect(selection).toBe('The café opened in 2023.');
  await expect(page.getByRole('region', { name: 'Claim and source evidence matrix' })).toBeVisible();
});

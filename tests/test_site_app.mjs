import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';


test('renders the published story without using a stale index', async () => {
  const app = await readFile(new URL('../site/app.js', import.meta.url), 'utf8');
  const index = JSON.parse(
    await readFile(new URL('../site/stories.json', import.meta.url), 'utf8'),
  );
  const elements = new Map([
    ['#story-count', { textContent: '' }],
    ['#world-count', { textContent: '' }],
    ['#thread-count', { textContent: '' }],
    ['#stories', { innerHTML: '' }],
  ]);
  let fetchOptions;
  const document = {
    querySelector(selector) {
      return elements.get(selector);
    },
    createElement() {
      let text = '';
      return {
        set textContent(value) {
          text = String(value);
        },
        get innerHTML() {
          return text
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
        },
      };
    },
  };
  const fetch = async (_path, options) => {
    fetchOptions = options;
    return { json: async () => structuredClone(index) };
  };

  vm.runInNewContext(app, { document, fetch, Set });
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(fetchOptions.cache, 'no-store');
  assert.deepEqual(Object.keys(fetchOptions), ['cache']);
  assert.equal(elements.get('#story-count').textContent, 1);
  assert.match(
    elements.get('#stories').innerHTML,
    /沉默联播：从地核空腔到星空/,
  );
});

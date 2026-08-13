import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';


test('renders the published story without using a stale index', async () => {
  const app = await readFile(new URL('../site/app.js', import.meta.url), 'utf8');
  const index = JSON.parse(
    await readFile(new URL('../site/stories.json', import.meta.url), 'utf8'),
  );
  const story = index.stories.find(
    (candidate) => candidate.story_id === 'wm-20260813-fe7aa82e',
  );
  assert.ok(story.detail_path);
  const details = JSON.parse(
    await readFile(new URL(`../site/${story.detail_path}`, import.meta.url), 'utf8'),
  );
  const detail = details.stories[story.detail_key];
  let fetchOptions;
  const fetch = async (_path, options) => {
    fetchOptions = options;
    return { ok: true, json: async () => structuredClone(index) };
  };
  const context = vm.createContext({ fetch, Set });

  vm.runInContext(app, context);
  await vm.runInContext('loadJson("./stories.json")', context);

  assert.equal(fetchOptions.cache, 'no-store');
  assert.deepEqual(Object.keys(fetchOptions), ['cache']);

  context.stories = index.stories;
  const graph = vm.runInContext('buildGraphModel(stories)', context);
  assert.ok(graph.nodes.some((node) => node.kind === 'story'));
  assert.equal(graph.nodes.filter((node) => node.kind === 'character').length, 7);
  assert.ok(graph.nodes.some((node) => node.kind === 'character' && node.label === '砺弦'));
  assert.ok(graph.edges.length > 0);

  context.firstTurn = detail.dialogue[0];
  const turnHtml = vm.runInContext('renderTurn(firstTurn)', context);
  assert.equal(detail.dialogue.length, 35);
  assert.match(turnHtml, /越界投射/);
  assert.match(
    turnHtml,
    /砺弦/,
  );
});

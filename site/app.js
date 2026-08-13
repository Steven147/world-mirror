const rootPath = './stories.json';
const sectionLabels = {
  oracle: '越界投射',
  resolution: '投射结算',
  mirror_change: '镜面变化',
  echoes: '延迟回响',
  creator: '创造者问答',
  collection: '碎片收集',
  history: '历史追溯',
  actions: '可执行行动',
  fragments: '世界碎片',
  time_jump: '时间跃迁',
  completion: '世界重建',
  statistics: '本局统计',
  answer_record: '玩家作答记录',
  prompt: '镜面提示',
  progress: '观测进度',
};
const fieldLabels = {
  raw_signal: '原始信号',
  translated: '镜面译文',
  options: '可选投射',
  result: '结果',
  explanation: '结算',
  question: '问题',
  answer: '玩家答案',
  passed: '判定',
  target_concept: '目标概念',
  elapsed: '世界时间经过',
  from_event: '起点事件',
  to_event: '抵达事件',
  projection_count: '投射次数',
  core_fragments: '核心碎片',
  collected_at: '收集时间',
  answered_at: '作答时间',
};
const graphKindLabels = {
  story: '故事',
  character: '人物',
  event: '事件',
  place: '地点',
  concept: '概念 / 规律',
};

let publishedStories = [];
let graphModel = { nodes: [], edges: [] };
let selectedGraphNodeId = null;
let activeStory = null;
let activeDialogue = [];
let activeTurnIndex = 0;
const detailFileCache = new Map();

async function loadJson(path) {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`无法读取 ${path}`);
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function formatDate(value) {
  if (!value) return '时间未知';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function renderStats(stories) {
  document.querySelector('#story-count').textContent = stories.length;
  document.querySelector('#world-count').textContent = new Set(
    stories.map((story) => story.world_id),
  ).size;
  document.querySelector('#thread-count').textContent = stories.filter(
    (story) => story.kind === 'community-thread',
  ).length;
}

function renderStories(stories) {
  const container = document.querySelector('#stories');
  if (!stories.length) return;
  container.innerHTML = stories
    .slice()
    .reverse()
    .map(
      (story) => `
        <article class="card">
          <div class="card-topline">
            <span class="kind">${escapeHtml(story.kind)}</span>
            <span class="turn-count">${escapeHtml(story.turn_count)} 回合</span>
          </div>
          <h3>${escapeHtml(story.title)}</h3>
          <p>${escapeHtml(story.summary)}</p>
          <div class="card-meta">
            <span>${escapeHtml(story.author.display_name)}</span>
            <time datetime="${escapeHtml(story.completed_at)}">${escapeHtml(formatDate(story.completed_at))}</time>
          </div>
          <div class="card-actions">
            <button class="read-story" type="button" data-story-id="${escapeHtml(story.story_id)}">翻阅完整流程 →</button>
            <span class="card-orbit">${escapeHtml(story.world_id)}</span>
          </div>
        </article>`,
    )
    .join('');

  container.addEventListener('click', (event) => {
    const button = event.target.closest('.read-story');
    if (button) openStory(button.dataset.storyId);
  });
}

function normalizeGraphKind(type) {
  if (type === '人物') return 'character';
  if (type === '事件') return 'event';
  if (type === '地点') return 'place';
  return 'concept';
}

function buildGraphModel(stories) {
  const nodes = new Map();
  const edges = new Map();

  function addNode(node) {
    const existing = nodes.get(node.id);
    if (existing) {
      if (node.description && !existing.description.includes(node.description)) {
        existing.description += ` ${node.description}`;
      }
      node.relations.forEach((relation) => existing.relations.add(relation));
      return existing;
    }
    nodes.set(node.id, node);
    return node;
  }

  function addEdge(source, target, label) {
    if (source === target) return;
    const pair = [source, target].sort();
    const id = `${pair[0]}::${pair[1]}`;
    const existing = edges.get(id);
    if (existing) {
      if (label) existing.labels.add(label);
      return;
    }
    edges.set(id, { id, source: pair[0], target: pair[1], labels: new Set(label ? [label] : []) });
  }

  stories.forEach((story) => {
    const storyId = `story:${story.story_id}`;
    addNode({
      id: storyId,
      label: story.title,
      kind: 'story',
      description: story.worldview || story.summary,
      relations: new Set(story.relations || []),
    });

    const storyEntities = new Map();
    (story.keywords || []).forEach((keyword) => {
      const kind = normalizeGraphKind(keyword.type);
      const id = `${kind}:${keyword.name}`;
      addNode({
        id,
        label: keyword.name,
        kind,
        description: keyword.description,
        relations: new Set(),
      });
      storyEntities.set(keyword.name, id);
      addEdge(storyId, id, `出现于《${story.title}》`);
    });

    (story.characters || []).forEach((name) => {
      if (storyEntities.has(name)) return;
      const id = `character:${name}`;
      addNode({
        id,
        label: name,
        kind: 'character',
        description: `《${story.title}》中的人物。`,
        relations: new Set(),
      });
      storyEntities.set(name, id);
      addEdge(storyId, id, `出现于《${story.title}》`);
    });

    (story.concepts || []).forEach((name) => {
      if (storyEntities.has(name)) return;
      const id = `concept:${name}`;
      addNode({
        id,
        label: name,
        kind: 'concept',
        description: `《${story.title}》世界线中的关键概念。`,
        relations: new Set(),
      });
      storyEntities.set(name, id);
      addEdge(storyId, id, `构成《${story.title}》的世界观`);
    });

    (story.relations || []).forEach((relation) => {
      const matched = [...storyEntities.entries()]
        .filter(([name]) => relation.includes(name))
        .map(([, id]) => id);
      matched.forEach((id) => nodes.get(id)?.relations.add(relation));
      for (let i = 0; i < matched.length; i += 1) {
        for (let j = i + 1; j < matched.length; j += 1) {
          addEdge(matched[i], matched[j], relation);
        }
      }
    });
  });

  return {
    nodes: [...nodes.values()].map((node) => ({ ...node, relations: [...node.relations] })),
    edges: [...edges.values()].map((edge) => ({ ...edge, labels: [...edge.labels] })),
  };
}

function positionGraphNodes(nodes) {
  const stories = nodes.filter((node) => node.kind === 'story');
  const entities = nodes.filter((node) => node.kind !== 'story');
  const positioned = [];

  stories.forEach((node, index) => {
    const angle = stories.length === 1 ? 0 : (Math.PI * 2 * index) / stories.length;
    const radius = stories.length === 1 ? 0 : 13;
    positioned.push({
      ...node,
      x: 50 + Math.cos(angle) * radius,
      y: 50 + Math.sin(angle) * radius,
    });
  });

  const ringCounts = [Math.ceil(entities.length / 2), Math.floor(entities.length / 2)];
  const ringIndexes = [0, 0];
  entities.forEach((node, index) => {
    const ring = index % 2;
    const count = Math.max(ringCounts[ring], 1);
    const angle = -Math.PI / 2 + (Math.PI * 2 * ringIndexes[ring]) / count + ring * .19;
    const radiusX = ring === 0 ? 31 : 44;
    const radiusY = ring === 0 ? 29 : 42;
    ringIndexes[ring] += 1;
    positioned.push({
      ...node,
      x: 50 + Math.cos(angle) * radiusX,
      y: 50 + Math.sin(angle) * radiusY,
    });
  });

  return positioned;
}

function renderGraph(stories) {
  graphModel = buildGraphModel(stories);
  graphModel.nodes = positionGraphNodes(graphModel.nodes);
  const nodesContainer = document.querySelector('#graph-nodes');
  const empty = document.querySelector('#graph-empty');
  if (!graphModel.nodes.length) return;

  empty.hidden = true;
  nodesContainer.innerHTML = graphModel.nodes
    .map(
      (node) => `
        <button
          class="graph-node kind-${escapeHtml(node.kind)}"
          type="button"
          style="--x:${node.x};--y:${node.y}"
          data-node-id="${escapeHtml(node.id)}"
          aria-label="${escapeHtml(graphKindLabels[node.kind])}：${escapeHtml(node.label)}"
        >${escapeHtml(node.label)}</button>`,
    )
    .join('');

  nodesContainer.addEventListener('click', (event) => {
    const node = event.target.closest('.graph-node');
    if (node) selectGraphNode(node.dataset.nodeId);
  });
  window.addEventListener('resize', drawGraphEdges);
  selectGraphNode(graphModel.nodes.find((node) => node.kind === 'story')?.id);
}

function drawGraphEdges() {
  const canvas = document.querySelector('#graph-canvas');
  const stage = document.querySelector('#graph-stage');
  if (!canvas || !stage || !graphModel.nodes.length) return;
  const rect = stage.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.round(rect.width * ratio));
  canvas.height = Math.max(1, Math.round(rect.height * ratio));
  const context = canvas.getContext('2d');
  context.scale(ratio, ratio);
  context.clearRect(0, 0, rect.width, rect.height);
  const nodeById = new Map(graphModel.nodes.map((node) => [node.id, node]));

  graphModel.edges.forEach((edge) => {
    const source = nodeById.get(edge.source);
    const target = nodeById.get(edge.target);
    if (!source || !target) return;
    const isSelected = edge.source === selectedGraphNodeId || edge.target === selectedGraphNodeId;
    context.beginPath();
    context.moveTo((source.x / 100) * rect.width, (source.y / 100) * rect.height);
    context.lineTo((target.x / 100) * rect.width, (target.y / 100) * rect.height);
    context.strokeStyle = isSelected ? '#8bd8cf99' : '#50606938';
    context.lineWidth = isSelected ? 1.5 : .75;
    context.stroke();
  });
}

function selectGraphNode(id) {
  if (!id) return;
  selectedGraphNodeId = id;
  const selected = graphModel.nodes.find((node) => node.id === id);
  if (!selected) return;
  const relatedIds = new Set([id]);
  const relatedEdges = graphModel.edges.filter((edge) => edge.source === id || edge.target === id);
  relatedEdges.forEach((edge) => {
    relatedIds.add(edge.source);
    relatedIds.add(edge.target);
  });

  document.querySelectorAll('.graph-node').forEach((element) => {
    element.classList.toggle('is-active', element.dataset.nodeId === id);
    element.classList.toggle('is-related', element.dataset.nodeId !== id && relatedIds.has(element.dataset.nodeId));
    element.classList.toggle('is-dim', !relatedIds.has(element.dataset.nodeId));
  });

  document.querySelector('#graph-detail-title').textContent = selected.label;
  document.querySelector('#graph-detail-type').textContent = graphKindLabels[selected.kind];
  document.querySelector('#graph-detail-description').textContent = selected.description;
  const relations = [...new Set([
    ...selected.relations,
    ...relatedEdges.flatMap((edge) => edge.labels),
  ])].slice(0, 5);
  document.querySelector('#graph-detail-relations').innerHTML = relations.length
    ? relations.map((relation) => `<p class="graph-relation">${escapeHtml(relation)}</p>`).join('')
    : '<p class="graph-relation">这个节点目前只与所属故事直接相连。</p>';
  drawGraphEdges();
}

function renderValue(value, field = '') {
  if (value === null || value === undefined) return '<p>未记录</p>';
  if (typeof value === 'string') {
    return value
      .split(/\n\s*\n/)
      .filter(Boolean)
      .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
      .join('');
  }
  if (typeof value === 'boolean') return `<p>${value ? '通过' : '未通过'}</p>`;
  if (typeof value === 'number') return `<p>${value}</p>`;
  if (Array.isArray(value)) {
    if (!value.length) return '<p>无</p>';
    const isOptions = value.every((item) => item && typeof item === 'object' && 'id' in item && 'text' in item);
    if (isOptions) {
      return `<ul class="option-list">${value
        .map((item) => `<li><strong>${escapeHtml(item.id)}</strong><span>${escapeHtml(item.text)}</span></li>`)
        .join('')}</ul>`;
    }
    return `<ul>${value.map((item) => `<li>${renderValue(item, field)}</li>`).join('')}</ul>`;
  }
  if (typeof value === 'object') {
    return `<dl>${Object.entries(value)
      .map(
        ([key, child]) => `
          <dt>${escapeHtml(fieldLabels[key] || key.replaceAll('_', ' '))}</dt>
          <dd>${renderValue(child, key)}</dd>`,
      )
      .join('')}</dl>`;
  }
  return `<p>${escapeHtml(value)}</p>`;
}

function renderTurn(turn) {
  return Object.entries(turn)
    .filter(([key]) => !['meta', 'time'].includes(key))
    .map(
      ([key, value]) => `
        <section class="turn-section${key === 'answer_record' ? ' answer-record' : ''}">
          <h4>${escapeHtml(sectionLabels[key] || key.replaceAll('_', ' '))}</h4>
          ${renderValue(value, key)}
        </section>`,
    )
    .join('');
}

async function getStoryDetail(story) {
  if (!detailFileCache.has(story.detail_path)) {
    detailFileCache.set(story.detail_path, loadJson(`./${story.detail_path}`));
  }
  const details = await detailFileCache.get(story.detail_path);
  return details.stories[story.detail_key];
}

async function openStory(storyId) {
  activeStory = publishedStories.find((story) => story.story_id === storyId);
  if (!activeStory) return;
  const dialog = document.querySelector('#story-reader');
  document.querySelector('#reader-title').textContent = activeStory.title;
  document.querySelector('#reader-summary').textContent = activeStory.summary;
  document.querySelector('#reader-kicker').textContent = `${activeStory.world_id} · ${activeStory.turn_count} TURNS`;
  document.querySelector('#turn-list').innerHTML = '<p class="graph-relation">正在读取公开档案……</p>';
  document.querySelector('#turn-content').innerHTML = '<section class="turn-section"><p>镜面正在显影。</p></section>';
  if (!dialog.open) dialog.showModal();

  try {
    const detail = await getStoryDetail(activeStory);
    activeDialogue = detail.dialogue;
    renderTurnList();
    showTurn(0);
  } catch (error) {
    document.querySelector('#turn-content').innerHTML = `<section class="turn-section"><h4>读取失败</h4><p>${escapeHtml(error.message)}</p></section>`;
  }
}

function renderTurnList() {
  const list = document.querySelector('#turn-list');
  list.innerHTML = activeDialogue
    .map(
      (turn, index) => `
        <button class="turn-tab" type="button" role="tab" data-turn-index="${index}" aria-selected="false">
          <strong>${String(turn.meta.turn).padStart(2, '0')}</strong>
          <span>${escapeHtml(turn.meta.label)}</span>
        </button>`,
    )
    .join('');
  list.onclick = (event) => {
    const tab = event.target.closest('.turn-tab');
    if (tab) showTurn(Number(tab.dataset.turnIndex));
  };
}

function showTurn(index) {
  if (!activeDialogue.length) return;
  activeTurnIndex = Math.min(Math.max(index, 0), activeDialogue.length - 1);
  const turn = activeDialogue[activeTurnIndex];
  document.querySelector('#reader-progress').textContent = `${activeTurnIndex + 1} / ${activeDialogue.length}`;
  document.querySelector('#turn-number').textContent = `TURN ${String(turn.meta.turn).padStart(2, '0')}`;
  document.querySelector('#turn-title').textContent = turn.meta.label;
  document.querySelector('#turn-mirror-time').textContent = turn.time?.mirror || '';
  document.querySelector('#turn-local-time').textContent = turn.time?.local || '';
  const content = document.querySelector('#turn-content');
  content.innerHTML = renderTurn(turn);
  content.scrollTop = 0;
  document.querySelector('#turn-prev').disabled = activeTurnIndex === 0;
  document.querySelector('#turn-next').disabled = activeTurnIndex === activeDialogue.length - 1;
  document.querySelectorAll('.turn-tab').forEach((tab, tabIndex) => {
    const active = tabIndex === activeTurnIndex;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
    if (active) tab.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  });
}

function bindReader() {
  const dialog = document.querySelector('#story-reader');
  document.querySelector('#reader-close').addEventListener('click', () => dialog.close());
  document.querySelector('#turn-prev').addEventListener('click', () => showTurn(activeTurnIndex - 1));
  document.querySelector('#turn-next').addEventListener('click', () => showTurn(activeTurnIndex + 1));
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
  });
  document.addEventListener('keydown', (event) => {
    if (!dialog.open) return;
    if (event.key === 'ArrowLeft') showTurn(activeTurnIndex - 1);
    if (event.key === 'ArrowRight') showTurn(activeTurnIndex + 1);
  });
}

function renderLoadError(error) {
  document.querySelector('#stories').innerHTML = `<p class="empty">档案读取失败：${escapeHtml(error.message)}</p>`;
  document.querySelector('#graph-empty').textContent = '关系星图暂时无法显影。';
}

async function boot() {
  const data = await loadJson(rootPath);
  publishedStories = data.stories || [];
  renderStats(publishedStories);
  renderStories(publishedStories);
  renderGraph(publishedStories);
  bindReader();
}

if (typeof document !== 'undefined') {
  boot().catch(renderLoadError);
}

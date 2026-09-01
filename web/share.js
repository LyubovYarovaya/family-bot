/* Публичная страница списка: гость смотрит и бронирует подарки. */

const token = location.pathname.split('/').filter(Boolean).pop();
// Тип списка приходит вместе с данными: в вишлистах важность не показываем.
let listKind = 'wishlist';
const itemsNode = document.getElementById('items');
const modalRoot = document.getElementById('modal-root');

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

const PRIORITIES = { 3: 'очень хочется', 2: 'хочется', 1: 'было бы приятно' };

const money = (value, currency) => {
  if (value === null || value === undefined) return '';
  const num = Number(value);
  const text = num % 1 === 0 ? num.toLocaleString('ru-RU') : num.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${text} ${currency}` : text;
};

// Секрет гостя — по нему он потом может снять свою бронь с этого же устройства.
function guestSecret() {
  let secret = localStorage.getItem('guest_secret');
  if (!secret) {
    secret = (crypto.randomUUID?.() || String(Math.random())).replace(/-/g, '');
    localStorage.setItem('guest_secret', secret);
  }
  return secret;
}

function toast(text) {
  const node = document.createElement('div');
  node.className = 'toast';
  node.textContent = text;
  document.body.appendChild(node);
  setTimeout(() => node.remove(), 2600);
}

async function api(path, { method = 'GET', body } = {}) {
  const response = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    let detail = `Ошибка ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* пусто */ }
    throw new Error(detail);
  }
  return response.json();
}

function itemCard(item) {
  const thumb = item.image_url
    ? `<img class="thumb" src="${esc(item.image_url)}" alt="" loading="lazy" onerror="this.remove()">`
    : '';
  const meta = [];
  if (item.price) meta.push(`<span class="price">${esc(money(item.price, item.currency))}</span>`);
  if (item.priority && listKind !== 'wishlist') {
    meta.push(`<span class="badge prio p${item.priority}">${esc(PRIORITIES[item.priority] || '')}</span>`);
  }
  if (item.is_reserved) {
    meta.push(`<span class="badge reserved">${icon('ribbon')} ${item.mine ? 'вы забронировали' : 'забронировано'}</span>`);
  }

  let action = `<button class="btn small primary" data-reserve="${item.id}">${icon('ribbon', 'ic-sm')} Забронировать</button>`;
  if (item.is_reserved) {
    action = item.mine
      ? `<button class="btn small" data-unreserve="${item.id}">Снять бронь</button>`
      : '';
  }

  return `<div class="card">
    ${thumb}
    <div class="body">
      <div class="title">${esc(item.title)}</div>
      <div class="meta">${meta.join('')}</div>
      ${item.note ? `<div class="meta">${icon('note', 'ic-sm')} ${esc(item.note)}</div>` : ''}
      <div class="actions">
        ${item.url ? `<a class="btn small outline" href="${esc(item.url)}" target="_blank" rel="noopener">
          ${icon('link', 'ic-sm')} Посмотреть</a>` : ''}
        ${action}
      </div>
    </div>
  </div>`;
}


/* Порядок списка выбирает сам гость. Сортируем на месте: список приходит
   целиком одним ответом, поэтому переключение мгновенное и сервер не трогаем.
   Выбор запоминается в браузере гостя — вернётся по ссылке, порядок тот же. */
const SORTS = {
  free: {
    label: 'Сначала свободные',
    sort: (a, b) => Number(a.is_reserved) - Number(b.is_reserved) || b.id - a.id,
  },
  fresh: {
    label: 'Сначала новые',
    sort: (a, b) => b.id - a.id,
  },
  title: {
    label: 'По названию',
    sort: (a, b) => String(a.title).localeCompare(String(b.title), 'ru'),
  },
  cheap: {
    label: 'Сначала дешёвые',
    needsPrice: true,
    sort: (a, b) => priceOrder(a) - priceOrder(b),
  },
  pricey: {
    label: 'Сначала дорогие',
    needsPrice: true,
    sort: (a, b) => priceOrder(b) - priceOrder(a),
  },
};

// Позиции без цены не должны перемешиваться с ценами — отправляем их в конец.
const priceOrder = (item) => (item.price === null || item.price === undefined
  ? Number.POSITIVE_INFINITY
  : Number(item.price));

function currentSort() {
  try {
    const saved = localStorage.getItem('guest_sort');
    if (saved && SORTS[saved]) return saved;
  } catch (_) { /* приватный режим — берём порядок по умолчанию */ }
  return 'free';
}

function renderSort(items) {
  const box = document.getElementById('sort');
  if (!box) return;
  // Один подарок сортировать незачем.
  if (items.length < 2) { box.hidden = true; return; }
  const withPrice = items.some((item) => item.price !== null && item.price !== undefined);
  const options = Object.entries(SORTS).filter(([, cfg]) => !cfg.needsPrice || withPrice);
  const active = currentSort();
  box.hidden = false;
  box.innerHTML = `<label class="sort-label" for="sort-select">Порядок</label>
    <select id="sort-select">${options.map(([key, cfg]) =>
      `<option value="${key}" ${key === active ? 'selected' : ''}>${esc(cfg.label)}</option>`).join('')}</select>`;
  box.querySelector('select').addEventListener('change', (event) => {
    try { localStorage.setItem('guest_sort', event.target.value); } catch (_) { /* ничего */ }
    paint();
  });
}

let loaded = [];

function paint() {
  const order = SORTS[currentSort()] || SORTS.free;
  const items = [...loaded].sort(order.sort);
  itemsNode.innerHTML = items.length
    ? items.map(itemCard).join('')
    : `<div class="empty"><div class="big">${icon('inbox')}</div>Список пока пуст</div>`;
  renderSort(loaded);
}

async function load() {
  try {
    const data = await api(`/api/public/${encodeURIComponent(token)}?secret=${encodeURIComponent(guestSecret())}`);
    document.getElementById('mark').innerHTML = iconForEmoji(data.emoji);
    listKind = data.kind || 'wishlist';
    document.getElementById('title').textContent = data.title;
    document.title = data.title;
    document.getElementById('subtitle').textContent = data.owner_name
      ? `Вишлист: ${data.owner_name}`
      : data.household_title;

    if (data.hide_from_owner) {
      document.getElementById('foot').innerHTML =
        'Отмечайте «Забронировать», чтобы никто не подарил одно и то же дважды.<br>'
        + 'Владелец вишлиста брони не видит — сюрприз останется сюрпризом.';
    }

    loaded = data.items;
    paint();
  } catch (error) {
    document.getElementById('mark').innerHTML = icon('lock');
    const box = document.getElementById('sort');
    if (box) box.hidden = true;
    itemsNode.innerHTML = `<div class="empty"><div class="big">${icon('sad')}</div>${esc(error.message)}</div>`;
    document.getElementById('title').textContent = 'Список недоступен';
  }
}

document.addEventListener('click', async (event) => {
  const target = event.target.closest('[data-reserve], [data-unreserve]');
  if (!target) return;

  try {
    if (target.dataset.reserve) {
      await api(`/api/public/${encodeURIComponent(token)}/items/${target.dataset.reserve}/reserve`, {
        method: 'POST', body: { secret: guestSecret() },
      });
      toast('Забронировано');
    } else {
      await api(`/api/public/${encodeURIComponent(token)}/items/${target.dataset.unreserve}/unreserve`, {
        method: 'POST', body: { secret: guestSecret() },
      });
      toast('Бронь снята');
    }
    await load();
  } catch (error) {
    toast(error.message);
    await load();
  }
});

load();

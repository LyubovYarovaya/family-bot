/* Mini App: списки покупок, вишлисты и траты. Ванильный JS, без сборки. */

const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

/* Telegram кладёт подписанную initData в адрес мини-приложения — обычно в хэш
   (#tgWebAppData=…), иногда в query. Оттуда её и достаёт telegram-web-app.js.
   Читаем сами по двум причинам: внешний скрипт может не загрузиться, а при
   перезагрузке страницы Telegram открывает адрес уже без этих параметров. */
function initDataFromUrl() {
  for (const part of [window.location.hash.replace(/^#/, ''), window.location.search.replace(/^\?/, '')]) {
    if (!part) continue;
    try {
      const value = new URLSearchParams(part).get('tgWebAppData');
      if (value) return value;
    } catch (_) { /* мусор в адресе — просто пробуем дальше */ }
  }
  return '';
}

/* Строку входа держим на время сеанса: если Telegram перезагрузит страницу без
   параметров, нам будет чем авторизоваться. sessionStorage живёт только пока
   открыто окно мини-приложения, а сервер всё равно проверяет подпись и срок
   (сутки) — просроченную строку он не примет. */
const INIT_DATA_KEY = 'tg_init_data';

function rememberInitData(value) {
  try {
    if (value) sessionStorage.setItem(INIT_DATA_KEY, value);
  } catch (_) { /* приватный режим — переживём */ }
}

function forgetInitData() {
  try { sessionStorage.removeItem(INIT_DATA_KEY); } catch (_) { /* ничего */ }
}

function storedInitData() {
  try { return sessionStorage.getItem(INIT_DATA_KEY) || ''; } catch (_) { return ''; }
}

const initData = tg?.initData || initDataFromUrl() || storedInitData();
rememberInitData(initData);

const state = {
  tab: 'shopping',
  me: null,
  lists: [],
  active: { shopping: null, wishlist: null },
  items: [],
  showBought: false,
  viewKind: 'shopping',
  expenseCategories: [],
  month: new Date(),
  expenses: [],
  templates: [],
  summary: null,
};

const view = document.getElementById('view');
const fab = document.getElementById('fab');
const modalRoot = document.getElementById('modal-root');

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

const money = (value, currency) => {
  if (value === null || value === undefined) return '';
  const num = Number(value);
  const text = num % 1 === 0 ? num.toLocaleString('ru-RU') : num.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${text} ${currency}` : text;
};

const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'];
const PERIODS = { once: 'Разовая', monthly: 'Ежемесячная', quarterly: 'Ежеквартальная', yearly: 'Ежегодная' };
// 0 — важность не выбирали: такие позиции ярлык не получают.
const PRIORITIES = { 3: 'высокий', 2: 'средний', 1: 'низкий' };

function toast(text) {
  const node = document.createElement('div');
  node.className = 'toast';
  node.textContent = text;
  document.body.appendChild(node);
  setTimeout(() => node.remove(), 2600);
}

function haptic(type = 'light') {
  try { tg?.HapticFeedback?.impactOccurred(type); } catch (_) { /* не критично */ }
}

async function api(path, { method = 'GET', body } = {}) {
  const response = await fetch(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-Telegram-Init-Data': initData,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    // Строка входа протухла или неверна — забываем её, иначе будем биться
    // об один и тот же 401 до конца сеанса.
    if (response.status === 401) forgetInitData();
    let detail = `Ошибка ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* пусто */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

/* ---------- загрузка данных ---------- */

async function loadCore() {
  state.me = await api('/api/me');
  document.getElementById('header-title').textContent = state.me.household_title;
  document.getElementById('header-sub').textContent =
    state.me.members.map((m) => m.name).join(' · ');
}

async function loadLists() {
  state.lists = await api('/api/lists');
  for (const kind of ['shopping', 'wishlist']) {
    const own = state.lists.filter((l) => l.kind === kind);
    if (!own.some((l) => l.id === state.active[kind])) {
      state.active[kind] = own.length ? own[0].id : null;
    }
  }
}

async function loadItems(listId) {
  state.items = listId ? await api(`/api/lists/${listId}/items`) : [];
}

function monthRange(date) {
  const from = new Date(date.getFullYear(), date.getMonth(), 1);
  const to = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return [iso(from), iso(to)];
}

async function loadExpenses() {
  const [from, to] = monthRange(state.month);
  const [categories, expenses, templates, summary] = await Promise.all([
    api('/api/expense-categories'),
    api(`/api/expenses?date_from=${from}&date_to=${to}`),
    api('/api/expenses?templates=true'),
    api(`/api/expenses/summary?date_from=${from}&date_to=${to}`),
  ]);
  state.expenseCategories = categories;
  state.expenses = expenses;
  state.templates = templates;
  state.summary = summary;
}

/* ---------- рендер: покупки и вишлисты ---------- */

function listChips(kind) {
  const lists = state.lists.filter((l) => l.kind === kind);
  return `<div class="chips">${lists.map((l) => `
    <button class="chip ${l.id === state.active[kind] ? 'active' : ''}" data-pick-list="${l.id}">
      ${iconForEmoji(l.emoji)}
      <span>${esc(l.title)}</span>
      <span class="count">${l.active_count}</span>
    </button>`).join('')}
    <button class="chip add" data-new-list="${kind}">${icon('plus', 'ic-sm')}</button>
  </div>`;
}

function itemCard(item) {
  const thumb = item.image_url
    ? `<img class="thumb" src="${esc(item.image_url)}" alt="" loading="lazy" onerror="this.remove()">`
    : '';
  // Цена — отдельной строкой и крупно, остальное приглушённой подписью под ней.
  const priceLine = item.price
    ? `<div class="meta"><span class="price">${esc(money(item.price, item.currency || state.me.currency))}</span></div>`
    : '';
  const meta = [];
  // В вишлистах приоритет не показываем: там его не выставляют.
  if (item.priority && state.viewKind !== 'wishlist') {
    meta.push(`<span class="badge prio p${item.priority}">${esc(PRIORITIES[item.priority])}</span>`);
  }
  if (item.shop) meta.push(`<span>${esc(item.shop)}</span>`);
  if (item.created_by) meta.push(`<span>${esc(item.created_by)}</span>`);
  if (item.is_reserved) {
    meta.push(`<span class="badge reserved">${icon('ribbon')} забронировано</span>`);
  }

  return `<div class="card ${item.status === 'bought' ? 'bought' : ''}">
    ${thumb}
    <div class="body">
      <div class="title">${esc(item.title)}</div>
      ${priceLine}
      ${meta.length ? `<div class="meta">${meta.join('')}</div>` : ''}
      ${item.note ? `<div class="meta">${icon('note', 'ic-sm')} ${esc(item.note)}</div>` : ''}
      <div class="actions">
        ${item.url ? `<a class="btn small outline" href="${esc(item.url)}" target="_blank" rel="noopener">
          ${icon('link', 'ic-sm')} Открыть</a>` : ''}
        <button class="btn small ${item.status === 'bought' ? 'outline' : 'primary'}" data-toggle-bought="${item.id}">
          ${item.status === 'bought' ? `${icon('undo', 'ic-sm')} Вернуть` : `${icon('check', 'ic-sm')} Куплено`}
        </button>
        <span class="spacer"></span>
        <button class="btn small icon outline" data-edit-item="${item.id}" aria-label="Изменить">${icon('pencil', 'ic-sm')}</button>
        <button class="btn small icon danger" data-delete-item="${item.id}" aria-label="Удалить">${icon('trash', 'ic-sm')}</button>
      </div>
    </div>
  </div>`;
}

function currentList(kind) {
  return state.lists.find((l) => l.id === state.active[kind]) || null;
}

function renderItemsView(kind) {
  state.viewKind = kind;
  const list = currentList(kind);
  const visible = state.items.filter((i) => state.showBought || i.status === 'active');
  const total = visible
    .filter((i) => i.status === 'active' && i.price)
    .reduce((sum, i) => sum + Number(i.price), 0);

  const body = visible.length
    ? visible.map(itemCard).join('')
    : `<div class="empty"><div class="big">${icon(kind === 'wishlist' ? 'gift' : 'bag')}</div>
        Пусто. Кинь боту ссылку на товар — он сам вытянет название, цену и картинку.</div>`;

  // Вишлисты имеют смысл вдвоём — если семья пока из одного человека,
  // подсказываем, как позвать второго, прямо здесь.
  const alone = kind === 'wishlist' && (state.me.members || []).length < 2;
  const invite = state.me.invite_url || '';
  const inviteBlock = alone ? `<div class="panel">
      <h3>${icon('users')} Пока ты одна в семье</h3>
      <div class="dim">Отправь эту ссылку второй половинке — вишлисты, списки и траты станут общими,
        и вы будете видеть списки друг друга.</div>
      <div class="share-box">
        <input readonly value="${esc(invite)}">
        <button class="btn small outline" data-copy="${esc(invite)}">${icon('copy', 'ic-sm')} Копировать</button>
      </div>
      ${invite.startsWith('http') ? `<button class="btn small primary block" data-send-invite="${esc(invite)}"
        style="margin-top:10px">${icon('share', 'ic-sm')} Отправить в Telegram</button>` : ''}
    </div>` : '';

  view.innerHTML = `
    ${listChips(kind)}
    ${inviteBlock}
    ${list ? `<div class="panel">
      <div class="list-head">
        ${iconBadge(list.emoji)}
        <span class="name">${esc(list.title)}</span>
        ${total ? `<span class="sum">${esc(money(total, state.me.currency))}</span>` : ''}
      </div>
      <div class="list-actions">
        <button class="btn small outline" data-toggle-shown>
          ${icon(state.showBought ? 'eyeOff' : 'eye', 'ic-sm')}
          ${state.showBought ? 'Скрыть купленное' : 'Показать купленное'}
        </button>
        <button class="btn small outline" data-share-list="${list.id}">
          ${icon(list.is_shared ? 'link' : 'share', 'ic-sm')} ${list.is_shared ? 'Ссылка' : 'Открыть доступ'}
        </button>
        ${list.is_shared ? `<button class="btn small primary" data-send-list="${list.id}">
          ${icon('share', 'ic-sm')} Отправить</button>` : ''}
        ${list.is_shared ? `
          <button class="btn small outline" data-toggle-prices="${list.id}">
            ${icon(list.show_prices_to_guests ? 'eye' : 'eyeOff', 'ic-sm')}
            ${list.show_prices_to_guests ? 'Цены видны гостям' : 'Цены скрыты'}
          </button>` : ''}
        ${list.kind === 'wishlist' && list.owner_id === state.me.user.id ? `
          <button class="btn small outline" data-toggle-surprise="${list.id}">
            ${icon(list.hide_reservations_from_owner ? 'eyeOff' : 'eye', 'ic-sm')}
            ${list.hide_reservations_from_owner ? 'Брони скрыты' : 'Брони видны'}
          </button>` : ''}
        <span class="spacer" style="flex:1"></span>
        <button class="btn small icon outline" data-rename-list="${list.id}" aria-label="Переименовать">${icon('pencil', 'ic-sm')}</button>
        <button class="btn small icon danger" data-delete-list="${list.id}" aria-label="Удалить список">${icon('trash', 'ic-sm')}</button>
      </div>
      ${list.is_shared ? `<div class="share-box">
        <input readonly value="${esc(list.share_url)}">
        <button class="btn small" data-copy="${esc(list.share_url)}">Копировать</button>
      </div>` : ''}
    </div>` : ''}
    ${body}`;
}

/* ---------- рендер: траты ---------- */

function expenseRow(expense) {
  const date = new Date(expense.spent_on);
  return `<div class="row">
    <div class="label">
      ${iconBadge(expense.category_emoji || '❔', 'sm')}
      <span>
        <div class="name">${esc(expense.title || expense.category_title || 'Трата')}</div>
        <div class="sub">
          ${String(date.getDate()).padStart(2, '0')}.${String(date.getMonth() + 1).padStart(2, '0')}
          ${expense.period !== 'once' ? ' · ' + esc(PERIODS[expense.period]) : ''}
          ${expense.created_by ? ' · ' + esc(expense.created_by) : ''}
        </div>
      </span>
    </div>
    <div class="value">
      ${esc(money(expense.amount, expense.currency))}
      <button class="btn small icon ghost" data-edit-expense="${expense.id}" aria-label="Изменить">${icon('pencil', 'ic-sm')}</button>
    </div>
  </div>`;
}

function renderExpensesView() {
  const summary = state.summary;
  const max = Math.max(1, ...summary.by_category.map((b) => b.total));
  const monthLabel = `${MONTHS[state.month.getMonth()]} ${state.month.getFullYear()}`;

  const categories = summary.by_category.map((bucket) => `
    <div class="row cat">
      <div class="label">${iconBadge(bucket.emoji, 'sm')}<span class="name">${esc(bucket.title)}</span></div>
      <div class="value">${esc(money(bucket.total, summary.currency))}</div>
      <div class="bar"><span style="width:${(bucket.total / max) * 100}%"></span></div>
    </div>`).join('') || '<div class="dim">Трат за месяц нет</div>';

  const others = summary.by_currency.filter((b) => b.key !== summary.currency);
  const templates = state.templates.map((template) => `
    <div class="row">
      <div class="label">${iconBadge(template.category_emoji || '🔁', 'sm')}<span>
        <div class="name">${esc(template.title || template.category_title || 'Платёж')}</div>
        <div class="sub">${esc(PERIODS[template.period])}</div>
      </span></div>
      <div class="value">${esc(money(template.amount, template.currency))}
        <button class="btn small primary" data-pay-template="${template.id}">Оплатить</button>
        <button class="btn small icon ghost" data-edit-expense="${template.id}" aria-label="Изменить">${icon('pencil', 'ic-sm')}</button>
      </div>
    </div>`).join('') || '<div class="dim">Регулярных платежей пока нет — добавь аренду, подписки, страховку.</div>';

  view.innerHTML = `
    <div class="panel">
      <div class="monthbar">
        <button class="btn small icon outline" data-month="-1" aria-label="Предыдущий месяц">${icon('left', 'ic-sm')}</button>
        <b>${esc(monthLabel)}</b>
        <button class="btn small icon outline" data-month="1" aria-label="Следующий месяц">${icon('right', 'ic-sm')}</button>
      </div>
      <div class="total">${esc(money(summary.total, summary.currency))}</div>
      <div class="total-caption">потрачено за месяц</div>
      ${others.length ? `<div class="dim" style="margin-top:4px">+ ${others.map((b) => esc(money(b.total, b.key))).join(' · ')}</div>` : ''}
      <div class="row"><div class="label">Регулярные в месяц</div>
        <div class="value">${esc(money(summary.planned_monthly, summary.currency))}</div></div>
      <div class="row"><div class="label">В квартал</div>
        <div class="value">${esc(money(summary.planned_quarterly, summary.currency))}</div></div>
      <div class="row"><div class="label">В год</div>
        <div class="value">${esc(money(summary.planned_yearly, summary.currency))}</div></div>
    </div>

    <div class="panel"><h3>${icon('wallet')} По категориям</h3>${categories}</div>

    <div class="panel"><h3>${icon('repeat')} Регулярные платежи</h3>${templates}
      <button class="btn small outline" data-new-template style="margin-top:12px">
        ${icon('plus', 'ic-sm')} Добавить регулярный
      </button>
    </div>

    <div class="panel"><h3>${icon('money')} Траты месяца</h3>
      ${state.expenses.length ? state.expenses.map(expenseRow).join('') : '<div class="dim">Пока пусто</div>'}
    </div>`;
}

/* ---------- рендер: настройки ---------- */

function renderSettings() {
  const me = state.me;
  const shared = state.lists.filter((l) => l.is_shared);
  view.innerHTML = `
    <div class="panel">
      <h3>${icon('users')} ${esc(me.household_title)}</h3>
      ${me.members.map((m) => `<div class="row"><div class="label">${esc(m.name)}</div>
        <div class="value dim">${m.id === me.user.id ? 'это ты' : ''}</div></div>`).join('')}
      <div class="share-box">
        <input readonly value="${esc(me.invite_url)}">
        <button class="btn small outline" data-copy="${esc(me.invite_url)}">${icon('copy', 'ic-sm')} Копировать</button>
      </div>
      <div class="dim" style="margin-top:10px">
        Отправь эту ссылку второй половинке — списки и траты станут общими.
      </div>
    </div>

    <div class="panel">
      <h3>${icon('link')} Открытые ссылки</h3>
      ${shared.length ? shared.map((l) => `<div class="row">
        <div class="label">${iconBadge(l.emoji, 'sm')} ${esc(l.title)}</div>
        <div class="value">
        <button class="btn small icon outline" data-send-list="${l.id}" aria-label="Отправить">${icon('share', 'ic-sm')}</button>
        <button class="btn small icon outline" data-copy="${esc(l.share_url)}" aria-label="Копировать">${icon('copy', 'ic-sm')}</button>
        <button class="btn small danger" data-unshare="${l.id}">Закрыть</button></div>
      </div>`).join('') : '<div class="dim">Пока ничего не расшарено. Открой список и нажми «Поделиться».</div>'}
    </div>

    <div class="panel">
      <h3>${icon('money')} Категории трат</h3>
      ${state.expenseCategories.map((c) => `<div class="row">
        <div class="label">${iconBadge(c.emoji, 'sm')} ${esc(c.title)}</div>
        <div class="value"><button class="btn small icon danger" data-delete-expense-category="${c.id}" aria-label="Удалить">${icon('trash', 'ic-sm')}</button></div>
      </div>`).join('')}
      <button class="btn small outline" data-new-expense-category style="margin-top:12px">
        ${icon('plus', 'ic-sm')} Новая категория
      </button>
    </div>

    <div class="panel">
      <h3>${icon('info')} Как это работает</h3>
      <div class="dim">
        Кидай боту ссылку на товар — он вытянет название, цену, валюту и картинку
        и положит в подходящую категорию. Пиши «450 бензин» — запишет трату.
        Любой список можно открыть по ссылке: гости увидят его без Telegram
        и смогут забронировать подарок.
      </div>
    </div>`;
}

/* ---------- модальные окна ---------- */

function closeSheet() { modalRoot.innerHTML = ''; }

function openSheet(title, html, onSubmit) {
  modalRoot.innerHTML = `<div class="sheet-backdrop">
    <form class="sheet"><h2>${esc(title)}</h2>${html}
      <div class="sheet-actions">
        <button type="button" class="btn" data-cancel>Отмена</button>
        <button type="submit" class="btn primary">Сохранить</button>
      </div>
    </form>
  </div>`;
  const backdrop = modalRoot.firstElementChild;
  const form = backdrop.querySelector('form');
  backdrop.addEventListener('click', (event) => { if (event.target === backdrop) closeSheet(); });
  form.querySelector('[data-cancel]').addEventListener('click', closeSheet);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    const button = form.querySelector('[type=submit]');
    button.disabled = true;
    try {
      await onSubmit(data);
      closeSheet();
    } catch (error) {
      toast(error.message);
      button.disabled = false;
    }
  });
  form.querySelector('input, select, textarea')?.focus();
}

/* В нативном <select> картинку не покажешь, поэтому в выпадающих списках
   остаются только названия — без эмодзи и без иконок. */
function listOptions(kind, selectedId) {
  return state.lists.filter((l) => l.kind === kind)
    .map((l) => `<option value="${l.id}" ${l.id === selectedId ? 'selected' : ''}>${esc(l.title)}</option>`)
    .join('');
}

/* Сетка иконок вместо поля «введи эмодзи». В базу уезжает всё тот же эмодзи —
   его бот пишет в чат, где svg не вставишь. */
function iconPicker(selected) {
  const current = ICON_CHOICES.includes(selected) ? selected : ICON_CHOICES[0];
  return `<label class="field"><span>Иконка</span>
    <div class="icon-picker">
      ${ICON_CHOICES.map((emoji, index) => `
        <input type="radio" name="emoji" id="icon-${index}" value="${esc(emoji)}" ${emoji === current ? 'checked' : ''}>
        <label for="icon-${index}">${iconForEmoji(emoji)}</label>`).join('')}
    </div>
  </label>`;
}


/* Своё фото для позиции. Content-Type не ставим руками — браузер сам допишет
   границу multipart, без неё сервер разбор не осилит. */
async function uploadPhoto(itemId, file) {
  const body = new FormData();
  body.append('file', file);
  const response = await fetch(`/api/items/${itemId}/image`, {
    method: 'POST',
    headers: { 'X-Telegram-Init-Data': initData },
    body,
  });
  if (!response.ok) {
    let detail = `Ошибка ${response.status}`;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* пусто */ }
    throw new Error(detail);
  }
  return response.json();
}

function photoField(item) {
  if (!item) return '';  // у новой позиции ещё нет id, грузить некуда
  return `<label class="field"><span>Фото</span>
    <div class="photo-row">
      <div class="photo-preview" id="photo-preview">${item.image_url
        ? `<img src="${esc(item.image_url)}" alt="" onerror="this.remove()">`
        : icon('inbox')}</div>
      <div class="photo-actions">
        <input type="file" accept="image/*" id="photo-input" hidden>
        <button type="button" class="btn small outline" data-pick-photo>
          ${icon('plus', 'ic-sm')} ${item.image_url ? 'Заменить фото' : 'Загрузить фото'}
        </button>
        ${item.image_url ? `<button type="button" class="btn small danger" data-drop-photo>Убрать</button>` : ''}
        <div class="dim" style="font-size:12px">JPEG, PNG, WEBP или GIF до 4 МБ</div>
      </div>
    </div>
  </label>`;
}

function openItemSheet(item = null) {
  const kind = state.tab === 'wishlist' ? 'wishlist' : 'shopping';
  const listId = item ? item.list_id : state.active[kind];
  const bothKinds = ['shopping', 'wishlist']
    .map((k) => `<optgroup label="${k === 'shopping' ? 'Покупки' : 'Вишлисты'}">${listOptions(k, listId)}</optgroup>`)
    .join('');
  const auto = item ? '' : '<option value="">Подобрать категорию автоматически</option>';

  openSheet(item ? 'Позиция' : 'Новая позиция', `
    <label class="field"><span>Ссылка на товар</span>
      <input name="url" type="url" inputmode="url" placeholder="https://…" value="${esc(item?.url || '')}"></label>
    ${item ? '' : '<div class="dim" style="margin:-6px 0 12px">Название, цену, валюту и картинку возьму со страницы сама — остальное можно не заполнять.</div>'}
    <label class="field"><span>Название ${item ? '' : '(необязательно)'}</span>
      <input name="title" value="${esc(item?.title || '')}"></label>
    ${photoField(item)}
    <div class="grid-2">
      <label class="field"><span>Цена</span>
        <input name="price" type="number" step="0.01" inputmode="decimal" value="${item?.price ?? ''}"></label>
      <label class="field"><span>Валюта</span>
        <input name="currency" value="${esc(item?.currency || state.me.currency)}"></label>
    </div>
    <label class="field"><span>Список</span><select name="list_id">${auto}${bothKinds}</select></label>
    ${kind === 'wishlist' ? '' : `<label class="field"><span>Приоритет</span>
      <select name="priority">
        <option value="0" ${!item?.priority ? 'selected' : ''}>Не выбран</option>
        <option value="3" ${item?.priority === 3 ? 'selected' : ''}>Высокий</option>
        <option value="2" ${item?.priority === 2 ? 'selected' : ''}>Средний</option>
        <option value="1" ${item?.priority === 1 ? 'selected' : ''}>Низкий</option>
      </select></label>`}
    <label class="field"><span>Заметка</span><input name="note" value="${esc(item?.note || '')}"></label>
  `, async (data) => {
    const payload = {
      url: data.url || null,
      title: data.title || null,
      price: data.price ? Number(data.price) : null,
      currency: data.currency || null,
      note: data.note || null,
      list_id: data.list_id ? Number(data.list_id) : null,
      priority: Number(data.priority || 0),
    };
    if (!payload.url && !payload.title) throw new Error('Нужна ссылка или название');
    if (item) {
      await api(`/api/items/${item.id}`, { method: 'PATCH', body: payload });
    } else {
      toast('Читаю страницу…');
      await api('/api/items', { method: 'POST', body: payload });
    }
    await refresh();
  });

  if (!item) return;
  const form = modalRoot.querySelector('form');
  const input = form?.querySelector('#photo-input');
  const preview = form?.querySelector('#photo-preview');

  form?.querySelector('[data-pick-photo]')?.addEventListener('click', () => input?.click());
  form?.querySelector('[data-drop-photo]')?.addEventListener('click', async () => {
    try {
      await api(`/api/items/${item.id}/image`, { method: 'DELETE' });
      if (preview) preview.innerHTML = icon('inbox');
      toast('Фото убрала');
      await refresh();
    } catch (error) {
      toast(error.message);
    }
  });
  input?.addEventListener('change', async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      toast('Загружаю…');
      const updated = await uploadPhoto(item.id, file);
      if (preview) preview.innerHTML = `<img src="${updated.image_url}?t=${Date.now()}" alt="">`;
      toast('Фото на месте');
      await refresh();
    } catch (error) {
      toast(error.message);
    }
  });
}

function openExpenseSheet(expense = null, { template = false } = {}) {
  const isTemplate = expense ? expense.is_template : template;
  const today = new Date().toISOString().slice(0, 10);
  const options = state.expenseCategories
    .map((c) => `<option value="${c.id}" ${c.id === expense?.category_id ? 'selected' : ''}>${esc(c.title)}</option>`)
    .join('');
  const periods = Object.entries(PERIODS)
    .map(([key, title]) => `<option value="${key}" ${key === (expense?.period || (isTemplate ? 'monthly' : 'once')) ? 'selected' : ''}>${title}</option>`)
    .join('');

  openSheet(isTemplate ? 'Регулярный платёж' : 'Трата', `
    <div class="grid-2">
      <label class="field"><span>Сумма</span>
        <input name="amount" type="number" step="0.01" inputmode="decimal" required value="${expense?.amount ?? ''}"></label>
      <label class="field"><span>Валюта</span>
        <input name="currency" value="${esc(expense?.currency || state.me.currency)}"></label>
    </div>
    <label class="field"><span>На что</span>
      <input name="title" placeholder="бензин, аптека, садик" value="${esc(expense?.title || '')}"></label>
    <label class="field"><span>Категория</span>
      <select name="category_id"><option value="">Без категории</option>${options}</select></label>
    <div class="grid-2">
      <label class="field"><span>Периодичность</span><select name="period">${periods}</select></label>
      <label class="field"><span>Дата</span>
        <input name="spent_on" type="date" value="${expense?.spent_on || today}"></label>
    </div>
    ${expense ? `<button type="button" class="btn danger block" data-delete-expense="${expense.id}">Удалить</button>` : ''}
  `, async (data) => {
    const payload = {
      amount: Number(data.amount),
      title: data.title || '',
      currency: data.currency || null,
      period: data.period,
      spent_on: data.spent_on || today,
      category_id: data.category_id ? Number(data.category_id) : null,
    };
    if (!payload.amount || payload.amount <= 0) throw new Error('Сумма должна быть больше нуля');
    if (expense) {
      await api(`/api/expenses/${expense.id}`, { method: 'PATCH', body: payload });
    } else {
      await api('/api/expenses', { method: 'POST', body: { ...payload, is_template: isTemplate } });
    }
    await refresh();
  });
}

function openListSheet(kind) {
  openSheet(kind === 'wishlist' ? 'Новый вишлист' : 'Новая категория', `
    <label class="field"><span>Название</span><input name="title" required></label>
    ${iconPicker(kind === 'wishlist' ? '🎁' : '📦')}
    ${kind === 'wishlist' ? `<label class="field"><span>Чей</span>
      <select name="personal"><option value="">Общий на двоих</option><option value="1">Только мой</option></select></label>` : ''}
  `, async (data) => {
    if (!data.title?.trim()) throw new Error('Нужно название');
    const created = await api('/api/lists', {
      method: 'POST',
      body: { kind, title: data.title.trim(), emoji: data.emoji || '📦', personal: Boolean(data.personal) },
    });
    state.active[kind] = created.id;
    await refresh();
  });
}

function openRenameSheet(list) {
  openSheet('Название списка', `
    <label class="field"><span>Название</span><input name="title" value="${esc(list.title)}" required></label>
    ${iconPicker(list.emoji)}
  `, async (data) => {
    await api(`/api/lists/${list.id}`, { method: 'PATCH', body: { title: data.title, emoji: data.emoji } });
    await refresh();
  });
}

function openExpenseCategorySheet() {
  openSheet('Категория трат', `
    <label class="field"><span>Название</span><input name="title" required></label>
    ${iconPicker('💸')}
  `, async (data) => {
    await api('/api/expense-categories', { method: 'POST', body: { title: data.title, emoji: data.emoji } });
    await refresh();
  });
}

/* ---------- действия ---------- */

async function shareList(listId) {
  const list = state.lists.find((l) => l.id === listId);
  if (!list.is_shared) {
    await api(`/api/lists/${listId}`, { method: 'PATCH', body: { is_shared: true } });
    await refresh();
    toast('Ссылка готова — копируй и отправляй');
    return;
  }
  copy(list.share_url);
}

/* Родной шеринг Telegram: открывает выбор чата и вставляет ссылку.
   Вне Telegram (обычный браузер) — та же страница в новой вкладке. */
function sendLink(url, title) {
  const share = 'https://t.me/share/url?url=' + encodeURIComponent(url)
    + '&text=' + encodeURIComponent(`${title} — список подарков`);
  if (tg?.openTelegramLink) tg.openTelegramLink(share);
  else window.open(share, '_blank', 'noopener');
}

function copy(text) {
  navigator.clipboard?.writeText(text)
    .then(() => toast('Скопировано'))
    .catch(() => toast(text));
}

document.addEventListener('click', async (event) => {
  const target = event.target.closest('[data-pick-list], [data-new-list], [data-toggle-bought], [data-edit-item],'
    + '[data-delete-item], [data-toggle-shown], [data-share-list], [data-rename-list], [data-delete-list],'
    + '[data-copy], [data-send-list], [data-send-invite], [data-toggle-surprise], [data-toggle-prices], [data-month], [data-edit-expense], [data-delete-expense], [data-pay-template],'
    + '[data-new-template], [data-new-expense-category], [data-delete-expense-category], [data-unshare]');
  if (!target) return;
  const data = target.dataset;

  try {
    if (data.pickList) {
      const kind = state.tab === 'wishlist' ? 'wishlist' : 'shopping';
      state.active[kind] = Number(data.pickList);
      haptic();
      await loadItems(state.active[kind]);
      renderItemsView(kind);
    } else if (data.newList) {
      openListSheet(data.newList);
    } else if (data.toggleBought) {
      const item = state.items.find((i) => i.id === Number(data.toggleBought));
      await api(`/api/items/${item.id}`, {
        method: 'PATCH', body: { status: item.status === 'bought' ? 'active' : 'bought' },
      });
      haptic();
      await refresh();
    } else if (data.editItem) {
      openItemSheet(state.items.find((i) => i.id === Number(data.editItem)));
    } else if (data.deleteItem) {
      if (!confirm('Удалить позицию?')) return;
      await api(`/api/items/${data.deleteItem}`, { method: 'DELETE' });
      await refresh();
    } else if (data.toggleShown !== undefined) {
      state.showBought = !state.showBought;
      renderItemsView(state.tab === 'wishlist' ? 'wishlist' : 'shopping');
    } else if (data.shareList) {
      await shareList(Number(data.shareList));
    } else if (data.unshare) {
      await api(`/api/lists/${data.unshare}`, { method: 'PATCH', body: { is_shared: false } });
      await refresh();
    } else if (data.renameList) {
      openRenameSheet(state.lists.find((l) => l.id === Number(data.renameList)));
    } else if (data.deleteList) {
      if (!confirm('Удалить список вместе со всем содержимым?')) return;
      await api(`/api/lists/${data.deleteList}`, { method: 'DELETE' });
      await refresh();
    } else if (data.copy) {
      copy(data.copy);
    } else if (data.togglePrices) {
      const target = state.lists.find((l) => l.id === Number(data.togglePrices));
      const show = !target.show_prices_to_guests;
      await api(`/api/lists/${target.id}`, { method: 'PATCH', body: { show_prices_to_guests: show } });
      toast(show ? 'Гости видят цены' : 'Цены от гостей скрыты');
      await refresh();
    } else if (data.toggleSurprise) {
      const wish = state.lists.find((l) => l.id === Number(data.toggleSurprise));
      const hide = !wish.hide_reservations_from_owner;
      await api(`/api/lists/${wish.id}`, { method: 'PATCH', body: { hide_reservations_from_owner: hide } });
      toast(hide ? 'Брони спрятаны — сюрприз сохранится' : 'Брони теперь видны тебе');
      await refresh();
    } else if (data.sendInvite) {
      sendLink(data.sendInvite, 'Наши списки и вишлисты');
    } else if (data.sendList) {
      const shared = state.lists.find((l) => l.id === Number(data.sendList));
      if (shared?.share_url) sendLink(shared.share_url, shared.title);
    } else if (data.month) {
      state.month = new Date(state.month.getFullYear(), state.month.getMonth() + Number(data.month), 1);
      await loadExpenses();
      renderExpensesView();
    } else if (data.editExpense) {
      const id = Number(data.editExpense);
      openExpenseSheet(state.expenses.find((e) => e.id === id) || state.templates.find((e) => e.id === id));
    } else if (data.deleteExpense) {
      if (!confirm('Удалить трату?')) return;
      await api(`/api/expenses/${data.deleteExpense}`, { method: 'DELETE' });
      closeSheet();
      await refresh();
    } else if (data.payTemplate) {
      await api(`/api/expenses/${data.payTemplate}/pay`, { method: 'POST', body: {} });
      haptic('medium');
      toast('Записала оплату');
      await refresh();
    } else if (data.newTemplate !== undefined) {
      openExpenseSheet(null, { template: true });
    } else if (data.newExpenseCategory !== undefined) {
      openExpenseCategorySheet();
    } else if (data.deleteExpenseCategory) {
      if (!confirm('Удалить категорию? Траты останутся без категории.')) return;
      await api(`/api/expense-categories/${data.deleteExpenseCategory}`, { method: 'DELETE' });
      await refresh();
    }
  } catch (error) {
    toast(error.message);
  }
});

document.querySelectorAll('nav.tabbar button').forEach((button) => {
  button.addEventListener('click', async () => {
    document.querySelectorAll('nav.tabbar button').forEach((b) => b.classList.remove('active'));
    button.classList.add('active');
    state.tab = button.dataset.tab;
    haptic();
    await refresh();
  });
});

fab.addEventListener('click', () => {
  if (state.tab === 'expenses') openExpenseSheet();
  else openItemSheet();
});

/* ---------- главный цикл ---------- */

async function refresh() {
  try {
    if (state.tab === 'shopping' || state.tab === 'wishlist') {
      await loadLists();
      await loadItems(state.active[state.tab]);
      renderItemsView(state.tab);
      fab.hidden = false;
    } else if (state.tab === 'expenses') {
      await loadExpenses();
      renderExpensesView();
      fab.hidden = false;
    } else {
      await Promise.all([loadLists(), (async () => {
        state.expenseCategories = await api('/api/expense-categories');
      })()]);
      renderSettings();
      fab.hidden = true;
    }
  } catch (error) {
    view.innerHTML = `<div class="empty"><div class="big">${icon('sad')}</div>${esc(error.message)}</div>`;
  }
}

(async function init() {
  try {
    await loadCore();
    await refresh();
  } catch (error) {
    const hint = initData
      ? 'Отправь боту /start и открой приложение кнопкой из свежего сообщения.'
      : 'Telegram не передал данные входа. Закрой это окно, отправь боту /start и нажми кнопку «Открыть приложение» — по обычной ссылке приложение не работает.';
    view.innerHTML = `<div class="empty"><div class="big">${icon('lock')}</div>
      Не получилось авторизоваться: ${esc(error.message)}<br><br>
      ${hint}
      <div class="dim" style="margin-top:16px;font-size:12px">
        SDK: ${tg ? 'загружен' : 'не загрузился'} · адрес: ${initDataFromUrl() ? 'с данными' : 'пуст'}
        · память: ${storedInitData() ? 'есть' : 'пусто'}<br>
        ${esc(tg?.platform || 'нет платформы')} · версия ${esc(tg?.version || '—')}
      </div></div>`;
  }
})();

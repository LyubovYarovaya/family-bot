/* Набор SVG-иконок. Рисуем контуром в 24×24, цвет берём из currentColor —
   поэтому иконка везде подхватывает цвет текста и не требует отдельных файлов.

   Эмодзи никуда не делись из базы: бот пишет их в чат, где иконку не вставишь.
   Приложение просто показывает вместо эмодзи картинку — карта EMOJI_ICON. */

const ICONS = {
  bag: '<path d="M5 8h14l-1.1 12H6.1L5 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
  gift: '<rect x="3" y="9.5" width="18" height="11.5" rx="2.2"/><path d="M3 13.8h18M12 9.5V21"/>'
    + '<path d="M12 9.5S10.6 5 8.6 5a2.2 2.2 0 1 0 0 4.5H12Z"/>'
    + '<path d="M12 9.5S13.4 5 15.4 5a2.2 2.2 0 1 1 0 4.5H12Z"/>',
  wallet: '<rect x="3" y="6" width="18" height="14" rx="3.2"/><path d="M3 10.2h18"/>'
    + '<circle cx="16.6" cy="15" r="1.3"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="2.2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2.2"/>'
    + '<rect x="3.5" y="13.5" width="7" height="7" rx="2.2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2.2"/>',

  plus: '<path d="M12 5.5v13M5.5 12h13"/>',
  check: '<path d="m5 12.8 4.3 4.2L19 7"/>',
  undo: '<path d="M9 14.5 4 9.5l5-5"/><path d="M4 9.5h10.5a5.5 5.5 0 0 1 0 11H9"/>',
  pencil: '<path d="M4 20h4.2L20 8.2a2.9 2.9 0 0 0-4.2-4.2L4 15.8V20Z"/><path d="m14.4 5.6 4 4"/>',
  trash: '<path d="M4 6.8h16M9.8 4h4.4"/><path d="M6.4 6.8 7.5 20h9l1.1-13.2"/><path d="M10.3 10.6v5.6M13.7 10.6v5.6"/>',
  link: '<path d="M10.2 13.8a4.2 4.2 0 0 0 6.2.5l2-2a4.2 4.2 0 0 0-5.9-5.9l-1.1 1"/>'
    + '<path d="M13.8 10.2a4.2 4.2 0 0 0-6.2-.5l-2 2a4.2 4.2 0 0 0 5.9 5.9l1.1-1"/>',
  share: '<circle cx="18" cy="5.5" r="2.6"/><circle cx="6" cy="12" r="2.6"/><circle cx="18" cy="18.5" r="2.6"/>'
    + '<path d="m8.3 10.7 7.4-3.9M8.3 13.3l7.4 3.9"/>',
  lock: '<rect x="4" y="10" width="16" height="10.5" rx="2.8"/><path d="M8 10V7.2a4 4 0 0 1 8 0V10"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2.6"/>'
    + '<path d="M15 9V6.6A2.6 2.6 0 0 0 12.4 4H6.6A2.6 2.6 0 0 0 4 6.6v5.8A2.6 2.6 0 0 0 6.6 15H9"/>',
  left: '<path d="m14 5.5-6.5 6.5L14 18.5"/>',
  right: '<path d="m10 5.5 6.5 6.5L10 18.5"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  repeat: '<path d="M17 3.2 20.2 6.4 17 9.6"/><path d="M3.8 12.5V9.4a3 3 0 0 1 3-3h13.4"/>'
    + '<path d="M7 20.8 3.8 17.6 7 14.4"/><path d="M20.2 11.5v3.1a3 3 0 0 1-3 3H3.8"/>',
  note: '<path d="M5.2 3.8h8.6l5 5V20a1 1 0 0 1-1 1H5.2a1 1 0 0 1-1-1V4.8a1 1 0 0 1 1-1Z"/>'
    + '<path d="M13.8 3.8v5h5"/><path d="M8 13h7M8 16.6h4.6"/>',
  ribbon: '<path d="M7 3.5h10v13.8L12 14l-5 3.3V3.5Z"/>',
  sparkles: '<path d="m11 4 1.5 4.2L16.7 9.7l-4.2 1.5L11 15.4 9.5 11.2 5.3 9.7l4.2-1.5L11 4Z"/>'
    + '<path d="m18 14.4.9 2.2 2.2.9-2.2.9-.9 2.2-.9-2.2-2.2-.9 2.2-.9.9-2.2Z"/>',
  info: '<circle cx="12" cy="12" r="8.8"/><path d="M12 11.2v5.2"/><path d="M12 7.6v.6"/>',
  question: '<circle cx="12" cy="12" r="8.8"/>'
    + '<path d="M9.6 9.7a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1.1 1-1.1 1.8v.4"/><path d="M12 17.3v.5"/>',
  sad: '<circle cx="12" cy="12" r="8.8"/><path d="M8.4 15.6a4.6 4.6 0 0 1 7.2 0"/>'
    + '<path d="M9.2 9.4v.6M14.8 9.4v.6"/>',
  users: '<circle cx="9.2" cy="8" r="3.3"/><path d="M3.2 19.6a6 6 0 0 1 12 0"/>'
    + '<path d="M15.6 5.4a3.3 3.3 0 0 1 0 5.2"/><path d="M17 14.6a5.6 5.6 0 0 1 3.8 5"/>',
  tag: '<path d="M4 4h6.8l9.2 9.2-6.8 6.8L4 10.8V4Z"/><circle cx="8.4" cy="8.4" r="1.4"/>',
  inbox: '<path d="M5.8 4.4h12.4l2.6 7.6v5.2a2 2 0 0 1-2 2H5.2a2 2 0 0 1-2-2V12l2.6-7.6Z"/>'
    + '<path d="M3.2 12h5l1.4 2.8h4.8L15.8 12h5"/>',
  eye: '<path d="M2.6 12S6.2 5.8 12 5.8 21.4 12 21.4 12 17.8 18.2 12 18.2 2.6 12 2.6 12Z"/>'
    + '<circle cx="12" cy="12" r="3"/>',
  eyeOff: '<path d="M4.4 4.4 19.6 19.6"/>'
    + '<path d="M9.5 6.2A9.6 9.6 0 0 1 12 5.8c5.8 0 9.4 6.2 9.4 6.2a17 17 0 0 1-3 3.7"/>'
    + '<path d="M6.4 8.5A17 17 0 0 0 2.6 12S6.2 18.2 12 18.2c1 0 2-.2 2.8-.5"/>'
    + '<path d="M10 10.1a3 3 0 0 0 4 4"/>',

  /* категории */
  plug: '<path d="M9 3v5.5M15 3v5.5"/><path d="M6.2 8.5h11.6v2.4a5.8 5.8 0 0 1-11.6 0V8.5Z"/><path d="M12 16.7V21"/>',
  pan: '<ellipse cx="9.6" cy="13" rx="6.4" ry="5.6"/><path d="M16 11.6h5.8"/>',
  house: '<path d="m3.2 11 8.8-7 8.8 7"/><path d="M5.6 9.5V20h12.8V9.5"/><path d="M9.8 20v-5h4.4v5"/>',
  thread: '<path d="M7.2 3.6h9.6M7.2 20.4h9.6"/><path d="M8.6 3.6v16.8M15.4 3.6v16.8"/>'
    + '<path d="M8.6 8.2h6.8M8.6 12h6.8M8.6 15.8h6.8"/>',
  bottle: '<path d="M10 2.8h4v2.6h-4z"/>'
    + '<path d="M9.2 5.4h5.6v2.8l1 2.2V19a2 2 0 0 1-2 2h-3.6a2 2 0 0 1-2-2v-8.6l1-2.2V5.4Z"/>'
    + '<path d="M8.6 13.2h6.8"/>',
  box: '<path d="m3.2 7.2 8.8-4 8.8 4v9.6l-8.8 4-8.8-4V7.2Z"/><path d="m3.2 7.2 8.8 4 8.8-4M12 11.2v9.6"/>',
  star: '<path d="m12 3.4 2.7 5.5 6 .9-4.3 4.2 1 6-5.4-2.8-5.4 2.8 1-6L3.3 9.8l6-.9L12 3.4Z"/>',
  car: '<path d="m4.8 11.4 1.7-4.3a2 2 0 0 1 1.9-1.3h7.2a2 2 0 0 1 1.9 1.3l1.7 4.3"/>'
    + '<path d="M4 11.4h16a1 1 0 0 1 1 1v4H3v-4a1 1 0 0 1 1-1Z"/>'
    + '<circle cx="7.4" cy="16.4" r="1.7"/><circle cx="16.6" cy="16.4" r="1.7"/>',
  health: '<path d="M12 20.2S4.6 15.4 4.6 10.4A4.6 4.6 0 0 1 12 6.9a4.6 4.6 0 0 1 7.4 3.5c0 5-7.4 9.8-7.4 9.8Z"/>'
    + '<path d="M6 12.4h2.8l1.4-2.4 2.2 4.8 1.4-2.4H18"/>',
  cart: '<circle cx="9.4" cy="19.6" r="1.6"/><circle cx="17" cy="19.6" r="1.6"/>'
    + '<path d="M3 4h2.2l2.6 11.2h10L20.4 7.4H6"/>',
  phone: '<rect x="7" y="2.6" width="10" height="18.8" rx="2.6"/><path d="M10.8 18.4h2.4"/>',
  dress: '<path d="M9 3.2 4.4 5.6l1.9 4.3 2-.7V20.8h7.4V9.2l2 .7 1.9-4.3L15 3.2a3 3 0 0 1-6 0Z"/>',
  film: '<rect x="3" y="5.2" width="18" height="13.6" rx="2.6"/><path d="M7.4 5.2v13.6M16.6 5.2v13.6M3 12h18"/>',
  money: '<rect x="2.6" y="6.2" width="18.8" height="11.6" rx="2.6"/><circle cx="12" cy="12" r="2.7"/>'
    + '<path d="M6 12h.5M17.5 12h.5"/>',
};

/* Эмодзи из базы → иконка. Чего нет в карте — рисуем ярлычком. */
const EMOJI_ICON = {
  '🔌': 'plug', '🍳': 'pan', '🏠': 'house', '🏡': 'house', '🧵': 'thread', '🧶': 'thread',
  '🍼': 'bottle', '👶': 'bottle', '📦': 'box', '🎁': 'gift', '⭐': 'star', '🌟': 'star',
  '🚗': 'car', '🚙': 'car', '🩺': 'health', '💊': 'health', '❤️': 'health', '🛒': 'cart',
  '🍔': 'cart', '🥦': 'cart', '📱': 'phone', '💻': 'plug', '👗': 'dress', '👕': 'dress',
  '👟': 'dress', '🎬': 'film', '🎮': 'film', '🎵': 'film', '💸': 'money', '💰': 'money',
  '🛍': 'bag', '🛍️': 'bag', '🔁': 'repeat', '🎀': 'ribbon', '🔗': 'link', '📝': 'note',
  '✨': 'sparkles', '🔒': 'lock', '❔': 'question', '❓': 'question', 'ℹ️': 'info',
  '👨‍👩‍👧': 'users', '👫': 'users', '🕊': 'inbox', '🙈': 'sad', '😕': 'sad', '📊': 'wallet',
};

/* Что предлагаем выбрать вместо ввода эмодзи руками. Значение — тот же эмодзи,
   он и уедет в базу, чтобы бот в чате писал его как раньше. */
const ICON_CHOICES = [
  '🛍', '📦', '🏠', '🍳', '🔌', '🧵', '🍼', '🎁', '⭐',
  '🚗', '🩺', '🛒', '📱', '👗', '🎬', '💸', '🔁', '🎀',
];

function icon(name, extraClass = '') {
  const body = ICONS[name] || ICONS.tag;
  return `<svg class="ic ${extraClass}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${body}</svg>`;
}

function iconForEmoji(emoji, extraClass = '') {
  return icon(EMOJI_ICON[String(emoji || '').trim()] || 'tag', extraClass);
}

/* Иконка категории в кружке — общий элемент списков, чипов и строк трат. */
function iconBadge(emoji, extraClass = '') {
  return `<span class="ibadge ${extraClass}">${iconForEmoji(emoji)}</span>`;
}

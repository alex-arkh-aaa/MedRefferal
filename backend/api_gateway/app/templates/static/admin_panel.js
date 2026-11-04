'use strict';

// ============================================================
// 1. УТИЛИТЫ
// ============================================================
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dt = v => v ? new Date(v).toLocaleString('ru-RU', {dateStyle:'short', timeStyle:'short'}) : '—';
const API = '/api/v1';

async function api(path, opts = {}) {
  const r = await fetch(API + path, { credentials: 'include', ...opts });
  if (r.status === 401) { location.href = '/'; throw new Error('401'); }
  if (r.status === 403) throw new Error('Нет доступа');
  const t = await r.text();
  let d = null;
  if (t) { try { d = JSON.parse(t); } catch { d = t; } }
  if (!r.ok) {
    let msg = 'HTTP ' + r.status;
    if (d && d.detail) {
      if (Array.isArray(d.detail)) {
        const FIELD_RU = {
          password:'Пароль', email:'Email', full_name:'ФИО', phone:'Телефон',
          name:'Название', city:'Город', address:'Адрес',
          default_rate:'Ставка', custom_rate:'Личная ставка', mode:'Режим',
          clinic_ids:'Клиники', specialization_ids:'Специализации',
          decision_reason:'Причина', active:'Статус', permissions:'Права',
        };
        const MSG_RU = [
          { re:/String should have at least (\d+) characters/i, fn:m=>`минимум ${m[1]} символов` },
          { re:/String should have at most (\d+) characters/i, fn:m=>`максимум ${m[1]} символов` },
          { re:/field required/i, fn:()=>'обязательное поле' },
          { re:/value is not a valid email address/i, fn:()=>'некорректный email' },
          { re:/Input should be a valid integer/i, fn:()=>'должно быть числом' },
          { re:/Input should be a valid number/i, fn:()=>'должно быть числом' },
          { re:/Input should be greater than or equal to (\d+)/i, fn:m=>`не меньше ${m[1]}` },
          { re:/Input should be less than or equal to (\d+)/i, fn:m=>`не больше ${m[1]}` },
          { re:/String should match pattern/i, fn:()=>'неверный формат' },
          { re:/Input should be a valid boolean/i, fn:()=>'должно быть true/false' },
          { re:/Input should be a valid list/i, fn:()=>'должен быть список' },
        ];
        msg = d.detail.map(e => {
          const key = Array.isArray(e.loc) ? e.loc.filter(x => !['body','query','path'].includes(x)).pop() : '';
          const fieldRu = FIELD_RU[key] || key || 'Поле';
          let msgRu = e.msg || 'ошибка';
          for (const m of MSG_RU) {
            const match = msgRu.match(m.re);
            if (match) { msgRu = m.fn(match); break; }
          }
          return `${fieldRu}: ${msgRu}`;
        }).join('; ');
      } else if (typeof d.detail === 'string') {
        msg = d.detail;
      } else {
        msg = 'Ошибка валидации';
      }
    } else if (d && d.error) {
      msg = d.error;
    }
    throw new Error(msg);
  }
  return d;
}

function validateForm(form) {
  const errors = [];
  form.querySelectorAll('input, select, textarea').forEach(el => {
    if (el.disabled || el.type === 'hidden') return;
    const v = (el.value || '').trim();
    const label = el.dataset.label || el.getAttribute('aria-label') || el.name || 'Поле';
    if (el.required && !v) { errors.push(`${label}: обязательно для заполнения`); return; }
    if (!v) return;
    if (el.type === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) errors.push(`${label}: некорректный email`);
    if (el.type === 'password' && el.minLength && v.length < el.minLength) errors.push(`${label}: минимум ${el.minLength} символов`);
    if (el.type === 'tel') {
      const digits = v.replace(/\D/g, '');
      if (digits.length < 10 || digits.length > 15) errors.push(`${label}: некорректный номер телефона`);
    }
    if (el.type === 'number') {
      const n = Number(v);
      if (el.min !== '' && n < Number(el.min)) errors.push(`${label}: не меньше ${el.min}`);
      if (el.max !== '' && n > Number(el.max)) errors.push(`${label}: не больше ${el.max}`);
    }
  });
  return errors;
}

function toast(m) {
  const t = $('#toast');
  t.textContent = m;
  t.classList.add('show');
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => t.classList.remove('show'), 4000);
}
function openDrawer(title, body) {
  $('#drawerTitle').textContent = title;
  $('#drawerBody').innerHTML = body;
  $('#backdrop').classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeDrawer() {
  $('#backdrop').classList.remove('open');
  document.body.style.overflow = '';
}

// ============================================================
// 2. СПРАВОЧНИКИ И РОЛЬ
// ============================================================
const S = { user: null, agents: [], admins: [], clinics: [], myClinics: [], specs: [] };

const NAME = {
  overview: 'Обзор',
  pending: 'Новые направления',
  admins: 'Администраторы',
  agents: 'Агенты',
  clinics: 'Клиники',
  reports: 'Отчёты',
};
const ICONS = {
  overview: 'fa-house',
  pending: 'fa-file-medical',
  admins: 'fa-user-shield',
  agents: 'fa-user-doctor',
  clinics: 'fa-hospital',
  reports: 'fa-chart-bar',
};
const SL = { pending: 'Ожидает', active: 'Активен', inactive: 'Отключён', rejected: 'Отклонён' };
const SP = { pending: 'new', active: 'approved', inactive: 'rejected', rejected: 'rejected' };

// ============================================================
// 3. СОСТОЯНИЕ
// ============================================================
let page = 'overview';
let query = '';
let agentFilter = 'all';
let agentId = null;
let adminId = null;
let clinicId = null;
let profileTab = 'rates';
let profileQuery = '';

window.__referrals = null;
window.__pendingAgents = null;
window.__pendingClinics = null;
window.__pendingSpecs = null;
window.__pendingAdmins = null;
window.__agentRates = [];
window.__agentSpecs = [];
window.__agentCurrentId = null;

// ============================================================
// 4. ХЕЛПЕРЫ
// ============================================================
const isChef = () => S.user?.role === 'chef';
const cName = id => S.clinics.find(c => c.id === Number(id))?.name || '—';
const aName = id => S.admins.find(a => a.id === Number(id))?.full_name || '—';
const sName = id => S.specs.find(s => s.id === Number(id))?.name || ('#' + id);
const myClinicIds = () => S.user?.clinic_ids || [];
const heading = (t, d, act = '') => `<div class="heading"><div><h1>${esc(t)}</h1>${d ? `<p class="muted">${esc(d)}</p>` : ''}</div>${act}</div>`;
const table = (h, rows) => `<div class="tablewrap"><table><thead><tr>${h.map(x => `<th>${x}</th>`).join('')}</tr></thead><tbody>${rows.join('') || `<tr><td colspan="${h.length}" class="empty">Ничего не найдено</td></tr>`}</tbody></table></div>`;
const pill = (l, t = '') => `<span class="pill ${t}">${esc(l)}</span>`;

// ============================================================
// 5. ЗАГРУЗКА ДАННЫХ
// ============================================================
async function loadAll() {
  try {
    const reqs = [api('/agents'), api('/clinics'), api('/specializations')];
    if (isChef()) reqs.push(api('/admins'));
    const [agents, clinics, specs, admins] = await Promise.all(reqs);
    S.agents = agents || [];
    S.clinics = clinics || [];
    S.specs = specs || [];
    S.admins = isChef() ? (admins || []) : [];
    S.myClinics = S.clinics.filter(c => myClinicIds().includes(c.id)).sort((a, b) => a.id - b.id);
  } catch (e) {
    console.error('loadAll error:', e);
    toast('Ошибка загрузки: ' + e.message);
  }
}


async function loadReferrals() {
  try {
    const list = await api('/admin/referrals?status=new');
    window.__referrals = Array.isArray(list) ? list : [];
  } catch (e) {
    window.__referrals = [];
    const el = document.getElementById('refResults');
    if (el) el.innerHTML = `<div class="empty">Ошибка загрузки: ${esc(e.message)}</div>`;
    return;
  }
  // Обновляем ТОЛЬКО таблицу, не всю страницу
  const el = document.getElementById('refResults');
  if (el) {
    const list = window.__referrals.filter(r => !query || [r.patient_full_name, r.clinic_name].join(' ').toLowerCase().includes(query.toLowerCase()));
    el.innerHTML = referralTable(list);
  }
}

async function loadPendingAgents() {
  const el = document.getElementById('regResults');
  if (!el) return;
  try {
    const reqs = [api('/agents?status=pending'), api('/clinics'), api('/specializations')];
    if (isChef()) reqs.push(api('/admins'));
    const [agents, clinics, specs, admins] = await Promise.all(reqs);
    window.__pendingAgents = Array.isArray(agents) ? agents : [];
    window.__pendingClinics = Array.isArray(clinics) ? clinics : [];
    window.__pendingSpecs = Array.isArray(specs) ? specs : [];
    window.__pendingAdmins = isChef() ? (Array.isArray(admins) ? admins : []) : [];
    renderPendingAgents();
  } catch (e) {
    el.innerHTML = `<div class="empty">Ошибка загрузки: ${esc(e.message)}</div>`;
  }
}

async function loadAgentRates(agentIdArg) {
  const el = document.getElementById('rateResults');
  if (!el) return;
  try {
    const [rates, specs] = await Promise.all([
      api(`/agents/${agentIdArg}/rates`),
      api('/specializations'),
    ]);
    window.__agentRates = Array.isArray(rates) ? rates : [];
    window.__agentSpecs = Array.isArray(specs) ? specs : [];
    window.__agentCurrentId = agentIdArg;
    renderAgentRates();
  } catch (e) {
    el.innerHTML = `<div class="empty">Ошибка загрузки: ${esc(e.message)}</div>`;
  }
}

async function loadHistoryModal(filter) {
  const el = document.getElementById('historyFilteredList');
  if (!el) return;
  try {
    const url = filter === 'all' ? '/history?limit=200' : `/history?limit=200&actor_type=${filter}`;
    const items = await api(url);
    el.innerHTML = items.length
      ? items.map(h => `<div class="change-item"><div class="change-item-body"><strong>${esc(h.label)}</strong><small>${esc(h.text)}</small><small style="color:#8da1a4;margin-top:2px">${esc(h.actor_type)}${h.actor_name ? ': ' + esc(h.actor_name) : ''}</small></div><div class="change-item-time">${dt(h.created_at)}</div></div>`).join('')
      : '<div class="empty">Нет записей</div>';
  } catch (e) {
    el.innerHTML = `<div class="empty">Ошибка: ${esc(e.message)}</div>`;
  }
}

// ============================================================
// 6. НАВИГАЦИЯ
// ============================================================
function navItems() {
  const base = ['overview', 'pending'];
  if (isChef()) base.push('admins');
  base.push('agents', 'clinics', 'reports');
  return base;
}
function navigate(p) {
  page = p;
  agentId = null;
  adminId = null;
  clinicId = null;
  query = '';
  location.hash = p;
  render();
  scrollTo(0, 0);
}
function render() {
  nav();
  const m = { overview, referrals, pending: referrals, admins, agents, clinics, reports };
  const html = (m[page] || overview)();
  const cont = document.querySelector('#content');
  if (cont) cont.innerHTML = html;
  setTimeout(() => {
    if (page === 'pending') loadReferrals();
    if (page === 'agents' && !agentId) loadPendingAgents();
    if (page === 'agents' && agentId) loadAgentRates(agentId);
  }, 0);
}
function nav() {
  const items = navItems();
$('#nav').innerHTML = items.map(t => `<button class="${page === t ? 'active' : ''}" data-page="${t}"><i class="fas ${ICONS[t]}"></i>${NAME[t]}</button>`).join('');
  const u = S.user || {};
  $('#userLabel').textContent = u.full_name || 'Пользователь';
  $('#userSub').textContent = isChef() ? 'Управление сетью' : (S.myClinics.map(c => c.name).join(', ') || 'Клиника');
  $('#topUserName').textContent = u.full_name || 'Пользователь';
  $('#topAvatar').textContent = (u.full_name || 'П').split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase();
  $('#sidebar').classList.remove('open');
}

// ============================================================
// 7. СТРАНИЦЫ
// ============================================================
function overview() {
  const pend = S.agents.filter(a => a.status === 'pending');
  const act = S.agents.filter(a => a.status === 'active');
  const stats = [
    { l: 'Новые направления', v: '—', d: 'Заявки агентов', p: 'pending' },
    { l: 'Агенты', v: act.length, d: 'Активные', p: 'agents' },
    { l: 'Клиники', v: S.myClinics.length, d: 'Ваши', p: 'clinics' },
  ];
  if (isChef()) stats.splice(1, 0, { l: 'Администраторы', v: S.admins.length, d: 'Всего', p: 'admins' });
  const cards = stats.map(i => `<button class="stat stat-action" data-page="${i.p}"><span class="stat-lbl">${i.l}</span><strong>${i.v}</strong><em>${i.d}</em></button>`).join('');

  const pendingBlock = `<section class="panel"><div class="panelhead"><div><h2>Заявки на регистрацию</h2><p>Ожидают рассмотрения</p></div><button class="btn small" data-page="agents">Все</button></div>${pend.length ? pend.slice(0, 5).map(a => `<div class="agent-overview"><span class="initials">${esc((a.full_name || '?').split(' ').map(n => n[0]).join('').slice(0, 2))}</span><span class="agent-overview-info"><strong>${esc(a.full_name)}</strong><small>${esc(a.email)}</small></span><button class="btn small profile-action" data-action="viewAgent" data-id="${a.id}">Открыть</button></div>`).join('') : '<div class="empty">Заявок нет</div>'}</section>`;

  const adminsBlock = isChef() ? `<section class="panel"><div class="panelhead"><div><h2>Администраторы</h2></div><button class="btn small" data-page="admins">Все</button></div>${S.admins.length ? S.admins.slice(0, 5).map(a => `<div class="agent-overview"><span class="initials">${esc((a.full_name || '?').split(' ').map(n => n[0]).join('').slice(0, 2))}</span><span class="agent-overview-info"><strong>${esc(a.full_name)}</strong><small>${esc(a.email)}</small></span><button class="btn small profile-action" data-action="viewAdmin" data-id="${a.id}">Профиль</button></div>`).join('') : '<div class="empty">Администраторов нет</div>'}</section>` : '';

  const historyBlock = `<section class="panel" style="margin-top:20px"><div class="panelhead"><div><h2>История изменений</h2><p>Последние 5 действий</p></div><button class="btn small" data-action="viewAllHistory">Показать всю историю</button></div><div id="historyList"><div class="empty">Загрузка...</div></div></section>`;

  return heading('Обзор', 'Сводная информация')
    + `<div class="grid">${cards}</div>`
    + `<div class="split">${pendingBlock}${adminsBlock}</div>`
    + historyBlock;
}

function referrals() {
  if (!window.__referrals) {
    return heading('Новые направления', 'Заявки агентов на рассмотрении')
      + `<section class="panel"><div id="refResults"><div class="empty">Загрузка...</div></div></section>`;
  }
  const list = window.__referrals.filter(r => !query || [r.patient_full_name, r.clinic_name].join(' ').toLowerCase().includes(query.toLowerCase()));
  return heading('Новые направления', 'Заявки агентов на рассмотрении')
    + `<section class="panel"><div class="panelhead"><input class="search" id="search" placeholder="Пациент или клиника" value="${esc(query)}"></div><div id="refResults">${referralTable(list)}</div></section>`;
}

function referralTable(list) {
  return table(['Пациент', 'Клиника', 'Специализация', 'Статус', ''], list.map(r => `<tr>
    <td><strong>${esc(r.patient_full_name || '—')}</strong><small>#${r.id}</small></td>
    <td class="wrap">${esc(r.clinic_name || '—')}</td>
    <td class="wrap">${esc(r.specialization_name || '—')}</td>
    <td>${r.status === 'new' ? pill('Новая', 'new') : r.status === 'approved' ? pill('Подтверждена', 'approved') : pill('Отклонена', 'rejected')}</td>
    <td><button class="btn small" data-action="viewReferral" data-id="${r.id}">Открыть</button></td>
  </tr>`));
}

function agents() {
  if (agentId) return agentProfile();
  const list = S.agents
    .filter(a => agentFilter === 'all' || a.status === agentFilter)
    .filter(a => !query || [a.full_name, a.email, a.phone || ''].join(' ').toLowerCase().includes(query.toLowerCase()));
  const pendingCount = S.agents.filter(a => a.status === 'pending').length;
  const adminCol = isChef() ? '<th>Админ</th>' : '';
  const headers = isChef()
    ? ['Агент', 'Email', 'Статус', 'Клиники', 'Админ', '']
    : ['Агент', 'Email', 'Статус', 'Клиники', ''];
  const rows = list.map(a => {
    const tds = `<td><strong>${esc(a.full_name)}</strong><small>#${a.id}</small></td>
      <td>${esc(a.email)}</td>
      <td>${pill(SL[a.status] || a.status, SP[a.status] || '')}</td>
      <td>${(a.clinic_ids || []).filter(c => isChef() || myClinicIds().includes(c)).map(cName).filter(Boolean).join(', ') || '—'}</td>`;
    const adminTd = isChef() ? `<td>${esc(aName(a.admin_id))}</td>` : '';
    const actionTd = `<td><button class="btn small" data-action="viewAgent" data-id="${a.id}">Профиль</button></td>`;
    return `<tr>${tds}${adminTd}${actionTd}</tr>`;
  });
  return heading('Агенты', isChef() ? 'Управление агентами' : 'Агенты ваших клиник',
    `<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      ${pendingCount ? `<button class="btn" data-action="scrollToRegistrations">Новые ↓ <span class="nav-count">${pendingCount}</span></button>` : ''}
    </div>`)
    + `<section class="panel"><div class="panelhead"><div class="controls"><input class="search" id="search" placeholder="Имя, email" value="${esc(query)}"><select class="filter" id="agentStatusFilter">${['all','pending','active','inactive','rejected'].map(s => `<option value="${s}" ${s === agentFilter ? 'selected' : ''}>${s === 'all' ? 'Все статусы' : SL[s]}</option>`).join('')}</select></div></div>${table(headers, rows)}</section>`
    + `<section class="panel section-anchor" id="registrationsBlock" style="margin-top:20px"><div class="panelhead"><div><h2>Регистрация агентов</h2><p>Новые заявки на рассмотрении</p></div><button class="btn small" data-action="refreshRegistrations">Обновить</button></div><div id="regResults"><div class="empty">Загрузка...</div></div></section>`;
}

function agentProfile() {
  const a = S.agents.find(x => x.id === Number(agentId));
  if (!a) return heading('Не найден', '', '<button class="btn small" data-page="agents">← Назад</button>');
  const actions = [
    a.status === 'pending' ? `<button class="btn primary" data-action="approve" data-id="${a.id}">Одобрить</button>` : '',
    a.status === 'pending' ? `<button class="btn danger-access" data-action="reject" data-id="${a.id}">Отклонить</button>` : '',
    `<button class="btn" data-action="editAgent" data-id="${a.id}">Редактировать</button>`,
    `<button class="btn danger-access" data-action="delAgent" data-id="${a.id}">Удалить</button>`,
  ].join('');
  return `<button class="btn small back-link" data-page="agents">← Назад</button>`
    + heading(a.full_name, `#${a.id} · ${a.email}`, `<div style="display:flex;gap:10px;flex-wrap:wrap">${actions}</div>`)
    + `<section class="panel profile-summary">
        <div><span class="meta-label">Статус</span>${pill(SL[a.status] || a.status, SP[a.status] || '')}</div>
        <div><span class="meta-label">Телефон</span><strong>${esc(a.phone || '—')}</strong></div>
        <div><span class="meta-label">Опыт</span><strong>${esc(a.experience || '—')}</strong></div>
        ${isChef() ? `<div><span class="meta-label">Админ</span><strong>${esc(aName(a.admin_id))}</strong></div>` : ''}
        <div style="grid-column:1/-1"><span class="meta-label">О себе</span><strong>${esc(a.about_myself || '—')}</strong></div>
      </section>`
    + `<section class="panel"><div class="panelhead"><h2>Клиники</h2></div><div style="padding:18px 22px">${(a.clinic_ids || []).filter(c => isChef() || myClinicIds().includes(c)).length ? (a.clinic_ids || []).filter(c => isChef() || myClinicIds().includes(c)).map(id => `<span class="multi-select-tag" style="margin:0 6px 6px 0">${esc(cName(id))}</span>`).join('') : '<span class="muted">Не привязан</span>'}</div></section>`
    + `<section class="panel"><div class="panelhead"><h2>Специализации</h2></div><div style="padding:18px 22px">${(a.specialization_ids || []).length ? (a.specialization_ids || []).map(id => `<span class="multi-select-tag" style="margin:0 6px 6px 0">${esc(sName(id))}</span>`).join('') : '<span class="muted">Нет</span>'}</div></section>`
    + `<div class="tabbar">
        <button class="${profileTab === 'rates' ? 'selected' : ''}" data-tab="rates">Вознаграждение</button>
        <button class="${profileTab === 'history' ? 'selected' : ''}" data-tab="history">История агента</button>
      </div>
      <section class="panel">
        <div class="panelhead">
          <div><h2>Вознаграждение агента</h2><p>Процент от стоимости услуги по её специализации</p></div>
          <input class="search" id="profileSearch" placeholder="Найти специализацию" value="${esc(profileQuery || '')}">
        </div>
        <div id="rateResults"><div class="empty">Загрузка...</div></div>
      </section>`;
}

function admins() {
  if (!isChef()) return heading('Доступ только для шефа', '', '<button class="btn small" data-page="overview">← Назад</button>');
  if (adminId) return adminProfile();
  const list = S.admins.filter(a => !query || [a.full_name, a.email].join(' ').toLowerCase().includes(query.toLowerCase()));
  return heading('Администраторы', '', `<button class="btn primary" data-action="newAdmin">Добавить</button>`)
    + `<section class="panel"><div class="panelhead"><input class="search" id="search" placeholder="Имя или email" value="${esc(query)}"></div>${table(['ФИО','Email','Клиники','Доступ',''], list.map(a => `<tr><td><strong>${esc(a.full_name)}</strong><small>#${a.id}</small></td><td>${esc(a.email)}</td><td>${(a.clinic_ids || []).map(cName).filter(Boolean).join(', ') || '—'}</td><td>${a.active ? pill('Активен', 'approved') : pill('Отключён', 'rejected')}</td><td><button class="btn small" data-action="viewAdmin" data-id="${a.id}">Профиль</button></td></tr>`))}</section>`;
}

function adminProfile() {
  const a = S.admins.find(x => x.id === Number(adminId));
  if (!a) return heading('Не найден', '', '<button class="btn small" data-page="admins">← Назад</button>');
  const linked = S.agents.filter(x => x.admin_id === a.id);
  return `<button class="btn small back-link" data-page="admins">← Назад</button>`
    + heading(a.full_name, `#${a.id}`, `<div style="display:flex;gap:10px"><button class="btn" data-action="editAdmin" data-id="${a.id}">Редактировать</button><button class="btn danger-access" data-action="delAdmin" data-id="${a.id}">Удалить</button></div>`)
    + `<section class="panel profile-summary">
        <div><span class="meta-label">ФИО</span><strong>${esc(a.full_name)}</strong></div>
        <div><span class="meta-label">Телефон</span><strong>${esc(a.phone || '—')}</strong></div>
        <div><span class="meta-label">Email</span><strong>${esc(a.email)}</strong></div>
        <div><span class="meta-label">Доступ</span>${a.active ? pill('Активен', 'approved') : pill('Отключён', 'rejected')}</div>
        <div><span class="meta-label">Регистрации агентов</span>${a.permissions?.reviewRegistrations ? pill('Разрешено', 'approved') : pill('Выключено', '')}</div>
      </section>`
    + `<section class="panel"><div class="panelhead"><h2>Клиники</h2></div><div style="padding:18px 22px">${(a.clinic_ids || []).length ? (a.clinic_ids || []).map(id => `<span class="multi-select-tag" style="margin:0 6px 6px 0">${esc(cName(id))}</span>`).join('') : '<span class="muted">Нет клиник</span>'}</div></section>`
    + `<section class="panel"><div class="panelhead"><h2>Агенты (${linked.length})</h2></div>${table(['Агент','Статус',''], linked.map(x => `<tr><td><strong>${esc(x.full_name)}</strong><small>${esc(x.email)}</small></td><td>${pill(SL[x.status] || x.status, SP[x.status] || '')}</td><td><button class="btn small" data-action="viewAgent" data-id="${x.id}">Профиль</button></td></tr>`))}</section>`;
}

function clinics() {
  if (clinicId) return clinicSettings();
  const list = S.clinics
    .filter(c => isChef() || myClinicIds().includes(c.id))
    .filter(c => !query || [c.name, c.city, c.address || '', c.phone || ''].join(' ').toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => a.id - b.id);
  const addBtn = isChef() ? `<button class="btn primary" data-action="newClinic">Добавить</button>` : '';
  return heading('Клиники', '', addBtn)
    + `<section class="panel"><div class="panelhead"><input class="search" id="search" placeholder="Название, город или адрес" value="${esc(query)}"></div>${table(['Клиника','Город','Адрес','Телефон','Статус','Агентов',''], list.map(c => `<tr><td><strong>${esc(c.name)}</strong><small>#${c.id}</small></td><td>${esc(c.city)}</td><td class="wrap">${esc(c.address || '—')}</td><td>${esc(c.phone || '—')}</td><td>${c.active ? pill('Активна', 'approved') : pill('Отключена', 'rejected')}</td><td>${S.agents.filter(a => (a.clinic_ids || []).includes(c.id)).length}</td><td><button class="btn small" data-action="clinicSettings" data-id="${c.id}">Настроить</button></td></tr>`))}</section>`;
}

function clinicSettings() {
  const c = S.clinics.find(x => x.id === Number(clinicId));
  if (!c) return heading('Не найдена', '', '<button class="btn small" data-page="clinics">← Назад</button>');
  const editBtn = isChef() ? `<button class="btn" data-action="editClinic" data-id="${c.id}">Редактировать</button>` : '';
  return `<button class="btn small back-link" data-page="clinics">← Назад</button>`
    + heading(c.name, `${c.city}${c.address ? ', ' + c.address : ''}`, editBtn)
    + `<div id="clinicSpecsBlock"></div>`;
}

async function clinicSpecsHtml(cid) {
  let list = [];
  try {
    list = await api(`/clinics/${cid}/specialties`);
  } catch (e) {
    return `<section class="panel"><div class="empty">Ошибка: ${esc(e.message)}</div></section>`;
  }
  list.sort((a, b) => a.specialization_id - b.specialization_id);
  return `<section class="panel"><div class="panelhead"><div><h2>Специализации</h2><p>Ставки и активность</p></div></div>
    ${table(['Специализация','Ставка','Статус',''], list.map(s => `<tr><td class="specialty-cell"><strong>${esc(s.specialization_name)}</strong><small>#${s.specialization_id}</small></td><td>${s.default_rate === null || s.default_rate === undefined ? '<span class="unset">Не задана</span>' : s.default_rate + '%'}</td><td>${s.active ? pill('Активна', 'approved') : pill('Отключена', 'rejected')}</td><td><button class="btn small" data-action="editSpec" data-clinic="${cid}" data-spec="${s.specialization_id}" data-rate="${s.default_rate ?? ''}" data-active="${s.active}">Изменить</button></td></tr>`))}
  </section>`;
}

function reports() {
  const by = {};
  ['pending', 'active', 'inactive', 'rejected'].forEach(s => by[s] = S.agents.filter(a => a.status === s).length);
  const byClinic = (isChef() ? S.clinics : S.myClinics).map(c => ({ name: c.name, agents: S.agents.filter(a => (a.clinic_ids || []).includes(c.id)).length }));
  const bySpec = {};
  S.agents.forEach(a => (a.specialization_ids || []).forEach(id => { bySpec[id] = (bySpec[id] || 0) + 1; }));
  const specRows = Object.entries(bySpec).map(([id, cnt]) => ({ name: sName(id), count: cnt })).sort((a, b) => b.count - a.count);
  return heading('Отчёты', 'Аналитика')
    + `<div class="grid">${Object.entries(by).map(([s, cnt]) => `<div class="stat"><span class="stat-lbl">${SL[s] || s}</span><strong>${cnt}</strong><em>агентов</em></div>`).join('')}</div>`
    + `<div class="report-cards"><section class="panel" style="padding:24px"><span class="report-tag">01 · КЛИНИКИ</span><h2 style="font-size:21px;margin:0 0 15px">Агенты по клиникам</h2>${table(['Клиника','Агентов'], byClinic.map(c => `<tr><td>${esc(c.name)}</td><td><strong>${c.agents}</strong></td></tr>`))}</section><section class="panel" style="padding:24px"><span class="report-tag">02 · СПЕЦИАЛИЗАЦИИ</span><h2 style="font-size:21px;margin:0 0 15px">Агенты по специализациям</h2>${table(['Специализация','Агентов'], specRows.map(s => `<tr><td>${esc(s.name)}</td><td><strong>${s.count}</strong></td></tr>`))}</section></div>`;
}

// ============================================================
// 8. МОДАЛКИ
// ============================================================
function multiSelectHtml(wrapId, dropId) {
  return `<div class="multi-select" id="${wrapId}"><span class="muted" style="font-size:13px">Выберите...</span><div class="multi-select-dropdown" id="${dropId}"></div></div>`;
}
function setupMultiSelect(wrapId, dropId, items, initial, onChange) {
  const wrap = document.getElementById(wrapId);
  const drop = document.getElementById(dropId);
  if (!wrap || !drop) return;
  const sel = new Set(initial || []);
  function render() {
    wrap.querySelectorAll('.multi-select-tag').forEach(t => t.remove());
    const m = wrap.querySelector('span.muted'); if (m) m.remove();
    if (!sel.size) wrap.insertAdjacentHTML('afterbegin', '<span class="muted" style="font-size:13px">Выберите...</span>');
    [...sel].forEach(id => {
      const it = items.find(x => Number(x.id) === Number(id));
      wrap.insertAdjacentHTML('afterbegin', `<span class="multi-select-tag" data-id="${id}">${esc(it?.name || ('#' + id))}<span class="x" data-remove="${id}">×</span></span>`);
    });
    drop.innerHTML = items.map(it => `<div class="multi-select-option ${sel.has(Number(it.id)) ? 'selected' : ''}" data-add="${it.id}">${esc(it.name)}</div>`).join('');
  }
  render();
  wrap.addEventListener('click', e => {
    const rm = e.target.closest('[data-remove]');
    if (rm) { sel.delete(Number(rm.dataset.remove)); render(); onChange([...sel]); e.stopPropagation(); return; }
    if (!e.target.closest('.multi-select-option')) drop.classList.toggle('show');
  });
  drop.addEventListener('click', e => {
    const o = e.target.closest('[data-add]');
    if (!o) return;
    const id = Number(o.dataset.add);
    if (sel.has(id)) sel.delete(id); else sel.add(id);
    render(); onChange([...sel]); drop.classList.add('show'); e.stopPropagation();
  });
  document.addEventListener('click', e => { if (!wrap.contains(e.target)) drop.classList.remove('show'); });
}

// ===== Регистрация агентов =====
function renderPendingAgents() {
  const el = document.getElementById('regResults');
  if (!el) return;
  const list = window.__pendingAgents || [];
  if (!list.length) { el.innerHTML = '<div class="empty">Новых заявок нет</div>'; return; }
  const clinicsOf = r => (r.clinic_ids || []).filter(c => isChef() || myClinicIds().includes(c)).map(cName).filter(Boolean).join(', ') || '—';
  el.innerHTML = table(
    ['Заявка / дата', 'Кандидат', 'Клиника', 'Статус', ''],
    list.map(r => `<tr>
      <td><strong>Р-${r.id}</strong><small>${r.created_at ? dt(r.created_at) : '—'}</small></td>
      <td><strong>${esc(r.full_name || '—')}</strong><small>${esc(r.email || '')}</small></td>
      <td class="wrap"><strong>${esc(clinicsOf(r))}</strong></td>
      <td>${pill('На рассмотрении', 'new')}</td>
      <td><button class="btn small" data-action="approvePendingAgent" data-id="${r.id}">Рассмотреть</button></td>
    </tr>`)
  );
}

function openPendingAgent(id) {
  const a = (window.__pendingAgents || []).find(x => x.id === Number(id));
  if (!a) { toast('Агент не найден'); return; }
  const clinics = isChef()
    ? (window.__pendingClinics || []).filter(c => c.active)
    : (S.myClinics || []);
  const specs = window.__pendingSpecs || [];
  const admins = isChef() ? (window.__pendingAdmins || []).filter(x => x.active) : [];
  openDrawer('Регистрация Р-' + a.id,
    `<div class="registration-person"><span class="initials">${esc((a.full_name || '?').split(' ').map(x => x[0]).join('').slice(0, 2))}</span><div><h3>${esc(a.full_name || '—')}</h3></div></div>
    <dl class="details">
      <div><dt>Подана</dt><dd>${a.created_at ? dt(a.created_at) : '—'}</dd></div>
      <div><dt>Почта</dt><dd>${esc(a.email || '—')}</dd></div>
      <div><dt>Телефон</dt><dd>${esc(a.phone || 'Не указан')}</dd></div>
      <div><dt>Статус</dt><dd>${pill('На рассмотрении', 'new')}</dd></div>
    </dl>
    <p class="note">${esc(a.about_myself || 'Комментария нет.')}</p>
    <form id="approvePendingForm" data-id="${a.id}" autocomplete="off">
      <div class="field"><label>Решение</label><select name="decision">
        <option value="approved">Одобрить регистрацию</option>
        <option value="rejected">Отклонить регистрацию</option>
      </select></div>
      <div class="field"><label>Клиники *</label>${multiSelectHtml('pClinic','pClinicD')}</div>
      <div class="field"><label>Специализации</label>${multiSelectHtml('pSpec','pSpecD')}</div>
      ${isChef() ? `<div class="field"><label>Администратор</label><select name="admin_id"><option value="">Не назначать</option>${admins.map(x => `<option value="${x.id}">${esc(x.full_name)}</option>`).join('')}</select></div>` : ''}
      <div class="field"><label>Комментарий / причина отклонения</label><textarea name="decision_reason" data-label="Причина" rows="3"></textarea></div>
      <div class="actions"><button class="btn primary" type="submit">Сохранить решение</button><button class="btn" type="button" onclick="closeDrawer()">Отмена</button></div>
    </form>`);
  setTimeout(() => {
    window.__selPendingClinic = [];
    window.__selPendingSpec = [];
    setupMultiSelect('pClinic', 'pClinicD', clinics.map(c => ({ id: c.id, name: c.name })), [], v => { window.__selPendingClinic = v; });
    setupMultiSelect('pSpec', 'pSpecD', specs.map(s => ({ id: s.id, name: s.name })), [], v => { window.__selPendingSpec = v; });
  }, 0);
}

async function handlePendingSubmit(f) {
  const id = Number(f.dataset.id);
  const fd = new FormData(f);
  const decision = fd.get('decision');
  const reason = String(fd.get('decision_reason') || '').trim();
  if (decision === 'rejected') {
    if (!reason) { toast('Укажите причину отклонения'); return; }
    await api(`/agents/${id}/reject`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision_reason: reason }) });
    toast('Регистрация отклонена'); closeDrawer(); await loadAll(); render();
    return;
  }
  const clinic_ids = window.__selPendingClinic || [];
  const specialization_ids = window.__selPendingSpec || [];
  if (!clinic_ids.length) { toast('Выберите хотя бы одну клинику'); return; }
  const body = { clinic_ids, specialization_ids };
  if (isChef()) {
    const admin_id = fd.get('admin_id') ? Number(fd.get('admin_id')) : null;
    body.admin_id = admin_id;
  }
  await api(`/agents/${id}/approve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  toast('Агент одобрен'); closeDrawer(); await loadAll(); render();
}

// ===== Редактирование агента =====
function openEditAgent(id) {
  const a = S.agents.find(x => x.id === Number(id)); if (!a) return;
  const clinicIds = (a.clinic_ids || []).filter(c => isChef() || myClinicIds().includes(c));
  const specIds = [...(a.specialization_ids || [])];
  const clinicsPool = isChef() ? S.clinics : S.myClinics;
  openDrawer('Редактировать: ' + a.full_name,
    `<form id="editAgentForm" data-id="${a.id}" autocomplete="off">
      <div class="field"><label>ФИО</label><input name="full_name" data-label="ФИО" required minlength="2" value="${esc(a.full_name)}"></div>
      <div class="field"><label>Телефон</label><input name="phone" type="tel" data-label="Телефон" value="${esc(a.phone||'')}"></div>
      <div class="field"><label>Статус</label><select name="status">${['pending','active','inactive','rejected'].map(s => `<option value="${s}" ${a.status === s ? 'selected' : ''}>${SL[s]}</option>`).join('')}</select></div>
      <div class="field"><label>Клиники</label>${multiSelectHtml('mcClinic','mdClinic')}</div>
      <div class="field"><label>Специализации</label>${multiSelectHtml('mcSpec','mdSpec')}</div>
      ${isChef() ? `<div class="field"><label>Администратор</label><select name="admin_id"><option value="">Не назначен</option>${S.admins.filter(x => x.active).map(x => `<option value="${x.id}" ${a.admin_id === x.id ? 'selected' : ''}>${esc(x.full_name)}</option>`).join('')}</select></div>` : ''}
      <div class="actions"><button class="btn primary" type="submit">Сохранить</button><button class="btn" type="button" onclick="closeDrawer()">Отмена</button></div>
    </form>`);
  setTimeout(() => {
    window.__selEditClinic = clinicIds;
    window.__selEditSpec = specIds;
    setupMultiSelect('mcClinic', 'mdClinic', clinicsPool.map(c => ({ id: c.id, name: c.name })), clinicIds, v => { window.__selEditClinic = v; });
    setupMultiSelect('mcSpec', 'mdSpec', S.specs.map(s => ({ id: s.id, name: s.name })), specIds, v => { window.__selEditSpec = v; });
  }, 0);
}

async function handleEditAgentSubmit(f) {
  const id = Number(f.dataset.id);
  const fd = new FormData(f);
  const body = {
    full_name: fd.get('full_name'),
    phone: fd.get('phone') || null,
    status: fd.get('status'),
    clinic_ids: window.__selEditClinic || [],
    specialization_ids: window.__selEditSpec || [],
  };
  if (isChef()) body.admin_id = fd.get('admin_id') ? Number(fd.get('admin_id')) : null;
  await api(`/agents/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  toast('Агент обновлён'); closeDrawer(); await loadAll(); render();
}

// ===== Ставки агента =====
function renderAgentRates() {
  const el = document.getElementById('rateResults');
  if (!el) return;
  const rates = window.__agentRates || [];
  const specs = window.__agentSpecs || [];
  const q = (document.getElementById('profileSearch')?.value || '').toLowerCase();
  const filtered = rates.filter(r => {
    const name = r.specialization_name || (specs.find(s => s.id === r.specialization_id)?.name) || '';
    return !q || name.toLowerCase().includes(q);
  });
  if (!filtered.length) { el.innerHTML = '<div class="empty">Нет ставок. Одобрите специализации агента.</div>'; return; }
  el.innerHTML = `<div class="tablewrap"><table><thead><tr><th>Специализация</th><th>Режим</th><th>Ставка</th><th></th></tr></thead><tbody>${filtered.map(r => {
    const name = r.specialization_name || (specs.find(s => s.id === r.specialization_id)?.name) || ('#' + r.specialization_id);
    const modeLabel = r.mode === 'custom' ? 'Личная' : 'По клинике';
    const rateLabel = (r.mode === 'custom' && r.custom_rate != null) ? r.custom_rate + '%' : '— (из клиники)';
    return `<tr><td><strong>${esc(name)}</strong></td><td>${pill(modeLabel, r.mode === 'custom' ? 'approved' : 'work')}</td><td>${rateLabel}</td><td><button class="btn small" data-action="editAgentRate" data-agent="${window.__agentCurrentId}" data-spec="${r.specialization_id}" data-mode="${r.mode}" data-custom="${r.custom_rate ?? ''}">Изменить</button></td></tr>`;
  }).join('')}</tbody></table></div>`;
}
function openEditAgentRate(agentIdArg, specId, mode, custom) {
  const specs = window.__agentSpecs || [];
  const name = specs.find(s => s.id === Number(specId))?.name || ('#' + specId);
  openDrawer('Ставка: ' + name,
    `<form id="editAgentRateForm" data-agent="${agentIdArg}" data-spec="${specId}" autocomplete="off">
      <div class="field"><label>Режим</label><select name="mode"><option value="clinic" ${mode === 'clinic' ? 'selected' : ''}>По клинике</option><option value="custom" ${mode === 'custom' ? 'selected' : ''}>Личная ставка</option></select></div>
<div class="field"><label>Личная ставка (%)</label><input name="custom_rate" type="number" data-label="Личная ставка" min="0" max="100" step="0.01" value="${custom}"></div>      <div class="actions"><button class="btn primary" type="submit">Сохранить</button><button class="btn" type="button" onclick="closeDrawer()">Отмена</button></div>
   </form>`);
}
async function handleEditAgentRate(f) {
  const agentIdArg = Number(f.dataset.agent);
  const specId = Number(f.dataset.spec);
  const fd = new FormData(f);
  const mode = fd.get('mode');
  const custom = String(fd.get('custom_rate') || '').trim();
  if (mode === 'custom' && custom === '') { toast('Укажите личную ставку'); return; }
  await api(`/agents/${agentIdArg}/rates/${specId}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode, custom_rate: mode === 'custom' ? Number(custom) : null }) });
  toast('Сохранено'); closeDrawer(); await loadAgentRates(agentIdArg);
}

// ===== Администратор =====
function openAdminForm(id) {
  if (!isChef()) return;
  const a = id ? S.admins.find(x => x.id === Number(id)) : null;
  const clinicIds = [...(a?.clinic_ids || [])];
  openDrawer(id ? 'Редактировать администратора' : 'Новый администратор',
    `<form id="adminForm" data-id="${id || ''}" autocomplete="off">
      <div class="field"><label>ФИО</label><input name="full_name" data-label="ФИО" required minlength="2" value="${esc(a?.full_name || '')}"></div>
      <div class="field"><label>Email</label><input name="email" type="email" data-label="Email" autocomplete="new-email" required ${id ? 'disabled' : ''} value="${esc(a?.email || '')}"></div>
      <div class="field"><label>Телефон</label><input name="phone" type="tel" data-label="Телефон" value="${esc(a?.phone || '')}"></div>
      ${id ? '' : `<div class="field"><label>Пароль (мин. 8)</label><input name="password" type="password" data-label="Пароль" autocomplete="new-password" required minlength="8"></div>`}
      <div class="field"><label>Клиники</label>${multiSelectHtml('mcAdminClinic','mdAdminClinic')}</div>
      <div class="field"><label>Доступ</label><select name="active">${['true','false'].map(v => `<option value="${v}" ${String(a?.active !== false) === v ? 'selected' : ''}>${v === 'true' ? 'Активен' : 'Отключён'}</option>`).join('')}</select></div>
      <fieldset class="permission-box">
        <legend>Дополнительные возможности</legend>
        <label class="permission-choice">
          <input type="checkbox" id="reviewRegistrations" name="reviewRegistrations" ${a?.permissions?.reviewRegistrations ? 'checked' : ''}>
          <span><strong>Рассмотрение регистраций агентов</strong><small>Показывает вкладку «Регистрация агентов». Разрешает просматривать, одобрять и отклонять заявки своей клиники.</small></span>
        </label>
      </fieldset>
      <div class="actions"><button class="btn primary" type="submit">${id ? 'Сохранить' : 'Создать'}</button><button class="btn" type="button" onclick="closeDrawer()">Отмена</button></div>
    </form>`);
  setTimeout(() => {
    window.__selAdminClinic = clinicIds;
    setupMultiSelect('mcAdminClinic', 'mdAdminClinic', S.clinics.filter(c => c.active).map(c => ({ id: c.id, name: c.name })), clinicIds, v => { window.__selAdminClinic = v; });
  }, 0);
}
async function handleAdminSubmit(f) {
  const id = f.dataset.id ? Number(f.dataset.id) : null;
  const fd = new FormData(f);
  const permissions = { reviewRegistrations: !!fd.get('reviewRegistrations') };
  const body = {
    full_name: fd.get('full_name'),
    phone: fd.get('phone') || null,
    active: fd.get('active') === 'true',
    permissions,
    clinic_ids: window.__selAdminClinic || [],
  };
  if (id) await api(`/admins/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  else {
    body.email = fd.get('email');
    body.password = fd.get('password');
    await api(`/admins`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  }
  toast(id ? 'Обновлён' : 'Создан'); closeDrawer(); await loadAll(); render();
}

// ===== Клиника =====
function openClinicForm(id) {
  if (!isChef()) return;
  const c = id ? S.clinics.find(x => x.id === Number(id)) : null;
  openDrawer(id ? 'Редактировать клинику' : 'Новая клиника',
    `<form id="clinicForm" data-id="${id || ''}" autocomplete="off">
      <div class="field"><label>Название</label><input name="name" data-label="Название" required minlength="2" value="${esc(c?.name||'')}"></div>
      <div class="field"><label>Город</label><input name="city" data-label="Город" required minlength="2" value="${esc(c?.city||'')}"></div>
      <div class="field"><label>Адрес</label><input name="address" data-label="Адрес" value="${esc(c?.address||'')}"></div>
      <div class="field"><label>Телефон</label><input name="phone" type="tel" data-label="Телефон" value="${esc(c?.phone||'')}"></div>
      <div class="field"><label>Статус</label><select name="active">${['true','false'].map(v => `<option value="${v}" ${String(c?.active !== false) === v ? 'selected' : ''}>${v === 'true' ? 'Активна' : 'Отключена'}</option>`).join('')}</select></div>
      <div class="actions"><button class="btn primary" type="submit">${id ? 'Сохранить' : 'Создать'}</button><button class="btn" type="button" onclick="closeDrawer()">Отмена</button></div>
    </form>`);
}
async function handleClinicSubmit(f) {
  const id = f.dataset.id ? Number(f.dataset.id) : null;
  const fd = new FormData(f);
  const body = { name: fd.get('name'), city: fd.get('city'), address: fd.get('address') || null, phone: fd.get('phone') || null, active: fd.get('active') === 'true' };
  if (id) await api(`/clinics/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  else await api(`/clinics`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  toast(id ? 'Обновлена' : 'Создана'); closeDrawer(); clinicId = null; await loadAll(); render();
}

// ===== Ставка клиники =====
function openEditSpec(clinic, sid, rate, active) {
  openDrawer('Ставка специализации',
    `<form id="specForm" data-clinic="${clinic}" data-spec="${sid}" autocomplete="off">
      <div class="field"><label>Ставка (%)</label><input name="default_rate" type="number" data-label="Ставка" min="0" max="100" step="0.01" value="${rate}"></div>      <div class="field"><label>Статус</label><select name="active">${['true','false'].map(v => `<option value="${v}" ${String(active) === v ? 'selected' : ''}>${v === 'true' ? 'Активна' : 'Отключена'}</option>`).join('')}</select></div>
      <div class="actions"><button class="btn primary" type="submit">Сохранить</button><button class="btn" type="button" onclick="closeDrawer()">Отмена</button></div>
    </form>`);
}
async function handleSpecSubmit(f) {
  const cid = Number(f.dataset.clinic), sid = Number(f.dataset.spec);
  const fd = new FormData(f);
  const r = String(fd.get('default_rate') || '').trim();
  await api(`/clinics/${cid}/specialties/${sid}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ default_rate: r === '' ? null : Number(r), active: fd.get('active') === 'true' }) });
  toast('Сохранено'); closeDrawer();
  document.getElementById('clinicSpecsBlock').innerHTML = await clinicSpecsHtml(cid);
}

// ===== Направление =====
function viewReferral(id) {
  const r = (window.__referrals || []).find(x => x.id === Number(id));
  if (!r) { toast('Направление не найдено'); return; }
  openDrawer('Направление #' + r.id,
    `<dl class="details">
      <div><dt>Пациент</dt><dd>${esc(r.patient_full_name || '—')}</dd></div>
      <div><dt>Клиника</dt><dd>${esc(r.clinic_name || '—')}</dd></div>
      <div><dt>Специализация</dt><dd>${esc(r.specialization_name || '—')}</dd></div>
      <div><dt>Период визита</dt><dd>${esc(r.expected_visit_start || '—')} — ${esc(r.expected_visit_end || '—')}</dd></div>
      <div><dt>Статус</dt><dd>${r.status === 'new' ? pill('Новая', 'new') : r.status === 'approved' ? pill('Подтверждена', 'approved') : pill('Отклонена', 'rejected')}</dd></div>
    </dl>
    <p class="note">${esc(r.med_indications || 'Показания не указаны.')}</p>
    <form id="referralDecisionForm" data-id="${r.id}">
      <div class="field"><label>Решение</label><select name="decision">
        <option value="approved" ${r.status === 'approved' ? 'selected' : ''}>Подтвердить</option>
        <option value="rejected" ${r.status === 'rejected' ? 'selected' : ''}>Отклонить</option>
      </select></div>
      <div class="actions"><button class="btn primary" type="submit">Сохранить</button><button class="btn" type="button" onclick="closeDrawer()">Отмена</button></div>
    </form>`);
}
async function handleReferralDecision(f) {
  const id = Number(f.dataset.id);
  const fd = new FormData(f);
  await api(`/admin/referrals/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: fd.get('decision') }) });
  toast('Статус обновлён'); closeDrawer(); await loadReferrals(); render();
}

// ============================================================
// 9. ОБРАБОТЧИКИ
// ============================================================
document.addEventListener('click', async e => {
  const pg = e.target.closest('[data-page]');
  if (pg) { navigate(pg.dataset.page); return; }

  const b = e.target.closest('[data-hist-filter]');
  if (b) { loadHistoryModal(b.dataset.histFilter); return; }

  const tab = e.target.closest('[data-tab]');
  if (tab) {
    profileTab = tab.dataset.tab;
    if (agentId) render();
    setTimeout(() => {
      if (profileTab === 'rates' && agentId) loadAgentRates(agentId);
      else if (document.getElementById('rateResults')) document.getElementById('rateResults').innerHTML = '<div class="empty">История агента недоступна (на бэке нет истории ставок).</div>';
    }, 0);
    return;
  }

  const a = e.target.closest('[data-action]');
  if (!a) return;
  const id = Number(a.dataset.id);
  try {
    switch (a.dataset.action) {
      case 'viewAgent': agentId = id; page = 'agents'; render(); scrollTo(0, 0); break;
      case 'viewAdmin': if (isChef()) { adminId = id; page = 'admins'; render(); scrollTo(0, 0); } break;
      case 'viewReferral': viewReferral(id); break;
      case 'clinicSettings':
        clinicId = id; page = 'clinics'; render(); scrollTo(0, 0);
        document.getElementById('clinicSpecsBlock').innerHTML = await clinicSpecsHtml(id);
        break;
      case 'approve':
      case 'approvePendingAgent':
      case 'rejectPendingAgent': openPendingAgent(id); break;
      case 'reject': openPendingAgent(id); break;
      case 'refreshRegistrations': loadPendingAgents(); break;
      case 'scrollToRegistrations': document.getElementById('registrationsBlock')?.scrollIntoView({ behavior: 'smooth' }); break;
      case 'editAgent': openEditAgent(id); break;
      case 'delAgent':
        if (!confirm('Удалить агента?')) return;
        await api(`/agents/${id}`, { method: 'DELETE' }); toast('Удалён'); await loadAll(); navigate('agents'); break;
      case 'editAdmin': openAdminForm(id); break;
      case 'newAdmin': openAdminForm(); break;
      case 'delAdmin':
        if (!confirm('Удалить администратора?')) return;
        await api(`/admins/${id}`, { method: 'DELETE' }); toast('Удалён'); await loadAll(); navigate('admins'); break;
      case 'newClinic': openClinicForm(); break;
      case 'editClinic': openClinicForm(id); break;
      case 'editSpec': openEditSpec(a.dataset.clinic, a.dataset.spec, a.dataset.rate, a.dataset.active); break;
      case 'editAgentRate': openEditAgentRate(a.dataset.agent, a.dataset.spec, a.dataset.mode, a.dataset.custom); break;
      case 'viewAllHistory':
        document.getElementById('historyModal').classList.add('open');
        document.getElementById('historyModalBody').innerHTML = `
          <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px">
            <button class="btn small" data-hist-filter="all">Все</button>
            ${isChef() ? `<button class="btn small" data-hist-filter="chef">Мои</button>` : ''}
            <button class="btn small" data-hist-filter="admin">Администраторы</button>
            <button class="btn small" data-hist-filter="agent">Агенты</button>
          </div>
          <div id="historyFilteredList"><div class="empty">Загрузка...</div></div>`;
        loadHistoryModal('all');
        break;
    }
  } catch (err) { toast('Ошибка: ' + err.message); }
});

document.addEventListener('change', e => {
  if (e.target.id === 'agentStatusFilter') { agentFilter = e.target.value; render(); }
});
document.addEventListener('input', e => {
  if (e.target.id === 'search') {
    const inp = e.target;
    const selStart = inp.selectionStart, selEnd = inp.selectionEnd;
    query = inp.value;
    render();
    requestAnimationFrame(() => {
      const newInp = document.querySelector('#search');
      if (newInp) { newInp.focus(); try { newInp.setSelectionRange(selStart, selEnd); } catch (_) {} }
    });
  }
  if (e.target.id === 'profileSearch') renderAgentRates();
});

document.addEventListener('submit', async e => {
  const f = e.target;
  const known = ['approvePendingForm','editAgentForm','editAgentRateForm','adminForm','clinicForm','specForm','referralDecisionForm'];
  if (!known.includes(f.id)) return;
  e.preventDefault();
  const errs = validateForm(f);
  if (errs.length) { toast(errs[0]); return; }
  try {
    if (f.id === 'approvePendingForm') return handlePendingSubmit(f);
    if (f.id === 'editAgentForm') return handleEditAgentSubmit(f);
    if (f.id === 'editAgentRateForm') return handleEditAgentRate(f);
    if (f.id === 'adminForm') return handleAdminSubmit(f);
    if (f.id === 'clinicForm') return handleClinicSubmit(f);
    if (f.id === 'specForm') return handleSpecSubmit(f);
    if (f.id === 'referralDecisionForm') return handleReferralDecision(f);
  } catch (err) { toast('Ошибка: ' + err.message); }
});

$('#close').onclick = closeDrawer;
$('#backdrop').addEventListener('click', e => { if (e.target.id === 'backdrop') closeDrawer(); });
$('#historyModal').addEventListener('click', e => { if (e.target.id === 'historyModal') document.getElementById('historyModal').classList.remove('open'); });
$('#logoutBtn').onclick = async () => { try { await api('/auth/logout', { method: 'POST' }); } catch {} location.href = '/'; };
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeDrawer();
    document.getElementById('historyModal').classList.remove('open');
    $('#sidebar').classList.remove('open');
  }
});
window.addEventListener('hashchange', () => {
  const h = location.hash.replace('#','') || 'overview';
  if (Object.keys(NAME).includes(h)) page = h;
  render();
});

// ============================================================
// 10. ИНИЦИАЛИЗАЦИЯ
// ============================================================
(async function init() {
  try {
    S.user = await api('/auth/me');
    if (!S.user) { location.href = '/'; return; }
    if (S.user.role !== 'chef' && S.user.role !== 'admin') { location.href = '/'; return; }
    await loadAll();
    const h = location.hash.replace('#','') || 'overview';
    page = Object.keys(NAME).includes(h) ? h : 'overview';
    render();
    // История в обзоре
    try {
      const hist = await api('/history?limit=5');
      window.__historyCache = hist;
      if (page === 'overview') {
        const el = document.getElementById('historyList');
        if (el) {
          el.innerHTML = hist.length
            ? hist.map(h => `<div class="change-item"><div class="change-item-body"><strong>${esc(h.label)}</strong><small>${esc(h.text)}</small></div><div class="change-item-time">${dt(h.created_at)}</div></div>`).join('')
            : '<div class="empty">История пуста</div>';
        }
      }
    } catch (_) {}
  } catch (e) { location.href = '/'; }
})();
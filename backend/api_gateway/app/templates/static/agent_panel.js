'use strict';

/* ==========================================================
   MedReferral · Agent Panel — JS (полный)
   1. Утилиты
   2. Справочники
   3. Состояние
   4. Хелперы
   5. Загрузка данных
   6. Навигация
   7. Страницы
   8. Модалки
   9. Обработчики
   10. Инициализация
   ========================================================== */

// ================== 1. УТИЛИТЫ ==================
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = n => new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 0}).format(n || 0) + ' ₽';
const percent = n => (n === null || n === undefined) ? '—' : new Intl.NumberFormat('ru-RU', {maximumFractionDigits: 2}).format(n) + '%';
const dt = v => v ? new Date(v).toLocaleString('ru-RU', {dateStyle: 'short', timeStyle: 'short'}) : '—';
const dateOnly = v => v ? new Date(v).toLocaleDateString('ru-RU') : '—';
const isoDate = d => d ? new Date(d).toISOString().slice(0, 10) : '';
const todayISO = () => isoDate(new Date());

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
          med_indications:'Показания', special_wishes:'Пожелания',
          amount:'Стоимость', date_of_birth:'Дата рождения',
          gender:'Пол', info:'Информация', code:'Код',
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
    const maxLen = el.maxLength;
    if (maxLen && maxLen > 0 && v.length > maxLen) errors.push(`${label}: максимум ${maxLen} символов`);
    if (el.type === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) errors.push(`${label}: некорректный email`);
    if (el.type === 'password' && el.minLength && v.length < el.minLength) errors.push(`${label}: минимум ${el.minLength} символов`);
    if (el.type === 'tel') {
      const digits = v.replace(/\D/g, '');
      if (digits.length < 10 || digits.length > 15) errors.push(`${label}: некорректный телефон`);
    }
    if (el.type === 'number') {
      const n = Number(v);
      if (el.min !== '' && n < Number(el.min)) errors.push(`${label}: не меньше ${el.min}`);
      if (el.max !== '' && n > Number(el.max)) errors.push(`${label}: не больше ${el.max}`);
    }
  });
  return errors;
}

let __toastTimer = null;
function toast(msg, type = 'info') {
  const t = $('#toast');
  if (!t) return;
  t.textContent = msg;
  t.className = 'toast show ' + (type === 'error' ? 'error' : type === 'success' ? 'success' : 'info');
  clearTimeout(__toastTimer);
  __toastTimer = setTimeout(() => t.classList.remove('show'), 4000);
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

// ================== 2. СПРАВОЧНИКИ ==================
const S = {
  user: null,
  clinics: [],
  specializations: [],
  patients: [],
  referrals: [],
  myRates: [],
  dashboard: {stats: null, activity: [], appointments: [], topClinics: []},
  reports: {stats: null, goal: null, facts: null},
  columnOrder: null,
};

const NAME = {
  dashboard: 'Главная',
  create_referral: 'Новое направление',
  referrals: 'Мои направления',
  patients: 'Пациенты',
  clinics: 'Клиники',
  reports: 'Отчеты',
  profile: 'Настройки',
};
const ICONS = {
  dashboard: 'fa-house',
  create_referral: 'fa-plus-circle',
  referrals: 'fa-list',
  patients: 'fa-user-injured',
  clinics: 'fa-hospital',
  reports: 'fa-chart-bar',
  profile: 'fa-user-cog',
};
const NAV = ['dashboard', 'create_referral', 'referrals', 'patients', 'clinics', 'reports', 'profile'];

const REFERRAL_STATUS = {new: 'Новая', approved: 'Подтверждена', rejected: 'Отклонена'};
const REFERRAL_STATUS_COLOR = {new: 'new', approved: 'approved', rejected: 'rejected'};
const PAYOUT_STATUS = {unpaid: 'Не выплачено', processing: 'К выплате', paid: 'Выплачено'};
const PAYOUT_STATUS_COLOR = {unpaid: 'new', processing: 'work', paid: 'approved'};

const DEFAULT_REFERRAL_COLUMNS = [
  'patient', 'clinic', 'specialization', 'created_at',
  'visit_period', 'status', 'status_changed_at',
  'commission_amount', 'payout_status', 'actions'
];
const REFERRAL_COLUMNS_DEF = {
  id: {label: '#', alwaysFirst: true},
  patient: {label: 'Пациент'},
  clinic: {label: 'Клиника'},
  specialization: {label: 'Специализация'},
  created_at: {label: 'Дата создания'},
  visit_period: {label: 'Период визита'},
  status: {label: 'Статус'},
  status_changed_at: {label: 'Изменение статуса'},
  commission_amount: {label: 'Сумма'},
  payout_status: {label: 'Выплата'},
  actions: {label: 'Действия'},
};

// ================== 3. СОСТОЯНИЕ ==================
let page = 'dashboard';
let query = '';
let filterStatus = 'all';
let filterClinic = 'all';
let patientFilterStatus = 'all';
let selectedClinicId = null;
let selectedSpecializationId = null;
let selectedPatientId = null;
let currentReferralId = null;
let currentPatientId = null;
let referralsLimit = 10;
let referralsPage = 1;
let referralsColumnOrder = [...DEFAULT_REFERRAL_COLUMNS];

// ================== 4. ХЕЛПЕРЫ ==================
const cName = id => S.clinics.find(c => c.id === Number(id))?.name || '—';
const sName = id => S.specializations.find(s => s.id === Number(id))?.name || ('#' + id);
const pName = id => S.patients.find(p => p.id === Number(id))?.full_name || '—';

const heading = (t, d = '', act = '') => `
  <div class="heading" style="display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:24px;flex-wrap:wrap">
    <div style="min-width:0">
      <h1 style="font-size:1.6rem;margin:0;line-height:1.2">${esc(t)}</h1>
      ${d ? `<p class="muted" style="margin-top:4px">${esc(d)}</p>` : ''}
    </div>
    ${act}
  </div>`;

const table = (headers, rows, emptyText = 'Ничего не найдено') => `
  <div class="tablewrap">
    <table>
      <thead><tr>${headers.map(h => `<th>${h}</th>`).join('')}</tr></thead>
      <tbody>${rows.length ? rows.join('') : `<tr><td colspan="${headers.length}" class="empty"><i class="fas fa-inbox"></i><div>${esc(emptyText)}</div></td></tr>`}</tbody>
    </table>
  </div>`;

const pill = (label, type = '') => `<span class="pill ${type}">${esc(label)}</span>`;
const options = (items, selected, placeholder = null) => {
  const opts = placeholder ? [`<option value="">${esc(placeholder)}</option>`] : [];
  (items || []).forEach(it => {
    opts.push(`<option value="${esc(it.id)}" ${String(it.id) === String(selected) ? 'selected' : ''}>${esc(it.name)}</option>`);
  });
  return opts.join('');
};

function getRateFor(clinicId, specId) {
  const rate = S.myRates.find(r => r.specialization_id === Number(specId));
  if (!rate) return null;
  if (rate.mode === 'custom' && rate.custom_rate != null) {
    return {rate: rate.custom_rate, source: 'личная ставка'};
  }
  const byClinic = (rate.by_clinic || []).find(c => c.clinic_id === Number(clinicId));
  if (byClinic && byClinic.active && byClinic.default_rate != null) {
    return {rate: byClinic.default_rate, source: 'ставка клиники'};
  }
  return null;
}

// ================== 5. ЗАГРУЗКА ==================
async function loadAll() {
  try {
    const [me, clinics, specs] = await Promise.all([
      api('/auth/me'),
      api('/clinics'),
      api('/auth/specializations'),
    ]);
    S.user = me;
    S.clinics = Array.isArray(clinics) ? clinics : [];
    S.specializations = Array.isArray(specs) ? specs : [];
    try {
      const rates = await api('/agents/me/rates');
      S.myRates = Array.isArray(rates) ? rates : [];
    } catch { S.myRates = []; }
    if (me?.column_order && Array.isArray(me.column_order) && me.column_order.length) {
      S.columnOrder = me.column_order;
      referralsColumnOrder = [...me.column_order];
    }
  } catch (e) {
    console.error('loadAll:', e);
    if (e.message !== '401' && e.message !== 'Нет доступа') toast('Ошибка загрузки: ' + e.message, 'error');
  }
}

async function loadReferrals() {
  try {
    const res = await api('/referrals?limit=100');
    S.referrals = Array.isArray(res) ? res : [];
  } catch (e) {
    console.error('loadReferrals:', e);
    S.referrals = [];
    toast('Ошибка загрузки направлений: ' + e.message, 'error');
  }
}
async function loadPatients() {
  try {
    const res = await api('/patients?limit=100');
    S.patients = Array.isArray(res) ? res : [];
  } catch (e) {
    console.error('loadPatients:', e);
    S.patients = [];
    toast('Ошибка загрузки пациентов: ' + e.message, 'error');
  }
}
async function loadDashboard() {
  try {
    const [stats, activity, appointments, top] = await Promise.all([
      api('/dashboard/stats').catch(() => null),
      api('/dashboard/activity?limit=5').catch(() => []),
      api('/dashboard/appointments?limit=4').catch(() => []),
      api('/dashboard/top-clinics?limit=4').catch(() => []),
    ]);
    S.dashboard = {
      stats: stats || {total_referrals:0, active_patients:0, today_referrals:0, upcoming_visits:0},
      activity: Array.isArray(activity) ? activity : [],
      appointments: Array.isArray(appointments) ? appointments : [],
      topClinics: Array.isArray(top) ? top : [],
    };
  } catch (e) { console.error('loadDashboard:', e); }
}
async function loadReports(from, to) {
  try {
    const now = new Date();
    const [stats, goal, facts] = await Promise.all([
      api(`/reports/stats?date_from=${from}&date_to=${to}`).catch(() => null),
      api('/goals/current').catch(() => null),
      api(`/goals/facts?month=${now.getMonth()+1}&year=${now.getFullYear()}`).catch(() => null),
    ]);
    S.reports = {stats, goal, facts};
  } catch (e) { console.error('loadReports:', e); }
}

// ================== 6. НАВИГАЦИЯ ==================
const PAGE_NAMES = Object.keys(NAME);

function readRoute() {
  const h = (location.hash || '').replace('#', '').trim() || 'dashboard';
  page = PAGE_NAMES.includes(h) ? h : 'dashboard';
  return page;
}

function navigate(p) {
  if (!PAGE_NAMES.includes(p)) p = 'dashboard';
  page = p;
  query = '';
  filterStatus = 'all';
  filterClinic = 'all';
  patientFilterStatus = 'all';
  currentReferralId = null;
  currentPatientId = null;
  selectedClinicId = null;
  selectedSpecializationId = null;
  selectedPatientId = null;
  location.hash = '#' + p;
  render();
  window.scrollTo(0, 0);
}

function nav() {
  const el = $('#nav');
  if (!el) return;
  el.innerHTML = NAV.map(t => `
    <button class="${page === t ? 'active' : ''}" data-page="${t}" title="${NAME[t]}">
      <i class="fas ${ICONS[t]}"></i>
      <span class="nav-label">${NAME[t]}</span>
    </button>`).join('');

  const u = S.user || {};
  const fullName = (u.full_name || u.email || 'Пользователь').trim();
  const parts = fullName.split(' ').filter(Boolean);
  const lastName = parts[0] || 'Пользователь';
  const initialsRest = parts.slice(1).join(' ');
  const initials = fullName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();

  // Сайдбар: Фамилия + И.О.
  if ($('#userLabel')) $('#userLabel').textContent = lastName;
  if ($('#userSub')) $('#userSub').textContent = initialsRest || (u.email || '');

  // Topbar: Фамилия + И.О. (двумя строками)
  if ($('#topUserName')) {
    $('#topUserName').innerHTML = `${esc(lastName)}${initialsRest ? `<br><span style="font-weight:400;font-size:.8rem;color:var(--gray)">${esc(initialsRest)}</span>` : ''}`;
  }
  if ($('#topAvatar')) $('#topAvatar').textContent = initials || '?';
  $('#sidebar')?.classList.remove('open');
}

function render() {
  nav();
  const map = {
    dashboard: pageDashboard,
    create_referral: pageCreateReferral,
    referrals: pageReferrals,
    patients: pagePatients,
    clinics: pageClinics,
    reports: pageReports,
    profile: pageProfile,
  };
  const fn = map[page] || pageDashboard;
  const c = $('#content');
  if (c) c.innerHTML = fn();
  afterRender();
}

function afterRender() {
  if (page === 'dashboard') {
    loadDashboard().then(() => { const c = $('#content'); if (c && page === 'dashboard') c.innerHTML = pageDashboard(); });
  } else if (page === 'referrals') {
    loadReferrals().then(() => { const c = $('#content'); if (c && page === 'referrals') c.innerHTML = pageReferrals(); });
  } else if (page === 'patients') {
    loadPatients().then(() => { const c = $('#content'); if (c && page === 'patients') c.innerHTML = pagePatients(); });
  } else if (page === 'create_referral') {
    setTimeout(() => initCreateReferral(), 0);
  } else if (page === 'reports') {
    const from = $('#repFrom')?.value || (() => { const d = new Date(); d.setMonth(d.getMonth() - 1); return isoDate(d); })();
    const to = $('#repTo')?.value || todayISO();
    loadReports(from, to).then(() => { const c = $('#content'); if (c && page === 'reports') c.innerHTML = pageReports(); });
  }
}

// ================== 7. СТРАНИЦЫ ==================

// ---------- DASHBOARD ----------
function pageDashboard() {
  const stats = S.dashboard?.stats || {};
  const activity = S.dashboard?.activity || [];
  const appointments = S.dashboard?.appointments || [];
  const topClinics = S.dashboard?.topClinics || [];
  const now = new Date();
  const dateStr = now.toLocaleDateString('ru-RU', {weekday:'long', year:'numeric', month:'long', day:'numeric'});
  const firstName = (S.user?.full_name || '').split(' ').slice(1, 2).join(' ') || 'агент';
  return heading('Главная', 'Сводка по вашей работе')
    + `<section style="background:linear-gradient(135deg,#2563eb,#8b5cf6);border-radius:12px;padding:28px 30px;color:#fff;margin-bottom:24px">
        <h2 style="font-size:1.5rem;margin:0 0 6px;color:#fff">Добро пожаловать, ${esc(firstName)}!</h2>
        <p style="opacity:.9;font-size:.9rem;margin:0 0 18px">${esc(dateStr.charAt(0).toUpperCase() + dateStr.slice(1))}</p>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px">
          ${[{v:stats.today_referrals||0, l:'Новых сегодня'},{v:stats.upcoming_visits||0, l:'Предстоящих визитов'},{v:stats.total_referrals||0, l:'Всего направлений'},{v:stats.active_patients||0, l:'Активных пациентов'}].map(s => `
            <div style="background:rgba(255,255,255,.15);border-radius:10px;padding:16px;text-align:center">
              <div style="font-size:1.8rem;font-weight:800">${s.v}</div>
              <div style="font-size:.8rem;opacity:.9">${s.l}</div>
            </div>`).join('')}
        </div>
      </section>`
    + `<div class="grid-2">
        <section class="panel">
          <div class="panelhead"><div><h2>Последние действия</h2></div><button class="btn small" data-page="referrals">Все</button></div>
          <div>${activity.length ? activity.map(a => `
            <div style="display:flex;gap:12px;align-items:flex-start;padding:14px 22px;border-bottom:1px solid var(--border)">
              <div style="width:36px;height:36px;border-radius:50%;background:#eff6ff;color:var(--primary);display:grid;place-items:center;flex-shrink:0"><i class="fas fa-bell"></i></div>
              <div style="flex:1;min-width:0">
                <div style="font-weight:600;font-size:.9rem">${esc(a.label||'')}</div>
                <div style="font-size:.85rem;color:var(--gray)">${esc(a.text||'')}</div>
              </div>
              <div style="font-size:.75rem;color:var(--gray);white-space:nowrap">${dt(a.created_at)}</div>
            </div>`).join('') : '<div class="empty"><i class="fas fa-inbox"></i><div>Действий пока нет</div></div>'}</div>
        </section>
        <section class="panel">
          <div class="panelhead"><div><h2>Ближайшие визиты</h2></div><button class="btn small" data-page="referrals">Все</button></div>
          <div>${appointments.length ? appointments.map(a => {
            const d = new Date(a.expected_visit_start);
            const months = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];
            return `<div style="display:flex;gap:14px;align-items:center;padding:14px 22px;border-bottom:1px solid var(--border)">
              <div style="text-align:center;min-width:50px">
                <div style="font-size:1.4rem;font-weight:700;color:var(--primary)">${isNaN(d)?'—':d.getDate()}</div>
                <div style="font-size:.75rem;color:var(--gray)">${isNaN(d)?'':months[d.getMonth()]}</div>
              </div>
              <div style="flex:1;min-width:0">
                <div style="font-weight:600;font-size:.9rem">${esc(a.patient_name||'—')}</div>
                <div style="font-size:.8rem;color:var(--gray)">${esc(a.clinic_name||'—')}</div>
              </div>
              ${pill(a.status==='approved'?'Подтверждён':'Ожидает', a.status==='approved'?'approved':'new')}
            </div>`;
          }).join('') : '<div class="empty"><i class="fas fa-calendar-check"></i><div>Визитов нет</div></div>'}</div>
        </section>
      </div>`
    + `<section class="panel">
        <div class="panelhead"><div><h2>Топ клиник</h2></div><button class="btn small" data-page="clinics">Все</button></div>
        <div>${topClinics.length ? topClinics.map(c => {
          const ini = (c.name||'?').split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();
          return `<div style="display:flex;gap:14px;align-items:center;padding:14px 22px;border-bottom:1px solid var(--border)">
            <div style="width:44px;height:44px;border-radius:50%;background:#eff6ff;color:var(--primary);display:grid;place-items:center;font-weight:700">${esc(ini)}</div>
            <div style="flex:1;min-width:0">
              <div style="font-weight:600;font-size:.9rem">${esc(c.name||'—')}</div>
              <div style="font-size:.8rem;color:var(--gray)">${esc(c.address||'')}</div>
            </div>
            <div style="text-align:right"><div style="font-size:1.2rem;font-weight:700;color:var(--primary)">${c.referrals_count||0}</div><div style="font-size:.75rem;color:var(--gray)">направлений</div></div>
          </div>`;
        }).join('') : '<div class="empty"><i class="fas fa-hospital"></i><div>Данных нет</div></div>'}</div>
      </section>`;
}

// ---------- REFERRALS ----------
function pageReferrals() {
  const clinicOpts = S.clinics.map(c => ({id: c.id, name: c.name}));
  const filtered = S.referrals.filter(r => {
    if (query) {
      const t = [r.patient_full_name, r.clinic_name, r.specialization_name].join(' ').toLowerCase();
      if (!t.includes(query.toLowerCase())) return false;
    }
    if (filterStatus !== 'all' && r.status !== filterStatus) return false;
    if (filterClinic !== 'all' && r.clinic_id !== Number(filterClinic)) return false;
    return true;
  });
  const totalPages = Math.max(1, Math.ceil(filtered.length / referralsLimit));
  if (referralsPage > totalPages) referralsPage = totalPages;
  const start = (referralsPage - 1) * referralsLimit;
  const pageData = filtered.slice(start, start + referralsLimit);
  const stats = {
    total: S.referrals.length,
    approved: S.referrals.filter(r => r.status === 'approved').length,
    pending: S.referrals.filter(r => r.status === 'new').length,
  };
  const conversion = stats.total ? Math.round((stats.approved / stats.total) * 100) : 0;

    return heading('Мои направления', 'Список ваших направлений в клиники',
    `<button class="btn primary" data-page="create_referral"><i class="fas fa-plus"></i> Новое направление</button>`)
    + `<div class="grid">
        ${[
          {l:'Всего', v: stats.total, i:'fa-file-medical', c:'#eff6ff'},
          {l:'Завершено', v: stats.approved, i:'fa-check-circle', c:'#d1fae5'},
          {l:'Ожидают', v: stats.pending, i:'fa-clock', c:'#fef3c7'},
          {l:'Конверсия', v: conversion + '%', i:'fa-percentage', c:'#ddd6fe'},
        ].map(s => `
          <div class="stat">
            <div class="stat-icon" style="background:${s.c};color:var(--primary)"><i class="fas ${s.i}"></i></div>
            <div class="stat-content"><div class="stat-value">${s.v}</div><div class="stat-label">${s.l}</div></div>
          </div>`).join('')}
      </div>`
    + `<section class="panel">
        <div class="panelhead">
          <div class="controls">
            <input class="search" id="refSearch" placeholder="Поиск по пациенту, клинике, специализации" value="${esc(query)}">
            <select class="filter" id="refStatusFilter">
              <option value="all">Все статусы</option>
              ${Object.entries(REFERRAL_STATUS).map(([k, v]) => `<option value="${k}" ${filterStatus===k?'selected':''}>${v}</option>`).join('')}
            </select>
            <select class="filter" id="refClinicFilter">
              <option value="all">Все клиники</option>
              ${clinicOpts.map(c => `<option value="${c.id}" ${String(filterClinic)===String(c.id)?'selected':''}>${esc(c.name)}</option>`).join('')}
            </select>
            <button class="btn small" data-action="resetReferralsFilters" style="margin-left:auto">↻ Сбросить</button>
          </div>
        </div>
        ${referralsTable(pageData)}
        <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 22px;border-top:1px solid var(--border);font-size:.85rem;color:var(--gray);flex-wrap:wrap;gap:10px">
          <div>Показано ${pageData.length} из ${filtered.length}</div>
          <div style="display:flex;gap:6px;align-items:center">
            <button class="btn small" data-action="refPage" data-page-num="${referralsPage-1}" ${referralsPage<=1?'disabled':''}>←</button>
            <span>Стр. ${referralsPage} / ${totalPages}</span>
            <button class="btn small" data-action="refPage" data-page-num="${referralsPage+1}" ${referralsPage>=totalPages?'disabled':''}>→</button>
            <button class="btn small" data-action="columns" style="margin-left:12px">⚙ Настройка таблицы</button>
          </div>
        </div>
      </section>`;
}

function referralsTable(rows) {
  const cols = ['id', ...referralsColumnOrder];
  return `<div class="tablewrap"><table>
    <thead><tr>${cols.map(c => `<th>${REFERRAL_COLUMNS_DEF[c]?.label || c}</th>`).join('')}</tr></thead>
    <tbody>${rows.length ? rows.map(r => `<tr>${cols.map(c => `<td>${renderReferralCell(c, r)}</td>`).join('')}</tr>`).join('') : `<tr><td colspan="${cols.length}" class="empty"><i class="fas fa-inbox"></i><div>Направления не найдены</div></td></tr>`}</tbody>
  </table></div>`;
}

function renderReferralCell(col, r) {
  switch (col) {
    case 'id': return `<strong style="color:var(--primary)">#${r.id}</strong>`;
    case 'patient': {
      return `<div><div style="font-weight:600">${esc(r.patient_full_name || '—')}</div><div style="font-size:.75rem;color:var(--gray)">${esc(r.patient_phone || '—')}</div></div>`;
    }
    case 'clinic': return `<strong>${esc(r.clinic_name || '—')}</strong>`;
    case 'specialization': return `<span style="font-size:.9rem;color:var(--gray)">${esc(r.specialization_name || '—')}</span>`;
    case 'created_at': return `<span>${dateOnly(r.created_at)}</span>`;
    case 'visit_period': return `<div><div>${dateOnly(r.expected_visit_start)}</div><div style="font-size:.75rem;color:var(--gray)">до ${dateOnly(r.expected_visit_end)}</div></div>`;
    case 'status': return pill(REFERRAL_STATUS[r.status] || r.status, REFERRAL_STATUS_COLOR[r.status] || '');
    case 'status_changed_at': return `<span style="font-size:.85rem">${dt(r.status_changed_at)}</span>`;
    case 'commission_amount': return `<strong style="color:var(--success)">${money(r.commission_amount)}</strong>`;
    case 'payout_status': return pill(PAYOUT_STATUS[r.payout_status] || r.payout_status, PAYOUT_STATUS_COLOR[r.payout_status] || '');
    case 'actions': return `<button class="btn small" data-action="deleteReferral" data-id="${r.id}" title="Удалить"><i class="fas fa-trash"></i></button>`;
    default: return '—';
  }
}

// ---------- PATIENTS ----------
function pagePatients() {
  const filtered = S.patients.filter(p => {
    if (query) {
      const t = [p.full_name, p.phone, p.email].join(' ').toLowerCase();
      if (!t.includes(query.toLowerCase())) return false;
    }
    if (patientFilterStatus !== 'all' && p.status !== patientFilterStatus) return false;
    return true;
  });
  return heading('Пациенты', 'Ваши пациенты',
    `<button class="btn primary" data-action="newPatient"><i class="fas fa-user-plus"></i> Добавить пациента</button>`)
    + `<section class="panel">
        <div class="panelhead">
          <div class="controls">
            <input class="search" id="patSearch" placeholder="Поиск по ФИО, телефону, email" value="${esc(query)}">
            <select class="filter" id="patStatusFilter">
              <option value="all">Все статусы</option>
              <option value="active" ${patientFilterStatus==='active'?'selected':''}>Активный</option>
              <option value="inactive" ${patientFilterStatus==='inactive'?'selected':''}>Неактивный</option>
            </select>
          </div>
        </div>
        ${table(['ФИО', 'Телефон', 'Email', 'Пол', 'Возраст', 'Статус', ''], filtered.map(p => `
          <tr>
            <td><strong>${esc(p.full_name || '—')}</strong><small>#${p.id}</small></td>
            <td>${esc(p.phone || '—')}</td>
            <td>${esc(p.email || '—')}</td>
            <td>${p.gender === 'female' ? 'Женский' : 'Мужской'}</td>
            <td>${p.age || '—'} лет</td>
            <td>${pill(p.status === 'active' ? 'Активен' : 'Неактивен', p.status === 'active' ? 'approved' : 'rejected')}</td>
            <td>
              <div style="display:flex;gap:5px">
                <button class="btn small" data-action="editPatient" data-id="${p.id}" title="Редактировать"><i class="fas fa-edit"></i></button>
                <button class="btn small" data-action="deletePatient" data-id="${p.id}" title="Удалить"><i class="fas fa-trash"></i></button>
              </div>
            </td>
          </tr>`))}
      </section>`;
}

// ---------- CLINICS ----------
function pageClinics() {
  return heading('Клиники', 'Клиники, к которым вы привязаны')
    + `<section class="panel">
        ${table(['Клиника', 'Город', 'Адрес', 'Телефон'], S.clinics.map(c => `
          <tr>
            <td><strong>${esc(c.name || '—')}</strong><small>#${c.id}</small></td>
            <td>${esc(c.city || '—')}</td>
            <td class="wrap">${esc(c.address || '—')}</td>
            <td>${esc(c.phone || '—')}</td>
          </tr>`), 'Клиник нет')}
      </section>`;
}

// ---------- REPORTS ----------
function pageReports() {
  const st = S.reports?.stats || {};
  const goal = S.reports?.goal || {};
  const facts = S.reports?.facts || {};
  const from = $('#repFrom')?.value || (() => { const d = new Date(); d.setMonth(d.getMonth() - 1); return isoDate(d); })();
  const to = $('#repTo')?.value || todayISO();
  const months = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
  const now = new Date();
  return heading('Отчеты', 'Аналитика и цели',
    `<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <input type="date" id="repFrom" value="${esc(from)}" style="height:40px;padding:0 10px;border:2px solid var(--border);border-radius:8px">
      <span>—</span>
      <input type="date" id="repTo" value="${esc(to)}" style="height:40px;padding:0 10px;border:2px solid var(--border);border-radius:8px">
      <button class="btn primary" data-action="loadReports">Обновить</button>
    </div>`)
    + `<div class="grid">
        ${[
          {l:'Доход', v:money(st.total_revenue||0), i:'fa-money-bill-wave'},
          {l:'Направлений', v:st.total_referrals||0, i:'fa-file-medical'},
          {l:'Завершено', v:st.completed_referrals||0, i:'fa-check-circle'},
          {l:'Конверсия', v:(st.conversion||0)+'%', i:'fa-percentage'},
        ].map(s => `<div class="stat"><div class="stat-icon" style="background:#eff6ff;color:var(--primary)"><i class="fas ${s.i}"></i></div><div class="stat-content"><div class="stat-value">${s.v}</div><div class="stat-label">${s.l}</div></div></div>`).join('')}
      </div>`
    + `<section class="panel">
        <div class="panelhead"><h2>Цели на ${months[now.getMonth()]} ${now.getFullYear()}</h2><button class="btn small" data-action="editGoals">Редактировать</button></div>
        <div style="padding:22px;display:grid;grid-template-columns:1fr 1fr;gap:22px">
          ${renderGoal('Доход', goal.income_money||0, facts.total_revenue||0, money)}
          ${renderGoal('Направления', goal.referrals||0, facts.total_referrals||0, v=>v)}
        </div>
      </section>`;
}

function renderGoal(label, target, fact, fmt) {
  const pct = target > 0 ? Math.min(100, Math.round((fact / target) * 100)) : 0;
  return `<div>
    <div style="display:flex;justify-content:space-between;margin-bottom:8px"><strong>${esc(label)}</strong><span style="color:var(--gray)">${pct}%</span></div>
    <div style="background:#e2e8f0;height:8px;border-radius:4px;overflow:hidden;margin-bottom:8px"><div style="background:var(--primary);height:100%;width:${pct}%"></div></div>
    <div style="font-size:.85rem;color:var(--gray)">Цель: <strong style="color:var(--dark)">${fmt(target)}</strong> · Факт: <strong style="color:var(--success)">${fmt(fact)}</strong></div>
  </div>`;
}

// ---------- PROFILE ----------
function pageProfile() {
  const u = S.user || {};
  const parts = (u.full_name || '').split(' ');

  // Специализации агента с процентами
  const specRows = S.specializations.map(s => {
    const rateEntry = S.myRates.find(r => r.specialization_id === s.id);
    let mode = 'По клиникам';
    let rate = '—';
    if (rateEntry) {
      if (rateEntry.mode === 'custom' && rateEntry.custom_rate != null) {
        mode = 'Личная';
        rate = rateEntry.custom_rate + '%';
      } else {
        // по клиникам: собираем уникальные проценты по клиникам агента
        const rates = (rateEntry.by_clinic || [])
          .filter(c => c.active && c.default_rate != null)
          .map(c => c.default_rate);
        const unique = [...new Set(rates)];
        if (unique.length === 0) {
          rate = '—';
        } else if (unique.length === 1) {
          rate = unique[0] + '%';
        } else {
          rate = unique.map(r => r + '%').join(' / ');
        }
      }
    }
    return { name: s.name, mode, rate, isCustom: rateEntry?.mode === 'custom' };
  });

    const specsHtml = specRows.length
    ? `<div class="tablewrap"><table>
        <thead><tr><th>Специализация</th><th>Вознаграждение</th></tr></thead>
        <tbody>${specRows.map(s => `
          <tr>
            <td><strong>${esc(s.name)}</strong></td>
            <td><strong style="color:var(--success);font-size:1rem">${esc(s.rate)}</strong></td>
          </tr>`).join('')}
        </tbody></table></div>`
    : '<div class="empty"><i class="fas fa-stethoscope"></i><div>Специализаций пока нет</div></div>';

  return heading('Настройки', 'Личная информация')
    + `<section class="panel" style="padding:22px">
        <div style="display:flex;gap:20px;align-items:center;margin-bottom:24px;padding-bottom:20px;border-bottom:1px solid var(--border);flex-wrap:wrap">
          <div style="width:80px;height:80px;border-radius:50%;background:var(--primary);color:#fff;display:grid;place-items:center;font-size:1.8rem;font-weight:700">${esc((parts[0]||'П')[0])}</div>
          <div>
            <h2 style="margin:0">${esc(u.full_name || '—')}</h2>
            <p class="muted" style="margin:4px 0 0">${esc(u.email || '')}</p>
          </div>
        </div>
        <form id="profileForm" data-id="${u.id || ''}">
          <h3 style="margin:0 0 16px;font-size:1rem">Личная информация</h3>
          <div class="form-grid">
            <div class="field"><label>ФИО</label><input name="full_name" data-label="ФИО" required maxlength="40" value="${esc(u.full_name || '')}"></div>
            <div class="field"><label>Телефон</label><input name="phone" type="tel" data-label="Телефон" maxlength="20" value="${esc(u.phone || '')}"></div>
            <div class="field"><label>Дата рождения</label><input name="date_of_birth" type="date" value="${esc(u.date_of_birth || '')}"></div>
            <div class="field"><label>Опыт (лет)</label><input name="experience" type="number" min="0" max="50" maxlength="20" value="${esc(u.experience || '')}"></div>
            <div class="field"><label>Образование</label>
              <select name="education">
                <option value="">Не указано</option>
                <option value="higher" ${u.education === 'higher' ? 'selected' : ''}>Высшее</option>
                <option value="secondary" ${u.education === 'secondary' ? 'selected' : ''}>Среднее</option>
                <option value="other" ${u.education === 'other' ? 'selected' : ''}>Другое</option>
              </select>
            </div>
            <div class="field full"><label>О себе</label><textarea name="about_myself" rows="4" maxlength="2000">${esc(u.about_myself || '')}</textarea></div>
          </div>
          <div class="form-actions"><button class="btn primary" type="submit">Сохранить изменения</button></div>
        </form>
      </section>`
    + `<section class="panel" style="margin-top:20px">
        <div class="panelhead">
          <div>
            <h2>Мои специализации</h2>
            <p>Вознаграждение по каждой специализации</p>
          </div>
        </div>
        ${specsHtml}
      </section>`;
}
// ---------- CREATE REFERRAL ----------
function pageCreateReferral() {
  if (!S.clinics.length) {
    return heading('Новое направление', '') + `<div class="panel"><div class="empty"><i class="fas fa-hospital"></i><h3>Нет доступных клиник</h3><p>Обратитесь к администратору</p></div></div>`;
  }
  if (!S.specializations.length) {
    return heading('Новое направление', '') + `<div class="panel"><div class="empty"><i class="fas fa-stethoscope"></i><h3>Нет одобренных специализаций</h3><p>Обратитесь к администратору</p></div></div>`;
  }

  return heading('Новое направление', 'Создание нового направления')
    + `<form id="createReferralForm" class="panel" style="padding:24px">
        <!-- 1. Клиника -->
        <h2 class="section-title" style="display:flex;align-items:center;gap:10px;font-size:1.15rem;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid var(--border)">
          <i class="fas fa-hospital" style="color:var(--primary)"></i> Выбор клиники
        </h2>
        <div class="clinic-select-container">
          <label>Выберите клинику для направления <span class="required">*</span></label>
          <div class="clinic-options" id="clinicOptions">
            <div style="text-align:center;padding:20px;color:var(--gray)">
              <i class="fas fa-spinner fa-spin"></i> Загрузка клиник...
            </div>
          </div>
        </div>

        <!-- 2. Специализация -->
        <h2 class="section-title" style="display:flex;align-items:center;gap:10px;font-size:1.15rem;margin:24px 0 16px;padding-bottom:10px;border-bottom:1px solid var(--border)">
          <i class="fas fa-stethoscope" style="color:var(--primary)"></i> Выбор специализации
        </h2>
        <div class="specialization-select-container">
          <label>Выберите специализацию <span class="required">*</span></label>
          <div class="specialization-options" id="specializationOptions">
            <div style="text-align:center;padding:20px;color:var(--gray)">
              <i class="fas fa-spinner fa-spin"></i> Загрузка специализаций...
            </div>
          </div>
        </div>

        <!-- 3. Пациент -->
        <h2 class="section-title" style="display:flex;align-items:center;gap:10px;font-size:1.15rem;margin:24px 0 16px;padding-bottom:10px;border-bottom:1px solid var(--border)">
          <i class="fas fa-user-injured" style="color:var(--primary)"></i> Информация о пациенте
        </h2>
        <div class="patient-search-container">
          <div class="search-toggle">
            <div class="toggle-btn active" id="existingPatientToggle">Выбрать из моих пациентов</div>
            <div class="toggle-btn" id="newPatientToggle">Добавить нового пациента</div>
          </div>
          <div id="existingPatientsSection">
            <div class="search-box">
              <i class="fas fa-search"></i>
              <input type="text" id="patientSearch" placeholder="Введите ФИО, телефон или email...">
            </div>
            <div class="patients-list" id="patientsList">
              <div style="padding:20px;text-align:center;color:var(--gray)">
                <i class="fas fa-spinner fa-spin"></i> Загрузка пациентов...
              </div>
            </div>
            <div class="hint" style="margin-top:10px">Выберите пациента из списка</div>
          </div>
          <div id="newPatientSection" style="display:none">
            <div class="form-grid">
              <div class="field"><label>ФИО <span class="required">*</span></label><input type="text" id="patientFullName" maxlength="40" placeholder="Иванов Иван Иванович"></div>
              <div class="field"><label>Дата рождения <span class="required">*</span></label><input type="date" id="patientBirthDate"></div>
              <div class="field"><label>Телефон <span class="required">*</span></label><input type="tel" id="patientPhone" maxlength="20" placeholder="+7 (999) 123-45-67"></div>
              <div class="field"><label>Email</label><input type="email" id="patientEmail" maxlength="255" placeholder="patient@example.com"></div>
              <div class="field"><label>Пол <span class="required">*</span></label>
                <select id="patientGender">
                  <option value="">Выберите пол</option>
                  <option value="male">Мужской</option>
                  <option value="female">Женский</option>
                </select>
              </div>
              <div class="field full"><button type="button" class="btn primary" data-action="addPatientInline"><i class="fas fa-user-plus"></i> Добавить пациента</button></div>
            </div>
          </div>
        </div>

        <!-- 4. Визит -->
        <h2 class="section-title" style="display:flex;align-items:center;gap:10px;font-size:1.15rem;margin:24px 0 16px;padding-bottom:10px;border-bottom:1px solid var(--border)">
          <i class="fas fa-calendar-check" style="color:var(--primary)"></i> Информация о визите
        </h2>
        <p class="muted" style="margin-bottom:16px">Укажите период, в который пациент планирует посетить клинику (не более 30 дней)</p>
                <div class="form-grid">
          <div class="field full">
            <label>Стоимость услуги (₽) <span class="required">*</span></label>
            <input type="number" id="crAmount" name="amount" min="0" step="100" maxlength="10" required value="0">
            <div id="commissionPreview" style="display:none;margin-top:10px;padding:12px 14px;background:#eff7f6;border-radius:8px;border:1px solid #cfe3e0">
              <div style="font-size:.8rem;color:#547078">Ваше вознаграждение</div>
              <div style="font-size:1.4rem;font-weight:800;color:#147b7d" id="commissionAmount">0 ₽</div>
              <div style="font-size:.75rem;color:#728d92" id="commissionRateInfo">—</div>
            </div>
          </div>
          <div class="field full">
            <label>Ожидаемый период визита <span class="required">*</span></label>
            <div style="display:flex;gap:8px;align-items:center">
              <input type="date" id="crStart" name="expected_visit_start" required style="flex:1">
              <span>—</span>
              <input type="date" id="crEnd" name="expected_visit_end" required style="flex:1">
            </div>
            <div class="hint">Максимум 30 дней</div>
          </div>
          <div class="field full">
            <label>Медицинские показания / жалобы <span class="required">*</span></label>
            <textarea id="crIndications" name="med_indications" rows="3" maxlength="2000" required placeholder="Опишите симптомы, диагноз или причину обращения..."></textarea>
          </div>
          <div class="field full">
            <label>Особые пожелания</label>
            <textarea id="crWishes" name="special_wishes" rows="2" maxlength="1000" placeholder="Особые требования или пожелания пациента..."></textarea>
          </div>
        </div>

        <div class="form-actions">
          <button type="button" class="btn" data-page="referrals">Отмена</button>
          <button type="submit" class="btn primary"><i class="fas fa-paper-plane"></i> Создать направление</button>
        </div>
      </form>`;
}

function initCreateReferral() {
  selectedClinicId = null;
  selectedSpecializationId = null;
  selectedPatientId = null;

  const today = new Date();
  const tomorrow = new Date(); tomorrow.setDate(today.getDate() + 1);
  const monthLater = new Date(); monthLater.setMonth(today.getMonth() + 1);
  if ($('#crStart')) { $('#crStart').value = isoDate(tomorrow); $('#crStart').min = todayISO(); }
  if ($('#crEnd')) $('#crEnd').value = isoDate(monthLater);
  if ($('#patientBirthDate')) $('#patientBirthDate').max = todayISO();

  // Клиники
  const clinicContainer = $('#clinicOptions');
  if (clinicContainer) {
    const active = S.clinics.filter(c => c.active);
    clinicContainer.innerHTML = active.map(c => `
      <div class="clinic-option" data-clinic-id="${c.id}">
        <div class="clinic-option-name">${esc(c.name)}</div>
        <div class="clinic-option-address"><i class="fas fa-map-marker-alt"></i> ${esc(c.city || '')}${c.address ? ', ' + esc(c.address) : ''}</div>
      </div>`).join('');
    clinicContainer.querySelectorAll('.clinic-option').forEach(el => {
      el.addEventListener('click', () => selectClinic(Number(el.dataset.clinicId)));
    });
    if (active.length) selectClinic(active[0].id);
  }

  // Специализации
  const specContainer = $('#specializationOptions');
  if (specContainer) {
    specContainer.innerHTML = S.specializations.map(s => `
      <div class="specialization-option" data-spec-id="${s.id}">${esc(s.name)}</div>`).join('');
    specContainer.querySelectorAll('.specialization-option').forEach(el => {
      el.addEventListener('click', () => selectSpecialization(Number(el.dataset.specId)));
    });
    if (S.specializations.length) selectSpecialization(S.specializations[0].id);
  }

  // Пациенты
  renderPatientsList();
  const search = $('#patientSearch');
  if (search) search.addEventListener('input', () => renderPatientsList(search.value));

  // Toggle
  const exT = $('#existingPatientToggle'), newT = $('#newPatientToggle');
  const exS = $('#existingPatientsSection'), newS = $('#newPatientSection');
  if (exT && newT && exS && newS) {
    exT.addEventListener('click', () => {
      exT.classList.add('active'); newT.classList.remove('active');
      exS.style.display = 'block'; newS.style.display = 'none';
    });
    newT.addEventListener('click', () => {
      newT.classList.add('active'); exT.classList.remove('active');
      newS.style.display = 'block'; exS.style.display = 'none';
    });
  }

    // Стоимость
  const amount = $('#crAmount');
  if (amount) {
    amount.addEventListener('input', calcCreateReferralCommission);
    amount.addEventListener('focus', () => {
      if (amount.value === '0' || amount.value === '') {
        amount.value = '';
      }
    });
    amount.addEventListener('blur', () => {
      if (amount.value === '') {
        amount.value = '0';
      }
      calcCreateReferralCommission();
    });
  }
  calcCreateReferralCommission();

  // Маска телефона
  const phone = $('#patientPhone');
  if (phone) {
    phone.addEventListener('input', e => {
      let x = e.target.value.replace(/\D/g, '').match(/(\d{0,1})(\d{0,3})(\d{0,3})(\d{0,2})(\d{0,2})/);
      if (!x) return;
      e.target.value = !x[2] ? '+7' : '+7 (' + x[2] + ') ' + x[3] + (x[4] ? '-' + x[4] : '') + (x[5] ? '-' + x[5] : '');
    });
  }
}

function selectClinic(id) {
  selectedClinicId = id;
  $$('.clinic-option').forEach(el => el.classList.toggle('selected', Number(el.dataset.clinicId) === id));
  calcCreateReferralCommission();
}
function selectSpecialization(id) {
  selectedSpecializationId = id;
  $$('.specialization-option').forEach(el => el.classList.toggle('selected', Number(el.dataset.specId) === id));
  calcCreateReferralCommission();
}
function selectPatient(id) {
  selectedPatientId = id;
  $$('.patient-item').forEach(el => el.classList.toggle('selected', Number(el.dataset.patientId) === id));
  const nm = S.patients.find(p => p.id === id)?.full_name || 'Пациент';
  toast('Выбран пациент: ' + nm, 'success');
}
function renderPatientsList(search = '') {
  const container = $('#patientsList');
  if (!container) return;
  if (!S.patients.length) {
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--gray)"><i class="fas fa-user-slash"></i><div>У вас пока нет пациентов</div></div>';
    return;
  }
  const q = (search || '').toLowerCase().trim();
  const list = S.patients.filter(p => !q || [p.full_name, p.phone, p.email].join(' ').toLowerCase().includes(q));
  if (!list.length) {
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--gray)">Ничего не найдено</div>';
    return;
  }
  container.innerHTML = list.map(p => `
    <div class="patient-item ${selectedPatientId === p.id ? 'selected' : ''}" data-patient-id="${p.id}">
      <div class="patient-name">${esc(p.full_name || '—')}</div>
      <div class="patient-details">
        <span><i class="fas fa-phone"></i> ${esc(p.phone || '—')}</span>
        <span><i class="fas fa-envelope"></i> ${esc(p.email || '—')}</span>
        <span><i class="fas fa-birthday-cake"></i> ${p.age || '—'} лет</span>
      </div>
    </div>`).join('');
  container.querySelectorAll('.patient-item').forEach(el => {
    el.addEventListener('click', () => selectPatient(Number(el.dataset.patientId)));
  });
}
function calcCreateReferralCommission() {
  const preview = $('#commissionPreview');
  if (!preview) return;
  const amount = parseFloat($('#crAmount')?.value) || 0;
  if (!selectedClinicId || !selectedSpecializationId || amount <= 0) { preview.style.display = 'none'; return; }
  const r = getRateFor(selectedClinicId, selectedSpecializationId);
  if (!r) { preview.style.display = 'none'; return; }
  const commission = Math.round(amount * r.rate / 100);
  $('#commissionAmount').textContent = money(commission);
  $('#commissionRateInfo').textContent = `${r.rate}%`;
  preview.style.display = 'block';
}

function selectClinic(id) {
  selectedClinicId = id;
  $$('.clinic-option').forEach(el => el.classList.toggle('selected', Number(el.dataset.clinicId) === id));
  calcCreateReferralCommission();
}
function selectSpecialization(id) {
  selectedSpecializationId = id;
  $$('.specialization-option').forEach(el => el.classList.toggle('selected', Number(el.dataset.specId) === id));
  calcCreateReferralCommission();
}
function selectPatient(id) {
  selectedPatientId = id;
  $$('.patient-item').forEach(el => el.classList.toggle('selected', Number(el.dataset.patientId) === id));
  const nm = S.patients.find(p => p.id === id)?.full_name || 'Пациент';
  toast('Выбран пациент: ' + nm, 'success');
}

function renderPatientsList(search = '') {
  const container = $('#patientsList');
  if (!container) return;
  if (!S.patients.length) {
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--gray)"><i class="fas fa-user-slash"></i><div>У вас пока нет пациентов</div></div>';
    return;
  }
  const q = (search || '').toLowerCase().trim();
  const list = S.patients.filter(p => !q || [p.full_name, p.phone, p.email].join(' ').toLowerCase().includes(q));
  if (!list.length) {
    container.innerHTML = '<div style="padding:20px;text-align:center;color:var(--gray)">Ничего не найдено</div>';
    return;
  }
  container.innerHTML = list.map(p => `
    <div class="patient-item ${selectedPatientId === p.id ? 'selected' : ''}" data-patient-id="${p.id}">
      <div class="patient-name">${esc(p.full_name || '—')}</div>
      <div class="patient-details">
        <span><i class="fas fa-phone"></i> ${esc(p.phone || '—')}</span>
        <span><i class="fas fa-envelope"></i> ${esc(p.email || '—')}</span>
        <span><i class="fas fa-birthday-cake"></i> ${p.age || '—'} лет</span>
      </div>
    </div>`).join('');
  container.querySelectorAll('.patient-item').forEach(el => {
    el.addEventListener('click', () => selectPatient(Number(el.dataset.patientId)));
  });
}

function calcCreateReferralCommission() {
  const preview = $('#commissionPreview');
  if (!preview) return;
  const amount = parseFloat($('#crAmount')?.value) || 0;
  if (!selectedClinicId || !selectedSpecializationId || amount <= 0) {
    preview.style.display = 'none';
    return;
  }
  const r = getRateFor(selectedClinicId, selectedSpecializationId);
  if (!r) { preview.style.display = 'none'; return; }
  const commission = Math.round(amount * r.rate / 100);
  $('#commissionAmount').textContent = money(commission);
  $('#commissionRateInfo').textContent = `${r.rate}%`;
  preview.style.display = 'block';
}
// ================== 8. МОДАЛКИ ==================

// --- Пациент: добавить ---
function openPatientForm(id = null) {
  const p = id ? S.patients.find(x => x.id === Number(id)) : null;
  openDrawer(id ? 'Редактировать пациента' : 'Новый пациент',
    `<form id="patientForm" data-id="${id || ''}" autocomplete="off">
      <div class="field"><label>ФИО <span class="required">*</span></label><input name="full_name" data-label="ФИО" required maxlength="40" value="${esc(p?.full_name || '')}"></div>
      <div class="field"><label>Телефон <span class="required">*</span></label><input name="phone" type="tel" data-label="Телефон" required maxlength="20" value="${esc(p?.phone || '')}"></div>
      <div class="field"><label>Дата рождения <span class="required">*</span></label><input name="date_of_birth" type="date" required value="${esc(p?.date_of_birth || '')}"></div>
      <div class="field"><label>Email</label><input name="email" type="email" data-label="Email" maxlength="255" value="${esc(p?.email || '')}"></div>
      <div class="field"><label>Пол <span class="required">*</span></label>
        <select name="gender" required>
          <option value="">Выберите</option>
          <option value="male" ${p?.gender === 'male' ? 'selected' : ''}>Мужской</option>
          <option value="female" ${p?.gender === 'female' ? 'selected' : ''}>Женский</option>
        </select>
      </div>
      <div class="actions"><button class="btn primary" type="submit">${id ? 'Сохранить' : 'Добавить'}</button><button class="btn" type="button" data-action="close">Отмена</button></div>
    </form>`);
}

// --- Настройка колонок ---
function openColumns() {
  const all = ['id', ...referralsColumnOrder];
  openDrawer('Настройка таблицы',
    `<p class="muted" style="margin-bottom:14px">Перетащите столбцы, чтобы изменить порядок</p>
     <div id="colsList">
       ${all.map(c => {
         const isId = c === 'id';
         return `<div class="column-item" data-col="${c}" draggable="${!isId}" style="display:flex;align-items:center;gap:10px;padding:12px 14px;background:#f8fafc;border:2px solid var(--border);border-radius:8px;margin-bottom:8px;cursor:${isId?'not-allowed':'grab'};${isId?'opacity:.7':''}">
           <i class="fas fa-grip-vertical" style="color:var(--gray)"></i>
           <span style="flex:1;font-weight:600">${esc(REFERRAL_COLUMNS_DEF[c]?.label || c)}</span>
           ${isId ? '<i class="fas fa-lock" style="color:var(--gray)"></i>' : ''}
         </div>`;
       }).join('')}
     </div>
     <div class="actions">
       <button class="btn" type="button" data-action="resetColumns">По умолчанию</button>
       <button class="btn primary" type="button" data-action="saveColumns">Сохранить</button>
     </div>`);
  setupColumnsDnD();
}

function setupColumnsDnD() {
  const list = $('#colsList');
  if (!list) return;
  let dragged = null;
  list.querySelectorAll('.column-item').forEach(item => {
    item.addEventListener('dragstart', e => {
      if (item.dataset.col === 'id') { e.preventDefault(); return; }
      dragged = item; setTimeout(() => item.style.opacity = '.4', 0);
    });
    item.addEventListener('dragend', () => { item.style.opacity = ''; dragged = null; });
    item.addEventListener('dragover', e => { e.preventDefault(); });
    item.addEventListener('drop', e => {
      e.preventDefault();
      if (!dragged || dragged === item || item.dataset.col === 'id') return;
      const rect = item.getBoundingClientRect();
      if (e.clientY < rect.top + rect.height / 2) item.before(dragged); else item.after(dragged);
    });
  });
}

// --- Редактирование целей ---
function openEditGoals() {
  const goal = S.reports?.goal || {};
  const now = new Date();
  openDrawer('Редактировать цели',
    `<form id="goalsForm" autocomplete="off">
      <div class="field"><label>Доход (₽)</label><input name="income_money" type="number" min="0" value="${goal.income_money || 0}"></div>
      <div class="field"><label>Направлений</label><input name="referrals" type="number" min="0" value="${goal.referrals || 0}"></div>
      <div class="actions"><button class="btn primary" type="submit">Сохранить</button><button class="btn" type="button" data-action="close">Отмена</button></div>
    </form>`);
}

// ================== 9. ОБРАБОТЧИКИ ==================
document.addEventListener('click', async e => {
  // Навигация
  const pg = e.target.closest('[data-page]');
  if (pg) { navigate(pg.dataset.page); return; }

  const a = e.target.closest('[data-action]');
  if (!a) return;
  const action = a.dataset.action;
  const id = Number(a.dataset.id);

  try {
    switch (action) {
      case 'createAnotherReferral': closeDrawer(); navigate('create_referral'); break;
      case 'goToReferrals': closeDrawer(); navigate('referrals'); break;
      case 'addPatientInline': openPatientForm(); break;
      case 'close': closeDrawer(); break;
      case 'newPatient': openPatientForm(); break;
      case 'editPatient': openPatientForm(id); break;
      case 'deletePatient': {
        if (!confirm('Удалить пациента?')) return;
        await api(`/patients/${id}`, {method: 'DELETE'});
        toast('Пациент удалён', 'success');
        await loadPatients();
        render();
        break;
      }
      case 'deleteReferral': {
        if (!confirm('Удалить направление?')) return;
        await api(`/referrals/${id}`, {method: 'DELETE'});
        toast('Направление удалено', 'success');
        await loadReferrals();
        render();
        break;
      }
      case 'columns': openColumns(); break;
      case 'addPatientInline': openPatientForm(); break;
      case 'resetColumns': {
        referralsColumnOrder = [...DEFAULT_REFERRAL_COLUMNS];
        closeDrawer();
        render();
        break;
      }
      case 'saveColumns': {
        const list = $('#colsList');
        if (list) {
          const cols = [...list.querySelectorAll('.column-item')].map(el => el.dataset.col).filter(c => c !== 'id');
          referralsColumnOrder = cols;
          await api('/auth/column_order', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({column_order: cols}),
          });
          toast('Порядок сохранён', 'success');
        }
        closeDrawer();
        render();
        break;
      }
      case 'resetReferralsFilters': {
        query = ''; filterStatus = 'all'; filterClinic = 'all'; referralsPage = 1;
        render();
        break;
      }
      case 'refPage': {
        const p = Number(a.dataset.pageNum);
        if (p >= 1) { referralsPage = p; render(); }
        break;
      }
      case 'loadReports': {
        const from = $('#repFrom')?.value;
        const to = $('#repTo')?.value;
        if (from && to) {
          await loadReports(from, to);
          render();
        }
        break;
      }
      case 'editGoals': openEditGoals(); break;
    }
  } catch (err) {
    toast('Ошибка: ' + err.message, 'error');
  }
});

// Фильтры referrals / patients (через input)
document.addEventListener('input', e => {
  if (e.target.id === 'refSearch') {
    const inp = e.target;
    const s = inp.selectionStart, en = inp.selectionEnd;
    query = inp.value;
    referralsPage = 1;
    render();
    requestAnimationFrame(() => {
      const n = document.getElementById('refSearch');
      if (n) { n.focus(); try { n.setSelectionRange(s, en); } catch {} }
    });
  }
  if (e.target.id === 'patSearch') {
    const inp = e.target;
    const s = inp.selectionStart, en = inp.selectionEnd;
    query = inp.value;
    render();
    requestAnimationFrame(() => {
      const n = document.getElementById('patSearch');
      if (n) { n.focus(); try { n.setSelectionRange(s, en); } catch {} }
    });
  }
});

document.addEventListener('change', e => {
  if (e.target.id === 'refStatusFilter') { filterStatus = e.target.value; referralsPage = 1; render(); }
  if (e.target.id === 'refClinicFilter') { filterClinic = e.target.value; referralsPage = 1; render(); }
  if (e.target.id === 'patStatusFilter') { patientFilterStatus = e.target.value; render(); }
});

// Submit форм
document.addEventListener('submit', async e => {
  e.preventDefault();
  const f = e.target;
  const fd = new FormData(f);

  try {
    // Профиль
    if (f.id === 'profileForm') {
      const data = {
        full_name: fd.get('full_name'),
        phone: fd.get('phone') || null,
        date_of_birth: fd.get('date_of_birth') || null,
        experience: fd.get('experience') || null,
        education: fd.get('education') || null,
        about_myself: fd.get('about_myself') || null,
      };
      const upd = await api('/auth/profile', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
      S.user = {...S.user, ...upd};
      toast('Профиль сохранён', 'success');
      render();
      return;
    }

    // Пациент
        if (f.id === 'patientForm') {
      const isEdit = f.dataset.id;
      const body = {
        full_name: fd.get('full_name'),
        phone: fd.get('phone'),
        date_of_birth: fd.get('date_of_birth'),
        email: fd.get('email') || null,
        gender: fd.get('gender'),
      };
      let savedId = null;
      if (isEdit) {
        await api(`/patients/${f.dataset.id}`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        savedId = Number(f.dataset.id);
        toast('Пациент обновлён', 'success');
      } else {
        const created = await api('/patients', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        savedId = created?.id || null;
        toast('Пациент добавлен', 'success');
      }
      closeDrawer();
      await loadPatients();

      // Если открыто create_referral — обновляем список и выбираем нового
      if (page === 'create_referral') {
        const existingSec = $('#existingPatientsSection');
        const newSec = $('#newPatientSection');
        const exT = $('#existingPatientToggle');
        if (existingSec && newSec && exT) {
          existingSec.style.display = 'block';
          newSec.style.display = 'none';
          exT.classList.add('active');
          $('#newPatientToggle')?.classList.remove('active');
        }
        renderPatientsList($('#patientSearch')?.value || '');
        if (savedId) selectPatient(savedId);
        return;
      }

      render();
      return;
    }

    // Цели
    if (f.id === 'goalsForm') {
      const now = new Date();
      await api('/goals', {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
        income_money: Number(fd.get('income_money')) || 0,
        referrals: Number(fd.get('referrals')) || 0,
        month: now.getMonth() + 1,
        year: now.getFullYear(),
      })});
      toast('Цели сохранены', 'success');
      closeDrawer();
      const from = $('#repFrom')?.value || isoDate(new Date(Date.now() - 30*86400000));
      const to = $('#repTo')?.value || todayISO();
      await loadReports(from, to);
      render();
      return;
    }

    // Создание направления
        if (f.id === 'createReferralForm') {
      if (!selectedClinicId) { toast('Выберите клинику', 'error'); return; }
      if (!selectedSpecializationId) { toast('Выберите специализацию', 'error'); return; }
      if (!selectedPatientId) { toast('Выберите пациента', 'error'); return; }
      const start = $('#crStart')?.value;
      const end = $('#crEnd')?.value;
      if (!start || !end) { toast('Укажите период визита', 'error'); return; }
      if (start > end) { toast('Дата начала позже окончания', 'error'); return; }
      const days = Math.ceil((new Date(end) - new Date(start)) / 86400000);
      if (days > 30) { toast('Период не больше 30 дней', 'error'); return; }
      const indications = $('#crIndications')?.value?.trim();
      if (!indications) { toast('Укажите медицинские показания', 'error'); return; }

      const body = {
        clinic_id: selectedClinicId,
        specialization_id: selectedSpecializationId,
        patient_id: selectedPatientId,
        amount: Number($('#crAmount')?.value) || 0,
        expected_visit_start: start,
        expected_visit_end: end,
        med_indications: indications,
        special_wishes: $('#crWishes')?.value || null,
      };
      await api('/referrals', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      await loadReferrals();

      // Красивая модалка «Направление создано»
      openDrawer('Направление создано', `
        <div style="text-align:center;padding:20px 10px 10px">
          <div style="width:80px;height:80px;background:#d1fae5;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;margin-bottom:20px">
            <i class="fas fa-check" style="font-size:2.4rem;color:#10b981"></i>
          </div>
          <h2 style="margin:0 0 12px;font-size:1.3rem">Направление успешно создано!</h2>
          <p style="color:var(--gray);margin:0 0 28px;line-height:1.6">
            Клиника получит уведомление<br>и подтвердит точную дату визита в течение 24 часов.
          </p>
          <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
            <button type="button" class="btn" data-action="createAnotherReferral">Создать ещё одно</button>
            <button type="button" class="btn primary" data-action="goToReferrals">Мои направления</button>
          </div>
        </div>
      `);
      return;
    }
  } catch (err) {
    toast('Ошибка: ' + err.message, 'error');
  }
});




// ================== 10. ИНИЦИАЛИЗАЦИЯ ==================
$('#close')?.addEventListener('click', closeDrawer);
$('#backdrop')?.addEventListener('click', e => { if (e.target.id === 'backdrop') closeDrawer(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });

const logoutBtn = $('#logoutBtn');
if (logoutBtn) {
  logoutBtn.addEventListener('click', async () => {
    try { await api('/auth/logout', {method: 'POST'}); } catch {}
    location.href = '/';
  });
}

window.addEventListener('hashchange', () => {
  readRoute();
  render();
});

(async function init() {
  try {
    const me = await api('/auth/me');
    if (!me) { location.href = '/'; return; }
    if (me.role !== 'agent') {
      if (me.role === 'chef') location.href = '/portal-admin';
      else if (me.role === 'admin') location.href = '/clinic-admin';
      else location.href = '/';
      return;
    }
    S.user = me;
    await loadAll();
    // Загружаем данные, чтобы страницы не были пустыми
    await Promise.all([loadReferrals(), loadPatients(), loadDashboard()]);
    readRoute();
    render();
  } catch (e) {
    if (e.message !== '401') console.error('init:', e);
    location.href = '/';
  }
})();
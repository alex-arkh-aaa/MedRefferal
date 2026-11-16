# Medpoint — STATE (снимок на 2026-11-12)

## Проект
Платформа медицинских агентов. Backend: FastAPI + PostgreSQL + RabbitMQ + Redis, Docker Compose. Frontend: HTML+JS (без сборщика).

## Архитектура
- `api_gateway` (порт 80) — JWT, rate limiting, HTML-роуты, проксирование в `service_users`, раздача `/static/`.
- `service_users` (порт 8000) — вся бизнес-логика.
- `service_notify` (порт 8003) — email через RabbitMQ (`email_queue`).
- `postgres` — БД `med_referral_db`.

## Роли (в JWT: `sub`, `user_id`, `full_name`, `role`)
- `agent` — агент.
- `admin` — админ клиники (видит только свои клиники).
- `chef` — шеф (один, `portaladmin@yandex.ru`).

## Модели (`service_users/app/models.py`)
- **`Agent`** (`agents`): email, password_hash, full_name, phone, date_of_birth, experience, education, about_myself, column_order (JSON), **status** (`pending/active/inactive/rejected`), deleted_at, **admin_id** (FK→Admins).
- **`Admin`** (`admins`): email, password_hash, full_name, phone, **role** (`chef/admin`), active, permissions (JSON), deleted_at. Partial unique index на `role='chef'`.
- **`AdminClinic`** — M2M admin↔clinic.
- **`Clinic`** (`clinics`): name, city, address, phone, active.
- **`Specialization`** — справочник (21 запись).
- **`AgentSpecialization`** — M2M + `active`. **Инвариант не поддерживается** (см. «Открытые вопросы»).
- **`AgentClinic`** — M2M agent↔clinic.
- **`AgentRate`** — agent_id, specialization_id, **mode** (`clinic/custom`), **custom_rate**. Хранит **только `mode='custom'`** (личные ставки). `mode='clinic'` — **вычисляется на лету**.
- **`ClinicSpecialty`** — clinic_id, specialization_id, default_rate, active.
- **`Patient`** — agent_id, full_name, date_of_birth, phone, email, gender, info, status.
- **`Referral`** — agent_id, clinic_id, patient_id, specialization_id, amount, expected_visit_start/end, med_indications, special_wishes, status (`new/approved/rejected`), status_changed_at, commission_rate, commission_amount, payout_status, paid_at, payment_reference, specialty_name_at_confirmation.
- **`Goal`** — agent_id, month, year, income_money, referrals.
- **`History`** — label, text, actor_type (`agent/admin/chef/system`), actor_id, actor_name, created_at.
- **`EmailVerification`** — email, code, expires_at.

## Миграции (применены)
`a799a240a7e2_init` → `6e7f57f74f06_add_seed_data` → `eeb75508a0e2_education` → `7eef4b5fae5c_patient_status` → `af67ab719462_gender` → `eb3997ec001d_remove_email_unique` → `4e349b2b7f44_clinics_coordinates` → `a9c8667245f8_fix_bugs` → `4e372c0c78b5_chef_and_admins` → `393ba10550f8_clinic_timestamps` → `3ed86b9cb8dc_1_try_of_the_final_db` → `add_specializations`.

**Не применяется:** `backfill_agent_rates_01` — **не нужен**, т.к. `mode='clinic'` вычисляется на лету.

---

## Frontend

### Удалено
- `Portal_Admin.html`, `Clinic_Admin.html` — заменены единым `admin_panel.html`.
- `earnings.html` + роут `/earnings` — **удалены**.
- Старые `old/*.html` — удалены.

### Актуальные файлы

#### `api_gateway/app/templates/`
- `404.html`, `index.html`, `terms_and_privacy.html` — публичные.
- **`admin_panel.html`** — единый кабинет шефа/админа.
- **`agent_panel.html`** — единый кабинет агента (новый).
- Старые `dashboard.html`, `create_referral.html`, `referrals.html`, `patients.html`, `clinics.html`, `reports.html`, `profile.html` — **не используются** (роуты → `agent_panel.html`). Можно удалить.

#### `api_gateway/app/templates/static/`
- `admin_panel.css`, `admin_panel.js` — единый кабинет админа/шефа.
- **`agent_panel.css`, `agent_panel.js`** — единый кабинет агента.

### `admin_panel` — кабинет шефа/админа
- Роуты: `/portal-admin`, `/clinic-admin`, `/admin_panel` → `admin_panel.html`.
- Роль определяется через `isChef()` (`S.user.role === 'chef'`).
- NAV: шеф — 6 разделов, админ — 5 (без `admins`).
- Иконки Font Awesome: `fa-house`, `fa-file-medical`, `fa-user-shield`, `fa-user-doctor`, `fa-hospital`, `fa-chart-bar`.
- Блок «Регистрация агентов» внизу «Агентов».
- Модалка «Одобрить регистрацию» — `registration-person` + `dl.details` + `p.note` + форма (`decision`, `clinic_ids`, `specialization_ids`, `admin_id` — только шеф, `decision_reason`).
- Вознаграждение агента в профиле — синтез из `GET /agents/{id}/rates` (реальные custom + виртуальные clinic) + колонка «Клиники» с кнопкой «Посмотреть» (`showAgentClinicsRates`), модалка «Изменить» с двумя карточками (`rateModeForm`, `onRateChoice`).
- «Новые направления» — `#refResults`, `referralTable`, модалка `viewReferral` → `PUT /admin/referrals/{id}`.
- Профиль администратора — ФИО, Телефон, Email, Доступ, Регистрации агентов.
- Поиск — `requestAnimationFrame` + `setSelectionRange` (фокус не теряется).
- Клиники сортируются по `id`.
- Валидация форм — `validateForm` (включая `maxLength`), `data-label`, `type`, `minlength`, `min`, `max`.
- Ошибки Pydantic → на русском (`FIELD_RU`, `MSG_RU`).
- **ФИО в сайдбаре/topbar:** фамилия + `<br>` + имя-отчество (серые), без обрезки.

### `agent_panel` — кабинет агента
- Роуты `/dashboard`, `/create_referral`, `/referrals`, `/patients`, `/clinics`, `/reports`, `/profile` → **редирект** на `/agent_panel#<page>` (302).
- `/agent_panel` → `agent_panel.html`, `location.hash` определяет страницу.
- Hash-роутинг: `#dashboard`, `#create_referral`, `#referrals`, `#patients`, `#clinics`, `#reports`, `#profile`.
- `init()`: проверяет `role === 'agent'`; если `chef` → `/portal-admin`, `admin` → `/clinic-admin`, иначе `/`.
- NAV (7 разделов): Главная, Новое направление, Мои направления, Пациенты, Клиники, Отчеты, Настройки.
- **`pageDashboard`** — приветствие, дата, 4 цифры (`today_referrals`, `upcoming_visits`, `total_referrals`, `active_patients`), «Последние действия», «Ближайшие визиты», «Топ клиник».
- **`pageReferrals`** — 4 стат-карточки, таблица с **настраиваемым порядком колонок** (модалка `openColumns` с drag&drop), поиск, фильтры (статус, клиника), пагинация, «⚙ Настройка таблицы» справа внизу, «Новое направление» (синяя) справа вверху, «↻ Сбросить» в controls (справа), удаление направления.
- **`pagePatients`** — таблица, поиск, фильтр статуса, «Добавить пациента» (синяя) → модалка `patientForm` → `POST/PUT /patients`.
- **`pageClinics`** — таблица клиник агента.
- **`pageReports`** — 4 стат-карточки, даты `с`/`по`, «Цели» с прогресс-барами, модалка `editGoals` → `PUT /goals`.
- **`pageProfile`** — личная информация (форма: ФИО, телефон, дата, опыт, образование, о себе) + **«Мои специализации»** (таблица: Специализация, Вознаграждение; **только для чтения**, без редактирования). `PUT /auth/profile` **без** `specialization_ids`.
- **`pageCreateReferral`** — красивый UI из старого `create_referral.html`:
  - **Клиники** — карточки с адресом, клик = выбор, автовыбор первой.
  - **Специализации** — карточки, клик = выбор, автовыбор первой.
  - **Пациенты** — toggle «Выбрать из моих / Добавить нового», поиск, список (ФИО + телефон + email + возраст), клик = выбор.
  - **«Добавить нового»** — форма (ФИО, дата, телефон с маской, email, пол) → модалка `patientForm` → после сохранения возврат на `#create_referral` + новый пациент выбран.
  - **Стоимость** — отдельная строка (`field full`), при фокусе `0` очищается, при blur пустое → `0`.
  - **Блок «Ваше вознаграждение»** — появляется при выборе клиники + специализации + вводе стоимости (`calcCreateReferralCommission`).
  - **Период визита** — две даты, `field full`, валидация ≤ 30 дней.
  - **Показания/пожелания** — textarea.
  - **После создания** — красивая модалка «Направление успешно создано» с зелёной галочкой + две кнопки: «Создать ещё одно» (`createAnotherReferral`) и «Мои направления» (`goToReferrals`).

---

## Backend — что сделано

### `api_gateway/app/main.py`
- `app.mount("/static", StaticFiles(directory="app/templates/static"))`.
- `/portal-admin`, `/clinic-admin`, `/admin_panel` → `admin_panel.html`.
- `/agent_panel` → `agent_panel.html`.
- 7 роутов `/dashboard`, `/create_referral`, `/referrals`, `/patients`, `/clinics`, `/reports`, `/profile` → **`RedirectResponse(url="/agent_panel#<page>", 302)`**.
- `/earnings` — **удалён**.
- `auth_middleware` — `public_paths` включает `/clinic-admin`, `/portal-admin`.
- `proxy_request` — передаёт `X-User-ID`, `X-User-Email`, `X-User-Role`.

### `service_users/app/main.py`
- `/auth/login`, `/auth/me`, `/auth/logout`, `/auth/register`, `/auth/send_code`.
- `get_current_agent`, `get_current_admin`, `get_current_chef`.
- `GET /api/v1/clinics` — фильтр по роли (шеф: все, админ: свои, агент: свои, без токена: активные).
- `GET /api/v1/agents` — шеф: все, админ: агенты своих клиник.
- `GET /api/v1/admins` — только шеф.
- `POST /agents/{id}/approve` — pending → active + clinic_ids + specialization_ids + admin_id (для шефа).
- `POST /agents/{id}/reject` — pending → rejected + decision_reason.
- `PUT /clinics/{id}` — **только шеф**.
- `GET /clinics/{id}/specialties` — **админ + агент** (свой), шеф — все. Ручной разбор токена, не `Depends(get_current_admin)`.
- `GET /agents/{id}/rates` — **синтез**: реальные `mode='custom'` + виртуальные `mode='clinic'` из `AgentSpecialization` (без записи в БД).
- `PUT /agents/{id}/rates/{spec_id}` — `set_agent_rate`: при `mode='clinic'` — **DELETE** строки из `agent_rates`, при `mode='custom'` — INSERT/UPDATE. Ответ: `specialization_name` из `Specialization` (если `rate.id is None`).
- `GET /agents/me/rates` — **агентский**, возвращает все специализации агента: `mode='custom'` (с `custom_rate`) или `mode='clinic'` (с `by_clinic[]`).
- `GET /history` — вариант А: шеф — всё, админ — только `actor_id=admin.id`.
- `GET/PUT /admin/referrals` — шеф — все, админ — своих клиник.

### `service_users/app/crud.py`
- `set_agent_specializations` — **не создаёт `AgentRate`** (только `AgentSpecialization`). **Правильно**, по архитектуре.
- `set_agent_rate` — при `mode='clinic'` **удаляет** строку, при `mode='custom'` — INSERT/UPDATE, после `commit` **перезагружает** с `selectinload(AgentRate.specialization)` (иначе `MissingGreenlet`).
- `get_agent_rates` — `select(AgentRate).options(selectinload(AgentRate.specialization))`.

### `service_users/app/schemas.py`
- Все строковые поля — с `max_length` (email 40, full_name 40, phone 20, password 8–128, name/city 100, address 255, med_indications 2000, special_wishes 1000, about_myself 2000, decision_reason 500).
- `AgentRateResponse.id: Optional[int] = None` — для виртуальных ставок.

---

## Что проверено и работает

- Единый `admin_panel` — все 6/5 разделов, drag&drop колонок, регистрация агентов, вознаграждение (личное / по клиникам), модалки.
- Единый `agent_panel` — все 7 разделов, hash-роутинг, редиректы, `create_referral` с красивым UI, модалки, `calculateCommission`.
- Синтез `GET /agents/{id}/rates` — реальные + виртуальные.
- `set_agent_rate` — удаляет строку при `mode='clinic'`.
- `GET /agents/me/rates` — ставки агента с `by_clinic[]`.
- `GET /clinics/{id}/specialties` — доступен агенту (для `calculateCommission` через `by_clinic`).
- Валидация форм на фронте (включая `maxLength`).
- Ошибки Pydantic → русский.
- Маска телефона в `create_referral` (inline-форма нового пациента).
- Модалка «Направление создано» с двумя кнопками.
- Поле «Стоимость» — очищается при фокусе, `0` при blur.
- ФИО в сайдбаре/topbar — фамилия + имя-отчество (двумя строками).
- Кнопки «Новый» / «Новое направление» / «Добавить пациента» — синие (`.btn.primary`).
- `earnings.html` + `/earnings` — удалены.
- `/agent_panel` — прямой доступ; 7 роутов — 302-редирект на `/agent_panel#<page>`.
- Старый `create_referral.html` — заменён красивым UI в `agent_panel.js`.

---

## Открытые вопросы / в плане

1. **`AgentSpecialization` без `AgentRate`** — **не баг**. `mode='clinic'` вычисляется на лету (`GET /agents/{id}/rates`, `GET /agents/me/rates`). Старые агенты без `AgentSpecialization` — «Вознаграждение» пусто, пока не добавят через админку.
2. **История агента** (таб в профиле) — **нет** `AgentRateHistory` на бэке. Не реализовано (не критично).
3. **`GET /admin/referrals`** — `specialization_name` из `r.specialization.name`; если специализация удалена, `None`. Не критично.
4. **Старые HTML** (`dashboard.html`, `referrals.html`, `patients.html`, `clinics.html`, `create_referral.html`, `reports.html`, `profile.html`) — **не используются** роутами. Можно **удалить**. Опционально.

---

## Известные баги (не критичные)

- `crud.get_patient_by_email` — при `patient_id=None` работает.
- `crud.get_user_by_email_including_inactive` — то же, что `get_user_by_email`.
- `ReferralDetailResponse.is_paid` — в `schemas.py` есть, в `main.py` для `GET /referrals` не передаётся (мелочь).

---

## Правила работы

- **Backend — источник правды.** Фронт подстраивается.
- **Если правок > 3 и файл небольшой** — присылать целиком. Иначе — блоками с уникальными якорями для Ctrl+F.
- **Стили** — не менять без запроса.
- **Autogenerate** — только для добавления; переименования/данные — ручные миграции.
- **`get_current_agent`, `get_current_admin`, `get_current_chef`** — зависимости.
- **`add_history(db, actor_type, actor_id, label, text, actor_name=None)`** — сигнатура.
- **`Agent.status`** — не `is_active`.
- **`Agent.about_myself`** — комментарий при регистрации.
- **`agent_rates`** — **только `mode='custom'`**. `mode='clinic'` — вычисляется на лету.
- **`set_agent_specializations`** — **не создаёт `AgentRate`**.
- **`set_agent_rate`** — при `mode='clinic'` **удаляет** строку.
- **`GET /agents/{id}/rates`** — синтез (реальные + виртуальные).
- **`GET /agents/me/rates`** — агентский, с `by_clinic[]`.
- **`GET /clinics/{id}/specialties`** — доступен агенту (для `by_clinic`).
- **Кеш** — браузер кеширует `.css`/`.js` через `StaticFiles`. Во время разработки — DevTools → Network → Disable cache + Ctrl+F5. Долгосрочно — `?v=mtime` (не реализовано).

---

## Тестирование

Пользователь тестирует сайт и присылает ошибки. Каждое сообщение — набор пунктов (1, 2, 3...). Задача: точечно чинить, не ломая остальное. Если непонятно — задавать уточняющие вопросы. Если правка затрагивает несколько файлов — присылать полные файлы или блоки с уникальными якорями для Ctrl+F. Пользователь **не любит** «попробуй так, а если не так — вот так». Нужны **точные** правки: что заменить, где, на что.

## Что делать в первую очередь (следующая итерация)

1. **Дождаться новых багов** от пользователя — чинить точечно.
2. **Опционально:** удалить старые HTML (`dashboard.html`, `referrals.html`, `patients.html`, `clinics.html`, `create_referral.html`, `reports.html`, `profile.html`) — не используются.
3. **Опционально:** добавить `?v=mtime` к `<link>`/`<script>` в `agent_panel.html` и `admin_panel.html` для сброса кеша.
4. **Опционально:** `AgentRateHistory` на бэке + история агента в `agent_panel`.
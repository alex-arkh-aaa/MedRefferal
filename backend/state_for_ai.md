# Medpoint — STATE (снимок на 2026-11-04, после переключения на admin_panel)

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
- **`Specialization`** — справочник (21 запись после `add_specializations`).
- **`AgentSpecialization`** — M2M + `active`. **Инвариант (не поддерживается кодом): каждой `AgentSpecialization` должна соответствовать `AgentRate`.**
- **`AgentClinic`** — M2M agent↔clinic.
- **`AgentRate`** — agent_id, specialization_id, **mode** (`clinic/custom`), **custom_rate**.
- **`ClinicSpecialty`** — clinic_id, specialization_id, default_rate, active.
- **`Patient`** — agent_id, full_name, date_of_birth, phone, email, gender, info, status.
- **`Referral`** — agent_id, clinic_id, patient_id, specialization_id, amount, expected_visit_start/end, med_indications, special_wishes, status (`new/approved/rejected`), status_changed_at, commission_rate, commission_amount, payout_status, paid_at, payment_reference, specialty_name_at_confirmation.
- **`Goal`** — agent_id, month, year, income_money, referrals.
- **`History`** — label, text, actor_type (`agent/admin/chef/system`), actor_id, actor_name, created_at.
- **`EmailVerification`** — email, code, expires_at.

## Миграции (применены)
`a799a240a7e2_init` → `6e7f57f74f06_add_seed_data` → `eeb75508a0e2_education` → `7eef4b5fae5c_patient_status` → `af67ab719462_gender` → `eb3997ec001d_remove_email_unique` → `4e349b2b7f44_clinics_coordinates` → `a9c8667245f8_fix_bugs` → `4e372c0c78b5_chef_and_admins` → `393ba10550f8_clinic_timestamps` → `3ed86b9cb8dc_1_try_of_the_final_db` → `add_specializations`.

**Не применена:** `backfill_agent_rates_01` — не создана. Нужен бэкфилл `AgentRate` для существующих `AgentSpecialization`.

## Frontend

### Удалено
`Portal_Admin.html` и `Clinic_Admin.html` — **удалены** (в структуре проекта их нет). Остался единый `admin_panel.html`.

### `api_gateway/app/templates/` (актуальный список)
- `404.html`, `admin_panel.html`, `clinics.html`, `create_referral.html`, `dashboard.html`, `earnings.html`, `index.html`, `patients.html`, `profile.html`, `referrals.html`, `reports.html`, `terms_and_privacy.html`.
- **Старые `old/login.html`, `old/orders.html`, `old/profile.html`, `old/register.html`** — тоже удалены из структуры.

### `api_gateway/app/templates/static/`
- `admin_panel.css` — все стили единой панели. **Подсветка меню есть** (`.nav button:hover,.nav button.active{background:#28545d;color:white}`), иконки Font Awesome есть (`.nav button i{...}`).
- `admin_panel.js` — вся логика (секции 1–10).

### `admin_panel.html`
- Подключён Font Awesome 6.4.0 CDN.
- `<link rel="stylesheet" href="/static/admin_panel.css">`, `<script src="/static/admin_panel.js">`.
- Роуты `/portal-admin`, `/clinic-admin`, `/admin_panel` **все** рендерят `admin_panel.html`.

### `admin_panel.js` — фичи
- `isChef()` — определяет роль через `S.user.role`.
- `NAV` у шефа: 6 разделов. У админа: 5 (без `admins`).
- Иконки: `fa-house`, `fa-file-medical`, `fa-user-shield`, `fa-user-doctor`, `fa-hospital`, `fa-chart-bar`.
- **Регистрация агентов** — внизу раздела «Агенты» (`#registrationsBlock`, `#regResults`), кнопка «Новые ↓ N» сверху.
- Модалка «Одобрить регистрацию» — как в `Medpoint_Portal_Admin`: `registration-person` с инициалами, `dl.details` (Подана, Почта, Телефон, Статус), `p.note` (комментарий), форма `approvePendingForm` с `decision`, `clinic_ids`, `specialization_ids`, `admin_id` (только шеф), `decision_reason`.
- **Вознаграждение агента** — в профиле агента (`#rateResults`), табы «Вознаграждение / История агента», таблица ставок.
- **Новые направления** — `#refResults`, `referralTable`, модалка `viewReferral` → `PUT /admin/referrals/{id}`.
- Профиль администратора — ФИО, Телефон, Email, Доступ, Регистрации агентов.
- **Поиск** — через `input` event, `requestAnimationFrame` + `setSelectionRange` (фокус не теряется).
- **Клиники** — сортируются по `id` (`sort((a,b)=>a.id-b.id)`).
- **Валидация форм** — `validateForm`, атрибуты `data-label`, `type`, `minlength`, `min`, `max`.
- **Ошибки Pydantic → на русском** — `FIELD_RU`, `MSG_RU` в `api()`.

## Backend — что сделано

### `api_gateway/app/main.py`
- `app.mount("/static", StaticFiles(directory="app/templates/static"))`.
- `GET /portal-admin`, `GET /clinic-admin`, `GET /admin_panel` — все рендерят `admin_panel.html`.
- `auth_middleware` — `public_paths` включает `/clinic-admin`, `/portal-admin`.
- `proxy_request` — передаёт `X-User-ID`, `X-User-Email`, `X-User-Role`.

### `service_users/app/main.py`
- `/auth/login`, `/auth/me`, `/auth/logout`, `/auth/register`, `/auth/send_code` — есть.
- `get_current_agent`, `get_current_admin`, `get_current_chef` — есть.
- `GET /api/v1/clinics` — фильтр по роли (шеф: все, админ: свои, агент: свои, без токена: активные).
- `GET /api/v1/agents` — шеф: все, админ: агенты своих клиник.
- `GET /api/v1/admins` — только шеф.
- `POST /api/v1/agents/{id}/approve` — pending → active + clinic_ids + specialization_ids + admin_id (для шефа).
- `POST /api/v1/agents/{id}/reject` — pending → rejected + decision_reason.
- `PUT /api/v1/clinics/{id}` — **только шеф** (`Depends(get_current_chef)`).
- `GET/PUT /api/v1/clinics/{id}/specialties` — админ клиники — свои, шеф — все.
- `GET/PUT /api/v1/agents/{id}/rates` — ставки агента.
- `GET /api/v1/history` — **вариант А**: шеф видит всё, админ — только `actor_id=admin.id`.
- `GET/PUT /api/v1/admin/referrals` — новые направления; шеф — все, админ — своих клиник.

### `service_users/app/crud.py`
- `set_agent_specializations` — **есть**, но **НЕ создаёт `AgentRate`** при добавлении специализации. Только `AgentSpecialization`. ⚠️ **Главная причина пустого «Вознаграждения».**
- `set_agent_rate` — upsert `AgentRate`.
- `get_agent_rates` — `select(AgentRate)`.
- `get_agent_specializations` — `select(AgentSpecialization).options(selectinload(specialization))`.

## Что НЕ работает / открытые вопросы (на 2026-11-04)

### 🔴 Срочно
1. **В профиле агента → «Вознаграждение» пусто.** `GET /agents/{id}/rates` возвращает `[]`. Причина: `crud.set_agent_specializations` **не создаёт** `AgentRate` при добавлении специализации. Инвариант `AgentSpecialization ⇒ AgentRate` **не поддерживается**.
   - **Фикс 1 (backend):** в `crud.set_agent_specializations` при добавлении новой специализации создавать `AgentRate(agent_id, specialization_id, mode='clinic', custom_rate=None)`.
   - **Фикс 2 (data):** бэкфилл для старых `agent_specializations` — SQL или миграция.
2. **У старых агентов нет `AgentSpecialization`** вообще (до появления `set_agent_specializations`). Значит в профиле «Специализации — Нет», в «Вознаграждении» — пусто. Лечится только перезаливкой через UI (редактировать агента → добавить специализации).

### 🟡 В плане
3. Миграция `backfill_agent_rates_01` — создать и применить.
4. История агента (таб «История агента») — заглушка. `AgentRateHistory` на бэке нет. Если нужно — отдельная задача.
5. `/api/v1/admin/referrals` — `specialization_name` берётся из `r.specialization.name`. Если специализация удалена (а её не удаляют), ок.

### 🟢 Проверено, всё ок
- Подсветка меню есть (`.nav button:hover,.nav button.active{background:#28545d;color:white}`).
- Иконки Font Awesome есть (CDN + `<i class="fas ${ICONS[t]}">`).
- Переключение `/portal-admin`, `/clinic-admin` на `admin_panel.html` — **сделано**.
- `GET /history` — вариант А (админ — только свои).
- `PUT /clinics/{id}` — только шеф.
- Старые `Portal_Admin.html`, `Clinic_Admin.html` — **удалены**.
- Старые `old/*.html` — **удалены**.

## Правила работы
- **Backend — источник правды.** Фронт подстраивается.
- **Если правок > 3 и файл небольшой** — присылать целиком. Иначе — блоками с маркерами.
- **Стили** — не менять без запроса.
- **Autogenerate** — только для добавления; переименования/данные — ручные миграции.
- **`get_current_agent`, `get_current_admin`, `get_current_chef`** — зависимости.
- **`add_history(db, actor_type, actor_id, label, text, actor_name=None)`** — сигнатура.
- **`Agent.status`** — не `is_active`.
- **`Agent.about_myself`** — комментарий при регистрации.
- **Инвариант:** `AgentSpecialization` ⇒ `AgentRate`. Создаётся в `set_agent_specializations`, поддерживается `set_agent_rate`.

## Известные баги (не критичные)
- `crud.get_patient_by_email` — при `patient_id=None` работает.
- `crud.get_user_by_email_including_inactive` — то же, что `get_user_by_email`.
- `crud.create_referral` — `commission_rate` может быть `None`.
- `ReferralDetailResponse.is_paid` — в `schemas.py` есть, но `ReferralDetailResponse` в `main.py` для `GET /referrals` его не передаёт. Мелочь.

## Тестирование
Пользователь тестирует сайт и присылает ошибки. Каждое сообщение — набор пунктов (1, 2, 3...). Задача: точечно чинить, не ломая остальное. Если непонятно — задавать уточняющие вопросы. Если правка затрагивает несколько файлов — присылать полные файлы или блоки с уникальными якорями для Ctrl+F.

## Что делать в первую очередь (следующая итерация)
1. **Починить `crud.set_agent_specializations`** — создавать `AgentRate` при добавлении специализации.
2. **Бэкфилл `AgentRate`** для существующих `AgentSpecialization` (SQL или миграция `backfill_agent_rates_01`).
3. **У старых агентов нет `AgentSpecialization`** — если нужно, перезалить через UI (редактировать → добавить специализации) или SQL-бэкфилл (если знаем, какие специализации у них были).
4. Дальше — по ошибкам от пользователя.
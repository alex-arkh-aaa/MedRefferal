# Medpoint — STATE (снимок на 2026-11-04, после итерации с admin_panel)

## Проект
Платформа медицинских агентов. Backend: FastAPI + PostgreSQL + RabbitMQ + Redis, Docker Compose. Frontend: HTML+JS (без сборщика).

## Архитектура
- `api_gateway` (порт 80) — JWT, rate limiting, HTML-роуты, проксирование в `service_users`.
- `service_users` (порт 8000) — вся бизнес-логика.
- `service_notify` (порт 8003) — email через RabbitMQ (`email_queue`).
- `postgres` — БД `med_referral_db`.

## Роли (в JWT: `sub`, `user_id`, `full_name`, `role`)
- `agent` — агент.
- `admin` — админ клиники (видит только свои клиники).
- `chef` — шеф (один, `portaladmin@yandex.ru`). **Логин шефа починен** (была проблема 422 — исправлено).

## Модели (`service_users/app/models.py`)
- **`Agent`** (`agents`): email, password_hash, full_name, phone, date_of_birth, experience, education, about_myself, column_order (JSON), **status** (`pending/active/inactive/rejected`), deleted_at, **admin_id** (FK→Admins).
- **`Admin`** (`admins`): email, password_hash, full_name, phone, **role** (`chef/admin`), active, permissions (JSON), deleted_at. Partial unique index на `role='chef'`.
- **`AdminClinic`** — M2M admin↔clinic.
- **`Clinic`** (`clinics`): name, city, address, phone, active.
- **`Specialization`** — справочник.
- **`AgentSpecialization`** — M2M + active. **Инвариант: каждой `AgentSpecialization` соответствует `AgentRate`.**
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

**Не применена:** `backfill_agent_rates_01` — **нужно создать** (бэкфилл `AgentRate` для существующих `AgentSpecialization`).

## Что сделано (итерации 1–4)

### Backend auth
- `/auth/login` для всех (agent/admin/chef), `role` в JWT.
- `/auth/me` возвращает разное по роли.
- `/auth/register` создаёт `Agent(status='pending')`.
- Зависимости `get_current_agent`, `get_current_admin`, `get_current_chef`.

### Фильтрация по роли
- `GET /api/v1/clinics` — шеф: все, админ: свои, агент: свои, без токена: только активные.
- `GET /api/v1/agents` — шеф: все, админ: агенты своих клиник.
- `GET /api/v1/admins` — только шеф.

### Админские эндпоинты (есть)
- `GET/PUT/DELETE /api/v1/agents` (с учётом роли).
- `POST /api/v1/agents/{id}/approve` — pending → active + clinic_ids + specialization_ids + admin_id (для шефа).
- `POST /api/v1/agents/{id}/reject` — pending → rejected + decision_reason.
- `GET/POST/PUT/DELETE /api/v1/admins` — только шеф.
- `GET/POST/PUT /api/v1/clinics` — **`PUT /clinics/{id}` теперь только шеф** (админ клиники не может редактировать клинику).
- `GET/PUT /api/v1/clinics/{id}/specialties` — админ клиники — свои, шеф — все.
- `GET/PUT /api/v1/agents/{id}/rates` — ставки агента.
- `GET /api/v1/history` — шеф: все, админ: только свои действия (`actor_id=admin.id`).
- `GET/PUT /api/v1/admin/referrals` — **добавлено** (список новых направлений; шеф — все, админ — своих клиник).

### `crud.py`
- `set_agent_specializations` — **добавлено** (создаёт `AgentRate` при добавлении специализации, удаляет при удалении).
- `set_agent_rate` — upsert ставки.
- `get_agent_rates` — select.

### api_gateway (`api_gateway/app/main.py`)
- `app.mount("/static", StaticFiles(directory="app/templates/static"))` — **добавлено**.
- `GET /admin_panel` — отдаёт `admin_panel.html` (новый единый файл).
- `/portal-admin` и `/clinic-admin` — **пока рендерят старые** `Portal_Admin.html` / `Clinic_Admin.html` (переключение на `admin_panel.html` — в плане).

### Новый единый файл `admin_panel`
- `api_gateway/app/templates/admin_panel.html` — скелет (80 строк).
- `api_gateway/app/templates/static/admin_panel.css` — все стили.
- `api_gateway/app/templates/static/admin_panel.js` — вся логика, секции 1–10.
- **Роль определяется через `S.user.role`** (`isChef()`).
- У шефа: 6 разделов (Обзор, Новые направления, Администраторы, Агенты, Клиники, Отчёты).
- У админа: 5 разделов (без Администраторы).
- Иконки Font Awesome (`fa-house`, `fa-file-medical`, `fa-user-shield`, `fa-user-doctor`, `fa-hospital`, `fa-chart-bar`).
- Блок «Регистрация агентов» внизу раздела «Агенты» (pending-агенты).
- Блок «Вознаграждение агента» в профиле агента (табы «Вознаграждение / История агента»).
- «Новые направления» — таблица referrals со статусом `new`, модалка «Подтвердить / Отклонить».
- Профиль администратора — с Email рядом с телефоном.
- Валидация форм на фронте (`validateForm`, `data-label`, `type`, `minlength`, `min`/`max`).
- Ошибки Pydantic → на русском (`FIELD_RU`, `MSG_RU`).

### Баги, которые починили
- Цикл `render() → loadReferrals() → render()` — убран (`loadReferrals` пишет только в `refResults`, не вызывает `render`).
- `pending: requests` → `pending: referrals` (раздел «Заявки» был недоступен).
- Поиск в клиниках терял фокус — `requestAnimationFrame` + `setSelectionRange`.
- Клиники сортируются по `id`.
- Белый экран после сохранения клиники — `clinicId=null` перед `render`.
- Модалка «Новый администратор» — отключённые клиники скрыты, `autocomplete="off"` + `new-password` на полях.
- Галочка «Рассмотрение регистраций» — `fieldset.permission-box`, сохраняется в `permissions.reviewRegistrations`.

## Что НЕ работает / открытые вопросы (на 2026-11-04)

### 🔴 Срочно
1. **В профиле агента → «Вознаграждение» пусто.** `GET /agents/{id}/rates` возвращает `[]`. Причины:
   - В `crud.py` **нет** `set_agent_specializations` (или она не вызывается из `approve_agent_endpoint` / `update_agent_endpoint`).
   - В БД нет `AgentRate` для существующих `AgentSpecialization` (нужен бэкфилл).
   - **Проверить:** есть ли `crud.set_agent_specializations`; вызывается ли из `main.py`; SQL `SELECT COUNT(*) FROM agent_specializations;` vs `agent_rates`.
2. **Подсветка активного пункта меню пропала.** В `admin_panel.css` **нет** строки `.nav button:hover,.nav button.active{background:#28545d;color:white}` — добавить.

### 🟡 В плане
3. Переключить `/portal-admin` и `/clinic-admin` на `admin_panel.html` (сейчас рендерят старые файлы).
4. Миграция `backfill_agent_rates_01` — создать и применить.
5. История агента (таб «История агента») — **на бэке нет** `AgentRateHistory`, пока заглушка. Если нужно — отдельная задача.
6. Удаление агента админом клиники — сейчас разрешено (только своих). Если запретить — правка `delete_agent_endpoint`.

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
- `ReferralCreate.amount` — в `schemas.py` есть, в `main.py` используется.
- `crud.create_referral` — `commission_rate` может быть `None`.

## Тестирование
Пользователь тестирует сайт и присылает ошибки. Каждое сообщение — набор пунктов (1, 2, 3...). Задача: точечно чинить, не ломая остальное. Если непонятно — задавать уточняющие вопросы. Если правка затрагивает несколько файлов — присылать полные файлы или блоки с уникальными якорями для Ctrl+F.

## Что делать в первую очередь (следующая итерация)
1. Проверить `crud.set_agent_specializations` и вызов из `main.py` — починить «Вознаграждение».
2. Бэкфилл `AgentRate` для старых данных (SQL или миграция).
3. Вернуть подсветку меню в `admin_panel.css`.
4. После — переключить `/portal-admin` и `/clinic-admin` на `admin_panel.html`.
5. Дальше — по ошибкам от пользователя.
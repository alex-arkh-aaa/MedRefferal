# Medpoint — STATE (снимок на конец итерации 3)

## Проект
Платформа медицинских агентов. Backend: FastAPI + PostgreSQL + RabbitMQ + Redis, Docker Compose. Frontend: HTML+JS (без сборщика).

## Архитектура
- `api_gateway` (порт 80) — JWT, rate limiting, HTML-роуты, проксирование в `service_users`.
- `service_users` (порт 8000) — вся бизнес-логика: агенты, админы, пациенты, направления, клиники, ставки, отчёты, цели.
- `service_notify` (порт 8003) — отправка email через RabbitMQ (`email_queue`).
- `postgres` — БД `med_referral_db`.

## Роли (в JWT: `sub`, `user_id`, `full_name`, `role`)
- `agent` — агент (бывший «doctor»).
- `admin` — админ клиники.
- `chef` — шеф (один, `chef@medpoint.local`, пароль `portaladmin`). **Не логинится (422) — отложено.**

## Модели (`service_users/app/models.py`)
- **`Agent`** (`agents`) — бывший `Doctor`. Поля: email, password_hash, full_name, phone, date_of_birth, experience, education, about_myself, column_order (JSON), **status** (`pending/active/inactive/rejected`), **deleted_at**, **admin_id** (FK→Admins), created_at, updated_at. `is_active` удалён.
- **`Admin`** (`admins`) — email, password_hash, full_name, phone, **role** (`chef/admin`), active, permissions (JSON), deleted_at. Partial unique index на `role='chef'`.
- **`AdminClinic`** — M2M admin↔clinic.
- **`Clinic`** (`clinics`) — name, **city**, address, phone, **active**, created_at, updated_at. **`coordinates` удалён.**
- **`Specialization`** — справочник.
- **`AgentSpecialization`** — M2M + **`active`** (bool).
- **`AgentClinic`** — M2M agent↔clinic.
- **`AgentRate`** — agent_id, specialization_id, **mode** (`clinic/custom`), **custom_rate** (Numeric).
- **`ClinicSpecialty`** — clinic_id, specialization_id, **default_rate**, **active**.
- **`Patient`** — `agent_id` (было `doctor_id`), full_name, date_of_birth, phone, email, gender, info, status.
- **`Referral`** — `agent_id`, clinic_id, patient_id, specialization_id, **amount**, expected_visit_start/end, med_indications, special_wishes, **status** (`new/approved/rejected`), status_changed_at, **commission_rate**, commission_amount, **payout_status** (`unpaid/processing/paid`), **paid_at**, **payment_reference**, **specialty_name_at_confirmation**, created_at.
- **`Goal`** — agent_id, month, year, income_money, referrals.
- **`History`** — единая: **label**, **text**, **actor_type** (`agent/admin/chef/system`), **actor_id**, actor_name, created_at.
- **`EmailVerification`** — **email** (было `doctor_email`), code, expires_at, created_at.
- **`Registration`** — **удалена** (миграция `drop registrations`).

## Миграции (применены)
`a799a240a7e2_init` → `6e7f57f74f06_add_seed_data` → `eeb75508a0e2_education` → `7eef4b5fae5c_patient_status` → `af67ab719462_gender` → `eb3997ec001d_remove_email_unique` → `4e349b2b7f44_clinics_coordinates` → `a9c8667245f8_fix_bugs` → **`4e372c0c78b5_chef_and_admins`** (ручная: admins, admin_clinics, agent_clinics, agent_rates, clinic_specialties, переименование doctors→agents, doctor_id→agent_id, is_active→status, coordinates→city/phone, слияние history, email_verifications.doctor_email→email, сид шефа) → **`393ba10550f8_clinic_timestamps`** (ручная: только `clinics.created_at`, `clinics.updated_at`).

## Что сделано (итерации 1–3)
1. **Backend auth:** `role` в JWT, `/auth/login` для всех (agent/admin/chef), `get_current_agent`, `get_current_admin`, `get_current_chef`, `/auth/me` возвращает разное по роли. `/auth/register` создаёт `Agent(status='pending')`, `comment` → `Agent.about_myself`.
2. **`/auth/login`** при `status='pending'` → 403 «Аккаунт ожидает подтверждения»; `inactive`/`rejected` → 403.
3. **`ClinicResponse`** без `coordinates`, с `city/phone/active`. `GET /api/v1/clinics` работает.
4. **`ReferralCreate.amount`** (опционально), `ReferralUpdate.status` — паттерн `^(new|approved|rejected)$`. `ReferralResponse`/`ReferralDetailResponse` — `agent_id` (не `doctor_id`), `payout_status`, `paid_at`, `payment_reference`, `commission_rate`, `specialty_name_at_confirmation`.
5. **`PatientResponse`** — `agent_id` (не `doctor_id`).
6. **`crud.set_agent_specializations`** — сохраняет `active` у существующих.
7. **`crud.create_registration`, `approve_registration`, `reject_registration`, `get_registration`, `list_registrations`** — удалены.
8. **`api_gateway`:** `public_paths` + `/api/v1/auth/recover_account`; `proxy_request` корректно передаёт `Set-Cookie`; `X-User-Role` вместо `X-User-Roles`.
9. **Агентский фронт:** `referrals.html` (статусы `new/approved/rejected`, `payout_status`, `DEFAULT_ORDER` с `payout_status`, `updateStats`, фильтр); `dashboard.html` (`activity.text` вместо `info`); `create_referral.html` (поле `amount`, передача, сброс); `clinics.html` (без карты, `.clinic-phone`); `index.html` (модалка входа с выбором роли: агент — синяя, админ — тёмно-зелёная; «Подать заявку» в 2 шага: email→код→данные+пароль+комментарий; редирект по роли).
10. **`index.html`** шлёт: `POST /auth/send_code` {email} → `POST /auth/register` {email, password, full_name, phone, code, comment}.

## Что НЕ работает / отложено
- **Шеф не логинится (422)** — `POST /auth/login` с `chef@medpoint.local/portaladmin` возвращает 422. **Не разобрано.** Скорее всего, Pydantic `UserLogin` не принимает `chef@medpoint.local` (EmailStr?) или проблема в Gateway (body теряется). **Первое — проверить `curl` на `:8000` и `:80`, прислать тело 422.**
- **Type changes:** в БД `TIMESTAMP` (без tz), в `models.py` — `DateTime(timezone=True)`. Autogenerate будет предлагать. Отложено.
- **Индексы:** в БД `ix_doctors_specializations_id`, в `models.py` — `ix_agent_specializations_*`. Autogenerate будет предлагать. Отложено.
- **`referrals.is_paid`** — в БД есть, в `models.py` нет. Autogenerate предлагает `DROP`. Отложено — надо решить (удалять или нет).
- **Autogenerate нельзя** — пока БД и `models.py` не синхронизированы.
- **`AgentResponse` / `AgentListResponse`** — не созданы. Нужны для админского фронта.
- **Эндпоинты для админов** (итерация 4) — **не написаны**.

## Что дальше (итерация 4)
1. **Эндпоинты `main.py`:**
   - `GET /api/v1/agents` — список агентов (шеф — все, админ — своих клиник; фильтр по `status`).
   - `GET /api/v1/agents/{id}` — профиль агента.
   - `PUT /api/v1/agents/{id}` — редактировать (шеф — всё, админ — свои клиники; `status`, `clinic_ids`, `specialization_ids`, `admin_id`, `name`, `phone`, `email`, `about_myself`).
   - `POST /api/v1/agents/{id}/approve` — одобрить `pending` → `active` + назначить `clinic_ids`, `specialization_ids`, `admin_id`.
   - `POST /api/v1/agents/{id}/reject` — `status='rejected'` + `decision_reason` (куда? `about_myself`? — решить).
   - `DELETE /api/v1/agents/{id}` — soft delete.
   - `GET /api/v1/admins` (есть), `POST /admins`, `PUT /admins/{id}`, `DELETE /admins/{id}`.
   - `GET /api/v1/clinics` (есть, но для админа — с фильтром по его клиникам; для шефа — все).
   - `POST /api/v1/clinics`, `PUT /api/v1/clinics/{id}`.
   - `GET /api/v1/clinics/{id}/specialties`, `PUT /api/v1/clinics/{id}/specialties/{spec_id}` (upsert: `default_rate`, `active`).
   - `GET /api/v1/agents/{id}/rates`, `PUT /api/v1/agents/{id}/rates/{spec_id}` (upsert: `mode`, `custom_rate`).
   - `GET /api/v1/agents/{id}/clinics`, `PUT /api/v1/agents/{id}/clinics` (`clinic_ids`).
   - `GET /api/v1/agents/{id}/specializations`, `PUT /api/v1/agents/{id}/specializations` (`specialization_ids`).
2. **`schemas.py`:** `AgentResponse`, `AgentListResponse`, `AgentUpdate`, `AgentApprove`, `AgentReject`, `ClinicCreate/Update`, `ClinicSpecialtyResponse/Update`, `AgentRateResponse/Update`.
3. **Админский фронт:** переписать `Medpoint_Clinic_Admin.html` и `Medpoint_Portal_Admin.html` с localStorage → `fetch` к API. Стили — **сохранить** (тёмно-зелёные, `.btn`, `.panel`, `.drawer`, `.pill`).
4. **Шеф** — починить 422 (после итерации 4 или параллельно).

## Правила работы
- **Backend — источник правды.** Фронт подстраивается под бэкенд.
- **Если правок > 3 и файл небольшой — присылать целиком.** Иначе — блоками с маркерами.
- **Стили не менять.** Если нужно — отдельным CSS-блоком.
- **Autogenerate** — только для добавления; переименования/миграции данных — ручные миграции.
- **`add_history(db, actor_type, actor_id, label, text, actor_name=None)`** — новая сигнатура.
- **`get_current_agent`, `get_current_admin`, `get_current_chef`** — зависимости.
- **`crud.py`** — `get_agent_by_email` = алиас `get_user_by_email`; `update_agent` = алиас `update_doctor`.
- **`Agent.status`** — не `is_active`.
- **`Agent.about_myself`** — используется для комментария при регистрации.

## Известные баги (не критичные)
- `crud.get_patient_by_email` — при `patient_id=None` работает (`Patient.id != None` всегда true).
- `crud.get_user_by_email_including_inactive` — то же, что `get_user_by_email` (не фильтрует).
- `ReferralCreate.amount` — в `schemas.py` есть, в `main.py` используется `data.amount` (ок).
- `crud.create_referral` — `commission_rate` может быть `None` (если нет `ClinicSpecialty` или `AgentRate`).
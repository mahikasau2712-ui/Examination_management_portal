# Examination Management Portal (EMP)

A Flask + SQLite web application for administrators, examiners, and students. The database is created from SQLAlchemy models when the app starts. Bootstrap supplies the responsive UI; core features use server-rendered forms and do not depend on JavaScript.

## Run locally

1. Use Python 3.10 or newer.
2. Create and activate a virtual environment, then install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Start the application:

   ```powershell
   py run.py
   ```

4. Open `http://127.0.0.1:5000`.

The first launch creates `instance/emp.sqlite3` and a pre-existing admin account. Defaults for local demonstration are `admin@emp.local` / `Admin@123`. Set `EMP_ADMIN_EMAIL`, `EMP_ADMIN_PASSWORD`, and `SECRET_KEY` environment variables before the first launch to customize them. Change the demo password for any shared deployment.

## Features

- Admin: overview counts, course and examination management, configurable slot and booking periods, rubric setup, examiner approval and activation, slot overview and examiner reassignment, booking search and rescheduling, record search, and result publication.
- Examiner: self-registration with approval, assigned exam slots, slot creation/edit/removal during the open period, their own booked students, rubric-based marks and remarks.
- Student: self-registration, filtered examination catalogue, slot booking/cancellation, booking history, published results, feedback, and profile editing.
- Server checks enforce role access, capacity, duplicate booking prevention, examiner ownership, booking windows and result visibility.

## Architecture map (comments are also placed at the relevant code)

- **MVC:** `app/routes.py` contains controllers, `app/models.py` the data model, and `app/templates/` the views. Routes coordinate validation, model operations and template responses.
- **ORM / database schema:** `app/models.py` defines all SQLAlchemy models and table relationships. `app/__init__.py` calls `db.create_all()` to create SQLite tables programmatically.
- **Request schemas:** `app/schemas.py` contains lightweight validation helpers for form input. These are validation schemas, distinct from the SQLAlchemy database models.
- **Jinja:** every file in `app/templates/` is a Jinja view (extends/includes, loops, conditionals and `url_for`). `base.html` is the shared layout.
- **Role routes:** `app/routes.py` groups admin, examiner and student controllers into Flask blueprints.

## Data model

`User` (admin/examiner/student) → `Course` → `Examination` → `Rubric`; `Examination` → `ExamSlot` ← `Booking` → student `User`; `Booking` → `RubricScore` → `Rubric`. Cancelled bookings remain in the database as history.

Before deleting an examination in a real deployment, review its historical records: cascading deletion is currently configured for its slots and associated bookings to support straightforward exam removal in this single-user local demo.

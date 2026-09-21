# Progress Tracker

A Django study tracker with a cyberpunk dashboard. Create tasks, press **START** to run a timed study session with a live progress bar, track breaks, review your history, and see how you rank against other users. Sign in with a username and password or with Google (OAuth).

It is built as a learning/portfolio project: plain Django templates, vanilla JavaScript, no frontend framework.

## Features

- Create tasks with a title, description, duration (minutes), break length, optional subject and privacy setting
- Start/stop a timer; the server records `started_at` / `completed_at` and is the source of truth
- Live progress bar with percentage, elapsed and remaining time (never exceeds 100%)
- One running timer per user, enforced in code **and** by a database constraint
- Break countdown after each session
- Study history for Today / This week / This month / This year / All time
- Study time grouped by subject (Today / Last 7 days / Last 30 days / Last year / All time)
- Rankings by study hours (overall, today, week, month, year), shown under each person's chosen username
- Required "choose your username" pop-up for people who sign up with Google
- Public progress pages per user (private tasks stay private)
- "Online now" and "studying" counters on the dashboard
- Live study room (`/live/`): everyone's running progress bars, updating as people start and stop
- Automatic reward badges plus rewards you attach yourself
- Google OAuth via `django-allauth`
- Responsive layout: 4 → 2 → 1 task columns, mobile navigation
- Django admin for users, tasks and rewards
- Ready to deploy on Vercel with a Neon PostgreSQL database
- Automated tests (models, auth, permissions, timer, rankings, privacy, presence, live room)

## Technologies

Python · Django · django-allauth · OAuth 2.0 (Google) · SQLite (default) · PostgreSQL / Neon (optional) · Vercel · HTML · CSS · JavaScript (vanilla)

## Project structure

```text
progress_tracker/
├── manage.py
├── requirements.txt
├── .env.example          # placeholders only - copy to .env
├── .gitignore
├── .python-version       # Python version for Vercel
├── config/               # project settings, root URLs, ASGI/WSGI
├── tracker/              # the app
│   ├── models.py         # Task, Reward
│   ├── services.py       # timer rules, rewards, stats, rankings, presence
│   ├── middleware.py     # PresenceMiddleware, UsernameSetupMiddleware
│   ├── adapters.py       # django-allauth hook: placeholder username for Google signups
│   ├── context_processors.py
│   ├── views.py          # thin views
│   ├── forms.py
│   ├── admin.py
│   ├── urls.py
│   ├── tests.py
│   ├── templatetags/tracker_extras.py
│   └── migrations/
├── templates/
│   ├── base.html
│   ├── account/          # login.html, signup.html (django-allauth overrides)
│   └── tracker/          # dashboard, tasks, history, rankings, ...
└── static/
    ├── css/style.css
    └── js/               # progress.js, timer.js, main.js, presence.js, live.js, username.js
```

> The spec suggested `templates/registration/`. Because sign-in is handled by django-allauth, the login and signup pages live in `templates/account/` (the path allauth looks for).

## Installation

```bash
git clone <your-repo-url> progress_tracker
cd progress_tracker
python -m venv venv
```

Activate the virtual environment:

```bash
# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

| Package | Why it is needed |
| --- | --- |
| `Django` | the framework |
| `django-allauth[socialaccount]` | login/signup and Google OAuth |
| `python-dotenv` | loads `.env` into environment variables |
| `dj-database-url` | turns `DATABASE_URL` into Django's `DATABASES` setting |
| `psycopg[binary]` | PostgreSQL driver (only used if `DATABASE_URL` points to PostgreSQL) |

## Environment variables

### Why `.env`?

Settings such as `SECRET_KEY` and the Google client secret differ between your laptop and a real server, and some of them are credentials. Keeping them in environment variables (loaded from a `.env` file locally) keeps them out of the source code.

### Why secrets must never be committed

Anything pushed to GitHub can be copied, and Git keeps history: deleting a secret in a later commit does **not** remove it from earlier commits. Bots scan public repositories for leaked keys within minutes. A leaked `SECRET_KEY` lets attackers forge sessions; a leaked Google client secret lets them impersonate your app. If it happens, rotate the secret immediately.

### Create your `.env`

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

Generate a real secret key and paste it after `SECRET_KEY=`:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

| Variable | Meaning |
| --- | --- |
| `SECRET_KEY` | required; Django's cryptographic key |
| `DEBUG` | `True` for local development, `False` in production |
| `ALLOWED_HOSTS` | comma-separated hosts, default `localhost,127.0.0.1` |
| `TIME_ZONE` | default `Asia/Manila`. "Today" and "this week" are calculated in this zone |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth credentials. Leave blank to hide the Google button |
| `DATABASE_URL` | blank = SQLite; otherwise a database URL (see below) |
| `DB_CONN_MAX_AGE` | seconds to keep DB connections open; default `0` (right for serverless) |
| `BEHIND_PROXY` | trust `X-Forwarded-Proto`; automatic on Vercel, set `True` on other proxies |

## Google OAuth setup

1. Open the [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Configure the consent screen: **APIs & Services → OAuth consent screen** (newer console: **Google Auth Platform**). Choose *External*, set an app name and your email. While the app is in *Testing*, add your Google account under **Test users**.
3. Create credentials: **APIs & Services → Credentials → Create credentials → OAuth client ID**, application type **Web application**.
4. Under **Authorized JavaScript origins** add:
   - `http://127.0.0.1:8000`
   - `http://localhost:8000`
5. Under **Authorized redirect URIs** add exactly:
   - `http://127.0.0.1:8000/accounts/google/login/callback/`
   - `http://localhost:8000/accounts/google/login/callback/`

   The URI must match character for character, including the trailing slash. For a deployed site use `https://your-domain/accounts/google/login/callback/`.
6. Copy the **Client ID** and **Client secret** into your `.env`:

   ```env
   GOOGLE_CLIENT_ID=1234567890-abc.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-...
   ```

7. Restart the server. A "Continue with Google" button now appears on the login and signup pages.

The credentials are read in `config/settings.py` and passed to django-allauth as the provider's `APP` setting, so no `SocialApp` needs to be created in the admin.

## Database setup

### SQLite (default)

Leave `DATABASE_URL=` blank. Django creates `db.sqlite3` in the project folder.

### PostgreSQL

Create a database and user (in `psql`):

```sql
CREATE DATABASE progress_tracker;
CREATE USER tracker_user WITH PASSWORD 'choose-a-password';
GRANT ALL PRIVILEGES ON DATABASE progress_tracker TO tracker_user;
\c progress_tracker
GRANT ALL ON SCHEMA public TO tracker_user;
```

Then set in `.env`:

```env
DATABASE_URL=postgres://tracker_user:choose-a-password@localhost:5432/progress_tracker
```

Special characters in the password must be URL-encoded (`@` becomes `%40`). To switch back to SQLite, blank the variable again. The data does not move between databases automatically.

## Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

The migrations for `tracker` are already included.

## Create a superuser

```bash
python manage.py createsuperuser
```

The admin is at `http://127.0.0.1:8000/admin/`.

## Run the server

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. Use the same host (`127.0.0.1` or `localhost`) that you registered with Google.

## Run the tests

```bash
python manage.py test
```

## Static files

CSS and JavaScript live in `static/` and are loaded with `{% static %}`. With `DEBUG=True`, `runserver` serves them automatically. On Vercel nothing is needed: because `STATIC_ROOT` is set, Vercel runs `collectstatic` during the build and serves the files from its CDN. On other hosts run `python manage.py collectstatic` and serve `staticfiles/` with your web server or WhiteNoise.

## GitHub

```bash
git init
git status            # check that .env and db.sqlite3 are NOT listed
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

**DO NOT COMMIT `.env`.** The `.gitignore` already excludes `.env`, `db.sqlite3`, `venv/`, `__pycache__/` and `staticfiles/`, while `.env.example` (placeholders only) is allowed. If `git status` ever shows `.env`, stop and fix `.gitignore` first. If you already pushed a secret, rotate it (new `SECRET_KEY`, new Google client secret).

---

## Deploy to Vercel with Neon

Vercel detects Django by finding `manage.py`, reads `WSGI_APPLICATION` from `config/settings.py`, runs `collectstatic` for you and serves static files from its CDN. No `vercel.json` is required. Your app runs as a serverless function, so it cannot use SQLite; the database is Neon (PostgreSQL).

1. **Push the project to GitHub** (see the GitHub section; `.env` must not be in the repo).
2. **Import it in Vercel:** *Add New → Project*, pick the repository. Vercel should recognise it as Django.
3. **Add the database:** in the Vercel project open *Storage* (or *Integrations*) and add **Neon**. Vercel then sets `DATABASE_URL` for you (a pooled connection string). It usually also sets a non-pooled one such as `DATABASE_URL_UNPOOLED`; check the exact names under *Settings → Environment Variables*.
4. **Set environment variables** (Vercel replaces your local `.env`, which is never uploaded). Set these *before* the first deploy, because the build imports your settings:

   | Variable | Value |
   | --- | --- |
   | `SECRET_KEY` | a **new** random key (not the one from your laptop) |
   | `DEBUG` | `False` |
   | `TIME_ZONE` | `Asia/Manila` (or yours) |
   | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | from Google Cloud Console |
   | `ALLOWED_HOSTS` | only needed for a custom domain, e.g. `example.com` (`.vercel.app` is added automatically) |
   | `CSRF_TRUSTED_ORIGINS` | custom domain only, e.g. `https://example.com` |

5. **Deploy.** Vercel installs `requirements.txt`, collects static files and publishes the site.
6. **Create the tables.** Vercel does not run migrations. Run them from your computer against Neon, using the *non-pooled* connection string, for that one command only:

   ```powershell
   # Windows PowerShell
   $env:DATABASE_URL = "postgres://...paste the unpooled string..."
   python manage.py migrate
   python manage.py createsuperuser
   Remove-Item Env:DATABASE_URL
   ```

   ```bash
   # macOS / Linux
   DATABASE_URL="postgres://..." python manage.py migrate
   ```

   (In Windows `cmd` use `set DATABASE_URL=...` and later `set DATABASE_URL=`.) Do not save the production URL in your local `.env`. Repeat `migrate` whenever you add a migration.
7. **Update Google OAuth:** in Google Cloud Console add the authorized origin `https://YOUR-PROJECT.vercel.app` and the redirect URI `https://YOUR-PROJECT.vercel.app/accounts/google/login/callback/`. Preview deployments get a different URL each time, so Google login works reliably only on your production or custom domain.
8. **Check it:** sign up, create a task, run a timer, and open `/live/` in a second browser.

Notes:
- The settings switch to serverless-friendly values automatically when `VERCEL` is set: `.vercel.app` hosts, trusted HTTPS origins, and `SECURE_PROXY_SSL_HEADER` (without it Google login would build `http://` URLs and fail).
- Database connections are not kept open (`DB_CONN_MAX_AGE=0`) and server-side cursors are disabled, which is what Neon's pooler expects.
- Sessions are stored in the database, so logins work across serverless instances.
- Neon's free tier suspends an idle database. The online counter and live room query the database regularly while someone has a tab open (never from hidden tabs), so a busy site keeps it awake and uses your monthly compute allowance.

---

## How it works

### Timer and progress bar

- Creating a task only inserts a row. Nothing runs.
- **START** (`POST /tasks/<id>/start/`) stores `started_at = now()` on the server, after checking that the task is yours, unstarted, and that you have no other running task.
- The dashboard renders `started_at`, the duration, and the server's current time as epoch milliseconds in `data-*` attributes. `timer.js` measures the difference between the server clock and the browser clock once, then updates the bar every 250 ms with `elapsed / duration`, clamped to 0-100%.
- When the bar hits 100%, `timer.js` sends a `POST` to the stop endpoint. If the browser is closed, the server closes expired sessions the next time anyone loads a page (`services.finalize_expired`).
- **STOP** (`POST /tasks/<id>/stop/`) records `completed_at = min(now, started_at + duration)` and `studied_seconds = completed_at - started_at`. The cap means an open tab can never inflate your study time, and refreshing or editing JavaScript cannot change what is recorded.

Task states are derived from the timestamps: `pending` (no `started_at`), `running` (started, not completed), `completed` (full duration studied) and `stopped` (ended early).

### Break representation

`break_duration` is the break length in minutes chosen when the task is created (default 5). The break window is *derived*, not stored: it runs from `completed_at` to `completed_at + break_duration`. The dashboard shows a countdown while it lasts; you may start the next task at any time. Storing only the plan plus real timestamps avoids ambiguous, duplicated data.

### Choosing a username after Google signup

- When someone signs up with Google, `TrackerSocialAccountAdapter` (`tracker/adapters.py`) replaces the username django-allauth would have built from their name or Gmail address with a throw-away placeholder such as `player_3fa9c1d2`, and creates a `Profile` with `needs_username = True`.
- allauth logs them in and sends them to the dashboard, where a fixed-position pop-up asks for a username. The rest of the page is made inert, Escape does nothing, and there is only a "Log out instead" alternative.
- `UsernameSetupMiddleware` enforces this on the server too: until a name is chosen, every page except the dashboard, the save endpoint, the heartbeat and the login/logout pages redirects to the dashboard.
- `POST /profile/username/` validates the name: 3-20 characters (letters, numbers, `_ . -`), not reserved (`admin`, `root`, ...), and unique **ignoring case**. It only works while a name is still needed, so usernames can't be changed later.
- The chosen name becomes the account's real `username`, so rankings, the live room and `/users/<username>/progress/` all use it. People who have not chosen yet are left out of the rankings.
- Password signups already type a username in the signup form, so they never see the pop-up. The same goes for Google accounts created before this feature existed; to make one of them choose again, add a **Profile** for that user in the admin and tick "needs username".

### Online count and live study room

- **Who is online:** `PresenceMiddleware` runs on every request. For a logged-in user it stores `last_seen` in the `Presence` table, at most once every 45 seconds (the time of the last write is kept in the session, so most requests cost no extra query). "Online" means `last_seen` within the last 2 minutes.
- **Heartbeat:** `presence.js` sends `POST /presence/ping/` every 30 seconds while the tab is visible, so someone who only watches a page stays online. The reply carries the current `online` and `studying` counts, which update the dashboard strip.
- **Studying** is the number of running timers.
- **Live room (`/live/`):** `live.js` polls `GET /live/data/` every 5 seconds to learn *who* has a running timer (usernames, titles, start time, duration). Between polls a 250 ms ticker computes each bar from the server's start time, so bars move smoothly without a request per second. Polling pauses while the tab is hidden.
- Private tasks appear as "Private session"; the JSON endpoints answer `401` (not a login redirect) for logged-out requests; user text is written into the page with `textContent`, never `innerHTML`.
- Nothing is instant: a new timer can take up to about 5 seconds to appear, and someone who closes the tab drops out of the online count within about 2 minutes.

### Extra fields beyond the spec

- `studied_seconds`: the measured result of a session. Stored so rankings can use a plain `Sum()` and stay accurate for stopped-early sessions.
- `category`: optional subject used by the "study time by subject" page (blank falls back to the task title).
- `is_public`: privacy flag; private titles appear as "Private session" on your public page.

### Rankings

Rankings sum `studied_seconds` of **completed** sessions per user, filtered by `completed_at` inside the period. A session belongs to the day it ended. Period boundaries are computed as timezone-aware midnights in `TIME_ZONE` (weeks start on Monday). Ties share a rank. Rankings show only username, hours and task count, never task titles. See `services.leaderboard`.

### Security

- Every view requires login; state changes are `POST` only with CSRF protection (`fetch` sends the `X-CSRFToken` header).
- Tasks are always looked up with `get_object_or_404(Task, pk=pk, user=request.user)`, so another user's ID returns 404 (no information leak). The reward form only offers your own tasks.
- The task owner is set on the server; it is never read from form data.
- Public pages expose username and statistics only: no email, no private task titles or descriptions.
- Secrets come from environment variables; secure cookies are on by default when `DEBUG=False`.
- OAuth login starts with a CSRF-protected `POST` (`SOCIALACCOUNT_LOGIN_ON_GET = False`).

---

# What I Should Learn Next

Work through these in order. Each line says why it matters *in this project*.

## Beginner

- **Django project vs app**: `config/` holds settings and root URLs, `tracker/` holds the features.
- **URLs and views**: `tracker/urls.py` maps paths like `tasks/<int:pk>/start/` to functions in `views.py`.
- **Templates and inheritance**: every page extends `base.html`; `{% url %}` builds links from URL names.
- **Static files**: how `style.css` and the scripts are found and served.
- **Forms and ModelForms**: `TaskForm` validates title and duration for you.
- **Django ORM and migrations**: models become tables; `makemigrations`/`migrate` keep them in sync.
- **Authentication basics**: users, sessions, `@login_required`.

## Intermediate

- **ForeignKey and `related_name`**: `Task.user` with `related_name="tasks"` gives `user.tasks`; `Reward.task` gives `task.rewards`.
- **`select_related` / `prefetch_related`**: the task cards prefetch rewards to avoid one query per card.
- **QuerySets and filtering by date**: history and rankings filter `completed_at` by ranges.
- **`annotate`, `aggregate`, `Count`, `Sum`, `Avg`**: rankings, dashboard statistics and the subject breakdown.
- **Timezone-aware datetimes**: "today" must mean today in your timezone, not UTC.
- **Database constraints**: `UniqueConstraint(condition=...)` guarantees one running timer per user.
- **Function decorators**: `@login_required`, `@require_POST` protect the timer endpoints.
- **Permissions and object ownership**: why the queries include `user=request.user`.
- **CSRF**: why every state-changing form has `{% csrf_token %}` and why `fetch` sends a header.
- **Middleware**: `PresenceMiddleware` wraps every request; read how `MIDDLEWARE` order matters (it needs sessions and authentication first).
- **Sessions as a cache**: the online counter stores its last-write time in the session to avoid extra queries.
- **django-allauth adapters**: `populate_user` and `save_user` are the hooks used to change how social signups create accounts.
- **Modal dialog accessibility**: `role="dialog"`, `aria-modal`, `inert` and a focus trap in `username.js`.
- **Case-insensitive uniqueness**: why the form checks `username__iexact` (the database column is case-sensitive).
- **Class-based views**: not used here on purpose. Rewrite a view as a `ListView` or `CreateView` to learn them.
- **Testing**: `tracker/tests.py` shows how to test permissions, timers and rankings.

## JavaScript

- **DOM and events**: `main.js` toggles the menu and expands cards.
- **`setInterval` and `Date`**: `timer.js` ticks every 250 ms and compares timestamps.
- **Fetch API and JSON**: the auto-stop request and its JSON response.
- **Frontend/backend communication**: the server renders the truth, JavaScript only displays it.
- **Asynchronous JavaScript (Promises)**: the `fetch(...).then(...)` chain.
- **Polling vs. push (heartbeats, Server-Sent Events, WebSockets)**: `live.js` polls; learn what the alternatives would change.
- **Page Visibility API**: `document.hidden` stops polling in background tabs.
- **XSS and `textContent`**: why `live.js` never puts usernames or titles into `innerHTML`.

## Frontend

- **CSS variables**: the colour palette and fonts are defined once in `:root`.
- **Flexbox and CSS Grid**: the navigation and the 4/2/1 column task grid.
- **Media queries and responsive design**: the mobile menu and column changes.
- **Transitions, transforms and animations**: bar fill, card hover, expandable details.
- **Accessibility**: `aria-expanded`, `role="progressbar"`, focus outlines, reduced-motion support.

## Authentication

- **Sessions and cookies**: how Django remembers you are logged in.
- **OAuth 2.0 and Google sign-in**: the redirect flow behind "Continue with Google".
- **django-allauth**: settings, middleware and provider configuration.
- **Client ID, client secret and redirect URIs**: why the callback URL must match exactly.
- **Environment variables**: how secrets reach `settings.py` without being in Git.

## Database

- **SQL basics and primary/foreign keys**: what the ORM generates for you.
- **`GROUP BY` and aggregation**: what `.values().annotate(Sum())` becomes.
- **Indexes**: `Index(fields=["user", "completed_at"])` speeds up the history and ranking filters.
- **Normalisation**: why `Reward` is a separate table instead of a text field on `Task`.
- **PostgreSQL**: a production-grade database and the target of `DATABASE_URL`.

## Deployment

- **Git and GitHub**: version history, `.gitignore`, never committing `.env`.
- **Production Django settings**: `DEBUG=False`, `ALLOWED_HOSTS`, secure cookies.
- **HTTPS and security headers**: required for secure cookies and OAuth callbacks.
- **Static/media storage**: `collectstatic`, WhiteNoise or a CDN.
- **PostgreSQL in production**: managed databases and backups.
- **Serverless functions**: why SQLite, local files and in-memory caches don't work on Vercel, and why connections are short-lived.
- **Connection pooling (Neon's pooler)**: why `DB_CONN_MAX_AGE=0` and `disable_server_side_cursors` are set.
- **Reverse proxies and `X-Forwarded-Proto`**: why `SECURE_PROXY_SSL_HEADER` is needed behind Vercel.
- **Docker**: package the app and its dependencies to run anywhere.
- **CI/CD**: run `python manage.py test` automatically on every push.
- **AWS (or another cloud)**: where the container and database eventually run.

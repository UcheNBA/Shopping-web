# Shopping Web (Flask)

Simple minimal shopping website scaffold using Flask.

Requirements
- Python 3.8+
- See `requirements.txt` (Flask)

Run locally (PowerShell):

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt; python "app.py"
```

App runs on `http://localhost:5000`.

## Cloudinary configuration

The app reads `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and
`CLOUDINARY_API_SECRET` from environment variables. For deployment, configure
these in your hosting provider's environment settings. Never commit `.env` or
put the API secret in browser JavaScript.

`.env.example` lists the variable names. Set `DATABASE_URL` to your PostgreSQL
connection URL to use persistent PostgreSQL storage; without it, the app uses
local SQLite. Copy `.env.example` to `.env` for local development.

This is a demo scaffold: replace the `secret_key`, add persistent storage, and integrate payment for production.

## Admin access

The app does not create a default admin account. Admin passwords are stored as
hashes in the database. To create or reset an admin on Render Free, add
`ADMIN_BOOTSTRAP_USERNAME` and `ADMIN_BOOTSTRAP_PASSWORD` in the service's
Environment settings. Use a password with at least 12 characters and keep both
variables configured: the app applies them on startup, which restores the admin
after a restart or redeploy. Change the password by updating the Render
environment variable and redeploying. Never commit the password to GitHub.

Render Free filesystems are ephemeral. Configure `DATABASE_URL` with the
PostgreSQL database's internal URL in the Render service's Environment settings
so accounts, products, carts, and orders persist across restarts and deploys.
Existing data in a local SQLite database is not copied automatically.
Users whose accounts were created before PostgreSQL is configured will need to
register again unless their existing database is migrated separately. Logging
out only clears the login session; it does not delete the account or saved cart.

Create or update admin user via Flask CLI

Set the `FLASK_APP` env var and run `flask create-admin`:

Windows PowerShell example:
```powershell
$env:FLASK_APP='app.py'
flask create-admin myadmin s3cret
```

This updates the admin user's password or creates a new admin user in `data.db`.

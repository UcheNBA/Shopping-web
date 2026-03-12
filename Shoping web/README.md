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

This is a demo scaffold: replace the `secret_key`, add persistent storage, and integrate payment for production.

Admin
- Default admin username: `admin`
- Default admin password: `adminpass`

You can override credentials by setting environment variables before running the app:

Windows PowerShell example:
```powershell
$env:SHOP_ADMIN_USER = 'myadmin'; $env:SHOP_ADMIN_PASS = 's3cret'; python .\app.py
```

Be sure to change the default credentials before exposing the app publicly.

Create or update admin user via Flask CLI

Set the `FLASK_APP` env var and run `flask create-admin`:

Windows PowerShell example:
```powershell
$env:FLASK_APP='app.py'
flask create-admin myadmin s3cret
```

This updates the admin user's password or creates a new admin user in `data.db`.

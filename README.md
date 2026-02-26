# Polymath's Curse API

## Create & setup envirnment

```bash
python -m venv .venv
cd .venv/Scripts
activate
pip install --upgrade pip
```

## Install dependencies
```bash
cd ../..
pip install -r requirements.txt
```

## Make env file
### first create google client 
- Google Cloud Console. New Project.
- SIdebar. APIs & Services > OAuth consent screen. Choose External.
- Create Credentials. choose OAuth client ID. choose Application type = Web application
- Add URI for Authorized JavaScript origins aka where your frontend runs.
- For local dev (typical Vite): http://127.0.0.1:5173 , For production later: https://yourdomain.com

Youll get client id, and secret. Need only the client id for the env file.

### (Optional) generate a_long_random_string
python -c "import secrets; print(secrets.token_urlsafe(32))"

### An example env file
```conf
ENV=local
DATABASE_URL=postgresql+psycopg://app:app@localhost:5432/polymath
JWT_SECRET=a_long_random_string
JWT_ACCESS_TTL_MIN=15
JWT_REFRESH_TTL_DAYS=30
GOOGLE_CLIENT_ID=your_google_oauth_client_id.apps.googleusercontent.com
```

## Run migrations
```bash
alembic upgrade head
```

## Run server
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
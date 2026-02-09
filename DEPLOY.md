# Deploying Panchanga on Coolify

This project is set up for deployment on [Coolify](https://coolify.io) using a Dockerfile.

## Prerequisites

- Code pushed to a Git repository (GitHub, GitLab, etc.)
- A Coolify instance with access to that repository

## Steps in Coolify

1. **New resource** → **Application** → **Git Repository**
2. Connect your Git provider and select the **Panchanga** repository.
3. **Build pack**: Choose **Dockerfile** (not Nixpacks).
4. **Branch**: `main` or your production branch.
5. **Base directory**: Leave as `/` (root).
6. **Port**: Set to **5000** (Coolify may default to 3000; this app listens on 5000 unless `PORT` is set).
7. **Environment variables** (optional): Add any `KEY=value` you need at runtime.
8. Click **Deploy**.

## Port note

The container runs:

```bash
gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120 api:app
```

- Default port is **5000**. In Coolify’s **Network** / **Ports** section, set the application port to **5000** so routing matches.
- If Coolify injects a `PORT` env var, the app will use that instead.

## Local Docker build (optional)

```bash
docker build -t panchanga .
docker run -p 5000:5000 panchanga
```

Then open `http://localhost:5000`.

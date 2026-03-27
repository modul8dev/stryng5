# Django Social Media App

## Development Setup

### Prerequisites
- Python 3.14+
- Node.js 22+

### Install dependencies
```bash
pip install -r requirements.txt
npm install
```

### Run database migrations
```bash
cd webapp
python manage.py migrate
```

### Start development server
In two terminals:

```bash
# Terminal 1 — Tailwind CSS watcher
npm run watch:css

# Terminal 2 — Django dev server
cd webapp
python manage.py runserver
```

---

## Deployment with Docker (mounted repo)

The app is served by **Gunicorn** on port **8100** with **WhiteNoise** handling static files.

### Build the image

```bash
docker build -f .devcontainer/Dockerfile -t webapp .
```

### Run with the repo mounted from the host

```bash
docker run --rm -it -d \
  -p 8100:8100 \
  -v "$(pwd)":/workspace \
  --env-file .env \
  --name stryng_new_app \
  --network stryng \
  webapp
```

The `start.sh` script runs automatically and will:
1. Install Python and Node.js dependencies
2. Build the Tailwind CSS bundle
3. Apply database migrations
4. Collect static files
5. Start Gunicorn on `0.0.0.0:8100`

### Environment variables

Create a `.env` file in the repo root (copy from `.env.example` if present):

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key (required in production) |
| `DEBUG` | Set to `False` for production |
| `DATABASE_URL` | Database connection string (optional; defaults to SQLite) |

### Manual startup (without Docker)

```bash
./start.sh
```




server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name app.uat.stryng.io;

    ssl_certificate     /root/ssl/cert.pem;
    ssl_certificate_key /root/ssl/key.pem;

    client_max_body_size 100M;

    location / {
        proxy_pass http://stryng_app:8001;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_read_timeout 300s;
        proxy_send_timeout 300s;

        error_page 502 503 504 /index.html;
    }

    location = /index.html {
        root /etc/nginx/html/maintenance;
    }

    location = /under_maintenance.png {
        alias /etc/nginx/html/maintenance/under_maintenance.png;
    }

    location /admin {
        return 404;
    }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name new.uat.stryng.io;

    ssl_certificate     /root/ssl/cert.pem;
    ssl_certificate_key /root/ssl/key.pem;

    client_max_body_size 100M;

    location / {
        proxy_pass http://stryng_new_app:8100;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        proxy_read_timeout 300s;
        proxy_send_timeout 300s;

        error_page 502 503 504 /index.html;
    }

    location = /index.html {
        root /etc/nginx/html/maintenance;
    }

    location = /under_maintenance.png {
        alias /etc/nginx/html/maintenance/under_maintenance.png;
    }

    location /admin {
        return 404;
    }
}

server {
    listen 80;
    listen [::]:80;
    server_name app.uat.stryng.io new.uat.stryng.io;
    return 301 https://$host$request_uri;
}
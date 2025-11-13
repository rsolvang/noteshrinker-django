# Podman/RedHat Deployment Guide

This guide covers deploying Noteshrinker-Django on Red Hat Enterprise Linux (RHEL), Fedora, CentOS Stream, and other RedHat-based distributions using Podman.

## Table of Contents
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Development Setup](#development-setup)
- [Production Deployment](#production-deployment)
- [Rootless vs Rootful](#rootless-vs-rootful)
- [SELinux Considerations](#selinux-considerations)
- [Systemd Integration](#systemd-integration)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements
- **OS**: RHEL 8/9, Fedora 37+, CentOS Stream 8/9
- **Python**: 3.11+ (available via RHEL AppStream or Fedora repos)
- **Podman**: 4.0+ (built-in compose support)
- **podman-compose**: Alternative to built-in compose (optional)

### Install Podman

#### RHEL 8/9
```bash
# Enable required repositories
sudo subscription-manager repos --enable codeready-builder-for-rhel-9-$(arch)-rpms

# Install Podman
sudo dnf install -y podman podman-compose

# Verify installation
podman --version
```

#### Fedora
```bash
# Install Podman (usually pre-installed)
sudo dnf install -y podman podman-compose

# Verify installation
podman --version
```

#### CentOS Stream
```bash
# Install Podman
sudo dnf install -y podman

# Install podman-compose from EPEL
sudo dnf install -y epel-release
sudo dnf install -y podman-compose
```

---

## Installation

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/noteshrinker-django.git
cd noteshrinker-django
```

### 2. Configure Environment
```bash
# Copy environment template
cp .env.example .env

# Edit environment variables (for production, set proper values)
nano .env
```

---

## Development Setup

### Using Podman Compose

#### Option 1: Built-in Compose (Podman 4.0+)
```bash
# Build and start containers
podman compose up

# Run in background
podman compose up -d

# View logs
podman compose logs -f

# Stop containers
podman compose down
```

#### Option 2: podman-compose
```bash
# Build and start containers
podman-compose up

# Run in background
podman-compose up -d

# View logs
podman-compose logs -f

# Stop containers
podman-compose down
```

### Access Application
Open browser: http://localhost:8000

### Run Django Commands
```bash
# Execute commands in running container
podman compose exec web python manage.py migrate
podman compose exec web python manage.py createsuperuser
podman compose exec web python manage.py test

# Or with podman-compose
podman-compose exec web python manage.py migrate
```

---

## Production Deployment

### 1. Build Production Image
```bash
# Build with specific tag
podman build -t noteshrinker:latest -f Dockerfile .

# Tag for registry (if pushing)
podman tag noteshrinker:latest registry.example.com/noteshrinker:latest
```

### 2. Create Production compose.yaml
Create `compose.production.yaml`:

```yaml
services:
  web:
    image: noteshrinker:latest
    user: "1000:1000"

    command: >
      sh -c "python manage.py migrate &&
             python manage.py collectstatic --noinput &&
             gunicorn noteshrinker_django.wsgi:application --bind 0.0.0.0:8000"

    volumes:
      - noteshrinker-static:/var/app/static_collected:Z
      - noteshrinker-media:/var/app/noteshrinker/media:Z
      - noteshrinker-logs:/var/app/logs:Z

    ports:
      - "127.0.0.1:8000:8000"  # Only expose to localhost

    environment:
      - DEBUG=False
      - DJANGO_SETTINGS_MODULE=noteshrinker_django.settings_production
      - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY:?err}
      - ALLOWED_HOSTS=${ALLOWED_HOSTS:?err}
      - CSRF_TRUSTED_ORIGINS=${CSRF_TRUSTED_ORIGINS:?err}

    restart: always

    healthcheck:
      test: ["CMD", "python", "manage.py", "check", "--deploy"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  noteshrinker-static:
  noteshrinker-media:
  noteshrinker-logs:
```

### 3. Deploy
```bash
# Set production environment variables
export DJANGO_SECRET_KEY="your-secure-secret-key"
export ALLOWED_HOSTS="yourdomain.com,www.yourdomain.com"
export CSRF_TRUSTED_ORIGINS="https://yourdomain.com"

# Start production deployment
podman compose -f compose.production.yaml up -d

# Check logs
podman compose -f compose.production.yaml logs -f
```

### 4. Setup Reverse Proxy (Nginx/Apache)
For production, use a reverse proxy:

#### Nginx Example
```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /var/lib/containers/storage/volumes/noteshrinker-static/_data/;
    }

    location /media/ {
        alias /var/lib/containers/storage/volumes/noteshrinker-media/_data/;
    }
}
```

---

## Rootless vs Rootful

### Rootless Podman (Recommended)
Runs containers as regular user without root privileges.

**Advantages:**
- Better security isolation
- No root access required
- User namespace separation

**Storage Location:**
- Volumes: `~/.local/share/containers/storage/volumes/`
- Images: `~/.local/share/containers/storage/`

**Usage:**
```bash
# Everything runs as your user
podman compose up
```

### Rootful Podman
Runs containers with root privileges.

**When to Use:**
- Need to bind to ports < 1024
- Require root filesystem access
- Legacy compatibility

**Storage Location:**
- Volumes: `/var/lib/containers/storage/volumes/`
- Images: `/var/lib/containers/storage/`

**Usage:**
```bash
# Requires sudo
sudo podman compose up
```

---

## SELinux Considerations

### Understanding SELinux Labels

Podman automatically handles SELinux contexts, but understanding labels is important:

- **:z** (lowercase) - Shared content between containers
- **:Z** (uppercase) - Private content for one container
- **:ro** - Read-only mount

### Example Volume Mounts
```yaml
volumes:
  # Source code - shared, read/write
  - ./:/var/app:z

  # Media files - private, read/write
  - noteshrinker-media:/var/app/media:Z

  # Config - shared, read-only
  - ./config:/etc/config:z,ro
```

### Check SELinux Status
```bash
# Check if SELinux is enforcing
getenforce

# View file contexts
ls -Z /path/to/volume

# Relabel if needed (rarely required)
sudo restorecon -Rv /path/to/volume
```

### Troubleshooting SELinux Issues

If you encounter permission denied errors:

```bash
# Check audit log
sudo ausearch -m avc -ts recent

# Temporarily set permissive (for debugging only)
sudo setenforce 0

# Re-enable enforcing
sudo setenforce 1

# Generate and apply policy (if needed)
sudo ausearch -m avc | audit2allow -M mypolicy
sudo semodule -i mypolicy.pp
```

---

## Systemd Integration

Run Podman containers as systemd services for automatic startup.

### 1. Generate Systemd Unit File
```bash
# For rootless (user service)
cd ~/noteshrinker-django
podman compose up -d
podman generate systemd --new --files --name noteshrinker-django-web-1

# Move to systemd user directory
mkdir -p ~/.config/systemd/user
mv container-noteshrinker-django-web-1.service ~/.config/systemd/user/noteshrinker.service

# For rootful (system service)
sudo podman generate systemd --new --files --name noteshrinker-django-web-1
sudo mv container-noteshrinker-django-web-1.service /etc/systemd/system/noteshrinker.service
```

### 2. Enable and Start Service

#### Rootless (User Service)
```bash
# Reload systemd
systemctl --user daemon-reload

# Enable on boot (requires loginctl enable-linger)
loginctl enable-linger $USER
systemctl --user enable noteshrinker.service

# Start service
systemctl --user start noteshrinker.service

# Check status
systemctl --user status noteshrinker.service

# View logs
journalctl --user -u noteshrinker.service -f
```

#### Rootful (System Service)
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable on boot
sudo systemctl enable noteshrinker.service

# Start service
sudo systemctl start noteshrinker.service

# Check status
sudo systemctl status noteshrinker.service

# View logs
sudo journalctl -u noteshrinker.service -f
```

### 3. Manage Service
```bash
# Restart
systemctl --user restart noteshrinker.service

# Stop
systemctl --user stop noteshrinker.service

# Disable auto-start
systemctl --user disable noteshrinker.service
```

---

## Troubleshooting

### Container Won't Start

**Check logs:**
```bash
podman compose logs web
podman logs <container-id>
```

**Check container status:**
```bash
podman ps -a
podman inspect <container-id>
```

### Port Already in Use

**Find what's using port 8000:**
```bash
sudo ss -tlnp | grep 8000
```

**Change port in compose.yaml:**
```yaml
ports:
  - "8080:8000"  # Use 8080 instead
```

### Permission Denied Errors

**Check SELinux context:**
```bash
ls -Z /path/to/file
```

**Try different volume label:**
```yaml
# Change from :Z to :z
volumes:
  - ./:/var/app:z
```

**Check user/group IDs:**
```bash
# Inside container
podman compose exec web id

# On host
id
```

### Volume Data Not Persisting

**List volumes:**
```bash
podman volume ls
```

**Inspect volume:**
```bash
podman volume inspect noteshrinker-django_noteshrinker-media
```

**Recreate volumes:**
```bash
podman compose down -v
podman compose up
```

### Network Issues

**List networks:**
```bash
podman network ls
```

**Inspect network:**
```bash
podman network inspect noteshrinker-django_default
```

**Recreate network:**
```bash
podman compose down
podman network rm noteshrinker-django_default
podman compose up
```

### Can't Connect to Container

**Check firewall:**
```bash
# Check if firewalld is blocking
sudo firewall-cmd --list-all

# Allow port temporarily
sudo firewall-cmd --add-port=8000/tcp

# Make permanent
sudo firewall-cmd --add-port=8000/tcp --permanent
sudo firewall-cmd --reload
```

### Out of Disk Space

**Check disk usage:**
```bash
podman system df
```

**Clean up:**
```bash
# Remove unused containers
podman container prune

# Remove unused images
podman image prune -a

# Remove unused volumes
podman volume prune

# Clean everything
podman system prune -a --volumes
```

---

## Performance Tuning

### Optimize Storage Driver
```bash
# Check current driver
podman info | grep -A5 graphDriverName

# Use overlay2 (recommended for RedHat)
# Edit ~/.config/containers/storage.conf or /etc/containers/storage.conf
[storage]
driver = "overlay"
```

### Increase Ulimits
```bash
# In compose.yaml
services:
  web:
    ulimits:
      nofile:
        soft: 65536
        hard: 65536
```

### Resource Limits
```bash
# In compose.yaml
services:
  web:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

---

## Security Best Practices

1. **Always use rootless Podman when possible**
2. **Keep SELinux enabled (enforcing mode)**
3. **Use secrets for sensitive data (not environment variables)**
4. **Regularly update images and base OS**
5. **Use specific user IDs, not root**
6. **Enable automatic security updates on RHEL**
7. **Scan images for vulnerabilities:**
   ```bash
   podman scan noteshrinker:latest
   ```

---

## Additional Resources

- [Podman Documentation](https://docs.podman.io/)
- [RedHat Podman Guide](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/9/html/building_running_and_managing_containers/)
- [SELinux User Guide](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/9/html/using_selinux/)
- [Systemd Integration](https://docs.podman.io/en/latest/markdown/podman-generate-systemd.1.html)

---

## Support

For issues specific to this deployment:
- Check [README_MODERNIZATION.md](README_MODERNIZATION.md)
- Review [GitHub Issues](https://github.com/delneg/noteshrinker-django/issues)
- Consult RedHat Knowledge Base for RHEL-specific issues

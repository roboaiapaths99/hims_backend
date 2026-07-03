# AGPK1 Inventory - Hostinger VPS Multisite Deployment Guide

## Overview
You have 10 websites already deployed. This guide shows how to add the AGPK1 Inventory system as website #11 on your Hostinger VPS using Docker with a **custom port** and reverse proxy configuration.

**Key Details:**
- **Port for this app:** 8089 (or any free port you choose)
- **Domain:** Your domain (e.g., inventory.agpkacademy.in)
- **Reverse Proxy:** Your main Hostinger web server (Apache/Nginx/LiteSpeed) routes traffic to Docker
- **SSL:** Auto-configured through Hostinger's SSL system

---

## PART 1: SSH ACCESS & INITIAL SETUP

### Step 1.1: Connect to Hostinger VPS via SSH

1. Open **Terminal** (macOS/Linux) or **PowerShell/PuTTY** (Windows)
2. Get your VPS credentials from Hostinger Dashboard → VPS → Access → SSH Credentials
3. Connect:
   ```bash
   ssh root@your_vps_ip_address
   # Example: ssh root@192.168.1.100
   # Password: [Your VPS password from Hostinger]
   ```

4. You're now in your VPS terminal. Verify by running:
   ```bash
   pwd
   # Should show: /root
   ```

### Step 1.2: Check if Docker & Docker Compose are installed

```bash
docker --version
docker-compose --version
```

**If NOT installed:**
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Add your user to docker group (so you don't need sudo)
sudo usermod -aG docker $USER
newgrp docker
```

---

## PART 2: UPLOAD PROJECT TO VPS

### Step 2.1: Clone the Project from GitHub

```bash
# Create a directory for this app
mkdir -p /var/www/agpk1-inventory
cd /var/www/agpk1-inventory

# Clone from GitHub
git clone https://github.com/roboaiapaths99/AGPK1_Inventory.git .
```

### Step 2.2: Verify Project Structure

```bash
ls -la
```

You should see:
```
backend/
frontend/
docker-compose.yml
deploy.sh
.env.example
nginx/
scripts/
```

---

## PART 3: CONFIGURE ENVIRONMENT VARIABLES

### Step 3.1: Create .env File

```bash
# Copy example to actual env file
cp .env.example .env

# Edit the env file
nano .env
```

### Step 3.2: Set Environment Variables

Replace these values in `.env`:

```env
# MongoDB Configuration
MONGO_ROOT_USERNAME=admin
MONGO_ROOT_PASSWORD=YourStrongPassword123!@#
MONGO_DATABASE=pharmacy_erp

# Backend
SECRET_KEY=your-super-secret-key-change-this-$(openssl rand -hex 32)
API_HOST=0.0.0.0
API_PORT=8000

# Frontend
NEXT_PUBLIC_API_URL=https://your-domain.com/api
NEXT_PUBLIC_API_BASE=https://your-domain.com

# Docker Internal Port (where nginx inside docker runs)
NGINX_PORT=8089

# Pharmacy Details
PHARMACY_NAME=Your Pharmacy Name
PHARMACY_GSTIN=27XXXXXXXXXX
PHARMACY_LICENSE=DL-MH-2024-001
PHARMACY_ADDRESS=Your Full Address
PHARMACY_PHONE=+91-XXXXXXXXXX
PHARMACY_EMAIL=your-email@example.com

# SMTP (for emails - optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# Environment
ENVIRONMENT=production
DEBUG=False
```

**To generate a strong SECRET_KEY:**
```bash
openssl rand -hex 32
```

Save the file: Press `CTRL+X`, then `Y`, then `ENTER`

---

## PART 4: BUILD & START DOCKER CONTAINERS

### Step 4.1: Build Docker Images

```bash
cd /var/www/agpk1-inventory
docker-compose build --no-cache
```

This may take 5-10 minutes. Wait for completion.

### Step 4.2: Start All Containers

```bash
docker-compose up -d
```

### Step 4.3: Verify Containers Are Running

```bash
docker-compose ps
```

Expected output:
```
NAME                    STATUS
pharmacy_frontend       Up 2 minutes
pharmacy_backend        Up 2 minutes
pharmacy_mongodb        Up 2 minutes
pharmacy_redis          Up 2 minutes
pharmacy_celery_worker  Up 2 minutes
pharmacy_celery_beat    Up 2 minutes
pharmacy_nginx          Up 2 minutes
```

### Step 4.4: Check Logs for Errors

```bash
# View backend logs
docker-compose logs backend

# View frontend logs
docker-compose logs frontend

# View all logs
docker-compose logs -f
```

Press `CTRL+C` to exit logs.

---

## PART 5: CONFIGURE REVERSE PROXY ON HOSTINGER

Your Hostinger web server needs to forward traffic to Docker on port 8089.

### Step 5.1: Access Hostinger Control Panel

1. Go to **Hostinger Dashboard**
2. Choose your VPS
3. Go to **CyberPanel** (or your panel - Apache/Nginx/LiteSpeed)

### OPTION A: CyberPanel / OpenLiteSpeed

1. Click **Websites → Create Website**
2. Fill in:
   - **Domain:** inventory.agpkacademy.in (or your domain)
   - **Email:** your-email@example.com
   - **Select PHP:** None (since we're using Docker)
3. Click **Create**

4. Go to **Websites → Manage** for your new domain
5. Scroll to **Rewrite Rules** section
6. Click **vHost Configuration File** or **Edit vHost Conf**
7. Add this proxy context at the end:

```xml
<extprocessor dockerproxy>
    type                proxy
    address             127.0.0.1:8089
    maxConns            100
    pcKeepAliveTimeout  60
    initTimeout         60
    retryTimeout        0
    respBuffer          0
</extprocessor>

<context /api>
    <extprocessor>
        name dockerproxy
    </extprocessor>
    <enableExpires> 1 </enableExpires>
    <expiresByType text/html>M86400</expiresByType>
</context>

<context />
    <enableExpires> 1 </enableExpires>
    <location /> 
        <extprocessor>
            name dockerproxy
        </extprocessor>
    </location>
    <expiresByType text/html>M86400</expiresByType>
</context>
```

8. Click **Save**
9. Go to **SSL** tab and click **Issue SSL Certificate** (Let's Encrypt)
10. Rebuild OpenLiteSpeed:
    ```bash
    sudo /usr/local/lsws/bin/lswsctrl restart
    ```

### OPTION B: Nginx (If Hostinger uses Nginx)

1. SSH into your VPS (as shown in Part 1.1)

2. Create a new Nginx config file:
```bash
sudo nano /etc/nginx/sites-available/inventory
```

3. Paste this configuration:
```nginx
server {
    listen 80;
    server_name inventory.agpkacademy.in;

    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name inventory.agpkacademy.in;

    # SSL certificates (Certbot will fill these)
    ssl_certificate /etc/letsencrypt/live/inventory.agpkacademy.in/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/inventory.agpkacademy.in/privkey.pem;

    # SSL settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Logging
    access_log /var/log/nginx/inventory_access.log;
    error_log /var/log/nginx/inventory_error.log;

    # Proxy to Docker
    location / {
        proxy_pass http://127.0.0.1:8089;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_max_temp_file_size 0;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }
}
```

4. Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/inventory /etc/nginx/sites-enabled/
```

5. Test Nginx config:
```bash
sudo nginx -t
```

6. Reload Nginx:
```bash
sudo systemctl reload nginx
```

7. Install SSL (Let's Encrypt):
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d inventory.agpkacademy.in
```

### OPTION C: Apache (If Hostinger uses Apache)

1. SSH into your VPS

2. Enable proxy modules:
```bash
sudo a2enmod proxy
sudo a2enmod proxy_http
sudo a2enmod rewrite
sudo a2enmod ssl
```

3. Create virtual host config:
```bash
sudo nano /etc/apache2/sites-available/inventory.conf
```

4. Paste:
```apache
<VirtualHost *:80>
    ServerName inventory.agpkacademy.in
    Redirect permanent / https://inventory.agpkacademy.in/
</VirtualHost>

<VirtualHost *:443>
    ServerName inventory.agpkacademy.in

    SSLEngine on
    SSLCertificateFile /etc/letsencrypt/live/inventory.agpkacademy.in/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/inventory.agpkacademy.in/privkey.pem

    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:8089/
    ProxyPassReverse / http://127.0.0.1:8089/

    # Security headers
    Header always set Strict-Transport-Security "max-age=31536000"
    Header always set X-Frame-Options "SAMEORIGIN"
    Header always set X-Content-Type-Options "nosniff"

    LogLevel warn
    CustomLog ${APACHE_LOG_DIR}/inventory_access.log combined
    ErrorLog ${APACHE_LOG_DIR}/inventory_error.log
</VirtualHost>
```

5. Enable site:
```bash
sudo a2ensite inventory.conf
```

6. Test Apache config:
```bash
sudo apache2ctl configtest
```

7. Restart Apache:
```bash
sudo systemctl restart apache2
```

8. Install SSL (Let's Encrypt):
```bash
sudo apt install certbot python3-certbot-apache
sudo certbot --apache -d inventory.agpkacademy.in
```

---

## PART 6: DNS CONFIGURATION

1. Go to **Hostinger → Domains → Your Domain → DNS**
2. Add A Record:
   - **Type:** A
   - **Name:** inventory (or subdomain name)
   - **Points to:** Your VPS IP Address
   - **TTL:** 3600

3. Or if using as subdomain on existing domain:
   - **Type:** A
   - **Name:** inventory.yourdomain.com
   - **Points to:** Your VPS IP Address

4. Wait 5-30 minutes for DNS to propagate

---

## PART 7: TEST & VERIFY

### Step 7.1: Test Docker is Running

```bash
curl http://127.0.0.1:8089
```

Should return HTML content (not errors).

### Step 7.2: Test Reverse Proxy Locally

```bash
curl -H "Host: inventory.agpkacademy.in" http://127.0.0.1:8089
```

### Step 7.3: Test from Browser

Open: **https://inventory.agpkacademy.in**

You should see:
- ✅ Green HTTPS lock
- ✅ Pharmacy inventory dashboard loads
- ✅ No API connection errors

### Step 7.4: Check Logs if Issues Occur

```bash
# Docker logs
docker-compose logs backend
docker-compose logs frontend

# Web server logs
# Nginx:
tail -f /var/log/nginx/inventory_error.log

# Apache:
tail -f /var/log/apache2/inventory_error.log

# CyberPanel/LiteSpeed:
tail -f /usr/local/lsws/logs/error.log
```

---

## PART 8: MANAGE MONGODB DATA

### Step 8.1: Import Initial Data (if needed)

```bash
# From your local machine, copy data file to VPS
scp /path/to/stockdata.json root@your_vps_ip:/var/www/agpk1-inventory/data/

# On VPS, import to MongoDB
docker exec pharmacy_mongodb mongoimport \
  --username admin \
  --password YourStrongPassword123!@# \
  --authenticationDatabase admin \
  --db pharmacy_erp \
  --collection medicines \
  --file /data/stockdata.json \
  --jsonArray
```

### Step 8.2: Backup MongoDB Data

```bash
# Create backup
docker exec pharmacy_mongodb mongodump \
  --username admin \
  --password YourStrongPassword123!@# \
  --authenticationDatabase admin \
  --out /backup/

# Copy backup to local machine
scp -r root@your_vps_ip:/backup /local/backup/location
```

---

## PART 9: MAINTENANCE & UPDATES

### Step 9.1: Monitor Container Health

```bash
# Check container status
docker-compose ps

# View resource usage
docker stats

# Check for disk space
df -h
```

### Step 9.2: Update Application

```bash
# Pull latest changes
cd /var/www/agpk1-inventory
git pull origin main

# Rebuild and restart
docker-compose down
docker-compose up -d --build

# Verify
docker-compose ps
```

### Step 9.3: View Application Logs

```bash
# Real-time logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100

# Only backend
docker-compose logs backend -f
```

### Step 9.4: Restart Services (if issues)

```bash
# Restart all containers
docker-compose restart

# Restart specific container
docker-compose restart backend
docker-compose restart frontend

# Full rebuild if stuck
docker-compose down
docker-compose up -d --build
```

---

## PART 10: FIREWALL & SECURITY

### Step 10.1: Configure UFW Firewall

```bash
# Enable firewall
sudo ufw enable

# Allow SSH (IMPORTANT - do this first!)
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Allow Docker port 8089 (only from localhost)
sudo ufw allow from 127.0.0.1 to 127.0.0.1 port 8089

# Check rules
sudo ufw status numbered
```

### Step 10.2: Secure SSH

```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config

# Change these lines:
Port 22  # Change to custom port (optional)
PermitRootLogin no  # Disable root login
PasswordAuthentication no  # Use keys only
```

Restart SSH:
```bash
sudo systemctl restart sshd
```

---

## PART 11: AUTO-RESTART CONTAINERS ON VPS REBOOT

### Step 11.1: Create SystemD Service

```bash
sudo nano /etc/systemd/system/agpk1-inventory.service
```

Paste:
```ini
[Unit]
Description=AGPK1 Inventory Docker Compose Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=root
WorkingDirectory=/var/www/agpk1-inventory
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
RemainAfterExit=yes
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable it:
```bash
sudo systemctl daemon-reload
sudo systemctl enable agpk1-inventory.service
sudo systemctl start agpk1-inventory.service
```

Verify:
```bash
sudo systemctl status agpk1-inventory.service
```

---

## PART 12: TROUBLESHOOTING

### Issue: "Connection refused" on port 8089

```bash
# Check if containers are running
docker-compose ps

# View container logs
docker-compose logs backend
docker-compose logs frontend

# Restart containers
docker-compose restart
```

### Issue: API Returns 500 Errors

```bash
# Check backend logs
docker-compose logs backend -f

# Check MongoDB connection
docker exec pharmacy_backend python -c "from pymongo import MongoClient; print('MongoDB OK')"

# Check database connection
docker-compose logs mongodb
```

### Issue: Frontend Shows "Cannot Connect to API"

```bash
# Verify .env has correct API URL
cat .env | grep NEXT_PUBLIC_API_URL

# Check reverse proxy is working
curl -v -H "Host: inventory.agpkacademy.in" http://127.0.0.1:8089
```

### Issue: SSL Certificate Not Working

```bash
# For Nginx
sudo certbot renew
sudo systemctl reload nginx

# For Apache
sudo certbot renew
sudo systemctl reload apache2

# For CyberPanel
# Go to SSL tab and reissue certificate
```

---

## SUMMARY OF KEY PORTS & ACCESS

| Service | Internal Port | Access |
|---------|---|---|
| Frontend | 3000 | Via reverse proxy only |
| Backend API | 8000 | Via reverse proxy only |
| Nginx (Docker) | 8089 | `http://127.0.0.1:8089` (local) |
| MongoDB | 27017 | Docker network only |
| Redis | 6379 | Docker network only |
| **Public Access** | 80/443 | `https://inventory.agpkacademy.in` |

---

## FINAL CHECKLIST

- [ ] Docker & Docker Compose installed
- [ ] Project cloned to `/var/www/agpk1-inventory`
- [ ] `.env` file configured with production values
- [ ] Docker containers built and running (`docker-compose ps`)
- [ ] Reverse proxy configured on web server
- [ ] DNS A record pointing to VPS IP
- [ ] SSL certificate installed
- [ ] Frontend loads at `https://your-domain.com`
- [ ] API responding without errors
- [ ] SystemD service created for auto-restart
- [ ] Firewall rules configured

---

## SUPPORT & NEXT STEPS

1. **Backup MongoDB regularly:**
   ```bash
   docker exec pharmacy_mongodb mongodump --username admin --password PASSWORD --authenticationDatabase admin --out /backup/
   ```

2. **Monitor logs daily:**
   ```bash
   docker-compose logs --tail=50
   ```

3. **Test after updates:**
   ```bash
   git pull && docker-compose up -d --build
   ```

**You're now live! 🚀**

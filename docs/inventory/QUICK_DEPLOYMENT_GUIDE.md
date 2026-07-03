# AGPK1 Inventory - Quick Deployment Cheat Sheet

## 🚀 EXPRESS DEPLOYMENT (For Experienced Users)

### 1. SSH & Clone (5 min)
```bash
ssh root@your_vps_ip
mkdir -p /var/www/agpk1-inventory && cd /var/www/agpk1-inventory
git clone https://github.com/roboaiapaths99/AGPK1_Inventory.git .
```

### 2. Configure & Build (15 min)
```bash
cp .env.example .env
nano .env
# Set: MONGO_ROOT_PASSWORD, SECRET_KEY, NEXT_PUBLIC_API_URL, NGINX_PORT=8089
docker-compose build --no-cache
```

### 3. Start Services (5 min)
```bash
docker-compose up -d
docker-compose ps  # Verify all running
```

### 4. Setup Reverse Proxy (10 min)
- **CyberPanel:** Add vHost proxy to 127.0.0.1:8089
- **Nginx:** Add config in `/etc/nginx/sites-available/` with proxy_pass http://127.0.0.1:8089
- **Apache:** Enable mod_proxy and add ProxyPass directives

### 5. SSL & DNS (5 min)
```bash
sudo certbot --nginx -d inventory.agpkacademy.in  # Nginx
# OR
sudo certbot --apache -d inventory.agpkacademy.in  # Apache
```

**Add DNS A Record pointing to VPS IP**

### 6. Test (2 min)
```bash
curl http://127.0.0.1:8089  # Should return HTML
# Visit https://inventory.agpkacademy.in in browser
```

---

## 📋 DETAILED STEP-BY-STEP (For Beginners)

### Prerequisites Check
```bash
# SSH to VPS
ssh root@your_vps_ip_address

# Verify Docker
docker --version
docker-compose --version

# If not installed, run in Terminal:
# curl -fsSL https://get.docker.com -o get-docker.sh && sudo sh get-docker.sh
```

### Step 1: Create Project Directory
```bash
mkdir -p /var/www/agpk1-inventory
cd /var/www/agpk1-inventory
```

### Step 2: Clone from GitHub
```bash
git clone https://github.com/roboaiapaths99/AGPK1_Inventory.git .
ls -la  # Verify files exist
```

### Step 3: Configure Environment
```bash
cp .env.example .env
nano .env
```

**Required .env values:**
```
MONGO_ROOT_PASSWORD=SetAStrongPassword123!
SECRET_KEY=GenerateWithOpenSSL
NEXT_PUBLIC_API_URL=https://your-domain.com/api
NGINX_PORT=8089
```

**To generate SECRET_KEY:**
```bash
openssl rand -hex 32
# Copy output and paste in .env
```

### Step 4: Build Docker Images
```bash
cd /var/www/agpk1-inventory
docker-compose build --no-cache
# Wait 5-10 minutes for build
```

### Step 5: Start Containers
```bash
docker-compose up -d
```

### Step 6: Verify All Running
```bash
docker-compose ps
# Should show 7 containers all with "Up" status
```

### Step 7: Test Docker Service Locally
```bash
curl -i http://127.0.0.1:8089
# Should return: HTTP/1.1 200 or 307
```

### Step 8: Configure Web Server Reverse Proxy

#### FOR CYBERPANEL / OPENLITESPEED:
```
1. Go to CyberPanel > Websites > Manage > Your Domain
2. Scroll to "vHost Configuration"
3. Add this at the end:

<extprocessor dockerproxy>
    type proxy
    address 127.0.0.1:8089
    maxConns 100
</extprocessor>

<context />
    <enableExpires> 1 </enableExpires>
    <location /> 
        <extprocessor>
            name dockerproxy
        </extprocessor>
    </location>
</context>

4. Save and click "Rebuild OpenLiteSpeed"
```

#### FOR NGINX:
```bash
sudo nano /etc/nginx/sites-available/inventory
# Paste this:

server {
    listen 80;
    server_name inventory.agpkacademy.in;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name inventory.agpkacademy.in;
    ssl_certificate /etc/letsencrypt/live/inventory.agpkacademy.in/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/inventory.agpkacademy.in/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8089;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Then:
sudo ln -s /etc/nginx/sites-available/inventory /etc/nginx/sites-enabled/
sudo systemctl reload nginx
```

#### FOR APACHE:
```bash
sudo a2enmod proxy proxy_http rewrite ssl
sudo nano /etc/apache2/sites-available/inventory.conf
# Paste this:

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
</VirtualHost>

# Then:
sudo a2ensite inventory.conf
sudo systemctl reload apache2
```

### Step 9: Setup SSL Certificate
```bash
# Nginx
sudo certbot --nginx -d inventory.agpkacademy.in

# Apache
sudo certbot --apache -d inventory.agpkacademy.in

# CyberPanel: Use CyberPanel UI > SSL > Issue Certificate
```

### Step 10: Configure DNS
```
1. Go to Hostinger > Domains > Your Domain > DNS
2. Add A Record:
   - Name: inventory
   - Type: A
   - Points to: [Your VPS IP Address]
   - TTL: 3600
3. Wait 5-30 minutes for propagation
```

### Step 11: Test Everything
```bash
# Local test
curl -H "Host: inventory.agpkacademy.in" http://127.0.0.1:8089

# Browser test
# Visit: https://inventory.agpkacademy.in
# Should show: ✅ Green lock, ✅ Dashboard loads, ✅ No API errors
```

---

## 🔧 COMMON COMMANDS

### Check Status
```bash
docker-compose ps
docker-compose logs -f              # Real-time logs
docker-compose logs backend -f      # Just backend
docker-compose logs --tail=50       # Last 50 lines
```

### Restart Services
```bash
docker-compose restart              # Restart all
docker-compose restart backend      # Restart specific
docker-compose down && docker-compose up -d  # Full restart
```

### View Logs
```bash
docker-compose logs backend
docker-compose logs frontend
docker exec pharmacy_backend cat /var/log/app.log
```

### Backup MongoDB
```bash
docker exec pharmacy_mongodb mongodump \
  --username admin \
  --password YOUR_PASSWORD \
  --authenticationDatabase admin \
  --out /backup/
```

### Update Application
```bash
cd /var/www/agpk1-inventory
git pull origin main
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## ⚙️ PORT ALLOCATION REFERENCE

| App | Service | Port | Access |
|-----|---------|------|--------|
| App #1 | Nginx | 8001 | Via Reverse Proxy |
| App #2 | Nginx | 8002 | Via Reverse Proxy |
| ... | ... | ... | ... |
| App #11 (AGPK1) | Nginx | **8089** | Via Reverse Proxy |
| Hostinger Main | Apache/Nginx | 80, 443 | Public |

**All Docker apps run on unique ports internally, but public access only via main web server on ports 80/443**

---

## ❌ TROUBLESHOOTING

### Docker containers not starting
```bash
docker-compose logs
# Check for MONGO errors, PORT in use, or config issues
docker-compose ps  # Any container stuck?
docker-compose restart
```

### Cannot access via browser
```bash
# 1. Check Docker running
docker-compose ps

# 2. Check reverse proxy working
curl http://127.0.0.1:8089

# 3. Check DNS resolved
nslookup inventory.agpkacademy.in

# 4. Check web server config
# Nginx: nginx -t
# Apache: apache2ctl configtest

# 5. Check firewall
sudo ufw status
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### API returns 500 error
```bash
docker-compose logs backend
# Check MongoDB connection
docker exec pharmacy_backend python -c "from pymongo import MongoClient; MongoClient('mongodb://admin:PASSWORD@mongodb:27017').admin.command('ping')"
```

### SSL certificate issues
```bash
# Check cert validity
sudo certbot certificates

# Renew manually
sudo certbot renew --force-renewal

# Restart web server
sudo systemctl restart nginx  # OR apache2
```

---

## 📞 SUPPORT COMMANDS

```bash
# System info
uname -a
df -h
docker stats

# Network info
netstat -tlnp | grep 8089
ss -tlnp | grep LISTEN

# Get all container IPs
docker network inspect agpk1-inventory_pharmacy_network

# Test port availability
nc -zv 127.0.0.1 8089
```

---

## ✅ FINAL VERIFICATION CHECKLIST

```bash
# All containers running?
docker-compose ps | grep "Up"

# Docker service responds?
curl -I http://127.0.0.1:8089

# MongoDB connected?
docker-compose logs backend | grep "MongoDB"

# Reverse proxy working?
curl -H "Host: inventory.agpkacademy.in" http://127.0.0.1:8089 | head -20

# SSL certificate valid?
openssl s_client -connect inventory.agpkacademy.in:443

# DNS resolving?
nslookup inventory.agpkacademy.in
```

---

## 🎯 TYPICAL DEPLOYMENT TIME

- Docker Setup: 5 min
- Project Clone: 2 min
- Configuration: 5 min
- Build Images: 10-15 min
- Start Services: 2 min
- Reverse Proxy Setup: 5-10 min (depends on control panel)
- SSL Certificate: 2 min
- DNS Propagation: 5-30 min
- Testing: 5 min

**TOTAL: ~45-75 minutes** (depending on your experience and server speed)

---

**Questions? Refer to full guide: HOSTINGER_MULTISITE_DEPLOYMENT.md**

# AGPK1 Inventory on Hostinger - Architecture & Port Mapping Guide

## 🏗️ ARCHITECTURE DIAGRAM

```
                          INTERNET (Public)
                                 |
                                 | HTTPS (Port 443)
                                 | HTTP (Port 80)
                                 ↓
                    ┌─────────────────────────┐
                    │   Hostinger VPS Main    │
                    │   Web Server            │
                    │ (Apache/Nginx/Litespeed)│
                    │   Ports: 80, 443        │
                    └──────────┬──────────────┘
                               |
                ┌──────────────┼──────────────┐
                |              |              |
                ↓              ↓              ↓
        ┌─────────────┐  ┌──────────┐  ┌──────────────┐
        │  Website 1  │  │Website 2 │  │Website #11   │
        │  (Reverse   │  │          │  │ AGPK1 Inv.   │
        │   Proxy to  │  │(Reverse  │  │ (Reverse     │
        │   8001)     │  │ Proxy to │  │  Proxy to    │
        │             │  │  8002)   │  │  8089)       │
        └──────┬──────┘  └─────┬────┘  └──────┬───────┘
               |               |              |
        ┌──────v──────┐ ┌──────v────┐ ┌──────v──────────┐
        │ Docker App1 │ │Docker App2│ │ Docker          │
        │ Port 8001   │ │ Port 8002 │ │ Compose App     │
        │             │ │           │ │ Port 8089       │
        └─────────────┘ └───────────┘ │                 │
                                      │ ┌─────────────┐ │
                                      │ │ Frontend:   │ │
                                      │ │ Next.js 3000│ │
                                      │ │ (internal)  │ │
                                      │ └─────────────┘ │
                                      │ ┌─────────────┐ │
                                      │ │ Backend:    │ │
                                      │ │ FastAPI 8000│ │
                                      │ │ (internal)  │ │
                                      │ └─────────────┘ │
                                      │ ┌─────────────┐ │
                                      │ │ MongoDB     │ │
                                      │ │ 27017       │ │
                                      │ │ (internal)  │ │
                                      │ └─────────────┘ │
                                      │ ┌─────────────┐ │
                                      │ │ Redis       │ │
                                      │ │ 6379        │ │
                                      │ │ (internal)  │ │
                                      │ └─────────────┘ │
                                      └─────────────────┘
                                      (Docker Network)
```

---

## 📊 PORT MAPPING TABLE

### Your Hostinger VPS Multisite Setup

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HOSTINGER VPS (Your Server)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  PUBLIC FACING (Internet)                                                   │
│  ├─ Port 80 (HTTP)    ──→ Hostinger Main Web Server                        │
│  └─ Port 443 (HTTPS)  ──→ Hostinger Main Web Server                        │
│                                                                              │
│  ───────────────────────────────────────────────────────────────────        │
│                                                                              │
│  INTERNAL - REVERSE PROXIED BY MAIN WEB SERVER                             │
│  ├─ Website #1:  domain1.com         → 127.0.0.1:8001 ✓ Running           │
│  ├─ Website #2:  domain2.com         → 127.0.0.1:8002 ✓ Running           │
│  ├─ Website #3:  domain3.com         → 127.0.0.1:8003 ✓ Running           │
│  ├─ Website #4:  domain4.com         → 127.0.0.1:8004 ✓ Running           │
│  ├─ Website #5:  domain5.com         → 127.0.0.1:8005 ✓ Running           │
│  ├─ Website #6:  domain6.com         → 127.0.0.1:8006 ✓ Running           │
│  ├─ Website #7:  domain7.com         → 127.0.0.1:8007 ✓ Running           │
│  ├─ Website #8:  domain8.com         → 127.0.0.1:8008 ✓ Running           │
│  ├─ Website #9:  domain9.com         → 127.0.0.1:8009 ✓ Running           │
│  ├─ Website #10: domain10.com        → 127.0.0.1:8010 ✓ Running           │
│  └─ Website #11: inventory.agpk.in   → 127.0.0.1:8089 ← NEW (AGPK1)      │
│                                                                              │
│  ───────────────────────────────────────────────────────────────────        │
│                                                                              │
│  DOCKER INTERNAL (AGPK1 INVENTORY ONLY)                                    │
│  ├─ Nginx Reverse Proxy:  127.0.0.1:8089 (EXPOSED - bridges to main web)  │
│  │   ├─ Frontend (Next.js):           127.0.0.1:3000 (docker network)     │
│  │   └─ Backend API (FastAPI):        127.0.0.1:8000 (docker network)     │
│  │                                                                           │
│  ├─ MongoDB:                          127.0.0.1:27017 (docker network)    │
│  ├─ Redis:                            127.0.0.1:6379  (docker network)    │
│  ├─ Celery Worker:                    (docker network, no port)           │
│  └─ Celery Beat:                      (docker network, no port)           │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 HOW TRAFFIC FLOWS

### User accesses inventory.agpkacademy.in:

```
Step 1: User opens browser
        User: https://inventory.agpkacademy.in
                     ↓
        
Step 2: Browser resolves DNS
        DNS Lookup: inventory.agpkacademy.in → 192.168.1.100 (Your VPS IP)
                     ↓
        
Step 3: Browser makes HTTPS request to port 443
        Request: HTTPS to 192.168.1.100:443
                     ↓
        
Step 4: Hostinger Main Web Server intercepts
        (Apache/Nginx/LiteSpeed on port 443)
        Checks: Where should this domain go?
                     ↓
        
Step 5: Web Server Reverse Proxy Configuration
        Matches: inventory.agpkacademy.in → 127.0.0.1:8089
                     ↓
        
Step 6: Web Server Forwards to Docker
        Internal Proxy: 192.168.1.100:443 → 127.0.0.1:8089
                     ↓
        
Step 7: Docker Nginx Receives Request
        Container: pharmacy_nginx listening on 8089
        Forwards internally to:
        - http://frontend:3000  (for UI pages)
        - http://backend:8000   (for API calls)
                     ↓
        
Step 8: Response sent back through reverse proxy
        Frontend HTML + CSS + JS returned
                     ↓
        
Step 9: Browser Renders Dashboard
        ✅ https://inventory.agpkacademy.in displays with green lock
```

---

## 🔐 SECURITY: WHY REVERSE PROXY?

### Without Reverse Proxy (❌ INSECURE):
```
Internet
  ↓
Port 8089 (EXPOSED)  ← Anyone can access!
  ↓
Docker App (NO HTTPS)  ← Connection unencrypted!
```

### With Reverse Proxy (✅ SECURE):
```
Internet
  ↓
Port 443 (Main Web Server with SSL) ✓ Encrypted
  ↓
Internal Firewall (UFW Blocks 8089)  ✓ Protected
  ↓
Localhost Proxy 127.0.0.1:8089  ✓ Only local access
  ↓
Docker App  ✓ Completely isolated
```

---

## 📝 CONFIGURATION CHECKLIST

### Hostinger Web Server Config

#### CyberPanel / LiteSpeed:
```
✓ Website: inventory.agpkacademy.in created
✓ vHost Configuration → Added proxy context
✓ Proxy Type: address 127.0.0.1:8089
✓ SSL Certificate: Let's Encrypt issued
✓ Rewrite Rules: All traffic → dockerproxy
```

#### Nginx:
```
✓ Site Config: /etc/nginx/sites-available/inventory
✓ Upstream: upstream docker { server 127.0.0.1:8089; }
✓ Location /: proxy_pass http://docker
✓ Proxy Headers: Set Host, X-Real-IP, X-Forwarded-*
✓ SSL: Certbot certificates auto-configured
✓ Site Enabled: /etc/nginx/sites-enabled/inventory (symlink)
```

#### Apache:
```
✓ VirtualHost: *:443 for inventory.agpkacademy.in
✓ Modules: mod_proxy, mod_proxy_http enabled
✓ ProxyPass: / http://127.0.0.1:8089/
✓ ProxyPreserveHost: On
✓ SSL: Certificate configured
✓ Headers: Set security headers
```

### Docker Config:
```
✓ docker-compose.yml: NGINX_PORT set to 8089
✓ .env file: All variables configured
✓ MongoDB: Credentials set
✓ Backend: Connected to MongoDB
✓ Frontend: NEXT_PUBLIC_API_URL correct
✓ Containers: All 7 services running
```

### DNS Config:
```
✓ A Record: inventory → Your VPS IP
✓ TTL: 3600
✓ DNS Propagated: nslookup returns VPS IP
```

### Firewall Config:
```
✓ Port 80: Allowed (HTTP redirect)
✓ Port 443: Allowed (HTTPS main)
✓ Port 8089: NOT exposed (only 127.0.0.1)
✓ Port 22: Allowed (SSH)
✓ Other ports: Blocked by default
```

---

## 🚀 DEPLOYMENT SEQUENCE

```
┌────────────────────────────────────────────────────────────────┐
│ STEP 1: Prepare VPS                                            │
│ ├─ SSH into VPS                                                │
│ ├─ Install Docker & Docker Compose                             │
│ └─ Verify installation                                         │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│ STEP 2: Clone & Configure                                      │
│ ├─ Clone AGPK1 from GitHub                                     │
│ ├─ Copy .env.example → .env                                    │
│ ├─ Edit .env with production values                            │
│ └─ Verify .env is correct                                      │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│ STEP 3: Build & Run Docker                                     │
│ ├─ docker-compose build --no-cache (15 min)                    │
│ ├─ docker-compose up -d                                        │
│ ├─ docker-compose ps (verify all running)                      │
│ └─ curl http://127.0.0.1:8089 (test)                           │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│ STEP 4: Configure Reverse Proxy                                │
│ ├─ Log into Hostinger Control Panel                            │
│ ├─ Add reverse proxy rule for inventory domain                 │
│ ├─ Point to 127.0.0.1:8089                                     │
│ └─ Issue SSL certificate                                       │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│ STEP 5: DNS & SSL                                              │
│ ├─ Add A record in DNS: inventory → VPS IP                     │
│ ├─ Wait for DNS propagation (5-30 min)                         │
│ ├─ Install SSL: certbot or via control panel                   │
│ └─ Test: https://inventory.agpkacademy.in                      │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│ STEP 6: Verify & Secure                                        │
│ ├─ Check all containers running                                │
│ ├─ Test API endpoints                                          │
│ ├─ Configure firewall                                          │
│ └─ Setup auto-restart via systemd                              │
└────────────────────────────────────────────────────────────────┘
                              ↓
                         ✅ LIVE!
```

---

## 🔧 MAINTENANCE WORKFLOW

```
Daily:
  └─ Monitor: docker-compose logs --tail=20
  
Weekly:
  ├─ Backup: docker exec pharmacy_mongodb mongodump
  └─ Check: docker stats (resource usage)
  
Monthly:
  ├─ Update: git pull && docker-compose up -d --build
  └─ Security: Check SSL certificate expiry
  
Quarterly:
  ├─ Test: Restore from backup
  └─ Plan: Capacity needs for next year
```

---

## 🆘 EMERGENCY PROCEDURES

### If App Goes Down:

```bash
# 1. SSH to VPS
ssh root@your_vps_ip

# 2. Check status
docker-compose ps

# 3. View logs
docker-compose logs | grep error

# 4. Restart
docker-compose restart

# 5. If still down, full rebuild
docker-compose down
docker-compose up -d --build
```

### If MongoDB is Corrupted:

```bash
# 1. Backup existing data
docker exec pharmacy_mongodb mongodump --out /backup/

# 2. Stop containers
docker-compose down

# 3. Remove MongoDB data volume (⚠️ CAREFUL!)
docker volume rm agpk1-inventory_mongodb_data

# 4. Restart (MongoDB will reinitialize)
docker-compose up -d
```

### If DNS is Not Resolving:

```bash
# 1. Check DNS propagation
nslookup inventory.agpkacademy.in

# 2. Check A record
dig inventory.agpkacademy.in

# 3. If wrong, update in Hostinger DNS
# Wait 5-30 minutes

# 4. Flush local DNS cache
sudo systemd-resolve --flush-caches  # Linux
ipconfig /flushdns  # Windows
sudo killall -HUP mDNSResponder  # macOS
```

---

## 📊 RESOURCE REQUIREMENTS

```
AGPK1 Inventory Containers Resource Needs:

Frontend (Next.js):
  CPU: 100-200 mCPU
  RAM: 256-512 MB
  Disk: 1 GB

Backend (FastAPI):
  CPU: 150-300 mCPU
  RAM: 512 MB - 1 GB
  Disk: 500 MB

MongoDB:
  CPU: 100-200 mCPU
  RAM: 1-2 GB
  Disk: 10-50 GB (depends on data)

Redis:
  CPU: 50-100 mCPU
  RAM: 256-512 MB
  Disk: 1 GB

Celery Worker + Beat:
  CPU: 100-200 mCPU
  RAM: 256-512 MB
  Disk: 500 MB

TOTAL:
  CPU: 500-1000 mCPU (0.5-1 vCPU)
  RAM: 2.5-5 GB
  Disk: 15-70 GB SSD

RECOMMENDED HOSTINGER PLAN:
  ✓ 2 vCPU
  ✓ 4-8 GB RAM
  ✓ 100 GB SSD
  (Enough for your 11 websites total)
```

---

## ✅ FINAL VERIFICATION

```
Before declaring deployment complete:

□ Browser shows https://inventory.agpkacademy.in
□ Green SSL lock visible
□ Dashboard loads (no 500 errors)
□ Can login with test credentials
□ Can create medicines
□ Can perform sales transactions
□ API documentation available: /api/docs
□ Docker containers not restarting frequently
□ No errors in logs (docker-compose logs)
□ MongoDB backup working
□ Reverse proxy functioning correctly
□ Firewall configured (port 8089 not exposed)
□ SSL certificate auto-renewal setup
```

---

**You're ready to deploy! 🎉**

Next step: Follow QUICK_DEPLOYMENT_GUIDE.md or HOSTINGER_MULTISITE_DEPLOYMENT.md

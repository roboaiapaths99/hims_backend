# AGPK1 Inventory - Docker Container Conflict Fix

## Problem
```
Error: Container name "/pharmacy_mongodb" is already in use
```

This happens when stopped/old containers still exist with the same names.

---

## ✅ SOLUTION - Run These Commands on Your VPS

### Step 1: Stop All Running Containers
```bash
docker-compose down
```

### Step 2: Remove All Stopped Containers (with this app name)
```bash
docker container prune -f
```

**OR remove specific containers:**
```bash
docker rm pharmacy_mongodb
docker rm pharmacy_redis
docker rm pharmacy_backend
docker rm pharmacy_frontend
docker rm pharmacy_celery_worker
docker rm pharmacy_celery_beat
docker rm pharmacy_nginx
```

### Step 3: Remove Old Volumes (if needed)
```bash
docker volume prune -f
```

**OR remove specific volumes:**
```bash
docker volume rm agpk1-inventory_mongodb_data
docker volume rm agpk1-inventory_redis_data
docker volume rm agpk1-inventory_backend_invoices
docker volume rm agpk1-inventory_backend_models
```

### Step 4: Verify Everything is Clean
```bash
docker ps -a
docker volume ls
```

**Expected output: Should show nothing or unrelated containers**

### Step 5: Now Try Starting Again
```bash
cd /var/www/agpk1-inventory
docker-compose up -d
```

### Step 6: Verify All Containers Running
```bash
docker-compose ps
```

**Expected output:**
```
NAME                    IMAGE                        COMMAND             CREATED    STATUS            PORTS
pharmacy_nginx          agpk1-inventory-nginx        "nginx -g..."       2s ago     Up 1s              0.0.0.0:8089->80/tcp
pharmacy_frontend       agpk1-inventory-frontend     "npm start"         2s ago     Up 1s              
pharmacy_backend        agpk1-inventory-backend      "python main.py"    2s ago     Up 1s              
pharmacy_mongodb        mongo:7.0                    "docker..."         3s ago     Up 2s              
pharmacy_redis          redis:7.2-alpine             "redis-server"      3s ago     Up 2s              
pharmacy_celery_worker  agpk1-inventory-backend      "celery -A..."      3s ago     Up 1s              
pharmacy_celery_beat    agpk1-inventory-backend      "celery -A..."      3s ago     Up 1s              
```

---

## 🚨 IF PROBLEM PERSISTS

### Nuclear Option - Remove Everything and Rebuild
```bash
# Stop containers
docker-compose down -v

# Remove all containers for this project
docker container ls -a | grep pharmacy | awk '{print $1}' | xargs docker rm -f

# Remove all volumes
docker volume ls | grep agpk1-inventory | awk '{print $2}' | xargs docker volume rm -f

# Remove all networks
docker network ls | grep pharmacy | awk '{print $1}' | xargs docker network rm

# Rebuild from scratch
docker-compose build --no-cache
docker-compose up -d
```

### Verify Cleanup
```bash
docker ps -a
docker volume ls
docker network ls

# Should show NO pharmacy or agpk1-inventory related items
```

---

## 📋 QUICK COPY-PASTE COMMANDS

### For Your VPS (run this sequence):

```bash
# 1. Navigate to project
cd /var/www/agpk1-inventory

# 2. Stop everything
docker-compose down

# 3. Clean up old containers and volumes
docker container prune -f
docker volume prune -f

# 4. Start fresh
docker-compose up -d

# 5. Check status
docker-compose ps
```

---

## 🔍 TROUBLESHOOTING

### If you still get the conflict error:

```bash
# Find exactly which containers exist
docker ps -a | grep pharmacy

# Remove them directly
docker rm -f <CONTAINER_ID>

# Example:
docker rm -f b5bcfc0d055b
docker rm -f pharmacy_mongodb
```

### If MongoDB won't start (Permission denied):

```bash
# Fix volume permissions
sudo chown 999:999 /var/lib/docker/volumes/agpk1-inventory_mongodb_data/_data

# Try again
docker-compose restart mongodb
```

### If Nginx port 8089 already in use:

```bash
# Find what's using port 8089
sudo lsof -i :8089
# or
sudo netstat -tlnp | grep 8089

# Kill that process
sudo kill -9 <PID>

# Restart Docker
docker-compose restart nginx
```

---

## ✅ ONCE FIXED

1. Verify all containers running:
   ```bash
   docker-compose ps
   ```

2. Test local access:
   ```bash
   curl http://127.0.0.1:8089
   ```

3. Check logs:
   ```bash
   docker-compose logs -f
   ```

4. Proceed with reverse proxy configuration

---

## 🎯 SUMMARY

The error you saw is **temporary** and easily fixed:

✅ Run `docker-compose down`  
✅ Run `docker container prune -f`  
✅ Run `docker-compose up -d`  
✅ Verify with `docker-compose ps`  
✅ Done! Continue deployment  

**Estimated fix time: 2-3 minutes**

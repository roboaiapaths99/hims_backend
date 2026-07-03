# IT Administrator Setup Guide
## For System Administrators & IT Support Team

---

## System Architecture Overview

```
┌─────────────┐         ┌──────────────┐         ┌────────────────┐
│   Browser   │◄────────│ Frontend     │◄────────│ Backend API    │
│ (Port 4000) │ HTTP    │ (Next.js)    │ HTTP    │ (FastAPI)      │
└─────────────┘         └──────────────┘         │ (Port 8000)    │
                                                  └────────────────┘
                                                         │
                                    ┌────────────────────┼────────────────────┐
                                    │                    │                    │
                            ┌───────▼────────┐  ┌───────▼────────┐  ┌────────▼─────┐
                            │   MongoDB      │  │   Redis        │  │ File Storage │
                            │   (Database)   │  │   (Cache/Jobs) │  │ (Uploads)    │
                            └────────────────┘  └────────────────┘  └──────────────┘
```

---

## Initial Setup (Step-by-Step)

### Step 1: Server Requirements Check

**Before Installation:**
```powershell
# Check OS version
[System.Environment]::OSVersion.VersionString

# Check available disk space
Get-Volume | Where-Object {$_.DriveLetter -eq 'C'} | Select-Object SizeRemaining, Size

# Check RAM
Get-WmiObject Win32_ComputerSystem | Select-Object TotalPhysicalMemory

# Check CPU cores
Get-WmiObject Win32_Processor | Select-Object NumberOfCores
```

**Minimum Requirements:**
- Windows 7+ or Linux (Ubuntu 18.04+)
- 2 CPU cores
- 4GB RAM
- 50GB disk space
- Internet: 4+ Mbps

---

### Step 2: Install Prerequisites

#### On Windows:

**Install Python 3.11+**
```powershell
# Download from python.org
# Or use:
choco install python311  # If Chocolatey installed
```

**Install Node.js 18+**
```powershell
# Download from nodejs.org
# Or use:
choco install nodejs
```

**Verify installations:**
```powershell
python --version
node --version
npm --version
```

#### On Linux (Ubuntu):

```bash
# Update package list
sudo apt update

# Install Python 3.11
sudo apt install python3.11 python3.11-venv python3-pip

# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install nodejs

# Verify
python3 --version
node --version
```

---

### Step 3: Setup MongoDB Atlas

**Free Tier (Recommended for testing):**

1. Go to [mongodb.com](https://www.mongodb.com)
2. Sign up for free account
3. Create new cluster:
   - Provider: AWS (or preferred)
   - Region: Asia (ap-south-1 recommended for India)
4. Create database user:
   - Username: `pharmacy_admin`
   - Password: Generate strong password (save it!)
5. Add IP whitelist:
   - Click "Network Access"
   - Add your server IP
   - Or allow all: `0.0.0.0/0` (less secure)
6. Get connection string:
   - Click "Connect"
   - Choose "Connect your application"
   - Copy connection string
   - Replace `<username>` and `<password>`

**Connection String Format:**
```
mongodb+srv://pharmacy_admin:YOUR_PASSWORD@cluster.mongodb.net/pharmacy_erp?retryWrites=true&w=majority
```

---

### Step 4: Setup Redis Server

**Option A: Windows**

```powershell
# Install using WSL or use Docker
docker run -d -p 6379:6379 redis:alpine
```

**Option B: Linux**

```bash
# Install Redis
sudo apt install redis-server

# Start Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify
redis-cli ping  # Should return: PONG
```

**Option C: Use Managed Redis (Recommended for Production)**

- AWS ElastiCache
- Azure Cache for Redis
- DigitalOcean Managed Database
- Redis Cloud (free tier available)

---

### Step 5: Deploy Backend

```bash
# Navigate to backend directory
cd AGPK0NE_INVENTRY_ANAGEMENT/backend

# Create virtual environment
python -m venv venv

# Activate venv
# On Windows:
venv\Scripts\activate
# On Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Edit .env with your configuration
```

**Edit `.backend/.env`:**

```env
# Database
MONGODB_URI=mongodb+srv://pharmacy_admin:PASSWORD@cluster.mongodb.net/pharmacy_erp?retryWrites=true&w=majority

# JWT Security
JWT_SECRET=generate_a_random_key_here_minimum_32_characters
JWT_EXPIRY_HOURS=24

# Redis
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0

# Pharmacy Info (Update with your details)
PHARMACY_NAME=Your Pharmacy Name
PHARMACY_GSTIN=27AABCP1234A1Z5
PHARMACY_LICENSE=DL-MH-2024-001
PHARMACY_ADDRESS=Your Full Address
PHARMACY_PHONE=+91-9876543210
PHARMACY_EMAIL=info@yourpharmacy.com

# Application
DEBUG=False  # Set to True for development
ENVIRONMENT=production
API_HOST=0.0.0.0
API_PORT=8000

# File Storage
MAX_FILE_SIZE=10485760  # 10MB
UPLOAD_DIR=uploads

# Email (Optional, for alerts)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_specific_password
SMTP_USE_TLS=True
```

**Start Backend:**

```bash
# Development (with auto-reload)
uvicorn main:app --reload --port 8000

# Production
uvicorn main:app --port 8000 --workers 4 --loop uvloop
```

---

### Step 6: Deploy Frontend

```bash
# Navigate to frontend
cd AGPK0NE_INVENTRY_ANAGEMENT/frontend

# Install dependencies
npm install

# Create .env.local (if needed)
# Copy any environment variables

# Start dev server
npm run dev

# Build for production
npm run build
npm start
```

---

### Step 7: Using Docker (Recommended for Deployment)

**Install Docker:**

- Windows: Download Docker Desktop from docker.com
- Linux: `sudo apt install docker.io docker-compose`

**Deploy with Docker:**

```bash
cd AGPK0NE_INVENTRY_ANAGEMENT

# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

---

## User Management

### Create Admin User (First Time)

```python
# Run from backend directory:
cd backend

# Activate venv
source venv/bin/activate  # Linux
# Or: venv\Scripts\activate  # Windows

# Run user creation script
python create_user_direct.py

# Follow prompts:
# - Enter email
# - Enter password
# - Enter name
# - Choose role (admin)
```

### Create Other Users

**Via Application:**
1. Login as admin
2. Go to Settings → User Management
3. Click "Add User"
4. Fill details:
   - Email
   - Name
   - Role (Admin/Store Manager/Pharmacist/Cashier)
   - Store/Department
5. System sends invitation email

**Via Script:**
```python
python create_test_user.py
```

### User Roles & Permissions

| Role | Permissions | Use Case |
|------|------------|----------|
| **Admin** | Full access | System configuration, user mgmt |
| **Store Manager** | Inventory overview, approvals, reports | Store operations oversight |
| **Pharmacist** | Sales, stock check, dispense | Daily pharmacy operations |
| **Cashier** | POS only | Billing & payment processing |

---

## System Configuration

### Pharmacy Information

**Update these in `backend/.env`:**

```env
PHARMACY_NAME=Your Pharmacy Name Here
PHARMACY_GSTIN=27AABCP1234A1Z5  # Your GSTIN (13 digits)
PHARMACY_LICENSE=DL-MH-2024-001  # Your license number
PHARMACY_ADDRESS=Full Address including street, city, state, pin
PHARMACY_PHONE=+91-9876543210
PHARMACY_EMAIL=contact@yourpharmacy.com
```

### Security Settings

**JWT Secret Generation:**
```python
import secrets
print(secrets.token_urlsafe(32))
```

Copy output to `.env` as `JWT_SECRET`

### Email Configuration (Optional)

For appointment/alert notifications:

```env
# Gmail Setup:
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your.email@gmail.com
SMTP_PASSWORD=your_app_specific_password  # Not your Gmail password
SMTP_USE_TLS=True
```

**Get Gmail App Password:**
1. Enable 2FA on Gmail
2. Go to myaccount.google.com/apppasswords
3. Select Mail → Windows Computer
4. Copy generated password
5. Paste in `.env`

---

## Database Management

### MongoDB Backup

**Automatic Backups (MongoDB Atlas):**
- Enabled by default
- Can download from Atlas dashboard
- Kept for 30+ days

**Manual Backup:**
```bash
# Using mongodump
mongodump --uri="your_mongodb_connection_string" --out=./backup_$(date +%Y%m%d)

# Using MongoDB Atlas CLI
atlas backups create --clusterName pharmacy_erp
```

### Database Monitoring

**Check MongoDB Status:**
- Login to MongoDB Atlas dashboard
- View Metrics tab:
  - Connections
  - Operations/sec
  - CPU usage
  - Memory usage
  - Network I/O

### Database Optimization

```javascript
// Remove old/archived data monthly
db.transactions.deleteMany({
  created_at: {$lt: ISODate("2025-01-01")}
});

// Create indexes for faster queries
db.medicines.createIndex({medicine_code: 1});
db.sales.createIndex({created_at: -1});
```

---

## Monitoring & Maintenance

### Daily Tasks

```bash
# Check logs
docker-compose logs backend | tail -50
docker-compose logs frontend | tail -50

# Verify services running
docker ps

# Check disk space
df -h
```

### Weekly Tasks

- Review error logs
- Check database size
- Verify backups completed
- Monitor Redis memory usage

### Monthly Tasks

- Clean old logs
- Optimize database
- Review user access
- Check security updates
- Generate system health report

### System Health Check Script

```bash
#!/bin/bash
echo "System Health Check"
echo "===================="

# Check services
docker ps | grep pharmacy

# Check disk
df -h | grep -E "/$"

# Check memory
free -m | grep Mem

# Check MongoDB
mongosh --eval "db.adminCommand('ping')" 

# Check Redis
redis-cli ping

# Check logs for errors
docker-compose logs --tail=100 | grep -i error
```

---

## Troubleshooting

### Backend Won't Start

**Error: Port 8000 already in use**
```bash
# Find process using port
lsof -i :8000  # Linux
netstat -ano | findstr :8000  # Windows

# Kill process
kill -9 <PID>  # Linux
taskkill /PID <PID> /F  # Windows
```

**Error: Cannot connect to MongoDB**
```
- Verify connection string in .env
- Check IP whitelist in MongoDB Atlas
- Verify MongoDB Atlas cluster is active
- Check firewall rules
```

**Error: Missing module (import error)**
```bash
# Reinstall dependencies
pip install -r requirements.txt

# Or recreate venv
rm -rf venv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Frontend Won't Build

**Error: npm ERR!**
```bash
# Clear npm cache
npm cache clean --force

# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install

# Try build again
npm run build
```

### Database Connection Issues

**Test connection:**
```python
from pymongo import MongoClient
uri = "your_mongodb_uri"
client = MongoClient(uri)
print(client.list_database_names())  # Should show databases
```

### High Memory/CPU Usage

**Diagnosis:**
```bash
# Monitor processes
top -p $(pgrep -f uvicorn)  # Backend
top -p $(pgrep node)  # Frontend

# Check database connections
mongosh --eval "db.currentOp()"
```

**Solutions:**
- Increase server resources
- Optimize database queries
- Clear old data/logs
- Implement caching

---

## Performance Optimization

### Backend Optimization

```python
# In main.py
uvicorn main:app --workers 4 --loop uvloop --access-log
```

### Frontend Optimization

```bash
# Build optimized version
npm run build

# Use production build
npm start
```

### Database Optimization

```javascript
// Add indexes
db.medicines.createIndex({stock_level: 1});
db.sales.createIndex({sale_date: -1});
db.medicines.createIndex({category: 1, stock_level: 1});

// Remove unused indexes
db.collection.dropIndex("index_name");
```

### Redis Optimization

```bash
# Monitor Redis
redis-cli info stats
redis-cli info memory

# Clear cache if needed
redis-cli FLUSHALL
```

---

## Security Hardening

### For Production Deployment

**1. SSL/HTTPS Setup**
```bash
# Using Let's Encrypt (free)
sudo apt install certbot
certbot certonly --standalone -d yourpharmacy.com

# Configure in nginx
ssl_certificate /etc/letsencrypt/live/yourpharmacy.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/yourpharmacy.com/privkey.pem;
```

**2. Database Security**
- Use strong, random MongoDB password (24+ characters)
- Restrict IP access to known ranges
- Enable encryption at rest
- Use MongoDB backup encryption

**3. API Security**
- Change JWT_SECRET to strong random value
- Use HTTPS only
- Implement rate limiting
- Add CORS restrictions

**4. User Access Control**
- Enforce strong passwords
- Enable 2FA for admins
- Regular access reviews
- Audit log monitoring

---

## Backup & Disaster Recovery

### Backup Strategy

**Daily:**
- Automatic MongoDB Atlas backup

**Weekly:**
- Manual database export
- Application configuration backup

**Monthly:**
- Full system backup
- Archive to external storage

```bash
# Backup script
#!/bin/bash
BACKUP_DIR="/backups/pharmacy_$(date +%Y%m%d_%H%M%S)"
mkdir -p $BACKUP_DIR

# Backup database
mongodump --uri="$MONGODB_URI" --out=$BACKUP_DIR/db

# Backup configuration
cp -r /app/backend/.env $BACKUP_DIR/

# Upload to storage
aws s3 sync $BACKUP_DIR s3://your-backup-bucket/

echo "Backup complete: $BACKUP_DIR"
```

### Restore from Backup

```bash
# Restore database
mongorestore --uri="your_mongodb_uri" /path/to/backup/db

# Verify restoration
mongosh --eval "db.medicines.countDocuments()"
```

---

## Updating & Patching

### Check for Updates

```bash
# Backend dependencies
pip list --outdated

# Frontend dependencies
npm outdated
```

### Apply Updates

```bash
# Backend
pip install -r requirements.txt --upgrade

# Frontend
npm update
npm audit fix
```

### Test Before Production

1. Update in staging environment first
2. Run full test suite
3. Check for breaking changes
4. Schedule production update during low-traffic time

---

## Support & Escalation

### Support Channels

1. **Email**: support@pharmacyerp.com
2. **Phone**: +91-XXXX-XXXX-XX
3. **Community Forum**: forum.pharmacyerp.com
4. **Emergency**: emergency@pharmacyerp.com

### Required Info for Support Tickets

- System version
- Error message (exact)
- Steps to reproduce
- Logs (from docker-compose logs)
- Server specs
- Network configuration

---

## Additional Resources

- **API Documentation**: http://your-server:8000/docs
- **Database Docs**: mongodb.com/docs
- **FastAPI Docs**: fastapi.tiangolo.com
- **Next.js Docs**: nextjs.org
- **Docker Docs**: docker.com/docs

---

**Last Updated**: May 2026
**Version**: 1.0.0

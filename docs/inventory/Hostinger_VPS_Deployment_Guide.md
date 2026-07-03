# Hostinger VPS Shared Deployment Guide

## Overview
This guide provides the exact steps to deploy the Inventory Management System on your Hostinger VPS. Because you already have multiple websites running, your server's ports 80 (HTTP) and 443 (HTTPS) are already in use by Hostinger's main web server (such as Apache, Nginx, LiteSpeed, or CyberPanel).

We have configured `docker-compose.yml` to run the application internally on port `8089` by default (which can be customized by setting `NGINX_PORT` in your `.env` file). Your Hostinger web server will act as a "Reverse Proxy" to securely route traffic from your domain (`inventory.agpkacademy.in`) to the Docker containers.

## Step 1: Upload Files to your VPS
1. Connect to your VPS via SSH or Hostinger's File Manager.
2. Clone or upload this entire `Inventory_management_system` folder to a directory on your server (e.g., `/var/www/inventory` or `/root/inventory`).

## Step 2: Configure Environment Variables
1. Navigate to the uploaded folder via SSH.
2. The `deploy.sh` script will automatically copy `.env.example` to `.env` if it doesn't exist, but you can do it manually:
   ```bash
   cp .env.example .env
   ```
3. Edit the `.env` file with your specific production values:
   - Provide a strong `MONGO_ROOT_PASSWORD`.
   - Update the `SECRET_KEY` with a random string.
   - Adjust `NEXT_PUBLIC_API_URL` to match your domain (e.g., `https://inventory.agpkacademy.in/api`).

## Step 3: Start the Docker Containers
1. Ensure Docker and Docker Compose are installed on your VPS.
2. From within the project directory, run:
   ```bash
   ./deploy.sh
   ```
   *(Or manually run `docker-compose up -d --build`)*
3. Check the status to ensure all containers (`frontend`, `backend`, `mongodb`, `redis`, `celery_worker`, `celery_beat`, `nginx`) are running:
   ```bash
   docker-compose ps
   ```

## Step 4: Configure the Hostinger Web Server (Reverse Proxy)
You must tell the main web server on your Hostinger VPS to route traffic for your domain to the Docker container running on port `8089` (or the port defined by `NGINX_PORT` in `.env`).

### Option A: If using CyberPanel / OpenLiteSpeed
1. Go to your CyberPanel Dashboard.
2. Navigate to **Websites -> Create Website** and create `inventory.agpkacademy.in` if you haven't already.
3. Go to **List Websites -> Manage** for your domain.
4. Scroll down and click **Rewrite Rules** or **vHost Conf**.
5. Add the following Proxy context to route all traffic to port `8089`:
   ```
   extprocessor dockerproxy {
     type proxy
     address 127.0.0.1:8089
     maxConns 100
     pcKeepAliveTimeout 60
     initTimeout 60
     retryTimeout 0
     respBuffer 0
   }
   ```
6. And in the rewrite rules:
   ```
   RewriteRule ^(.*)$ http://dockerproxy/$1 [P,L,E=Proxy-Host:inventory.agpkacademy.in]
   ```
7. Issue an SSL certificate from the CyberPanel SSL menu.

### Option B: If using Nginx (Directly or via hPanel)
1. Add a new server block configuration for your domain (e.g., in `/etc/nginx/sites-available/inventory` or via Hostinger's custom dashboard for Nginx proxying).
2. Set up the configuration like this:
   ```nginx
   server {
       listen 80;
       server_name inventory.agpkacademy.in;
       
       # Hostinger Certbot will automatically rewrite this to handle HTTPS.
       location / {
           proxy_pass http://127.0.0.1:8089;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```
3. Use Certbot on the host to generate SSL: `sudo certbot --nginx -d inventory.agpkacademy.in`
4. Restart Nginx: `sudo systemctl restart nginx`

### Option C: If using Apache (Directly or via cPanel/Webuzo)
1. In cPanel/Webuzo, go to Apache proxy/Reverse Proxy settings, OR edit your virtual host configuration.
2. Add the ProxyPass directives:
   ```apache
   <VirtualHost *:443>
       ServerName inventory.agpkacademy.in
       
       # Ensure you have SSL certificates configured here
       
       ProxyPreserveHost On
       ProxyPass / http://127.0.0.1:8089/
       ProxyPassReverse / http://127.0.0.1:8089/
   </VirtualHost>
   ```
3. Restart Apache.

## Step 5: Verify Deployment
1. Go to `https://inventory.agpkacademy.in`.
2. The frontend should load securely via HTTPS.
3. API requests to `https://inventory.agpkacademy.in/api/...` will automatically route to the FastAPI backend without interfering with your other websites.

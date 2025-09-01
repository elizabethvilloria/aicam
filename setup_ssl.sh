#!/bin/bash
# SSL Setup Script for E-Trike Dashboard

echo "🔒 Setting up HTTPS for E-Trike Dashboard"

# Check if running on server
if [ ! -f "/etc/os-release" ]; then
    echo "❌ This script must be run on your Google Cloud server"
    exit 1
fi

# Update system packages
echo "📦 Updating system packages..."
sudo apt update

# Install required packages
echo "🔧 Installing SSL tools..."
sudo apt install -y certbot python3-certbot-nginx nginx

# Stop any running dashboard
echo "⏹️  Stopping dashboard if running..."
sudo pkill -f "python.*dashboard.py" || true

# Configure nginx for E-Trike
echo "⚙️  Configuring Nginx..."
sudo tee /etc/nginx/sites-available/etrike > /dev/null <<EOF
server {
    listen 80;
    server_name etrikedashboard.com;
    
    location / {
        proxy_pass http://localhost:5001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Enable nginx site
sudo ln -sf /etc/nginx/sites-available/etrike /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Get SSL certificate
echo "🔐 Getting SSL certificate..."
sudo certbot --nginx -d etrikedashboard.com --non-interactive --agree-tos --email admin@etrikedashboard.com

# Open firewall for HTTPS
echo "🔥 Opening firewall for HTTPS..."
gcloud compute firewall-rules create allow-https --allow tcp:443 --source-ranges 0.0.0.0/0 2>/dev/null || echo "HTTPS firewall rule already exists"

echo "✅ SSL setup complete!"
echo ""
echo "🌐 Your dashboard is now available at:"
echo "   https://etrikedashboard.com"
echo ""
echo "📝 Next steps:"
echo "1. Start your dashboard: python3 dashboard.py"
echo "2. Test HTTPS access in browser"
echo "3. Update Pi sync to use HTTPS URL"

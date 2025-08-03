import os

# Configuration for QR Code URLs
# Set this environment variable to your production domain
# Example: export BASE_URL="https://yourdomain.com"
# For local development, leave it unset to use localhost

BASE_URL = os.environ.get('BASE_URL', None)

# Instructions for setting up QR codes:
# 1. For local development: Leave BASE_URL unset (will use localhost)
# 2. For production: Set BASE_URL environment variable to your domain
# 3. For testing: You can set BASE_URL to any valid URL

# Examples:
# export BASE_URL="https://yourcompany.com"
# export BASE_URL="https://tracking.yourdomain.com"
# export BASE_URL="http://192.168.1.100:5000"  # For local network access 
# Asset Tracking System

A comprehensive web-based asset tracking system built with Flask, featuring QR code generation, user authentication, and organizational management.

## 🚀 Features

### Core Functionality
- **Asset Management**: Add, edit, delete, and track assets with unique QR codes
- **QR Code Generation**: Automatic QR code generation for individual assets and departments
- **User Authentication**: Secure login system with role-based access control
- **Organizational Structure**: Manage buildings, departments, and users
- **Bulk Operations**: Bulk delete and status updates for multiple assets
- **Search & Filter**: Advanced filtering and search capabilities

### User Roles
- **Admin**: Full access to all features including user management
- **Purchasing**: Asset management and tracking capabilities

### Security Features
- Password encryption using Fernet (cryptography)
- Password hashing with SHA-256
- Role-based access control
- Secure session management

## 🛠️ Technology Stack

- **Backend**: Flask (Python)
- **Database**: SQLite
- **Authentication**: Flask-Login
- **QR Codes**: qrcode library
- **Frontend**: HTML, CSS, JavaScript, Bootstrap
- **Encryption**: cryptography (Fernet)

## 📋 Prerequisites

- Python 3.7+
- pip (Python package installer)

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Jaypeeeee6/Asset-Tracking-System.git
   cd Asset-Tracking-System
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   python app.py
   ```

4. **Access the application**
   - Open your browser and go to `http://localhost:5000`
   - The login page will be the landing page

## 🔧 Initial Setup

### First Time Setup
1. Run the application for the first time to create the database
2. Use the provided script to create your first admin user:
   ```bash
   python create_first_admin.py
   ```
3. Follow the prompts to create your admin account

### Database Structure
The system automatically creates the following tables:
- `users_auth`: User authentication and roles
- `assets`: Asset information and tracking
- `buildings`: Building management
- `departments`: Department management
- `users`: User profiles and assignments

## 📱 Usage

### Login
- Visit the application URL
- Login page is the landing page
- Use your admin credentials to access the system

### Asset Management
1. **Add Assets**: Use the "Add Asset" form to create new assets
2. **View Assets**: Browse all assets with filtering and search options
3. **QR Codes**: Generate QR codes for individual assets or departments
4. **Bulk Operations**: Select multiple assets for bulk operations

### Organization Management
- **Buildings**: Add and manage buildings
- **Departments**: Create departments within buildings
- **Users**: Manage user accounts and assignments

### QR Code Features
- **Individual Assets**: Scan QR codes to view asset details
- **Department QR Codes**: Scan to view all assets in a department
- **Mobile Friendly**: QR codes work on mobile devices

## 🔐 Security

### Password Management
- Passwords are encrypted using Fernet encryption
- Password hashes are stored for verification
- Admin users can recover passwords using the forgot password feature

### Access Control
- Role-based permissions
- Session management with Flask-Login
- Secure redirects and authentication checks

## 📁 Project Structure

```
Asset-Tracking-System/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── README.md             # Project documentation
├── .gitignore            # Git ignore rules
├── static/               # Static files (CSS, images)
│   ├── style.css
│   └── MAA_Logo.png
├── templates/            # HTML templates
│   ├── login.html        # Login page (landing page)
│   ├── index.html        # Main dashboard
│   ├── add_asset.html    # Asset addition form
│   ├── add_user.html     # User management
│   ├── manage_users.html # User listing
│   └── ...
└── login_system/         # Authentication system files
    ├── decrypt_password.py
    ├── encryption_key.key
    └── LOGIN_SYSTEM_README.md
```

## 🔧 Configuration

### Database
- SQLite database (`production_assets.db`) is created automatically
- No manual database setup required

### Encryption
- Encryption key is stored in `login_system/encryption_key.key`
- Key is generated automatically on first run

### Network Access
- Default: `http://localhost:5000`
- For network access: `http://192.168.100.20:5000`

## 🚀 Deployment

### Local Development
```bash
python app.py
```

### Production Considerations
- Use a production WSGI server (Gunicorn, uWSGI)
- Set up proper SSL/TLS certificates
- Configure environment variables for sensitive data
- Use a production database (PostgreSQL, MySQL)

## 📝 API Endpoints

### Authentication
- `GET/POST /` - Login page and authentication
- `GET /logout` - User logout
- `GET /forgot_password` - Password recovery (admin only)

### Asset Management
- `GET /dashboard` - Main asset dashboard
- `POST /add` - Add new asset
- `POST /delete/<id>` - Delete asset
- `POST /update_status/<id>` - Update asset status

### Organization Management
- `GET/POST /buildings` - Building management
- `GET/POST /departments` - Department management
- `GET/POST /users` - User management

### QR Code Generation
- `GET /qrcode/<id>` - Individual asset QR code
- `GET /department_qr/<building>/<department>` - Department QR code

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

## 👨‍💻 Author

**Jaypeeeee6**
- GitHub: [@Jaypeeeee6](https://github.com/Jaypeeeee6)
- Repository: [Asset-Tracking-System](https://github.com/Jaypeeeee6/Asset-Tracking-System)

## 🆘 Support

If you encounter any issues or have questions:
1. Check the [Issues](https://github.com/Jaypeeeee6/Asset-Tracking-System/issues) page
2. Create a new issue with detailed information
3. Include system information and error messages

---

**Note**: This system is designed for internal asset tracking and should be deployed in a secure environment with proper access controls. 
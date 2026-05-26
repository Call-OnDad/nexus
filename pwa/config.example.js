// NEXUS Configuration Template
// 1. Copy this file to config.js:  cp config.example.js config.js
// 2. Fill in YOUR values below
// 3. config.js is in .gitignore and will not be committed

window.NEXUS_CONFIG = {
  // Local IP and port of your NEXUS Flask API server (CT117 or wherever api_server.py runs)
  // Example: 'http://192.168.1.100:5000'
  localUrl: 'http://YOUR_SERVER_IP:5000',

  // Public HTTPS URL for when you're away from home (optional but recommended)
  // Example: 'https://nexus.yourdomain.com'
  externalUrl: 'https://YOUR_NEXUS_DOMAIN',
};

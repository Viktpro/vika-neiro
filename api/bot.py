{
  "functions": {
    "api/bot.py": {
      "runtime": "python3.9"
    }
  },
  "routes": [
    {
      "src": "/webhook",
      "dest": "/api/bot.py"
    },
    {
      "src": "/",
      "dest": "/api/bot.py"
    }
  ]
}
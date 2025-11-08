# Massachusetts Lease Analyzer

AI-powered lease analysis using RAG and Massachusetts housing laws.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# 2. Set up environment variables
# Create .env file with:
GEMINI_API_KEY=your_key
SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_USER=your_user
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_WAREHOUSE=your_warehouse
SNOWFLAKE_DATABASE=your_database
SNOWFLAKE_SCHEMA=your_schema

# 3. Start the server
cd app
python server.py

# 4. Open the app
# Navigate to: http://localhost:8000/app
# API docs at: http://localhost:8000/docs
```

That's it! 🎉


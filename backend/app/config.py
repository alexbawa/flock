import os


class Config:
    AMADEUS_CLIENT_ID = os.environ["AMADEUS_CLIENT_ID"]
    AMADEUS_CLIENT_SECRET = os.environ["AMADEUS_CLIENT_SECRET"]
    SUPABASE_DB_URL = os.environ["SUPABASE_DB_URL"]
    REDIS_URL = os.environ["REDIS_URL"]

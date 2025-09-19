# framework/secrets.py
import os
from dotenv import load_dotenv, find_dotenv

def get_env(name: str) -> str:
    load_dotenv(find_dotenv())
    v = os.getenv(name)
    if not v:
        return None
        # raise RuntimeError(f"Missing env: {name}")
    return v


if __name__ == "__main__":
    print(get_env("TUSHARE_TOKEN"))
from infrared_sdk import InfraredClient
import os

_client = None

async def get_infrared_client() -> InfraredClient:
    """Get or initialize the Infrared client."""
    global _client
    if _client is None:
        api_key = os.getenv("INFRARED_API_KEY")
        if not api_key or api_key == "your-infrared-api-key-here":
            raise ValueError(
                "INFRARED_API_KEY not configured. "
                "Please set it in backend/.env file."
            )
        print(f"\n=== INITIALIZING INFRARED CLIENT ===")
        print(f"API Key: {api_key[:10]}...{api_key[-10:]}")
        print(f"Key Length: {len(api_key)}")
        print(f"Base URL: https://api.infrared.city/v2")
        print(f"=== END INIT ===\n")
        _client = InfraredClient(api_key=api_key)
    return _client

def close_infrared_client():
    """Close the Infrared client connection."""
    global _client
    if _client:
        _client.close()
        _client = None

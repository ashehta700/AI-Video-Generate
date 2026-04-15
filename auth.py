from google_auth_oauthlib.flow import InstalledAppFlow

scopes = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",
    scopes=scopes
)

creds = flow.run_local_server(
    host="localhost",
    port=8080,
    prompt="consent"
)

print("REFRESH TOKEN:", creds.refresh_token)
import os, anthropic
client = anthropic.Anthropic()

vault = client.beta.vaults.create(display_name="trip-planner")
client.beta.vaults.credentials.create(
    vault_id=vault.id,
    display_name="Firecrawl",
    auth={
        "type": "static_bearer",
        "mcp_server_url": "https://mcp.firecrawl.dev/v2/mcp",
        "token": os.environ["FIRECRAWL_API_KEY"],
    },
)
print("VAULT_ID =", vault.id)

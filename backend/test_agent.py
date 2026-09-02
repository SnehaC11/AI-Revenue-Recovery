from agents.recovery_agent import client


response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Reply with exactly: RecoverAI is working."
)

print(response.text)
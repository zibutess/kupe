import os, anthropic
client = anthropic.Anthropic()

def plan_trip(request: str) -> str:
    session = client.beta.sessions.create(
        agent=os.environ["AGENT_ID"],
        environment_id=os.environ["ENVIRONMENT_ID"],
        vault_ids=[os.environ["VAULT_ID"]],
        title="Trip plan",
    )
    out = []
    with client.beta.sessions.events.stream(session.id) as stream:
        client.beta.sessions.events.send(
            session.id,
            events=[{"type": "user.message",
                     "content": [{"type": "text", "text": request}]}],
        )
        for event in stream:
            print("EVENT:", event.type)   # temporary: shows progress and helps debugging
            if event.type == "agent.message":
                out += [b.text for b in event.content if b.type == "text"]
            elif event.type == "session.status_idle":
                break
    return "".join(out)

if __name__ == "__main__":
    print(plan_trip("Vilnius to Prague, 3 nights from 20 Dec, cheapest route, hotel near the station"))

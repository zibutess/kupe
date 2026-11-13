import os, json, anthropic
from agent.transit import TOOL_HANDLERS

client = anthropic.Anthropic()
MAX_TOOL_CALLS = 4  # caps Google spend per request


def plan_trip(request: str) -> str:
    session = client.beta.sessions.create(
        agent=os.environ["AGENT_ID"],
        environment_id=os.environ["ENVIRONMENT_ID"],
        vault_ids=[os.environ["VAULT_ID"]],
        title="Trip plan",
    )
    out, pending, calls = [], {}, 0

    with client.beta.sessions.events.stream(session.id) as stream:
        client.beta.sessions.events.send(
            session.id,
            events=[{"type": "user.message",
                     "content": [{"type": "text", "text": request}]}],
        )
        for event in stream:
            print("EVENT:", event.type)  # temporary: shows progress and helps debugging

            if event.type == "agent.message":
                out += [b.text for b in event.content if b.type == "text"]

            elif event.type == "agent.custom_tool_use":
                pending[event.id] = event

            elif event.type == "session.status_idle":
                if event.stop_reason.type == "requires_action":
                    results = []
                    for eid in event.stop_reason.event_ids:
                        ev = pending.get(eid)
                        if ev is None:
                            continue
                        calls += 1
                        handler = TOOL_HANDLERS.get(ev.name)
                        if calls > MAX_TOOL_CALLS:
                            data = {"error": "tool call budget reached"}
                        elif handler:
                            data = handler(**ev.input)
                        else:
                            data = {"error": f"unknown tool {ev.name}"}
                        results.append({
                            "type": "user.custom_tool_result",
                            "custom_tool_use_id": eid,
                            "content": [{"type": "text", "text": json.dumps(data)}],
                        })
                    if results:
                        client.beta.sessions.events.send(session.id, events=results)
                    continue
                break
    return "".join(out)


if __name__ == "__main__":
    print(plan_trip("How do I get from Vilnius railway station to Vilnius Cathedral by public transport, leaving at 9am tomorrow?"))  # replace with your original line

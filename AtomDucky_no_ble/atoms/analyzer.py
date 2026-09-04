# analyzer.py

def analyze_payload_stream(payload):
    if isinstance(payload, bytes):
        payload = payload.decode()
    i = 0
    while i < len(payload):
        # Escape: backslash before < > or \ (so they are not treated as tags)
        if payload[i] == "\\" and i + 1 < len(payload) and payload[i+1] in "<>\\":
            yield payload[i+1]
            i += 2
            continue
        if payload[i] == "<":
            end_index = payload.find(">", i)
            if end_index != -1 and " " not in payload[i+1:end_index]:
                yield payload[i:end_index+1]
                i = end_index + 1
                continue
        yield payload[i]
        i += 1
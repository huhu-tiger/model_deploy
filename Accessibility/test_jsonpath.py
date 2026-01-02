from jsonpath_ng import parse
import json

data = {
    "data": [
        {
            "audio_url": "http://old.com/1.mp3",
            "image_url": "http://old.com/1.jpg"
        },
        {
            "audio_url": "http://old.com/2.mp3",
            "image_url": "http://old.com/2.jpg"
        }
    ]
}

paths = ["$.data[*].audio_url", "$.data[*].image_url"]
url_map = {
    "http://old.com/1.mp3": "http://new.com/1.mp3",
    "http://old.com/1.jpg": "http://new.com/1.jpg",
    "http://old.com/2.mp3": "http://new.com/2.mp3",
    "http://old.com/2.jpg": "http://new.com/2.jpg"
}

all_matches = []
for p in paths:
    expr = parse(p)
    matches = expr.find(data)
    all_matches.extend(matches)

print(f"Found {len(all_matches)} matches")

for match in all_matches:
    if match.value in url_map:
        new_url = url_map[match.value]
        print(f"Updating {match.value} -> {new_url}")
        
        # In-place update logic matching api.py
        if match.context is not None:
            container = match.context.value
            updated = False
            if isinstance(container, dict):
                for k, v in container.items():
                    if v == match.value:
                        container[k] = new_url
                        updated = True
            elif isinstance(container, list):
                for i, v in enumerate(container):
                    if v == match.value:
                        container[i] = new_url
                        updated = True


print(json.dumps(data, indent=2))

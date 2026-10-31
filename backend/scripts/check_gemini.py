"""Probe the configured model using a synthetic prompt, without customer data."""
import httpx
from backend.app.core.config import settings


def main(model=None):
    model = (model or settings.GEMINI_MODEL).removeprefix('models/')
    response = httpx.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        headers={'x-goog-api-key': settings.GEMINI_API_KEY},
        json={'contents': [{'parts': [{'text': 'Reply with the single word OK.'}]}],
              'generationConfig': {'maxOutputTokens': 128, 'temperature': 0}},
        timeout=20,
    )
    print('Configured model:', model)
    print('Generation HTTP:', response.status_code)
    body = response.json()
    candidates = body.get('candidates', [])
    if response.status_code != 200:
        # Print the error code only: response messages may contain account information.
        print('Provider error:', body.get('error', {}).get('status', 'unknown'))
        raise SystemExit(1)
    text = ''.join(p.get('text', '') for c in candidates
                   for p in c.get('content', {}).get('parts', []) if not p.get('thought'))
    print('Received text:', bool(text.strip()))
    if not text.strip():
        raise SystemExit(1)


if __name__ == '__main__':
    main()

"""Read-only provider model discovery. No generation or trading calls live here."""

import re

import httpx


_MODEL_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}\Z')
_ENDPOINTS = {
    'openai': 'https://api.openai.com/v1/models',
    'anthropic': 'https://api.anthropic.com/v1/models',
    'gemini': 'https://generativelanguage.googleapis.com/v1beta/models',
}
_MALFORMED = 'AI 제공자의 모델 목록 응답을 확인할 수 없습니다.'


class ProviderError(Exception):
    """An AI provider failure whose message is safe to display."""


class ReportValidationError(ProviderError):
    """A validated model draft failed local evidence checks, after token usage."""
    def __init__(self, issue, usage):
        self.issue=issue
        self.usage=usage
        super().__init__(f"AI 응답의 재무 비교 근거를 확인해야 합니다: {issue['code']} · {issue['account']}. {issue['reason']} 아래 검증 상세를 확인하세요.")


def list_models(provider: str, key: str, *, http=None) -> list[dict[str, str]]:
    """Return model candidates, without claiming generation access or testing billing.

    ``http`` may be a synchronous httpx.Client for transport injection. The caller
    owns injected clients; this function closes clients it creates. Pagination is
    limited to ten pages of at most 1000 rows, and every request has a 15s timeout.
    """
    if not isinstance(provider, str) or provider not in _ENDPOINTS:
        raise ProviderError('지원하지 않는 AI 제공자입니다.')
    if (not isinstance(key, str) or not 1 <= len(key) <= 8192
            or not all(33 <= ord(char) <= 126 for char in key)):
        raise ProviderError('API 키 형식을 확인해 주세요.')

    if http is None:
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            return _list_models(provider, key, client)
    return _list_models(provider, key, http)


def _list_models(provider, key, http):
    headers = {'accept': 'application/json'}
    params = {}
    if provider == 'openai':
        headers['authorization'] = 'Bearer ' + key
    elif provider == 'anthropic':
        headers.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
        params['limit'] = 1000
    else:
        headers['x-goog-api-key'] = key
        params['pageSize'] = 1000

    models, model_ids, cursors = [], set(), set()
    for _ in range(10):
        payload = _get_page(http, _ENDPOINTS[provider], headers, params)
        rows = payload.get('models' if provider == 'gemini' else 'data')
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ProviderError(_MALFORMED)
        for row in rows:
            model = _model_candidate(provider, key, row)
            if model is not None and model['id'] not in model_ids:
                models.append(model)
                model_ids.add(model['id'])

        if provider == 'openai':
            return models
        if provider == 'anthropic':
            more = payload.get('has_more')
            if not isinstance(more, bool):
                raise ProviderError(_MALFORMED)
            if not more:
                return models
            cursor = payload.get('last_id')
            cursor_param = 'after_id'
        else:
            cursor = payload.get('nextPageToken', '')
            if cursor == '':
                return models
            cursor_param = 'pageToken'
        # Cursor strings are sent only as encoded query values to the fixed host.
        # Reject echoed credentials before they could enter a URL or HTTP log.
        if (not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048
                or not all(33 <= ord(char) <= 126 for char in cursor)
                or key in cursor or cursor in cursors):
            raise ProviderError(_MALFORMED)
        if provider == 'anthropic' and not _MODEL_ID.fullmatch(cursor):
            raise ProviderError(_MALFORMED)
        cursors.add(cursor)
        params[cursor_param] = cursor
    raise ProviderError('모델 목록이 조회 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.')


def _get_page(http, url, headers, params):
    try:
        response = http.get(url, headers=headers, params=params, timeout=15,
                            follow_redirects=False)
    except httpx.HTTPError:
        raise ProviderError('AI 제공자에 연결할 수 없습니다. 네트워크를 확인해 주세요.') from None
    if response.status_code in (401, 403):
        raise ProviderError('API 키 또는 모델 목록 조회 권한을 확인해 주세요.')
    if response.status_code == 429:
        raise ProviderError('AI 제공자의 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.')
    if response.status_code != 200:
        raise ProviderError('AI 제공자의 모델 목록 조회에 실패했습니다.')
    if len(response.content) > 2 * 1024 * 1024:
        raise ProviderError(_MALFORMED)
    try:
        payload = response.json()
    except (ValueError, UnicodeError):
        raise ProviderError(_MALFORMED) from None
    if not isinstance(payload, dict):
        raise ProviderError(_MALFORMED)
    return payload


def _model_candidate(provider, key, row):
    if not isinstance(row, dict):
        raise ProviderError(_MALFORMED)
    model_id = row.get('name' if provider == 'gemini' else 'id')
    if provider == 'gemini' and isinstance(model_id, str) and model_id.startswith('models/'):
        model_id = model_id[len('models/'):]
    if (not isinstance(model_id, str) or not _MODEL_ID.fullmatch(model_id)
            or key in model_id):
        raise ProviderError(_MALFORMED)
    name_field = {'openai': 'id', 'anthropic': 'display_name', 'gemini': 'displayName'}[provider]
    name = row.get(name_field, model_id)
    if not isinstance(name, str) or key in name:
        raise ProviderError(_MALFORMED)
    if not name.strip() or len(name) > 160 or not name.isprintable():
        name = model_id

    if provider == 'openai':
        # Naming-based candidates: listing alone cannot prove endpoint access.
        if (not (model_id.startswith('gpt-') or re.match(r'o\d+(?:-|$)', model_id))
                or any(part in model_id.lower() for part in
                       ('audio', 'realtime', 'tts', 'image', 'embedding', 'transcribe'))):
            return None
    elif provider == 'anthropic':
        if not model_id.startswith('claude-'):
            return None
    else:
        methods = row.get('supportedGenerationMethods', [])
        if not isinstance(methods, list) or not all(isinstance(method, str) for method in methods):
            raise ProviderError(_MALFORMED)
        if 'generateContent' not in methods:
            return None
    return {'id': model_id, 'name': name}

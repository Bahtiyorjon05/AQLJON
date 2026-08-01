import logging
import threading
from collections import OrderedDict

from modules.config import Config

logger = logging.getLogger(__name__)

_USE_NEW = False
_genai_new = None
_genai_legacy = None

# ─── 🔑 API Key Pool ───────────────────────────────────────────
# Multiple free-tier keys are rotated automatically when one hits its quota,
# which multiplies the daily request budget without any paid plan.
_keys: list[str] = []
_clients: dict[int, object] = {}
_key_index = 0
_lock = threading.Lock()

# Uploaded files live inside the Google project that owns the uploading key, so
# every later call touching a file must reuse that same key. Name -> key index.
_file_keys: "OrderedDict[str, int]" = OrderedDict()
_MAX_TRACKED_FILES = 500


def _load_library():
    global _USE_NEW, _genai_new, _genai_legacy
    if _genai_new or _genai_legacy:
        return
    try:
        from google import genai as genai_new
    except ImportError:
        genai_new = None
    if genai_new is not None:
        _genai_new = genai_new
        _USE_NEW = True
        return
    try:
        import google.generativeai as genai_legacy
    except ImportError as exc:
        raise ImportError("Missing Gemini SDK. Install google-genai.") from exc
    _genai_legacy = genai_legacy
    _USE_NEW = False


def _load_keys() -> list[str]:
    global _keys
    if _keys:
        return _keys
    _keys = Config.GEMINI_KEYS
    if not _keys:
        raise ValueError("No Gemini API keys configured")
    logger.info("Gemini key pool initialised with %d key(s)", len(_keys))
    return _keys


def key_count() -> int:
    """Number of configured API keys (used for logging/diagnostics)."""
    try:
        return len(_load_keys())
    except ValueError:
        return 0


def _client_for(index: int):
    """Return the SDK client bound to the key at `index`."""
    _load_library()
    key = _load_keys()[index]
    if _USE_NEW:
        client = _clients.get(index)
        if client is None:
            client = _genai_new.Client(api_key=key)
            _clients[index] = client
        return client
    # The legacy SDK keeps the key in module-global state, so it must be
    # reconfigured on every switch rather than cached per key.
    _genai_legacy.configure(api_key=key)
    return _genai_legacy


def _current_index() -> int:
    with _lock:
        return _key_index


def _is_quota_error(exc: Exception) -> bool:
    """True when the failure is quota/rate-limit related, i.e. worth another key."""
    message = str(exc).lower()
    return (
        "429" in message
        or "resource_exhausted" in message
        or "resource exhausted" in message
        or "quota" in message
        or "rate limit" in message
        or "ratelimit" in message
        or "too many requests" in message
    )


def _rotate_key(exhausted_index: int) -> bool:
    """Advance past `exhausted_index`. False when there is nowhere to rotate to."""
    global _key_index
    keys = _load_keys()
    if len(keys) < 2:
        return False
    with _lock:
        # Another thread may have already rotated off this key; adopt its choice
        # instead of skipping a key that was never tried.
        if _key_index != exhausted_index:
            return True
        _key_index = (_key_index + 1) % len(keys)
        new_index = _key_index
    logger.warning(
        "Gemini key #%d hit its quota; switching to key #%d",
        exhausted_index + 1,
        new_index + 1,
    )
    return True


def _call_with_rotation(func, pin_index: int | None = None):
    """
    Run `func(client)`, moving to the next API key on quota errors.

    `pin_index` forces a specific key and disables rotation — required for calls
    that reference an uploaded file, which only exists under its own key.
    Each key is tried at most once, so an exhausted pool raises rather than loops.
    """
    if pin_index is not None:
        return func(_client_for(pin_index))

    keys = _load_keys()
    last_exc: Exception | None = None
    for _ in range(len(keys)):
        index = _current_index()
        try:
            return func(_client_for(index))
        except Exception as exc:
            last_exc = exc
            if not _is_quota_error(exc) or not _rotate_key(index):
                raise
    logger.error("All %d Gemini key(s) are exhausted", len(keys))
    raise last_exc  # type: ignore[misc]


def _remember_file(file_obj, index: int):
    """Pin an uploaded file to the key that created it."""
    name = getattr(file_obj, "name", None)
    if not name:
        return
    with _lock:
        _file_keys[name] = index
        _file_keys.move_to_end(name)
        while len(_file_keys) > _MAX_TRACKED_FILES:
            _file_keys.popitem(last=False)


def _key_for_file(name: str | None) -> int | None:
    if not name:
        return None
    with _lock:
        return _file_keys.get(name)


def _pinned_index_for(contents) -> int | None:
    """
    Find the key that owns any uploaded file referenced by `contents`.

    Handlers pass prompts as `[instruction, uploaded_file]`, so this walks the
    payload looking for a tracked file name.
    """
    if contents is None or isinstance(contents, (str, bytes)):
        return None
    items = contents if isinstance(contents, (list, tuple)) else [contents]
    for item in items:
        index = _key_for_file(getattr(item, "name", None))
        if index is not None:
            return index
    return None


def _is_model_unavailable_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "not found for api version" in message
        or "not supported for generatecontent" in message
        or ("model" in message and "not found" in message)
    )


class _BaseModelAdapter:
    """Shared model-fallback behaviour for both SDK generations."""

    def __init__(self, model_name: str, fallback_name: str | None = None):
        self._model_name = model_name
        self._fallback_name = fallback_name
        self._current_name = model_name

    def _maybe_fallback(self, exc: Exception) -> bool:
        if not self._fallback_name or self._current_name == self._fallback_name:
            return False
        if not _is_model_unavailable_error(exc):
            return False
        logger.warning(
            "Gemini model %s unavailable; falling back to %s",
            self._current_name,
            self._fallback_name,
        )
        self._current_name = self._fallback_name
        return True

    def _invoke(self, client, contents):
        raise NotImplementedError

    def generate_content(self, contents):
        pin = _pinned_index_for(contents)

        def call(client):
            return self._invoke(client, contents)

        try:
            return _call_with_rotation(call, pin_index=pin)
        except Exception as exc:
            if self._maybe_fallback(exc):
                return _call_with_rotation(call, pin_index=pin)
            raise


class GeminiModelAdapter(_BaseModelAdapter):
    def _invoke(self, client, contents):
        return client.models.generate_content(
            model=self._current_name,
            contents=contents,
        )


class LegacyModelAdapter(_BaseModelAdapter):
    def _invoke(self, client, contents):
        # Rebuilt per call because the legacy SDK binds the API key at
        # construction time, and the active key can change between calls.
        return client.GenerativeModel(self._current_name).generate_content(contents)


def build_gemini_model():
    _load_library()
    _load_keys()
    adapter = GeminiModelAdapter if _USE_NEW else LegacyModelAdapter
    return adapter(Config.GEMINI_MODEL, Config.GEMINI_MODEL_FALLBACK)


def upload_file(file_path: str):
    _load_library()

    def call(client):
        return client.files.upload(file=file_path) if _USE_NEW else client.upload_file(file_path)

    # The index is captured after the call so rotation during upload is reflected.
    index_holder: dict[str, int] = {}

    def tracked(client):
        index_holder["index"] = _current_index()
        return call(client)

    result = _call_with_rotation(tracked)
    _remember_file(result, index_holder.get("index", _current_index()))
    return result


def get_file(file_name: str):
    _load_library()
    pin = _key_for_file(file_name)

    def call(client):
        return client.files.get(name=file_name) if _USE_NEW else client.get_file(file_name)

    return _call_with_rotation(call, pin_index=pin)


def get_file_state(file_obj):
    """Safely get file state string from various SDK versions"""
    state = getattr(file_obj, "state", None)
    if state is None:
        return None

    # Handle dictionary response
    if isinstance(state, dict):
        val = state.get("name") or state.get("state")
        return str(val).upper() if val else None

    # Handle string response
    if isinstance(state, str):
        return state.upper()

    # Handle Enum or Object (new SDK)
    # Convert to string (e.g. "FileState.ACTIVE" or "ACTIVE")
    state_str = str(state)

    # If it's an enum name like 'ACTIVE', accessing .name might work
    if hasattr(state, "name"):
        return state.name.upper()

    # Clean up "FileState." prefix if present
    if "." in state_str:
        return state_str.split(".")[-1].upper()

    return state_str.upper()

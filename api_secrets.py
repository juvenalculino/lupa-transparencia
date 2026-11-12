import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from threading import Lock

from cryptography.fernet import Fernet, InvalidToken


class SecretStoreError(RuntimeError):
    pass


_api_keys_lock = Lock()


_CONFIGURATION_KEYS = {
    "PORTAL_API_KEY_ENCRYPTION_KEY",
    "PORTAL_API_ADMIN_TOKEN",
}


def _set_private_file_permissions(descriptor: int, path: str) -> None:
    if os.name != "posix":
        return
    fchmod = getattr(os, "fchmod", None)
    if fchmod is not None:
        fchmod(descriptor, 0o600)
    else:
        os.chmod(path, 0o600)


def _configuration_path() -> Path:
    return Path(__file__).parent / ".secrets" / "server.env"


def load_server_secrets(path: Path | None = None) -> None:
    config_path = path or _configuration_path()
    if not config_path.is_file():
        return
    if os.name == "posix" and stat.S_IMODE(config_path.stat().st_mode) & 0o077:
        raise SecretStoreError(
            f"As permissões de {config_path} são muito abertas; execute chmod 600."
        )

    for line_number, line in enumerate(
            config_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        name, separator, value = line.partition("=")
        if not separator or name not in _CONFIGURATION_KEYS or not value:
            raise SecretStoreError(
                f"Configuração secreta inválida na linha {line_number}."
            )
        os.environ.setdefault(name, value)


def create_server_secrets(path: Path | None = None) -> bool:
    config_path = path or _configuration_path()
    config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        config_path.parent.chmod(0o700)

    values = {
        "PORTAL_API_KEY_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
    }
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".server-env-", dir=config_path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
            _set_private_file_permissions(
                temporary_file.fileno(), temporary_path)
            for name, value in values.items():
                temporary_file.write(f"{name}={value}\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        try:
            os.link(temporary_path, config_path)
        except FileExistsError:
            return False
        return True
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def _storage_path() -> Path:
    configured_path = os.environ.get("PORTAL_API_KEY_FILE")
    if configured_path:
        path = Path(configured_path).expanduser()
        return path if path.is_absolute() else Path(__file__).parent / path
    return Path(__file__).parent / ".secrets" / "portal_api_key.enc"


def _cipher() -> Fernet:
    encryption_key = os.environ.get("PORTAL_API_KEY_ENCRYPTION_KEY")
    if not encryption_key:
        raise SecretStoreError(
            "Configure PORTAL_API_KEY_ENCRYPTION_KEY para habilitar o cofre."
        )
    try:
        return Fernet(encryption_key.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as error:
        raise SecretStoreError(
            "PORTAL_API_KEY_ENCRYPTION_KEY não é uma chave Fernet válida."
        ) from error


def encryption_key_is_valid() -> bool:
    try:
        _cipher()
    except SecretStoreError:
        return False
    return True


def _read_api_keys() -> list[str]:
    path = _storage_path()
    if not path.is_file():
        return []
    try:
        decrypted = _cipher().decrypt(path.read_bytes()).decode("utf-8")
    except InvalidToken as error:
        raise SecretStoreError(
            "A chave salva não pode ser descriptografada; verifique a chave de "
            "criptografia configurada no servidor."
        ) from error

    try:
        stored_data = json.loads(decrypted)
    except json.JSONDecodeError:
        stored_data = None
    stored_keys = (
        stored_data["keys"]
        if isinstance(stored_data, dict)
        and stored_data.get("format") == "portal-api-keys-v1"
        else [decrypted]
    )
    if not isinstance(stored_keys, list) or not all(
            isinstance(key, str) and key for key in stored_keys):
        raise SecretStoreError("O arquivo de chaves da API possui formato inválido.")
    return list(dict.fromkeys(stored_keys))


def _write_api_keys(api_keys: list[str]) -> None:
    path = _storage_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not os.environ.get("PORTAL_API_KEY_FILE"):
        path.parent.chmod(0o700)

    encrypted_keys = _cipher().encrypt(
        json.dumps(
            {"format": "portal-api-keys-v1", "keys": api_keys},
            ensure_ascii=False,
        ).encode("utf-8"))
    descriptor, temporary_path = tempfile.mkstemp(
        prefix=".portal-api-key-", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            _set_private_file_permissions(
                temporary_file.fileno(), temporary_path)
            temporary_file.write(encrypted_keys)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def is_api_key_stored() -> bool:
    return bool(_read_api_keys())


def list_api_keys() -> list[dict[str, str]]:
    return [
        {
            "id": hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
            "label": f"••••{key[-4:]}" if len(key) >= 4 else "••••",
        }
        for key in _read_api_keys()
    ]


def save_api_key(api_key: str) -> None:
    if not api_key.strip():
        raise SecretStoreError("A chave da API não pode estar vazia.")
    with _api_keys_lock:
        api_keys = _read_api_keys()
        if api_key not in api_keys:
            api_keys.append(api_key)
            _write_api_keys(api_keys)


def load_api_key() -> str | None:
    api_keys = _read_api_keys()
    return api_keys[0] if api_keys else None


def load_api_keys() -> list[str]:
    return _read_api_keys()


def delete_api_key(key_id: str | None = None) -> bool:
    with _api_keys_lock:
        if key_id is not None:
            api_keys = _read_api_keys()
            remaining_keys = [
                key for key in api_keys
                if hashlib.sha256(key.encode("utf-8")).hexdigest()[:16] != key_id
            ]
            if len(remaining_keys) == len(api_keys):
                return False
            if remaining_keys:
                _write_api_keys(remaining_keys)
                return True
        try:
            _storage_path().unlink()
        except FileNotFoundError:
            return False
        return True

"""Read ONLY one explicit privileged env file; no shell evaluation or secret output.

Web process receives nonsecret settings; only the standalone worker receives
the API key. Never load dotenv from current directory or inject VITE keys.
"""
import os
import re
import stat
from pathlib import Path


class SecretConfigError(ValueError):
    def __init__(self,code):
        super().__init__(code)
        self.code=code


def load_server_environment(path:Path, *, with_provider_key:bool):
    if type(with_provider_key) is not bool:
        raise SecretConfigError("ENV_MODE_INVALID")
    path=Path(path)
    if not path.is_absolute() or path.is_symlink():
        raise SecretConfigError("ENV_PATH_INVALID")
    try:
        file_stat=path.stat()
        dir_stat=path.parent.stat()
    except OSError:
        raise SecretConfigError("ENV_UNAVAILABLE") from None
    if (not stat.S_ISREG(file_stat.st_mode)
        or (file_stat.st_mode & 0o777)!=0o600
        or (dir_stat.st_mode & 0o777)!=0o700
        or file_stat.st_uid!=os.geteuid()
        or dir_stat.st_uid!=os.geteuid()):
        raise SecretConfigError("ENV_PERMISSIONS_INVALID")
    from dotenv import dotenv_values
    content=dotenv_values(path,interpolate=False)
    if not isinstance(content.get("OPENAI_API_KEY"),str) or not (
        20<=len(content["OPENAI_API_KEY"])<=512
        and re.fullmatch(r"[!-~]+",content["OPENAI_API_KEY"])
    ):
        raise SecretConfigError("OPENAI_KEY_FORMAT_INVALID")
    models={}
    for key in ("OPENAI_MODEL_TEXT","OPENAI_MODEL_VISION","OPENAI_REASONING_EFFORT"):
        val=content.get(key)
        if val:
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}",val):
                raise SecretConfigError("MODEL_CONFIG_INVALID")
            models[key]=val
    if with_provider_key:
        models["OPENAI_API_KEY"]=content["OPENAI_API_KEY"]
    # Explicit approval policy is supplied separately, never persisted to
    # the shared secret env file or treated as a consequence of key existence.
    for key,value in models.items():
        os.environ[key]=value
    return {
       "key_present":True,"key_loaded":bool(with_provider_key),
       "model_text":models.get("OPENAI_MODEL_TEXT"),
       "model_vision":models.get("OPENAI_MODEL_VISION"),
       "effort":models.get("OPENAI_REASONING_EFFORT"),
    }


def load_from_fixed_path(*,worker:bool):
    fixed=Path("/home/macstudio/ittem-remote-demo-20261030/config/openai.env")
    return load_server_environment(fixed,with_provider_key=worker)
